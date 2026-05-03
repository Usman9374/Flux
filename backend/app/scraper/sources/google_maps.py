"""Google Maps scraper.

Defensive against selector drift: every extraction step has a fallback and
returns whatever it can. We never crash the whole run because one card
failed to parse.
"""
import logging
import re
from urllib.parse import quote_plus

from playwright.async_api import BrowserContext, Page
from playwright.async_api import TimeoutError as PWTimeout

from ..engine import polite_sleep
from ..types import ScrapedLead

log = logging.getLogger(__name__)

GMAPS_BASE = "https://www.google.com/maps/search/"

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
        await polite_sleep(1.0, 2.0)


async def _extract_detail(page: Page, listing_url: str) -> dict[str, str | None]:
    detail: dict[str, str | None] = {}
    try:
        await page.goto(listing_url, wait_until="domcontentloaded", timeout=20000)
    except Exception as e:  # noqa: BLE001
        log.debug("detail nav failed for %s: %s", listing_url, e)
        return detail
    await polite_sleep(0.6, 1.2)

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

    return detail


async def scrape(
    context: BrowserContext,
    niche: str,
    location: str,
    max_results: int = 20,
    *,
    enrich_top_n: int | None = None,
) -> list[ScrapedLead]:
    """Search Google Maps for `niche in location` and return up to max_results leads.

    The first pass extracts what's visible on the result cards (fast).
    The second pass (`enrich_top_n`) clicks into each detail panel to grab
    website/phone/full-address — costly, so capped.
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
        await polite_sleep(1.0, 2.0)

        await _scroll_feed(page, max_results)
        cards = await page.evaluate(_CARDS_JS)
        cards = [c for c in cards if c.get("name")][:max_results]
        log.info("Extracted %d cards from feed", len(cards))

        leads: list[ScrapedLead] = []
        for i, card in enumerate(cards):
            href = card.get("href")
            detail: dict[str, str | None] = {}
            if href and i < enrich_top_n:
                detail = await _extract_detail(page, href)
                await polite_sleep(0.8, 1.6)

            leads.append(
                ScrapedLead(
                    name=(card.get("name") or "").strip(),
                    website=detail.get("website"),
                    phone=detail.get("phone") or card.get("phoneSnippet"),
                    address=detail.get("address") or card.get("addressSnippet"),
                    location=location,
                    niche=niche,
                    category=card.get("category"),
                    rating=card.get("rating"),
                    reviews=card.get("reviews"),
                    source="google_maps",
                    source_url=href,
                )
            )
        return leads
    finally:
        await page.close()
