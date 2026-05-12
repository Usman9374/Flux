"""Lightweight idempotent schema migrations.

We don't want to bring in Alembic for a single-table app, but `create_all` only
*creates* tables — it never alters them. When we extend the Lead model with new
columns (phone, address, etc.) the existing Phase-2 table needs to grow. This
helper runs `ADD COLUMN IF NOT EXISTS` for each column the ORM model declares,
then ensures the dedupe index exists. Safe to run on every boot.
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)


# (column_name, postgres_type, default_clause_or_None)
_LEADS_COLUMNS: list[tuple[str, str, str | None]] = [
    ("phone", "varchar(64)", None),
    ("email", "varchar(255)", None),
    ("address", "text", None),
    ("category", "varchar(255)", None),
    ("description", "text", None),
    ("hours", "text", None),
    ("plus_code", "varchar(64)", None),
    ("rating", "double precision", None),
    ("reviews_count", "integer", None),
    ("social_links", "jsonb", None),
    ("source", "varchar(64)", "DEFAULT 'google_maps' NOT NULL"),
    ("source_url", "text", None),
    ("signals", "jsonb", None),
    ("updated_at", "timestamptz", "DEFAULT now() NOT NULL"),
    ("owner_uid", "varchar(128)", None),
]


def ensure_leads_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    if "leads" not in inspector.get_table_names():
        # Fresh DB — create_all() already produced the full table; nothing to alter.
        return

    existing_cols = {c["name"] for c in inspector.get_columns("leads")}

    with engine.begin() as conn:
        for col_name, col_type, default_clause in _LEADS_COLUMNS:
            if col_name in existing_cols:
                continue
            tail = f" {default_clause}" if default_clause else ""
            stmt = f'ALTER TABLE leads ADD COLUMN IF NOT EXISTS "{col_name}" {col_type}{tail}'
            log.info("migration: %s", stmt)
            conn.execute(text(stmt))

        # Replace the legacy global-dedupe index with a per-owner one. Two
        # users scraping the same business should each get their own row.
        conn.execute(text("DROP INDEX IF EXISTS ux_leads_name_location_source"))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_leads_owner_name_location_source "
            "ON leads (coalesce(owner_uid, ''), lower(name), lower(coalesce(location, '')), source)"
        ))
        # Helpful single-column indexes for filtering (idempotent).
        for col in ("location", "niche", "quality_score", "owner_uid"):
            conn.execute(text(
                f"CREATE INDEX IF NOT EXISTS ix_leads_{col} ON leads ({col})"
            ))
