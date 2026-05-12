"""Top-level scrape orchestrator.

Pipeline (§7-8 of LEAD_GENERATION_FIX.md):
  1. parse_intent(req.niche) — pull qualifiers like "without website" out of
     the niche string and clean it for the search query.
  2. Google Maps scrape — open a Playwright context, fetch + enrich cards.
  3. Search-engine verification — for offline-mode leads, run a SERP query
     and confirm/refute the "no website" verdict (§4).
  4. First-pass quality filter — drop hard rejects (closed, aggregator,
     no-overlap niche, no-overlap location).
  5. Website enrichment — fetch homepage + /contact + /about for kept leads
     in require_website mode; extract email/socials/description.
  6. Final scoring pass — assign tier + confidence; sort by quality.
  7. Floor — if kept_count == 0 but raw_count > 0, relax the filter one tier
     at a time so the UI never shows "no results, no explanation".

Everything is wrapped in a single wall-clock cap; if the cap fires we return
whatever's ready with `partial=True` rather than a hung 92% spinner.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from .engine import browser_context, with_retries
from .quality import (
    filter_and_score,
    is_aggregator,
    parse_intent,
)
from .sources import google_maps
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

# Backfill threshold — if Maps returns fewer than this many cards, we try
# the DuckDuckGo fallback to top up.
_BACKFILL_BELOW = 5

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
      stage ∈ {"searching", "scrolling", "enriching_details",
               "verifying_websites", "enriching_websites", "scoring",
               "relaxing_filter", "done"}
    and a payload dict carrying progress (0.0–1.0), counts, and messages.
    The caller maps these into SSE/polling events.
    """
    on_progress = progress or _noop_progress

    intent = parse_intent(req.niche)
    require_website = (
        req.require_website if req.require_website is not None else intent.require_website
    )
    cleaned_niche = intent.cleaned_niche

    log.info(
        "scrape start: niche=%r (cleaned=%r) location=%r max=%d require_website=%s",
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
    cancel_event = asyncio.Event()
    raw: list[ScrapedLead] = []

    # ---- Stage 1: Google Maps ----
    async def _gmaps_progress(stage: str, payload: dict[str, Any]) -> None:
        # Map per-stage payloads to a 0.05–0.55 progress band.
        if stage == "scrolling":
            await on_progress("scrolling", {
                **payload,
                "progress": 0.20,
            })
        elif stage == "enriching_details":
            total = max(1, payload.get("total", 1))
            done = payload.get("enriched", 0)
            await on_progress("enriching_details", {
                **payload,
                "progress": 0.25 + 0.30 * (done / total),
            })
        else:
            await on_progress(stage, {**payload, "progress": 0.10})

    async def _do_gmaps() -> list[ScrapedLead]:
        async with browser_context(headless=req.headless) as ctx:
            return await google_maps.scrape(
                ctx,
                cleaned_niche,
                req.location,
                req.max_results,
                progress_cb=_gmaps_progress,
                cancel_event=cancel_event,
            )

    async def _run_with_walltime() -> None:
        nonlocal raw, partial
        try:
            raw = await asyncio.wait_for(
                with_retries(_do_gmaps, attempts=2, base_delay=2.0, label="google_maps.scrape"),
                timeout=req.wall_clock_s * 0.65,  # leave headroom for verify + enrich
            )
        except asyncio.TimeoutError:
            partial = True
            log.warning("google_maps stage exceeded its time budget — returning whatever's ready")
            cancel_event.set()
            raw = []

    await _run_with_walltime()
    log.info("raw leads scraped: %d", len(raw))

    # ---- Stage 1.5: backfill if thin ----
    if len(raw) < _BACKFILL_BELOW and not partial:
        await on_progress("backfill", {
            "progress": 0.55,
            "message": "Maps returned thin results — trying search-engine backfill…",
            "raw_count": len(raw),
        })
        try:
            extras = await _backfill(cleaned_niche, req.location, req.max_results - len(raw))
            if extras:
                log.info("backfill: %d additional candidates from DuckDuckGo", len(extras))
                raw.extend(extras)
        except Exception as e:  # noqa: BLE001
            log.warning("backfill failed: %s", e)

    # ---- Stage 2: search verification (only in offline mode) ----
    if not require_website and raw:
        await on_progress("verifying_websites", {
            "progress": 0.60,
            "message": f"Verifying {len(raw)} leads against the web (offline mode)…",
        })
        try:
            await _verify_offline_mode(raw, on_progress)
        except Exception as e:  # noqa: BLE001
            log.warning("verification stage failed: %s", e)

    # ---- Stage 3: first-pass filter ----
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

    # ---- Stage 4: website enrichment (require_website only) ----
    if req.enrich_websites and require_website and survivors:
        await on_progress("enriching_websites", {
            "progress": 0.78,
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

    # ---- Stage 5: final scoring pass ----
    kept, dropped_low = filter_and_score(
        survivors, min_score=req.min_quality_score, require_website=require_website,
    )
    dropped.extend(dropped_low)

    relaxed = False
    if kept and len(kept) > 0:
        pass
    elif len(raw) > 0:
        # Floor: don't return empty when raw cards exist. Drop the threshold
        # progressively and resurface what we can.
        kept, dropped, relaxed = _relax_filter(survivors, dropped_low, dropped, require_website)
        for lead in kept:
            merged = dict(lead.signals or {})
            merged["relaxed_filter"] = True
            lead.signals = merged
        if relaxed:
            await on_progress("relaxing_filter", {
                "progress": 0.92,
                "message": f"No A-tier leads — showing best available ({len(kept)}).",
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
        "scrape done: raw=%d kept=%d dropped=%d partial=%s relaxed=%s",
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


async def _backfill(niche: str, location: str, want: int) -> list[ScrapedLead]:
    """Pull candidate leads from a DuckDuckGo SERP query."""
    if want <= 0:
        return []
    async with httpx.AsyncClient(http2=False) as client:
        candidates = await backfill_candidates(client, niche, location, limit=want)
    out: list[ScrapedLead] = []
    for c in candidates:
        out.append(ScrapedLead(
            name=c["name"],
            website=c["website"],
            description=c.get("snippet"),
            niche=niche,
            location=location,
            source="duckduckgo",
            source_url=c["website"],
            sources=["duckduckgo"],
        ))
    return out


async def _verify_offline_mode(
    leads: list[ScrapedLead],
    on_progress: ProgressCb,
) -> None:
    """Run search verification on each Maps lead that came in without a website.

    See §4: a lead may only pass `require_website=False` if the search engine
    *also* fails to find a homepage. This patches the biggest false-positive
    in the v1 pipeline — businesses with chain-or-aggregator presence that
    Maps just happened to not surface on the detail panel.
    """
    if not leads:
        return

    targets: list[tuple[int, ScrapedLead]] = []
    for i, l in enumerate(leads):
        # If Maps already gave us a non-aggregator website, we already know
        # this lead is not offline — let the filter reject it via rejection_reason.
        if l.website and not is_aggregator(l.website):
            continue
        if not l.name:
            continue
        targets.append((i, l))

    sem = asyncio.Semaphore(_VERIFY_CONCURRENCY)
    done = 0
    total = max(1, len(targets))

    async with httpx.AsyncClient(http2=False) as client:
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
                            "progress": 0.60 + 0.10 * (done / total),
                            "enriched": done,
                            "total": total,
                        })
                    except Exception as e:  # noqa: BLE001
                        log.debug("progress raised: %s", e)

                if verdict is None:
                    return
                signals = dict(lead.signals or {})
                if verdict.confidence >= _CONFIRM_THRESHOLD and verdict.url:
                    # Definitively has a website. Promote into website so the
                    # downstream filter rejects it from offline mode.
                    lead.website = verdict.url
                    signals["website_confirmed"] = True
                    signals["website_source"] = "duckduckgo"
                    sources = list(lead.sources or [])
                    if "duckduckgo" not in sources:
                        sources.append("duckduckgo")
                    lead.sources = sources
                elif verdict.confidence >= _POSSIBLE_THRESHOLD and verdict.url:
                    # Plausible — keep as offline candidate but flag.
                    signals["possible_website"] = verdict.url
                    signals["website_unverified"] = True
                else:
                    # Search ran, found nothing convincing → confirmed offline.
                    signals["offline_verified"] = True
                lead.signals = signals

        await asyncio.gather(
            *(worker(i, l) for i, l in targets),
            return_exceptions=True,
        )


def _relax_filter(
    survivors: list[ScrapedLead],
    just_dropped: list[ScrapedLead],
    already_dropped: list[ScrapedLead],
    require_website: bool,
) -> tuple[list[ScrapedLead], list[ScrapedLead], bool]:
    """Drop the min-score threshold one tier at a time until we have results.

    Returns (kept, dropped, relaxed_flag). `relaxed_flag` is True if we had
    to relax to surface anything.
    """
    # Try min_score=25, then 0. Each iteration re-uses the survivors pool —
    # they're already past the hard-reject phase, so the only thing we're
    # toggling is the numeric threshold.
    for relaxed_score in (25, 0):
        kept, low = filter_and_score(
            survivors, min_score=relaxed_score, require_website=require_website,
        )
        if kept:
            return kept, already_dropped + low, relaxed_score < 40
    return [], already_dropped + just_dropped, False
