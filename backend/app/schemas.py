from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LeadBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    website: str | None = Field(default=None, max_length=2048)
    phone: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None)
    location: str | None = Field(default=None, max_length=255)
    niche: str | None = Field(default=None, max_length=255)
    category: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None)
    tagline: str | None = Field(default=None, max_length=255)
    hours: str | None = Field(default=None)
    plus_code: str | None = Field(default=None, max_length=64)
    rating: float | None = Field(default=None, ge=0, le=5)
    reviews_count: int | None = Field(default=None, ge=0)
    years_in_business: int | None = Field(default=None, ge=0)
    social_links: dict[str, str] | None = None
    source: str = Field(default="google_maps", max_length=64)
    sources: list[str] | None = None
    source_url: str | None = Field(default=None)
    map_url: str | None = Field(default=None)
    quality_score: int | None = Field(default=None, ge=0, le=100)
    tier: str | None = Field(default=None, max_length=4)
    confidence: float | None = Field(default=None, ge=0, le=1)
    signals: dict[str, Any] | None = None
    fetched_at: datetime | None = None


class LeadCreate(LeadBase):
    pass


class LeadOut(LeadBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_uid: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class LeadList(BaseModel):
    items: list[LeadOut]
    count: int


class ScrapeRequestIn(BaseModel):
    niche: str = Field(..., min_length=2, max_length=120)
    location: str = Field(..., min_length=2, max_length=120)
    max_results: int = Field(default=20, ge=1, le=100)
    min_quality_score: int = Field(default=0, ge=0, le=100)
    headless: bool = True
    # Optional explicit overrides — if omitted, backend infers from the niche
    # text (e.g. "dental clinics without website" toggles require_website off).
    require_website: bool | None = None
    enrich_websites: bool = True
    wall_clock_s: float = Field(default=90.0, ge=10.0, le=300.0)


class IntentPreview(BaseModel):
    cleaned_niche: str
    require_website: bool
    mode_label: str


class ScrapeResultOut(BaseModel):
    niche: str
    location: str
    raw_count: int
    kept_count: int
    dropped_count: int
    persisted_count: int
    inserted_count: int
    updated_count: int
    partial: bool = False
    relaxed_filter: bool = False
    intent: IntentPreview | None = None
    leads: list[LeadOut]


class JobCreateOut(BaseModel):
    job_id: str


class JobLeadPreview(BaseModel):
    """Trimmed lead representation for streaming progress."""
    name: str
    website: str | None = None
    phone: str | None = None
    email: str | None = None
    location: str | None = None
    category: str | None = None
    quality_score: int | None = None
    tier: str | None = None
    confidence: float | None = None
    signals: dict[str, Any] | None = None
    sources: list[str] | None = None
    map_url: str | None = None
    rating: float | None = None
    reviews: int | None = None


class JobStatusOut(BaseModel):
    job_id: str
    stage: str
    progress: float
    message: str | None = None
    raw_count: int = 0
    kept_count: int = 0
    dropped_count: int = 0
    enriched: int = 0
    partial: bool = False
    relaxed_filter: bool = False
    intent: IntentPreview | None = None
    kept_preview: list[JobLeadPreview] = []
    result: ScrapeResultOut | None = None
    error: str | None = None
    finished: bool = False
