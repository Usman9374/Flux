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
"""
import asyncio
import logging
import re
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

    out.push({ name, href, rating, reviews, category, addressSnippet, phoneSnippet });
  }
  return out;
}
"""


async def _accept_consent(page: Page) -> None:
    if "consent.google" not in page.url:
        return
    for label in ("Reject all", "Accept all", "I agree"):
        try:
            btn = page.get_by_role("button", name=label)
            if await btn.count() > 0:
                await btn.first.click()
                await page.wait_for_load_state("domcontentloaded", timeout=10000)
                log.info("Dismissed Google consent screen via '%s'", label)
                return
        except Exception:  # noqa: BLE001
            continue


async def _scroll_feed(page: Page, max_results: int) -> None:
    feed = page.locator('div[role="feed"]')
    try:
        await feed.wait_for(timeout=15000)
    except PWTimeout:
        log.warning("Feed never appeared — page layout may differ or query had zero results")
        return

    seen = -1
    stagnant = 0
    for step in range(40):
        n = await page.locator('a.hfpxzc').count()
        if n >= max_results:
            log.info("Loaded %d cards (>= max %d) after %d scrolls", n, max_results, step)
            return
        if n == seen:
            stagnant += 1
            if stagnant >= 3:
                # End of results — Google shows a 'You've reached the end of the list' marker.
                log.info("Feed stagnant at %d cards after %d scrolls — assuming end", n, step)
                return
        else:
            stagnant = 0
        seen = n
        try:
            await feed.evaluate("(el) => el.scrollBy(0, el.clientHeight)")
        except Exception:  # noqa: BLE001
            return
        await polite_sleep(0.4, 0.9)


async def _extract_detail(page: Page, listing_url: str) -> dict[str, str | None]:
    detail: dict[str, str | None] = {}
    try:
        await page.goto(listing_url, wait_until="domcontentloaded", timeout=20000)
    except Exception as e:  # noqa: BLE001
        log.debug("detail nav failed for %s: %s", listing_url, e)
        return detail

    # Wait for the detail panel header (business name h1) to appear.
    try:
        await page.locator('h1').first.wait_for(timeout=5000)
    except Exception:  # noqa: BLE001
        pass

    # Website
    try:
        ws = page.locator('a[data-item-id="authority"]')
        if await ws.count() > 0:
            href = await ws.first.get_attribute("href")
            if href:
                detail["website"] = href
    except Exception:  # noqa: BLE001
        pass

    # Phone
    try:
        ph = page.locator('button[data-item-id^="phone"]')
        if await ph.count() > 0:
            label = await ph.first.get_attribute("aria-label") or ""
            m = re.search(r"(\+?\d[\d \-().]{7,}\d)", label)
            if m:
                detail["phone"] = m.group(1).strip()
    except Exception:  # noqa: BLE001
        pass

    # Address
    try:
        addr = page.locator('button[data-item-id="address"]')
        if await addr.count() > 0:
            label = await addr.first.get_attribute("aria-label") or ""
            detail["address"] = label.split(":", 1)[1].strip() if ":" in label else label.strip()
    except Exception:  # noqa: BLE001
        pass

    # Plus code (Google's geo-shorthand — handy as a stable location key)
    try:
        plus = page.locator('button[data-item-id="oloc"]')
        if await plus.count() > 0:
            label = await plus.first.get_attribute("aria-label") or ""
            detail["plus_code"] = label.split(":", 1)[1].strip() if ":" in label else label.strip()
    except Exception:  # noqa: BLE001
        pass

    # Hours — collapsed text on the listing panel ("Open · Closes 6 PM" style).
    try:
        hours = page.locator('div[aria-label*="Hours"]').first
        if await hours.count() > 0:
            text = (await hours.inner_text()) or ""
            text = " ".join(text.split())
            if text:
                detail["hours"] = text[:300]
    except Exception:  # noqa: BLE001
        pass

    # Description / editorial summary — Google's own short blurb when present.
    try:
        desc = page.locator('div.PYvSYb, div[jsaction*="description"]').first
        if await desc.count() > 0:
            text = (await desc.inner_text()) or ""
            text = " ".join(text.split())
            if text and len(text) > 12:
                detail["description"] = text[:600]
    except Exception:  # noqa: BLE001
        pass

    return detail


async def _enrich_concurrent(
    context: BrowserContext,
    cards: list[dict],
    enrich_top_n: int,
) -> dict[int, dict[str, str | None]]:
    """Run _extract_detail across multiple pages in parallel.

    Returns {card_index: detail_dict}. Failed cards are simply absent.
    """
    targets = [(i, c["href"]) for i, c in enumerate(cards) if c.get("href") and i < enrich_top_n]
    if not targets:
        return {}

    sem = asyncio.Semaphore(_DETAIL_CONCURRENCY)
    results: dict[int, dict[str, str | None]] = {}

    async def worker(idx: int, href: str) -> None:
        async with sem:
            page = await context.new_page()
            try:
                detail = await _extract_detail(page, href)
                if detail:
                    results[idx] = detail
            except Exception as e:  # noqa: BLE001
                log.debug("detail worker failed for idx=%d: %s", idx, e)
            finally:
                try:
                    await page.close()
                except Exception:  # noqa: BLE001
                    pass

    await asyncio.gather(*(worker(i, h) for i, h in targets), return_exceptions=True)
    return results


async def scrape(
    context: BrowserContext,
    niche: str,
    location: str,
    max_results: int = 20,
    *,
    enrich_top_n: int | None = None,
) -> list[ScrapedLead]:
    """Search Google Maps for `niche in location` and return up to max_results leads.

    Pass 1: scroll the feed and pull structured card data via a single JS
    evaluation (fast — no per-card round-trip).
    Pass 2: open each detail panel concurrently to extract website, phone,
    full address, plus_code, hours, and description.
    """
    if enrich_top_n is None:
        enrich_top_n = max_results

    page = await context.new_page()
    try:
        query = f"{niche} in {location}".strip()
        url = f"{GMAPS_BASE}{quote_plus(query)}?hl=en&gl=us"
        log.info("Navigating: %s", url)
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await _accept_consent(page)
        await polite_sleep(0.5, 1.0)

        await _scroll_feed(page, max_results)
        cards = await page.evaluate(_CARDS_JS)
        cards = [c for c in cards if c.get("name")][:max_results]
        log.info("Extracted %d cards from feed", len(cards))
    finally:
        await page.close()

    details = await _enrich_concurrent(context, cards, enrich_top_n)
    log.info("Enriched %d/%d details concurrently", len(details), min(len(cards), enrich_top_n))

    leads: list[ScrapedLead] = []
    for i, card in enumerate(cards):
        detail = details.get(i, {})
        leads.append(
            ScrapedLead(
                name=(card.get("name") or "").strip(),
                website=detail.get("website"),
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
                source="google_maps",
                source_url=card.get("href"),
            )
        )
    return leads
