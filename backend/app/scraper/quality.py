"""Lead quality scoring + filtering.

Goal: separate real B2B businesses from noise. The default posture is strict —
we want Apollo-style results, not whatever Google returned. The scorer rewards
businesses with their own website, working contact channels (phone, email,
socials), local presence matching the queried area, and reputation signals.

Two filter modes are available via `parse_intent` / `ScrapeRequest.require_website`:
  - require_website=True (default): no first-party website ⇒ rejected.
    A listing without a website is rarely worth contacting.
  - require_website=False: enabled when the user explicitly types "without
    website" / "no website" in the niche. Inverts the rule — listings with
    a website are deprioritized or rejected so the user gets the offline
    businesses they asked for.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from .types import ScrapedLead

# Domains that aren't a real "company website" — they're directory/social profiles.
# We hard-reject these; downscoring still lets junk pass when other signals
# happen to be strong.
AGGREGATOR_DOMAINS = {
    "facebook.com", "fb.com", "m.facebook.com", "instagram.com",
    "linkedin.com", "twitter.com", "x.com", "tiktok.com", "pinterest.com",
    "youtube.com", "youtu.be",
    "yelp.com", "yellowpages.com", "yp.com", "foursquare.com",
    "tripadvisor.com", "tripadvisor.co.uk", "opentable.com", "zomato.com",
    "thumbtack.com", "houzz.com", "angi.com", "homeadvisor.com",
    "google.com", "maps.google.com", "g.co", "goo.gl",
    "business.site", "sites.google.com",
    "wix.com", "wixsite.com", "blogspot.com", "wordpress.com",
    "weebly.com", "godaddysites.com", "squarespace.com",
    "indeed.com", "glassdoor.com", "ziprecruiter.com",
    "trustpilot.com", "bbb.org", "manta.com", "bizapedia.com",
    "crunchbase.com", "zoominfo.com", "rocketreach.co",
}

CLOSED_HINTS = ("permanently closed", "temporarily closed")

# Tokens in the *niche* string that signal the user wants offline-only leads.
_NO_WEBSITE_PATTERNS = (
    r"\bwithout\s+(?:a\s+)?website",
    r"\bno\s+website",
    r"\bnot\s+having\s+(?:a\s+)?website",
    r"\b(?:doesn'?t|don'?t|do\s+not|does\s+not)\s+have\s+(?:a\s+)?website",
    r"\boffline(?:\s+only)?\b",
)


@dataclass(frozen=True)
class QueryIntent:
    cleaned_niche: str          # niche with qualifier phrases stripped
    require_website: bool       # True ⇒ reject leads with no website (default)


def parse_intent(niche: str) -> QueryIntent:
    """Pull qualifier phrases out of the niche string.

    Examples:
      "dental clinics in islamabad without website" → require_website=False
      "law firm" → require_website=True (default)

    Returns the cleaned niche so the actual Google Maps query doesn't carry
    the qualifier (it confuses the search ranker).
    """
    n = niche or ""
    require_website = True
    for pat in _NO_WEBSITE_PATTERNS:
        if re.search(pat, n, flags=re.IGNORECASE):
            require_website = False
            n = re.sub(pat, " ", n, flags=re.IGNORECASE)

    cleaned = re.sub(r"\s+", " ", n).strip(" ,.-")
    return QueryIntent(cleaned_niche=cleaned or niche, require_website=require_website)


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


def rejection_reason(lead: ScrapedLead, *, require_website: bool = True) -> str | None:
    """Hard rejects — disqualifies the lead before scoring."""
    name = (lead.name or "").strip()
    if len(name) < 3:
        return "name missing or too short"
    lname = name.lower()
    if any(h in lname for h in CLOSED_HINTS):
        return "marked closed"

    # Aggregator domains slip past Maps when the actual business has no site
    # of its own. They're not real prospects — drop them.
    if lead.website and is_aggregator(lead.website):
        return "website is a directory/social profile, not first-party"

    if require_website:
        if not lead.website:
            return "no first-party website"
    else:
        # Inverted mode — user asked for offline businesses, so a website
        # disqualifies (contact channel is still required via phone).
        if lead.website:
            return "has a website (user asked for offline businesses)"
        if not lead.phone:
            return "no website and no phone — uncontactable"

    if lead.rating is not None and lead.rating < 2.5 and (lead.reviews or 0) >= 10:
        return "rating below 2.5 with sufficient reviews"
    return None


def score_lead(lead: ScrapedLead) -> tuple[int, dict[str, bool]]:
    """Return (0-100 score, signal flags).

    Scoring philosophy: we want leads that are reachable AND on-target AND
    look like established businesses. Each axis tops out so a single signal
    can't carry the score.
    """
    score = 0
    signals: dict[str, bool] = {}

    if lead.name and len(lead.name.strip()) > 2:
        score += 4
        signals["has_name"] = True

    # Reachability — multi-channel rewarded
    if lead.website:
        score += 22
        signals["own_website"] = True
    if lead.phone:
        score += 10
        signals["has_phone"] = True
    if lead.email:
        score += 14
        signals["has_email"] = True
    socials = lead.social_links or {}
    if socials:
        score += min(8, 2 + 2 * len(socials))
        signals["has_socials"] = True

    # Locality
    if lead.address:
        score += 6
        signals["has_address"] = True
        if lead.location:
            loc_tokens = [
                t.strip().lower()
                for t in lead.location.replace(",", " ").split()
                if len(t.strip()) > 1
            ]
            addr_l = lead.address.lower()
            if any(t in addr_l for t in loc_tokens):
                score += 8
                signals["location_match"] = True

    # Niche fit
    if lead.category and lead.niche:
        cat_l = lead.category.lower()
        niche_tokens = [t for t in lead.niche.lower().split() if len(t) > 2]
        if any(t in cat_l for t in niche_tokens):
            score += 12
            signals["category_match"] = True

    # Reputation — established beats bare-minimum
    if lead.rating is not None:
        if lead.rating >= 4.0:
            score += 10
            signals["rating_strong"] = True
        elif lead.rating >= 3.0:
            score += 5

    if lead.reviews is not None:
        if lead.reviews >= 100:
            score += 10
            signals["reviews_high"] = True
        elif lead.reviews >= 25:
            score += 6
        elif lead.reviews >= 10:
            score += 3

    # Depth — extra context that proves it's a real business
    if lead.description:
        score += 3
        signals["has_description"] = True
    if lead.hours:
        score += 2
        signals["has_hours"] = True

    return min(score, 100), signals


def filter_and_score(
    leads: list[ScrapedLead],
    min_score: int = 35,
    *,
    require_website: bool = True,
) -> tuple[list[ScrapedLead], list[ScrapedLead]]:
    """Annotate leads with score/signals/rejection_reason.

    Returns (kept, dropped). kept is sorted by quality_score desc.
    """
    kept: list[ScrapedLead] = []
    dropped: list[ScrapedLead] = []
    for lead in leads:
        reason = rejection_reason(lead, require_website=require_website)
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
