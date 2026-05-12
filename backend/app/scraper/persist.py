"""Persist ScrapedLead → leads table with dedupe-friendly upsert.

We dedupe on (lower(name), lower(coalesce(location,'')), source) — the same
unique index installed by `migrations.ensure_leads_schema`. On conflict we
refresh the dynamic fields (rating, score, signals, contact info) so a re-scrape
keeps the lead fresh instead of stacking duplicates.
"""
from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..models import Lead
from .types import ScrapedLead

log = logging.getLogger(__name__)


def _row_from_scraped(
    lead: ScrapedLead, niche_default: str, location_default: str, owner_uid: str | None
) -> dict:
    return {
        "owner_uid": owner_uid,
        "name": (lead.name or "").strip(),
        "website": lead.website,
        "phone": lead.phone,
        "email": lead.email,
        "address": lead.address,
        "location": lead.location or location_default,
        "niche": lead.niche or niche_default,
        "category": lead.category,
        "description": lead.description,
        "hours": lead.hours,
        "plus_code": lead.plus_code,
        "rating": lead.rating,
        "reviews_count": lead.reviews,
        "social_links": lead.social_links or {},
        "source": lead.source or "google_maps",
        "source_url": lead.source_url,
        "quality_score": lead.quality_score,
        "signals": lead.signals or {},
    }


def upsert_leads(
    db: Session,
    leads: list[ScrapedLead],
    niche: str,
    location: str,
    owner_uid: str | None,
) -> tuple[list[Lead], int, int]:
    """Insert-or-update each lead. Returns (rows, inserted_count, updated_count).

    `inserted_count` vs `updated_count` is determined by comparing
    `created_at` and `updated_at` post-upsert: a freshly inserted row has them
    equal (both = now()).
    """
    if not leads:
        return [], 0, 0

    rows = [_row_from_scraped(l, niche, location, owner_uid) for l in leads]

    stmt = pg_insert(Lead).values(rows)
    update_cols = {
        "website": stmt.excluded.website,
        "phone": stmt.excluded.phone,
        "email": stmt.excluded.email,
        "address": stmt.excluded.address,
        "niche": stmt.excluded.niche,
        "category": stmt.excluded.category,
        "description": stmt.excluded.description,
        "hours": stmt.excluded.hours,
        "plus_code": stmt.excluded.plus_code,
        "rating": stmt.excluded.rating,
        "reviews_count": stmt.excluded.reviews_count,
        "social_links": stmt.excluded.social_links,
        "source_url": stmt.excluded.source_url,
        "quality_score": stmt.excluded.quality_score,
        "signals": stmt.excluded.signals,
        "updated_at": func.now(),
    }
    stmt = stmt.on_conflict_do_update(
        index_elements=[
            func.coalesce(Lead.owner_uid, ""),
            func.lower(Lead.name),
            func.lower(func.coalesce(Lead.location, "")),
            Lead.source,
        ],
        set_=update_cols,
    ).returning(Lead.id, Lead.created_at, Lead.updated_at)

    result = db.execute(stmt)
    upserted = result.all()  # list of (id, created_at, updated_at)
    db.commit()

    inserted = sum(1 for _id, c, u in upserted if c == u)
    updated = len(upserted) - inserted
    ids = [row[0] for row in upserted]

    rows_out = list(db.scalars(select(Lead).where(Lead.id.in_(ids))).all())
    # Preserve original kept ordering (highest score first).
    order = {row_id: i for i, row_id in enumerate(ids)}
    rows_out.sort(key=lambda l: order.get(l.id, 1_000_000))

    log.info("upsert: inserted=%d updated=%d", inserted, updated)
    return rows_out, inserted, updated
