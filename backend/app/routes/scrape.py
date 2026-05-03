"""POST /api/scrape — run the scraper, persist kept leads, return them.

This is the wiring point for Phase 4: scraper → backend → DB. The scraper
itself is async (Playwright), so the route handler is async; persistence is
synchronous SQLAlchemy and runs after the browser context has closed.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import LeadOut, ScrapeRequestIn, ScrapeResultOut
from ..scraper.persist import upsert_leads
from ..scraper.runner import run_scrape
from ..scraper.types import ScrapeRequest

log = logging.getLogger(__name__)

router = APIRouter(prefix="/scrape", tags=["scrape"])


@router.post("", response_model=ScrapeResultOut, status_code=status.HTTP_200_OK)
async def scrape(payload: ScrapeRequestIn, db: Session = Depends(get_db)) -> ScrapeResultOut:
    req = ScrapeRequest(
        niche=payload.niche,
        location=payload.location,
        max_results=payload.max_results,
        headless=payload.headless,
        min_quality_score=payload.min_quality_score,
    )

    try:
        result = await run_scrape(req)
    except Exception as exc:  # noqa: BLE001
        log.exception("scrape failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Scraper error: {exc}",
        ) from exc

    kept = result["kept"]  # list[ScrapedLead]
    rows, inserted, updated = upsert_leads(db, kept, niche=payload.niche, location=payload.location)

    return ScrapeResultOut(
        niche=payload.niche,
        location=payload.location,
        raw_count=int(result["raw_count"]),
        kept_count=int(result["kept_count"]),
        dropped_count=int(result["dropped_count"]),
        persisted_count=len(rows),
        inserted_count=inserted,
        updated_count=updated,
        leads=[LeadOut.model_validate(r) for r in rows],
    )
