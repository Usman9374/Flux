"""Scrape routes.

Two flows are supported:
  - **Job flow (preferred):** `POST /api/scrape/jobs` returns a job_id
    immediately; the worker runs in a background task. Clients poll
    `GET /api/scrape/jobs/{job_id}` (or stream `…/events` over SSE) for
    real progress.
  - **Sync flow (legacy):** `POST /api/scrape` blocks until the scrape
    is done. Kept for backwards-compatibility — the frontend no longer
    uses it, but external callers might.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..auth import CurrentUser, require_user
from ..database import SessionLocal, get_db
from ..schemas import (
    IntentPreview,
    JobCreateOut,
    JobLeadPreview,
    JobStatusOut,
    LeadOut,
    ScrapeRequestIn,
    ScrapeResultOut,
)
from ..scraper.jobs import JobState, get_registry
from ..scraper.persist import upsert_leads
from ..scraper.runner import run_scrape
from ..scraper.types import ScrapeRequest, ScrapedLead

log = logging.getLogger(__name__)

router = APIRouter(prefix="/scrape", tags=["scrape"])


def _request_from_payload(payload: ScrapeRequestIn) -> ScrapeRequest:
    return ScrapeRequest(
        niche=payload.niche,
        location=payload.location,
        max_results=payload.max_results,
        headless=payload.headless,
        min_quality_score=payload.min_quality_score,
        require_website=payload.require_website,
        enrich_websites=payload.enrich_websites,
        wall_clock_s=payload.wall_clock_s,
    )


def _lead_preview(lead: ScrapedLead) -> dict[str, Any]:
    return {
        "name": lead.name,
        "website": lead.website,
        "phone": lead.phone,
        "email": lead.email,
        "location": lead.location,
        "category": lead.category,
        "quality_score": lead.quality_score,
        "tier": lead.tier,
        "confidence": lead.confidence,
        "signals": lead.signals,
        "sources": lead.sources or [],
        "map_url": lead.map_url or lead.source_url,
        "rating": lead.rating,
        "reviews": lead.reviews,
    }


# ---- Legacy sync endpoint (kept for compatibility) -----------------------


@router.post("", response_model=ScrapeResultOut, status_code=status.HTTP_200_OK)
async def scrape(
    payload: ScrapeRequestIn,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_user),
) -> ScrapeResultOut:
    req = _request_from_payload(payload)
    try:
        result = await run_scrape(req)
    except Exception as exc:  # noqa: BLE001
        log.exception("scrape failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Scraper error: {exc}",
        ) from exc

    kept = result["kept"]
    rows, inserted, updated = upsert_leads(
        db, kept,
        niche=payload.niche, location=payload.location, owner_uid=user.uid,
    )
    intent = result.get("intent") or {}
    return ScrapeResultOut(
        niche=payload.niche,
        location=payload.location,
        raw_count=int(result["raw_count"]),
        kept_count=int(result["kept_count"]),
        dropped_count=int(result["dropped_count"]),
        persisted_count=len(rows),
        inserted_count=inserted,
        updated_count=updated,
        partial=bool(result.get("partial")),
        relaxed_filter=bool(result.get("relaxed_filter")),
        intent=IntentPreview(**intent) if intent else None,
        leads=[LeadOut.model_validate(r) for r in rows],
    )


# ---- Job-based async flow -----------------------------------------------


@router.post("/jobs", response_model=JobCreateOut, status_code=status.HTTP_202_ACCEPTED)
async def create_scrape_job(
    payload: ScrapeRequestIn,
    user: CurrentUser = Depends(require_user),
) -> JobCreateOut:
    """Kick off an async scrape. Returns a job_id immediately."""
    registry = get_registry()
    state = await registry.create(owner_uid=user.uid)

    req = _request_from_payload(payload)
    # Fire-and-forget. The task references the user's uid and the job state;
    # the registry's TTL eventually cleans the JobState entry up.
    asyncio.create_task(
        _run_job(state.job_id, req, owner_uid=user.uid, payload=payload),
        name=f"scrape:{state.job_id}",
    )
    return JobCreateOut(job_id=state.job_id)


@router.get("/jobs/{job_id}", response_model=JobStatusOut)
async def get_scrape_job(
    job_id: str,
    user: CurrentUser = Depends(require_user),
) -> JobStatusOut:
    state = get_registry().get_for(job_id, owner_uid=user.uid)
    if state is None:
        raise HTTPException(status_code=404, detail="job not found")
    return _status_from_state(state)


@router.get("/jobs/{job_id}/events")
async def stream_scrape_job(
    job_id: str,
    user: CurrentUser = Depends(require_user),
):
    registry = get_registry()
    state = registry.get_for(job_id, owner_uid=user.uid)
    if state is None:
        raise HTTPException(status_code=404, detail="job not found")

    async def event_stream():
        # Emit current state immediately so a late subscriber gets a snapshot.
        yield _sse_event(state.snapshot())
        # Then stream updates until finished or the client disconnects.
        last_rev = state.revision
        while not state.finished:
            await registry.wait_for_change(job_id, timeout=2.0)
            current = registry.get(job_id)
            if current is None:
                break
            if current.revision != last_rev:
                last_rev = current.revision
                yield _sse_event(current.snapshot())
        # Final state.
        final = registry.get(job_id)
        if final is not None:
            yield _sse_event(final.snapshot())

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable proxy buffering (nginx, render)
            "Connection": "keep-alive",
        },
    )


# ---- Helpers ------------------------------------------------------------


def _sse_event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


def _status_from_state(state: JobState) -> JobStatusOut:
    intent = IntentPreview(**state.intent) if state.intent else None
    result_obj: ScrapeResultOut | None = None
    if state.result:
        # `state.result` is a serialized dict — coerce back into the model.
        result_obj = ScrapeResultOut(**state.result)
    return JobStatusOut(
        job_id=state.job_id,
        stage=state.stage,
        progress=state.progress,
        message=state.message,
        raw_count=state.raw_count,
        kept_count=state.kept_count,
        dropped_count=state.dropped_count,
        enriched=state.enriched,
        partial=state.partial,
        relaxed_filter=state.relaxed_filter,
        intent=intent,
        kept_preview=[JobLeadPreview(**p) for p in state.kept_preview],
        result=result_obj,
        error=state.error,
        finished=state.finished,
    )


async def _run_job(
    job_id: str,
    req: ScrapeRequest,
    *,
    owner_uid: str | None,
    payload: ScrapeRequestIn,
) -> None:
    """Worker coroutine for a single scrape job.

    Owns its own DB session — we can't depend on the request-scoped `db`
    because the request handler has long since returned. Errors are caught
    and written into the job's error field; we never let them surface as
    silent task failures.
    """
    registry = get_registry()
    try:
        async def progress(stage: str, payload: dict[str, Any]) -> None:
            update: dict[str, Any] = {"stage": stage}
            if "progress" in payload:
                update["progress"] = float(payload["progress"])
            if "message" in payload:
                update["message"] = payload["message"]
            if "raw_count" in payload:
                update["raw_count"] = int(payload["raw_count"])
            if "kept_count" in payload:
                update["kept_count"] = int(payload["kept_count"])
            if "dropped_count" in payload:
                update["dropped_count"] = int(payload["dropped_count"])
            if "enriched" in payload and "total" in payload:
                update["enriched"] = int(payload["enriched"])
            if "intent" in payload:
                update["intent"] = payload["intent"]
            if "relaxed_filter" in payload:
                update["relaxed_filter"] = bool(payload["relaxed_filter"])
            if "partial" in payload:
                update["partial"] = bool(payload["partial"])
            await registry.update(job_id, **update)

        result = await run_scrape(req, progress=progress)

        # Stream kept leads into the preview so the table fills as we score.
        for lead in result["kept"][:50]:
            await registry.append_kept(job_id, _lead_preview(lead))

        # Persist.
        db = SessionLocal()
        try:
            rows, inserted, updated = upsert_leads(
                db, result["kept"],
                niche=req.niche, location=req.location, owner_uid=owner_uid,
            )
        finally:
            db.close()

        intent = result.get("intent") or {}
        result_out = ScrapeResultOut(
            niche=req.niche,
            location=req.location,
            raw_count=int(result["raw_count"]),
            kept_count=int(result["kept_count"]),
            dropped_count=int(result["dropped_count"]),
            persisted_count=len(rows),
            inserted_count=inserted,
            updated_count=updated,
            partial=bool(result.get("partial")),
            relaxed_filter=bool(result.get("relaxed_filter")),
            intent=IntentPreview(**intent) if intent else None,
            leads=[LeadOut.model_validate(r) for r in rows],
        )
        await registry.finish(job_id, result=result_out.model_dump(mode="json"))
    except Exception as exc:
        log.exception("scrape job %s failed: %s", job_id, exc)
        await registry.finish(job_id, error=str(exc) or exc.__class__.__name__)
