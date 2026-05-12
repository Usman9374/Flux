"""Google Maps scraper.

Defensive against selector drift: every extraction step has a fallback and
returns whatever it can. We never crash the whole run because one card
failed to parse.

Performance notes:
- Static assets (images/fonts/css) are blocked at the context level — see
  engine.BLOCKED_RESOURCE_TYPES — so every page navigation is several
  seconds faster than a normal browser load.
- Detail enrichment runs in parallel across multiple pages bounded by
  `_DETAIL_CONCURRENCY`. The previous sequential loop was the dominant
  bottleneck (≈2–3s per lead × N).
- The `gl=` param (geo-location hint) is picked from the queried location
  string. Sending `gl=us` for a query in Pakistan triggers the consent loop
  much more aggressively; matching the hint to the region keeps the page
  layout stable.
"""
import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from urllib.parse import quote_plus

from playwright.async_api import BrowserContext, Page
from playwright.async_api import TimeoutError as PWTimeout

from ..engine import polite_sleep
from ..types import ScrapedLead

log = logging.getLogger(__name__)

GMAPS_BASE = "https://www.google.com/maps/search/"

# How many detail pages we open in parallel. Google tolerates a handful from
# a single context; raising this further trades stability for marginal speed.
_DETAIL_CONCURRENCY = 5

# Country code → `gl=` hint for Google's regional routing. We pick from the
# user's location string at scrape time so a query in Islamabad doesn't get
# `gl=us`, which Google rate-limits aggressively for non-US IPs.
_COUNTRY_HINTS = {
    # Pakistan
    "pakistan": "pk", "islamabad": "pk", "karachi": "pk", "lahore": "pk", "rawalpindi": "pk",
    "peshawar": "pk", "quetta": "pk", "faisalabad": "pk", "multan": "pk", "hyderabad": "pk",
    # India
    "india": "in", "mumbai": "in", "delhi": "in", "bengaluru": "in", "bangalore": "in",
    "chennai": "in", "kolkata": "in", "hyderabad,": "in", "pune": "in",
    # UK / IE
    "united kingdom": "gb", "uk": "gb", "london": "gb", "manchester": "gb",
    "edinburgh": "gb", "birmingham": "gb", "glasgow": "gb", "leeds": "gb",
    "ireland": "ie", "dublin": "ie",
    # Canada / Mexico
    "canada": "ca", "toronto": "ca", "vancouver": "ca", "montreal": "ca", "calgary": "ca",
    "mexico": "mx", "mexico city": "mx",
    # AU/NZ
    "australia": "au", "sydney": "au", "melbourne": "au", "brisbane": "au", "perth": "au",
    "new zealand": "nz", "auckland": "nz", "wellington": "nz",
    # UAE / Saudi
    "uae": "ae", "dubai": "ae", "abu dhabi": "ae",
    "saudi arabia": "sa", "riyadh": "sa", "jeddah": "sa",
    # Bangladesh / Indonesia
    "bangladesh": "bd", "dhaka": "bd",
    "indonesia": "id", "jakarta": "id",
    # Major EU
    "germany": "de", "berlin": "de", "munich": "de",
    "france": "fr", "paris": "fr",
    "spain": "es", "madrid": "es", "barcelona": "es",
    "italy": "it", "rome": "it", "milan": "it",
    "netherlands": "nl", "amsterdam": "nl",
}


def country_hint(location: str) -> str:
    """Pick a `gl=` parameter from a free-text location string.

    Defaults to `us` when nothing matches, but we try the second-to-last
    token first (typical format "City, Country" or "Karachi, Pakistan") so
    "Islamabad" alone still picks up `pk`.
    """
    if not location:
        return "us"
    lower = location.lower().strip()
    if lower in _COUNTRY_HINTS:
        return _COUNTRY_HINTS[lower]
    # Try comma-split chunks right-to-left (last token usually = country).
    for chunk in reversed([c.strip() for c in lower.split(",")]):
        if chunk in _COUNTRY_HINTS:
            return _COUNTRY_HINTS[chunk]
    # Try every word in case the location is unpunctuated.
    for word in lower.split():
        if word in _COUNTRY_HINTS:
            return _COUNTRY_HINTS[word]
    return "us"


# JS that reads listing cards and pulls structured data straight from the DOM.
# Keeps work in the page and avoids 20+ Playwright round-trips per result.
_CARDS_JS = r"""
() => {
  const out = [];
  const anchors = Array.from(document.querySelectorAll('a.hfpxzc'));
  for (const a of anchors) {
    const root = a.closest('div[jsaction]') || a.parentElement;
    const href = a.href || null;
    const aria = a.getAttribute('aria-label') || '';
    let name = aria;
    const nameEl = root && root.querySelector('.qBF1Pd, .fontHeadlineSmall');
    if (nameEl && nameEl.textContent) name = nameEl.textContent.trim();

    let rating = null, reviews = null;
    const rEl = root && root.querySelector('span.MW4etd');
    if (rEl) {
      const v = parseFloat(rEl.textContent);
      if (!isNaN(v)) rating = v;
    }
    const revEl = root && root.querySelector('span.UY7F9');
    if (revEl) {
      const m = revEl.textContent.match(/[\d,]+/);
      if (m) reviews = parseInt(m[0].replace(/,/g, ''), 10);
    }

    let category = null, addressSnippet = null, phoneSnippet = null;
    const efs = root ? root.querySelectorAll('div.W4Efsd > div.W4Efsd') : [];
    if (efs.length > 0) {
      const txt = efs[0].textContent.replace(/\s+/g, ' ').trim();
      const parts = txt.split('·').map(s => s.trim()).filter(Boolean);
      if (parts.length >= 1) category = parts[0] || null;
      if (parts.length >= 2) addressSnippet = parts.slice(1).join(' · ') || null;
    }
    if (efs.length > 1) {
      const txt2 = efs[1].textContent.replace(/\s+/g, ' ').trim();
      const phoneMatch = txt2.match(/(\+?\d[\d \-().]{7,}\d)/);
      if (phoneMatch) phoneSnippet = phoneMatch[0];
    }

    // Closed-business marker. Listing has "Permanently closed" or
    // "Temporarily closed" in a span near the rating row.
    const closedEl = root && root.querySelector('span.eXlrNe');
    const closedNote = closedEl ? (closedEl.textContent || '').trim() : null;

    // Cheap heuristic for "has website" — Maps sometimes shows a globe icon
    // button right on the card. We don't follow it, but we record the hint.
    const websiteHint = root && root.querySelector('a[aria-label^="Website"]');
    const cardWebsite = websiteHint ? websiteHint.href || null : null;

    out.push({
      name, href, rating, reviews,
      category, addressSnippet, phoneSnippet,
      closedNote, cardWebsite,
    });
  }
  return out;
}
"""


async def _accept_consent(page: Page, *, attempts: int = 5) -> bool:
    """Dismiss the Google consent screen. Retries with backoff.

    Returns True if dismissed (or never present), False if we kept hitting it.
    The previous version tried three labels once and gave up — that's why
    "0 results" was a frequent failure mode for non-US locations.
    """
    for attempt in range(attempts):
        if "consent.google" not in page.url and "consent" not in (await page.title() or "").lower():
            return True
        for label in ("Reject all", "Accept all", "I agree", "Aceptar todo", "Tout accepter"):
            try:
                btn = page.get_by_role("button", name=label)
                if await btn.count() > 0:
                    await btn.first.click(timeout=2000)
                    await page.wait_for_load_state("domcontentloaded", timeout=10000)
                    log.info("Dismissed Google consent via '%s'", label)
                    await polite_sleep(0.3, 0.7)
                    break
            except Exception as e:  # noqa: BLE001
                log.debug("consent click '%s' failed: %s", label, e)
                continue
        await polite_sleep(0.6, 1.3)
    log.warning("Consent screen still present after %d attempts", attempts)
    return False


async def _scroll_feed(page: Page, max_results: int) -> int:
    """Scroll the results feed until we have `max_results` cards or reach the end.

    Returns the final card count seen so the caller can decide whether the
    query was thin.
    """
    feed = page.locator('div[role="feed"]')
    try:
        await feed.wait_for(timeout=15000)
    except PWTimeout:
        log.warning("Feed never appeared — page layout may differ or query had zero results")
        return 0

    seen = -1
    stagnant = 0
    last = 0
    for step in range(50):
        n = await page.locator('a.hfpxzc').count()
        last = n
        if n >= max_results:
            log.info("Loaded %d cards (>= max %d) after %d scrolls", n, max_results, step)
            return n
        if n == seen:
            stagnant += 1
            if stagnant >= 3:
                log.info("Feed stagnant at %d cards after %d scrolls — assuming end", n, step)
                return n
        else:
            stagnant = 0
        seen = n
        try:
            await feed.evaluate("(el) => el.scrollBy(0, el.clientHeight)")
        except Exception as e:  # noqa: BLE001
            log.debug("scroll failed: %s", e)
            return n
        await polite_sleep(0.4, 0.9)
    return last


async def _extract_detail(page: Page, listing_url: str) -> dict[str, str | None]:
    detail: dict[str, str | None] = {}
    try:
        await page.goto(listing_url, wait_until="domcontentloaded", timeout=20000)
    except Exception as e:  # noqa: BLE001
        log.debug("detail nav failed for %s: %s", listing_url, e)
        return detail

    try:
        await page.locator('h1').first.wait_for(timeout=5000)
    except Exception as e:  # noqa: BLE001
        log.debug("h1 wait failed: %s", e)

    # Website — primary selector first, then fall-backs.
    try:
        ws = page.locator('a[data-item-id="authority"]')
        if await ws.count() > 0:
            href = await ws.first.get_attribute("href")
            if href:
                detail["website"] = href
    except Exception as e:  # noqa: BLE001
        log.debug("website selector failed: %s", e)

    if "website" not in detail:
        try:
            # Fallback: any anchor labelled "Website" in the panel.
            ws2 = page.locator('a[aria-label^="Website"]')
            if await ws2.count() > 0:
                href = await ws2.first.get_attribute("href")
                if href and href.startswith("http"):
                    detail["website"] = href
        except Exception as e:  # noqa: BLE001
            log.debug("website fallback failed: %s", e)

    # Phone
    try:
        ph = page.locator('button[data-item-id^="phone"]')
        if await ph.count() > 0:
            label = await ph.first.get_attribute("aria-label") or ""
            m = re.search(r"(\+?\d[\d \-().]{7,}\d)", label)
            if m:
                detail["phone"] = m.group(1).strip()
    except Exception as e:  # noqa: BLE001
        log.debug("phone selector failed: %s", e)

    # Address
    try:
        addr = page.locator('button[data-item-id="address"]')
        if await addr.count() > 0:
            label = await addr.first.get_attribute("aria-label") or ""
            detail["address"] = label.split(":", 1)[1].strip() if ":" in label else label.strip()
    except Exception as e:  # noqa: BLE001
        log.debug("address selector failed: %s", e)

    # Plus code
    try:
        plus = page.locator('button[data-item-id="oloc"]')
        if await plus.count() > 0:
            label = await plus.first.get_attribute("aria-label") or ""
            detail["plus_code"] = label.split(":", 1)[1].strip() if ":" in label else label.strip()
    except Exception as e:  # noqa: BLE001
        log.debug("plus_code selector failed: %s", e)

    # Hours
    try:
        hours = page.locator('div[aria-label*="Hours"]').first
        if await hours.count() > 0:
            text = (await hours.inner_text()) or ""
            text = " ".join(text.split())
            if text:
                detail["hours"] = text[:300]
    except Exception as e:  # noqa: BLE001
        log.debug("hours selector failed: %s", e)

    # Editorial description
    try:
        desc = page.locator('div.PYvSYb, div[jsaction*="description"]').first
        if await desc.count() > 0:
            text = (await desc.inner_text()) or ""
            text = " ".join(text.split())
            if text and len(text) > 12:
                detail["description"] = text[:600]
    except Exception as e:  # noqa: BLE001
        log.debug("description selector failed: %s", e)

    # Closed marker on the detail panel
    try:
        closed_loc = page.locator('div.fCEvvc, span:has-text("Permanently closed"), span:has-text("Temporarily closed")').first
        if await closed_loc.count() > 0:
            text = (await closed_loc.inner_text()) or ""
            if "closed" in text.lower():
                detail["closed_note"] = text.strip()
    except Exception as e:  # noqa: BLE001
        log.debug("closed-note selector failed: %s", e)

    return detail


async def _enrich_concurrent(
    context: BrowserContext,
    cards: list[dict],
    enrich_top_n: int,
    *,
    progress_cb: Callable[[int, int], Awaitable[None]] | None = None,
    cancel_event: asyncio.Event | None = None,
) -> dict[int, dict[str, str | None]]:
    """Run _extract_detail across multiple pages in parallel.

    Returns {card_index: detail_dict}. Failed or cancelled cards are absent
    rather than throwing.
    """
    targets = [(i, c["href"]) for i, c in enumerate(cards) if c.get("href") and i < enrich_top_n]
    if not targets:
        return {}

    sem = asyncio.Semaphore(_DETAIL_CONCURRENCY)
    results: dict[int, dict[str, str | None]] = {}
    done = 0
    total = len(targets)

    async def worker(idx: int, href: str) -> None:
        nonlocal done
        if cancel_event is not None and cancel_event.is_set():
            return
        async with sem:
            if cancel_event is not None and cancel_event.is_set():
                return
            page = await context.new_page()
            try:
                detail = await _extract_detail(page, href)
                if detail:
                    results[idx] = detail
            except Exception as e:  # noqa: BLE001
                log.warning("detail worker failed for idx=%d: %s", idx, e)
            finally:
                try:
                    await page.close()
                except Exception as e:  # noqa: BLE001
                    log.debug("page.close failed: %s", e)
                done += 1
                if progress_cb is not None:
                    try:
                        await progress_cb(done, total)
                    except Exception as e:  # noqa: BLE001
                        log.debug("progress callback failed: %s", e)

    await asyncio.gather(*(worker(i, h) for i, h in targets), return_exceptions=True)
    return results


async def scrape(
    context: BrowserContext,
    niche: str,
    location: str,
    max_results: int = 20,
    *,
    enrich_top_n: int | None = None,
    progress_cb: Callable[[str, dict], Awaitable[None]] | None = None,
    cancel_event: asyncio.Event | None = None,
) -> list[ScrapedLead]:
    """Search Google Maps for `niche in location` and return up to max_results leads.

    Pass 1: scroll the feed and pull structured card data via a single JS
    evaluation (fast — no per-card round-trip).
    Pass 2: open each detail panel concurrently to extract website, phone,
    full address, plus_code, hours, and description.

    `progress_cb(stage, payload)` is invoked at every meaningful pipeline
    transition so the caller can stream status. It must be tolerant — we
    swallow exceptions from it.
    """
    if enrich_top_n is None:
        enrich_top_n = max_results

    gl = country_hint(location)
    page = await context.new_page()
    cards: list[dict] = []
    try:
        query = f"{niche} in {location}".strip()
        url = f"{GMAPS_BASE}{quote_plus(query)}?hl=en&gl={gl}"
        log.info("Navigating: %s", url)
        if progress_cb:
            await _safe_progress(progress_cb, "searching", {"message": f"Querying Google Maps ({gl})…"})
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await _accept_consent(page)
        await polite_sleep(0.5, 1.0)

        if progress_cb:
            await _safe_progress(progress_cb, "scrolling", {"message": "Loading result feed…"})
        feed_count = await _scroll_feed(page, max_results)
        if progress_cb:
            await _safe_progress(progress_cb, "scrolling", {"raw_count": feed_count})

        try:
            cards = await page.evaluate(_CARDS_JS)
        except Exception as e:  # noqa: BLE001
            log.warning("card extraction JS failed: %s", e)
            cards = []
        cards = [c for c in cards if c.get("name")][:max_results]
        log.info("Extracted %d cards from feed (gl=%s)", len(cards), gl)
        if len(cards) < 3 and feed_count > 0:
            log.warning("SELECTOR_DRIFT: feed had %d nodes but only %d parsed", feed_count, len(cards))
    finally:
        try:
            await page.close()
        except Exception as e:  # noqa: BLE001
            log.debug("page.close failed: %s", e)

    if not cards:
        return []

    async def detail_progress(done: int, total: int) -> None:
        if progress_cb:
            await _safe_progress(progress_cb, "enriching_details", {
                "enriched": done,
                "total": total,
            })

    if progress_cb:
        await _safe_progress(progress_cb, "enriching_details", {
            "enriched": 0,
            "total": min(len(cards), enrich_top_n),
        })

    details = await _enrich_concurrent(
        context,
        cards,
        enrich_top_n,
        progress_cb=detail_progress,
        cancel_event=cancel_event,
    )
    log.info("Enriched %d/%d details concurrently", len(details), min(len(cards), enrich_top_n))

    leads: list[ScrapedLead] = []
    for i, card in enumerate(cards):
        detail = details.get(i, {})
        # Skip cards explicitly marked closed on the listing.
        closed_note = (card.get("closedNote") or detail.get("closed_note") or "").lower()
        name = (card.get("name") or "").strip()
        if "closed" in closed_note and name:
            name = f"{name} (Permanently closed)"
        website = detail.get("website") or card.get("cardWebsite")
        leads.append(
            ScrapedLead(
                name=name,
                website=website,
                phone=detail.get("phone") or card.get("phoneSnippet"),
                address=detail.get("address") or card.get("addressSnippet"),
                location=location,
                niche=niche,
                category=card.get("category"),
                description=detail.get("description"),
                hours=detail.get("hours"),
                plus_code=detail.get("plus_code"),
                rating=card.get("rating"),
                reviews=card.get("reviews"),
                map_url=card.get("href"),
                source="google_maps",
                source_url=card.get("href"),
                sources=["google_maps"],
            )
        )
    return leads


async def _safe_progress(
    cb: Callable[[str, dict], Awaitable[None]],
    stage: str,
    payload: dict,
) -> None:
    try:
        await cb(stage, payload)
    except Exception as e:  # noqa: BLE001
        log.debug("progress callback raised: %s", e)
