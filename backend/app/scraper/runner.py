import logging

from .engine import browser_context, with_retries
from .quality import filter_and_score
from .sources import google_maps
from .types import ScrapeRequest, ScrapedLead

log = logging.getLogger(__name__)


async def run_scrape(req: ScrapeRequest) -> dict[str, list[ScrapedLead] | int]:
    """Top-level entry point. Returns a dict with kept + dropped leads and counts.

    Phase 4 will wrap this with a /scrape endpoint and DB persistence; Phase 3
    keeps it standalone so it can be invoked from a CLI or notebook.
    """
    log.info(
        "scrape start: niche=%r location=%r max=%d headless=%s",
        req.niche, req.location, req.max_results, req.headless,
    )

    async def _do() -> list[ScrapedLead]:
        async with browser_context(headless=req.headless) as ctx:
            return await google_maps.scrape(ctx, req.niche, req.location, req.max_results)

    raw = await with_retries(_do, attempts=2, base_delay=2.0, label="google_maps.scrape")
    log.info("raw leads scraped: %d", len(raw))

    kept, dropped = filter_and_score(raw, min_score=req.min_quality_score)
    log.info("after filter: kept=%d dropped=%d", len(kept), len(dropped))

    return {
        "kept": kept,
        "dropped": dropped,
        "raw_count": len(raw),
        "kept_count": len(kept),
        "dropped_count": len(dropped),
    }
