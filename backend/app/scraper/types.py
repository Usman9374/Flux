from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ScrapeRequest:
    niche: str
    location: str
    max_results: int = 20
    headless: bool = True
    min_quality_score: int = 40
    # Filter intent — None means "infer from the niche string"
    # (e.g. "dental clinics without website" → False).
    # True drops listings that have no first-party website (default Apollo-style).
    # False inverts: only listings WITHOUT a website pass.
    require_website: bool | None = None
    enrich_websites: bool = True
    # Wall-clock cap for the whole scrape. If exceeded, whatever's ready is
    # returned with partial=True.
    wall_clock_s: float = 90.0


@dataclass
class ScrapedLead:
    name: str
    website: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    location: str | None = None
    niche: str | None = None
    category: str | None = None
    description: str | None = None
    tagline: str | None = None
    hours: str | None = None
    plus_code: str | None = None
    rating: float | None = None
    reviews: int | None = None
    years_in_business: int | None = None
    social_links: dict[str, str] = field(default_factory=dict)
    map_url: str | None = None
    source: str = "google_maps"
    source_url: str | None = None
    sources: list[str] = field(default_factory=list)
    quality_score: int | None = None
    tier: str | None = None
    confidence: float | None = None
    rejection_reason: str | None = None
    signals: dict[str, Any] = field(default_factory=dict)
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
