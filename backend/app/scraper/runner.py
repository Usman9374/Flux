"""Top-level scrape orchestrator.

v2 of the pipeline (per LEAD_GENERATION_FIX.md). Two big architecture
changes from v1:

  * **OSM is the primary source.** Pure HTTP (Nominatim + Overpass)
    means it works from cloud IPs, doesn't need Chromium, and isn't
    rate-limited the way Google is. v1 returned 0 leads in production
    because Maps was the only source and Google blocks Render's IPs.
  * **Google Maps is best-effort.** If Playwright isn't installed, or
    Chromium fails to launch, or any nav throws, we log + skip — never
    let it abort the run. Same for the DDG backfill.

Stages:

  1. parse_intent(req.niche)             — pull "without website" etc. out
  2. geocode(req.location)               — bbox + country code via Nominatim
  3. parallel sources:                   — OSM, DDG, optional Maps
       osm.search → ScrapedLead[]
       ddg.backfill_candidates → ScrapedLead[]
       google_maps.scrape (best effort)  → ScrapedLead[]
  4. merge + dedupe                      — same name+city or same domain
  5. verify offline mode (if applicable) — DDG search per lead
  6. filter_and_score                    — annotate tier/score/signals
  7. enrich_websites (top kept)          — homepage email/socials/desc
  8. floor                               — never return 0 if any source
                                           had any rows; relaxed_filter=True

Wall-clock cap protects the whole thing; if it fires we return whatever
is ready with `partial=True`.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from .quality import (
    filter_and_score,
    is_aggregator,
    parse_intent,
)
from .sources import osm
from .sources.search_engine import (
    _CONFIRM_THRESHOLD,
    _POSSIBLE_THRESHOLD,
    backfill_candidates,
    verify_website,
)
from .types import ScrapeRequest, ScrapedLead
from .website_enrich import enrich_leads

log = logging.getLogger(__name__)

ProgressCb = Callable[[str, dict[str, Any]], Awaitable[None]]

# Verification concurrency for the per-lead DuckDuckGo lookups.
_VERIFY_CONCURRENCY = 4


async def _noop_progress(stage: str, payload: dict[str, Any]) -> None:
    pass


async def run_scrape(
    req: ScrapeRequest,
    progress: ProgressCb | None = None,
) -> dict[str, Any]:
    """Run the full pipeline. Returns a dict matching ScrapeResultOut.

    `progress` is called at every meaningful stage transition with
      stage ∈ {"searching", "geocoding", "osm", "search_engine",
               "google_maps", "merging", "verifying_websites",
               "scoring", "enriching_websites", "relaxing_filter", "done"}
    and a payload dict carrying progress (0.0–1.0), counts, and messages.
    """
    on_progress = progress or _noop_progress

    intent = parse_intent(req.niche)
    require_website = (
        req.require_website if req.require_website is not None else intent.require_website
    )
    cleaned_niche = intent.cleaned_niche

    log.info(
        "scrape v2 start: niche=%r (cleaned=%r) location=%r max=%d require_website=%s",
        req.niche, cleaned_niche, req.location, req.max_results, require_website,
    )

    await on_progress("searching", {
        "progress": 0.02,
        "message": f"Searching for {cleaned_niche!r} in {req.location}…",
        "intent": {
            "cleaned_niche": cleaned_niche,
            "require_website": require_website,
            "mode_label": intent.mode_label,
        },
    })

    partial = False
    raw: list[ScrapedLead] = []

    # ---- Stage 0: geocode location ----
    geo = None
    async with httpx.AsyncClient(http2=False) as client:
        await on_progress("geocoding", {
            "progress": 0.05,
            "message": f"Geocoding {req.location!r}…",
        })
        try:
            geo = await asyncio.wait_for(
                osm.geocode(client, req.location),
                timeout=10.0,
            )
        except asyncio.TimeoutError:
            log.warning("geocode timed out for %r", req.location)

        if geo is not None:
            log.info(
                "geocoded %r → bbox=%s cc=%s",
                req.location, geo.bbox, geo.country_code,
            )
        else:
            log.info("geocode returned nothing — OSM stage will be skipped")

        # ---- Stage 1: run all sources in parallel ----
        await on_progress("running_sources", {
            "progress": 0.10,
            "message": "Querying OSM, search engine, and (best effort) Maps…",
        })

        osm_task = asyncio.create_task(
            _run_osm(client, cleaned_niche, req.location, req.max_results, geo)
        )
        ddg_task = asyncio.create_task(
            _run_ddg(client, cleaned_niche, req.location, req.max_results)
        )
        gmaps_task = asyncio.create_task(
            _run_gmaps_best_effort(req, cleaned_niche)
        )

        # Bound the whole parallel block by ~55% of the wall clock —
        # leaves headroom for verify + enrich + scoring.
        sources_budget = max(20.0, req.wall_clock_s * 0.55)
        try:
            done, pending = await asyncio.wait(
                {osm_task, ddg_task, gmaps_task},
                timeout=sources_budget,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("source gather raised: %s", e)
            done, pending = set(), {osm_task, ddg_task, gmaps_task}

        for t in pending:
            t.cancel()
            partial = True
            log.warning("source task %s exceeded budget", t.get_name())

        osm_leads = _result_or_empty(osm_task, "osm")
        ddg_leads = _result_or_empty(ddg_task, "duckduckgo")
        gmaps_leads = _result_or_empty(gmaps_task, "google_maps")

        log.info(
            "source counts: osm=%d ddg=%d gmaps=%d",
            len(osm_leads), len(ddg_leads), len(gmaps_leads),
        )
        await on_progress("merging", {
            "progress": 0.55,
            "message": (
                f"OSM={len(osm_leads)} · search={len(ddg_leads)} · "
                f"maps={len(gmaps_leads)} — merging…"
            ),
        })

        # ---- Stage 2: merge + dedupe ----
        raw = _merge_dedupe(osm_leads + gmaps_leads + ddg_leads, max_total=max(req.max_results * 3, 60))
        log.info("after merge+dedupe: %d unique leads", len(raw))

        # ---- Stage 3a: website discovery for online mode ----
        # OSM has rich coverage but most POIs lack `contact:website` tags. We
        # ask DuckDuckGo for each lead missing a website; any plausible match
        # gets promoted into `lead.website` and the existing website-enricher
        # then fills in email/socials/description. Without this step, OSM-
        # seeded leads would all fail the "must have a contact channel" rule
        # in `quality.rejection_reason`.
        if require_website and raw:
            await on_progress("verifying_websites", {
                "progress": 0.60,
                "message": "Discovering websites for unmatched leads…",
            })
            try:
                await asyncio.wait_for(
                    _discover_websites(client, raw, on_progress),
                    timeout=max(15.0, req.wall_clock_s * 0.22),
                )
            except asyncio.TimeoutError:
                partial = True
                log.warning("website discovery timed out — keeping what we have")
            except Exception as e:  # noqa: BLE001
                log.warning("website discovery failed: %s", e)

        # ---- Stage 3b: search verification (only in offline mode) ----
        if not require_website and raw:
            await on_progress("verifying_websites", {
                "progress": 0.62,
                "message": f"Verifying {len(raw)} leads against the web (offline mode)…",
            })
            try:
                await asyncio.wait_for(
                    _verify_offline_mode(client, raw, on_progress),
                    timeout=max(15.0, req.wall_clock_s * 0.20),
                )
            except asyncio.TimeoutError:
                partial = True
                log.warning("verification stage timed out")
            except Exception as e:  # noqa: BLE001
                log.warning("verification stage failed: %s", e)

    # ---- Stage 4: first-pass filter (lenient: tier C+ kept) ----
    survivors, dropped = filter_and_score(
        raw, min_score=0, require_website=require_website,
    )
    log.info("after first-pass filter: survivors=%d dropped=%d", len(survivors), len(dropped))
    await on_progress("scoring", {
        "progress": 0.72,
        "message": f"First-pass survivors: {len(survivors)} of {len(raw)}",
        "raw_count": len(raw),
        "kept_count": len(survivors),
        "dropped_count": len(dropped),
    })

    # ---- Stage 5: website enrichment (require_website only) ----
    if req.enrich_websites and survivors:
        await on_progress("enriching_websites", {
            "progress": 0.80,
            "message": f"Fetching contact info from {len(survivors)} websites…",
        })
        try:
            await asyncio.wait_for(
                enrich_leads(survivors),
                timeout=max(10.0, req.wall_clock_s * 0.20),
            )
        except asyncio.TimeoutError:
            partial = True
            log.warning("website enrichment timed out — using whatever fields we have")
        except Exception as e:  # noqa: BLE001
            log.warning("website enrichment failed: %s", e)

    # ---- Stage 6: final scoring pass ----
    kept, dropped_low = filter_and_score(
        survivors, min_score=req.min_quality_score, require_website=require_website,
    )
    dropped.extend(dropped_low)

    relaxed = False
    if not kept and len(raw) > 0:
        # Floor: don't return empty when raw cards exist. Drop the threshold,
        # then if still empty fall back to top-N by raw signal strength.
        kept, dropped, relaxed = _relax_filter(survivors, dropped_low, dropped, require_website)
        if not kept and raw:
            kept = _last_resort_top(raw, want=min(req.max_results, 10), require_website=require_website)
            relaxed = True
        for lead in kept:
            merged = dict(lead.signals or {})
            merged["relaxed_filter"] = True
            lead.signals = merged
        if relaxed:
            await on_progress("relaxing_filter", {
                "progress": 0.92,
                "message": f"No top-tier leads — showing best available ({len(kept)}).",
                "relaxed_filter": True,
            })

    await on_progress("scoring", {
        "progress": 0.95,
        "message": f"Scored {len(kept)} kept leads.",
        "raw_count": len(raw),
        "kept_count": len(kept),
        "dropped_count": len(dropped),
    })

    log.info(
        "scrape v2 done: raw=%d kept=%d dropped=%d partial=%s relaxed=%s",
        len(raw), len(kept), len(dropped), partial, relaxed,
    )

    return {
        "kept": kept,
        "dropped": dropped,
        "raw_count": len(raw),
        "kept_count": len(kept),
        "dropped_count": len(dropped),
        "partial": partial,
        "relaxed_filter": relaxed,
        "intent": {
            "cleaned_niche": cleaned_niche,
            "require_website": require_website,
            "mode_label": intent.mode_label,
        },
    }


# ---------- Sources ----------


async def _run_osm(
    client: httpx.AsyncClient,
    niche: str,
    location: str,
    want: int,
    geocoded,
) -> list[ScrapedLead]:
    if geocoded is None:
        # No bbox = nothing for Overpass to scope. Skip; the other
        # sources will carry the run.
        return []
    try:
        return await osm.search(
            client,
            niche,
            location,
            limit=max(want * 2, 30),
            geocoded=geocoded,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("osm source failed: %s", e)
        return []


async def _run_ddg(
    client: httpx.AsyncClient,
    niche: str,
    location: str,
    want: int,
) -> list[ScrapedLead]:
    try:
        cands = await backfill_candidates(client, niche, location, limit=max(want, 15))
    except Exception as e:  # noqa: BLE001
        log.warning("ddg backfill failed: %s", e)
        return []
    out: list[ScrapedLead] = []
    for c in cands:
        out.append(
            ScrapedLead(
                name=c["name"],
                website=c.get("website"),
                description=c.get("snippet"),
                niche=niche,
                location=location,
                source="duckduckgo",
                source_url=c.get("website"),
                sources=["duckduckgo"],
            )
        )
    return out


async def _run_gmaps_best_effort(req: ScrapeRequest, niche: str) -> list[ScrapedLead]:
    """Attempt the Maps scrape but never let it blow up the run.

    Playwright/Chromium frequently fails on cloud dynos (OOM, missing
    binary, blocked IP). We capture and log; the OSM + DDG sources still
    produce a usable result set.
    """
    try:
        # Lazy import — if Playwright isn't installed in this environment,
        # we don't even pay the import cost.
        from .engine import browser_context
        from .sources import google_maps
    except Exception as e:  # noqa: BLE001
        log.info("google_maps source unavailable (import failed): %s", e)
        return []

    try:
        async with browser_context(headless=req.headless) as ctx:
            return await google_maps.scrape(
                ctx,
                niche,
                req.location,
                req.max_results,
            )
    except Exception as e:  # noqa: BLE001
        log.warning("google_maps best-effort scrape failed: %s", e)
        return []


# ---------- Merge / dedupe ----------


def _norm_name(name: str | None) -> str:
    import re
    if not name:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", name.lower())).strip()


def _norm_phone(phone: str | None) -> str | None:
    import re
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    return digits[-10:] if len(digits) >= 10 else (digits or None)


def _norm_domain(url: str | None) -> str | None:
    if not url:
        return None
    from urllib.parse import urlparse
    try:
        h = (urlparse(url if url.startswith("http") else f"https://{url}").hostname or "").lower()
        return h.removeprefix("www.") or None
    except Exception:  # noqa: BLE001
        return None


def _merge_dedupe(leads: list[ScrapedLead], *, max_total: int) -> list[ScrapedLead]:
    """Dedupe across sources by name+city, phone, or domain.

    First lead wins for name/phone/domain conflicts; subsequent matches
    contribute their `sources` list and any missing fields. This is how
    OSM + DDG + Maps cooperate: a Maps lead with rich detail beats a
    DDG lead with just a name+homepage; OSM tags the niche even when
    Maps gave us a freer-form category.
    """
    by_name: dict[tuple[str, str], ScrapedLead] = {}
    by_phone: dict[str, ScrapedLead] = {}
    by_domain: dict[str, ScrapedLead] = {}
    out: list[ScrapedLead] = []

    for lead in leads:
        nm = _norm_name(lead.name)
        if not nm:
            continue
        loc = (lead.location or "").lower().split(",")[0].strip()
        nm_key = (nm, loc)
        ph = _norm_phone(lead.phone)
        dom = _norm_domain(lead.website)

        existing = (
            by_name.get(nm_key)
            or (by_phone.get(ph) if ph else None)
            or (by_domain.get(dom) if dom else None)
        )
        if existing is not None:
            _merge_into(existing, lead)
            if ph:
                by_phone.setdefault(ph, existing)
            if dom:
                by_domain.setdefault(dom, existing)
            by_name.setdefault(nm_key, existing)
            continue

        by_name[nm_key] = lead
        if ph:
            by_phone[ph] = lead
        if dom:
            by_domain[dom] = lead
        out.append(lead)
        if len(out) >= max_total:
            break
    return out


def _merge_into(target: ScrapedLead, other: ScrapedLead) -> None:
    """Fold `other`'s fields into `target` without overwriting existing data."""
    for attr in (
        "website", "phone", "email", "address", "category",
        "description", "tagline", "hours", "plus_code",
        "rating", "reviews", "years_in_business", "map_url",
    ):
        if getattr(target, attr) in (None, "", 0):
            v = getattr(other, attr)
            if v not in (None, ""):
                setattr(target, attr, v)
    # Merge socials
    if other.social_links:
        merged = dict(target.social_links or {})
        for k, v in other.social_links.items():
            merged.setdefault(k, v)
        target.social_links = merged
    # Sources list — accumulate so the lead carries provenance.
    sources = list(target.sources or [])
    if target.source and target.source not in sources:
        sources.append(target.source)
    for s in (other.sources or []):
        if s not in sources:
            sources.append(s)
    if other.source and other.source not in sources:
        sources.append(other.source)
    target.sources = sources
    # Signals — union, target wins on conflict.
    if other.signals:
        merged_sig = dict(other.signals)
        merged_sig.update(target.signals or {})
        target.signals = merged_sig


def _result_or_empty(task: asyncio.Task, label: str) -> list[ScrapedLead]:
    if not task.done():
        return []
    if task.cancelled():
        log.warning("%s task cancelled", label)
        return []
    exc = task.exception()
    if exc is not None:
        log.warning("%s task raised: %s", label, exc)
        return []
    res = task.result()
    return list(res) if isinstance(res, list) else []


# ---------- Website discovery (online mode) ----------


# Confidence at which we trust a DDG result enough to populate `lead.website`.
# Lower than _CONFIRM_THRESHOLD (which gates the offline-mode rejection)
# because here we're populating, not rejecting — false positives surface in
# the website enricher (a wrong domain just yields no email + bad
# description, then drops out of the kept list).
_DISCOVER_THRESHOLD = 0.55


async def _discover_websites(
    client: httpx.AsyncClient,
    leads: list[ScrapedLead],
    on_progress: ProgressCb,
) -> None:
    """For leads with no website, query the search engine to find one.

    Critical for OSM-seeded leads: OSM POIs frequently have only `name`
    + `addr:*` + `amenity=*`, so without this step they all fail the
    "must have a contact channel" rule. The discovered URL feeds into
    the website-enrichment stage that fills in email + socials.
    """
    targets = [
        l for l in leads
        if not l.website and l.name and not is_aggregator(l.website)
    ]
    if not targets:
        return
    # Cap to keep within the DDG fair-use budget — DDG starts blocking
    # if we burst more than a couple dozen queries from one IP.
    if len(targets) > 30:
        # Prefer leads that already have at least one corroborating signal
        # (rating/reviews/category). Maximizes the value of each DDG call.
        targets = sorted(
            targets,
            key=lambda l: (
                bool(l.rating or l.reviews),
                bool(l.category),
                len(l.sources or []),
            ),
            reverse=True,
        )[:30]

    sem = asyncio.Semaphore(_VERIFY_CONCURRENCY)
    done = 0
    total = max(1, len(targets))

    async def worker(lead: ScrapedLead) -> None:
        nonlocal done
        async with sem:
            try:
                verdict = await verify_website(client, lead.name, lead.location)
            except Exception as e:  # noqa: BLE001
                log.warning("discover_website failed for %r: %s", lead.name, e)
                verdict = None
            done += 1
            if done % 5 == 0 or done == total:
                try:
                    await on_progress("verifying_websites", {
                        "progress": 0.60 + 0.10 * (done / total),
                        "enriched": done,
                        "total": total,
                    })
                except Exception as e:  # noqa: BLE001
                    log.debug("progress raised: %s", e)
            if verdict is None or not verdict.url:
                return
            if verdict.confidence < _DISCOVER_THRESHOLD:
                return
            if is_aggregator(verdict.url):
                return
            lead.website = verdict.url
            sigs = dict(lead.signals or {})
            sigs["website_discovered"] = True
            sigs["website_source"] = "duckduckgo"
            sigs["website_confidence"] = verdict.confidence
            lead.signals = sigs
            srcs = list(lead.sources or [])
            if "duckduckgo" not in srcs:
                srcs.append("duckduckgo")
            lead.sources = srcs

    await asyncio.gather(
        *(worker(l) for l in targets),
        return_exceptions=True,
    )
    discovered = sum(1 for l in leads if (l.signals or {}).get("website_discovered"))
    log.info("website discovery: found %d of %d", discovered, len(targets))


# ---------- Offline-mode verification ----------


async def _verify_offline_mode(
    client: httpx.AsyncClient,
    leads: list[ScrapedLead],
    on_progress: ProgressCb,
) -> None:
    """Run search verification on each lead that came in without a website.

    See LEAD_GENERATION_FIX.md §4: a lead may only pass require_website=False
    if the search engine *also* fails to find a homepage for it. Patches the
    biggest false-positive in the v1 pipeline.
    """
    if not leads:
        return

    targets: list[tuple[int, ScrapedLead]] = []
    for i, l in enumerate(leads):
        if l.website and not is_aggregator(l.website):
            continue
        if not l.name:
            continue
        targets.append((i, l))

    sem = asyncio.Semaphore(_VERIFY_CONCURRENCY)
    done = 0
    total = max(1, len(targets))

    async def worker(idx: int, lead: ScrapedLead) -> None:
        nonlocal done
        async with sem:
            try:
                verdict = await verify_website(client, lead.name, lead.location)
            except Exception as e:  # noqa: BLE001
                log.warning("verify_website failed for %r: %s", lead.name, e)
                verdict = None
            done += 1
            if done % 3 == 0 or done == total:
                try:
                    await on_progress("verifying_websites", {
                        "progress": 0.62 + 0.08 * (done / total),
                        "enriched": done,
                        "total": total,
                    })
                except Exception as e:  # noqa: BLE001
                    log.debug("progress raised: %s", e)

            if verdict is None:
                return
            signals = dict(lead.signals or {})
            if verdict.confidence >= _CONFIRM_THRESHOLD and verdict.url:
                lead.website = verdict.url
                signals["website_confirmed"] = True
                signals["website_source"] = "duckduckgo"
                sources = list(lead.sources or [])
                if "duckduckgo" not in sources:
                    sources.append("duckduckgo")
                lead.sources = sources
            elif verdict.confidence >= _POSSIBLE_THRESHOLD and verdict.url:
                signals["possible_website"] = verdict.url
                signals["website_unverified"] = True
            else:
                signals["offline_verified"] = True
            lead.signals = signals

    await asyncio.gather(
        *(worker(i, l) for i, l in targets),
        return_exceptions=True,
    )


# ---------- Floor ----------


def _relax_filter(
    survivors: list[ScrapedLead],
    just_dropped: list[ScrapedLead],
    already_dropped: list[ScrapedLead],
    require_website: bool,
) -> tuple[list[ScrapedLead], list[ScrapedLead], bool]:
    """Drop the min-score threshold one tier at a time until we have results."""
    for relaxed_score in (10, 0):
        kept, low = filter_and_score(
            survivors, min_score=relaxed_score, require_website=require_website,
        )
        if kept:
            return kept, already_dropped + low, relaxed_score < 25
    return [], already_dropped + just_dropped, False


def _last_resort_top(
    raw: list[ScrapedLead],
    *,
    want: int,
    require_website: bool,
) -> list[ScrapedLead]:
    """Final safety net: rank the raw set by signal strength and keep top N.

    Used when every other path returned 0. We discard the strict
    rejection_reason logic and just prefer leads with the most contact
    channels + reputation. The caller marks every survivor with
    `relaxed_filter=True` so the UI can be honest.
    """
    def signal_strength(l: ScrapedLead) -> tuple[int, int]:
        score = 0
        if l.website and not is_aggregator(l.website):
            score += 30 if require_website else 0
        if l.phone:
            score += 20
        if l.email:
            score += 15
        if l.category:
            score += 5
        if l.rating:
            score += int((l.rating or 0) * 2)
        if l.reviews:
            score += min(int((l.reviews or 0) / 50), 10)
        return (score, len(l.sources or []))

    out = sorted(raw, key=signal_strength, reverse=True)[:want]
    for lead in out:
        if not lead.tier:
            lead.tier = "C"
        if lead.quality_score is None:
            lead.quality_score = 30
    return out
