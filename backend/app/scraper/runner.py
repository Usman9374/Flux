"""Top-level scrape orchestrator.

Pipeline:
  1. parse_intent(req.niche) — pull qualifiers like "without website" out of
     the niche string and clean it for the search query.
  2. Google Maps scrape — open a Playwright context, fetch + enrich cards.
  3. First-pass quality filter — drop closed listings, aggregator domains,
     and (depending on intent) leads without a website.
  4. Website enrichment — for kept leads with their own site, fetch homepage
     + /contact + /about and pull email / socials / description.
  5. Final scoring pass — now that we know about email/socials/description,
     compute the final quality score and signals.

Steps 3 and 5 use the same scoring code; the first pass is just so we don't
waste enrichment HTTP requests on leads we'd reject anyway.
"""
import logging

from .engine import browser_context, with_retries
from .quality import filter_and_score, parse_intent
from .sources import google_maps
from .types import ScrapeRequest, ScrapedLead
from .website_enrich import enrich_leads

log = logging.getLogger(__name__)


async def run_scrape(req: ScrapeRequest) -> dict[str, list[ScrapedLead] | int]:
    intent = parse_intent(req.niche)
    # Explicit override on the request beats inferred intent.
    require_website = (
        req.require_website if req.require_website is not None else intent.require_website
    )
    cleaned_niche = intent.cleaned_niche

    log.info(
        "scrape start: niche=%r (cleaned=%r) location=%r max=%d require_website=%s",
        req.niche, cleaned_niche, req.location, req.max_results, require_website,
    )

    async def _do() -> list[ScrapedLead]:
        async with browser_context(headless=req.headless) as ctx:
            return await google_maps.scrape(ctx, cleaned_niche, req.location, req.max_results)

    raw = await with_retries(_do, attempts=2, base_delay=2.0, label="google_maps.scrape")
    log.info("raw leads scraped: %d", len(raw))

    # First pass — drop the obviously bad ones BEFORE we spend time hitting
    # their websites. min_score=0 here; we only care about hard rejects.
    survivors, dropped = filter_and_score(raw, min_score=0, require_website=require_website)
    log.info("after first-pass filter: survivors=%d dropped=%d", len(survivors), len(dropped))

    # Enrich the survivors' websites — concurrent httpx fetches.
    if req.enrich_websites and require_website:
        await enrich_leads(survivors)

    # Final pass — now scoring sees email / socials / description.
    kept, dropped_low = filter_and_score(
        survivors, min_score=req.min_quality_score, require_website=require_website
    )
    dropped.extend(dropped_low)
    log.info("after final filter: kept=%d dropped=%d", len(kept), len(dropped))

    return {
        "kept": kept,
        "dropped": dropped,
        "raw_count": len(raw),
        "kept_count": len(kept),
        "dropped_count": len(dropped),
    }
