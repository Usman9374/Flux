from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ScrapeRequest:
    niche: str
    location: str
    max_results: int = 20
    headless: bool = True
    min_quality_score: int = 35


@dataclass
class ScrapedLead:
    name: str
    website: str | None = None
    phone: str | None = None
    address: str | None = None
    location: str | None = None
    niche: str | None = None
    category: str | None = None
    rating: float | None = None
    reviews: int | None = None
    source: str = "google_maps"
    source_url: str | None = None
    quality_score: int | None = None
    rejection_reason: str | None = None
    signals: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
