"""Lead quality scoring + filtering.

Goal: separate real B2B businesses from noise. We keep entries that scrape
cleanly and have at least one actionable contact channel; we score the rest
to bias toward established, on-niche businesses with their own web presence.
"""
from urllib.parse import urlparse

from .types import ScrapedLead

# Domains that aren't a real "company website" — they're directory/social profiles.
AGGREGATOR_DOMAINS = {
    "facebook.com", "fb.com", "instagram.com", "linkedin.com", "twitter.com", "x.com",
    "yelp.com", "yellowpages.com", "foursquare.com", "tripadvisor.com",
    "google.com", "maps.google.com", "g.co", "goo.gl",
    "business.site", "sites.google.com", "wix.com", "wixsite.com",
    "blogspot.com", "wordpress.com", "weebly.com", "godaddysites.com",
}

CLOSED_HINTS = ("permanently closed", "temporarily closed")


def _hostname(url: str | None) -> str | None:
    if not url:
        return None
    try:
        h = urlparse(url).hostname or ""
        return h.lower().lstrip(".")
    except Exception:  # noqa: BLE001
        return None


def is_aggregator(url: str | None) -> bool:
    h = _hostname(url)
    if not h:
        return False
    h = h.removeprefix("www.")
    return any(h == d or h.endswith("." + d) for d in AGGREGATOR_DOMAINS)


def rejection_reason(lead: ScrapedLead) -> str | None:
    """Hard rejects — disqualifies the lead before scoring."""
    name = (lead.name or "").strip()
    if len(name) < 3:
        return "name missing or too short"
    lname = name.lower()
    if any(h in lname for h in CLOSED_HINTS):
        return "marked closed"
    if not lead.website and not lead.phone:
        return "no website and no phone — uncontactable"
    if lead.rating is not None and lead.rating < 2.5 and (lead.reviews or 0) >= 10:
        return "rating below 2.5 with sufficient reviews"
    return None


def score_lead(lead: ScrapedLead) -> tuple[int, dict[str, bool]]:
    """Return (0-100 score, signal flags)."""
    score = 0
    signals: dict[str, bool] = {}

    if lead.name and len(lead.name.strip()) > 2:
        score += 5
        signals["has_name"] = True

    if lead.website:
        if is_aggregator(lead.website):
            score += 8
            signals["website_aggregator"] = True
        else:
            score += 30
            signals["own_website"] = True

    if lead.phone:
        score += 10
        signals["has_phone"] = True

    if lead.address:
        score += 10
        signals["has_address"] = True

        if lead.location:
            loc_tokens = [t.strip().lower() for t in lead.location.replace(",", " ").split() if len(t.strip()) > 1]
            addr_l = lead.address.lower()
            if any(t in addr_l for t in loc_tokens):
                score += 10
                signals["location_match"] = True

    if lead.category and lead.niche:
        cat_l = lead.category.lower()
        niche_tokens = [t for t in lead.niche.lower().split() if len(t) > 2]
        if any(t in cat_l for t in niche_tokens):
            score += 15
            signals["category_match"] = True

    if lead.rating is not None:
        if lead.rating >= 4.0:
            score += 10
            signals["rating_strong"] = True
        elif lead.rating >= 3.0:
            score += 5

    if lead.reviews is not None:
        if lead.reviews >= 50:
            score += 10
            signals["reviews_high"] = True
        elif lead.reviews >= 10:
            score += 5

    return min(score, 100), signals


def filter_and_score(
    leads: list[ScrapedLead],
    min_score: int = 35,
) -> tuple[list[ScrapedLead], list[ScrapedLead]]:
    """Annotate leads with score/signals/rejection_reason.

    Returns (kept, dropped). kept is sorted by quality_score desc.
    """
    kept: list[ScrapedLead] = []
    dropped: list[ScrapedLead] = []
    for lead in leads:
        reason = rejection_reason(lead)
        if reason:
            lead.rejection_reason = reason
            dropped.append(lead)
            continue
        score, signals = score_lead(lead)
        lead.quality_score = score
        lead.signals = signals
        if score >= min_score:
            kept.append(lead)
        else:
            lead.rejection_reason = f"quality score {score} < threshold {min_score}"
            dropped.append(lead)

    kept.sort(key=lambda x: x.quality_score or 0, reverse=True)
    return kept, dropped
