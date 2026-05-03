from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LeadBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    website: str | None = Field(default=None, max_length=2048)
    phone: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None)
    location: str | None = Field(default=None, max_length=255)
    niche: str | None = Field(default=None, max_length=255)
    category: str | None = Field(default=None, max_length=255)
    rating: float | None = Field(default=None, ge=0, le=5)
    reviews_count: int | None = Field(default=None, ge=0)
    source: str = Field(default="google_maps", max_length=64)
    source_url: str | None = Field(default=None)
    quality_score: int | None = Field(default=None, ge=0, le=100)
    signals: dict[str, Any] | None = None


class LeadCreate(LeadBase):
    pass


class LeadOut(LeadBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime | None = None


class LeadList(BaseModel):
    items: list[LeadOut]
    count: int


class ScrapeRequestIn(BaseModel):
    niche: str = Field(..., min_length=2, max_length=120)
    location: str = Field(..., min_length=2, max_length=120)
    max_results: int = Field(default=20, ge=1, le=100)
    min_quality_score: int = Field(default=35, ge=0, le=100)
    headless: bool = True


class ScrapeResultOut(BaseModel):
    niche: str
    location: str
    raw_count: int
    kept_count: int
    dropped_count: int
    persisted_count: int
    inserted_count: int
    updated_count: int
    leads: list[LeadOut]
