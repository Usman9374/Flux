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

The scorer here is a strict rewrite of the previous additive scheme. We assign
a tier (A/B/C) based on the *kind* of signals present, not a raw point sum,
and the user sees the tier in the UI. Hard rejects drop the lead before
scoring — quality-over-volume.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from .niche_taxonomy import synonyms_for
from .types import ScrapedLead

# Bare platform / aggregator hosts — pure platform pages are blocked,
# but customer subdomains/path-deep pages are fine. The check is implemented
# in `is_aggregator` so that `*.wixsite.com/business-name` and
# `business.squarespace.com` are NOT mistaken for the platform itself.
AGGREGATOR_DOMAINS = {
    "facebook.com", "fb.com", "m.facebook.com", "instagram.com",
    "linkedin.com", "twitter.com", "x.com", "tiktok.com", "pinterest.com",
    "youtube.com", "youtu.be",
    "yelp.com", "yellowpages.com", "yp.com", "foursquare.com",
    "tripadvisor.com", "tripadvisor.co.uk", "opentable.com", "zomato.com",
    "thumbtack.com", "houzz.com", "angi.com", "homeadvisor.com",
    "google.com", "maps.google.com", "g.co", "goo.gl",
    "business.site", "sites.google.com",
    "blogspot.com", "wordpress.com",
    "indeed.com", "glassdoor.com", "ziprecruiter.com",
    "trustpilot.com", "bbb.org", "manta.com", "bizapedia.com",
    "crunchbase.com", "zoominfo.com", "rocketreach.co",
}

# These are SaaS site-builders. We only block the bare platform — a customer
# subdomain or a path-deep URL is a real business homepage. See `is_aggregator`.
PLATFORM_HOSTS = {
    "wix.com", "wixsite.com", "squarespace.com", "weebly.com",
    "godaddysites.com", "site.com", "shopify.com", "myshopify.com",
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

# Toll-free / well-known spam ranges (US/CA). Conservative — only obviously
# non-direct lines are dropped. Add ranges per region as we encounter them.
_SPAM_PHONE_PREFIXES = (
    "+1800", "+1888", "+1877", "+1866", "+1855", "+1844", "+1833",
    "1-800-", "1-888-", "1-877-", "1-866-", "1-855-", "1-844-",
)

# Generic mailboxes — present but lower-value than a named address.
_GENERIC_EMAIL_LOCALS = ("info", "contact", "hello", "support", "office", "admin", "team", "mail")

# Common stop words removed when comparing niche-vs-category.
_STOP_WORDS = {
    "the", "a", "an", "in", "on", "of", "and", "or", "to", "for",
    "with", "without", "near", "around", "best", "top", "good", "cheap",
    "services", "service", "company", "companies", "business", "businesses",
    "shop", "shops", "store", "stores",
}


@dataclass(frozen=True)
class QueryIntent:
    cleaned_niche: str          # niche with qualifier phrases stripped
    require_website: bool       # True ⇒ reject leads with no website (default)
    mode_label: str             # human-readable summary for UI


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
    matched_no_website = False
    for pat in _NO_WEBSITE_PATTERNS:
        if re.search(pat, n, flags=re.IGNORECASE):
            require_website = False
            matched_no_website = True
            n = re.sub(pat, " ", n, flags=re.IGNORECASE)

    # Strip whitespace and common punctuation. Em-dash and en-dash are not
    # handled by str.strip's character class — handle them explicitly.
    cleaned = re.sub(r"[\s,.\-—–]+$", "", re.sub(r"^[\s,.\-—–]+", "", re.sub(r"\s+", " ", n)))
    if not cleaned:
        cleaned = niche

    if matched_no_website:
        label = "Mode: offline businesses only (no first-party website)"
    else:
        label = "Mode: businesses with first-party websites"

    return QueryIntent(
        cleaned_niche=cleaned,
        require_website=require_website,
        mode_label=label,
    )


def _hostname(url: str | None) -> str | None:
    if not url:
        return None
    try:
        h = urlparse(url if url.startswith("http") else f"https://{url}").hostname or ""
        return h.lower().lstrip(".")
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).debug("hostname parse failed for %r: %s", url, e)
        return None


def _path_of(url: str | None) -> str:
    if not url:
        return ""
    try:
        return (urlparse(url if url.startswith("http") else f"https://{url}").path or "").rstrip("/")
    except Exception:  # noqa: BLE001
        return ""


def is_aggregator(url: str | None) -> bool:
    """Return True if `url` is a directory/social profile, NOT a real homepage.

    Platform builders (Wix, Squarespace) get a path-depth check: bare
    `wixsite.com` is the platform, `mybiz.wixsite.com/mybiz` is the customer.
    Only the former is treated as an aggregator. This was the cause of
    legitimate small-business sites being silently dropped in v1.
    """
    h = _hostname(url)
    if not h:
        return False
    h = h.removeprefix("www.")

    # Hard list — these are pure directories / social profiles
    if any(h == d or h.endswith("." + d) for d in AGGREGATOR_DOMAINS):
        return True

    # Platform builders — only reject the platform homepage itself
    for plat in PLATFORM_HOSTS:
        if h == plat or h == "www." + plat:
            return True
        if h.endswith("." + plat):
            # Customer subdomain (e.g. mybiz.wixsite.com). Real business unless
            # the path is the bare site root. Accept it.
            path = _path_of(url)
            if not path or path == "/":
                # Bare platform subdomain with no path — most likely the
                # platform's default landing. Keep as aggregator.
                return False
            return False
    return False


def _tokens(text: str | None) -> list[str]:
    if not text:
        return []
    parts = re.findall(r"[A-Za-z]{3,}", text.lower())
    return [t for t in parts if t not in _STOP_WORDS]


def category_matches_niche(category: str | None, niche: str | None) -> bool:
    """True if any meaningful niche token appears in the category string.

    Three layers, cheapest first:
      1. Taxonomy synonyms — "dentist" niche accepts "dental clinic"
         category and vice versa, even when the strings don't share a
         token.
      2. Exact substring of any niche token.
      3. Prefix-stem (first 4 chars) so "dental" matches "dentist", etc.

    Without the taxonomy layer, Maps' "Indian restaurant" category gets
    rejected by a "restaurants in Islamabad" niche — exactly the kind of
    over-strict reject that causes the empty-result complaint.
    """
    if not category or not niche:
        return False
    cat = category.lower()

    # Layer 1: taxonomy synonyms.
    for syn in synonyms_for(niche):
        if syn and syn in cat:
            return True

    # Layer 2/3: token + stem.
    cat_tokens = _tokens(category)
    for nt in _tokens(niche):
        if nt in cat:
            return True
        stem = nt[:4] if len(nt) >= 5 else nt
        if any(ct.startswith(stem) or stem in ct for ct in cat_tokens):
            return True
    return False


def location_matches(address: str | None, location: str | None) -> bool:
    if not address or not location:
        return False
    addr = address.lower()
    return any(t in addr for t in _tokens(location))


def _is_spam_phone(phone: str | None) -> bool:
    if not phone:
        return False
    p = re.sub(r"[^\d+]", "", phone)
    return any(p.startswith(prefix.replace("-", "").replace(" ", "")) for prefix in _SPAM_PHONE_PREFIXES)


def _is_named_email(email: str | None) -> bool:
    if not email:
        return False
    local = email.split("@", 1)[0].lower()
    return local not in _GENERIC_EMAIL_LOCALS


def rejection_reason(lead: ScrapedLead, *, require_website: bool = True) -> str | None:
    """Hard rejects — disqualifies the lead before scoring.

    Order matters: we check name/closed/aggregator first because those are
    cheap and definitive. Niche/location overlap is checked next; these are
    required, not optional. The "no contact channel at all" check is last so
    `rejection_reason` for an offline-mode lead surfaces something useful.
    """
    name = (lead.name or "").strip()
    if len(name) < 3:
        return "name missing or too short"
    lname = name.lower()
    if any(h in lname for h in CLOSED_HINTS):
        return "marked closed"

    if lead.website and is_aggregator(lead.website):
        return "website is a directory/social profile, not first-party"

    # Niche alignment. If the source already proved the match (OSM tag),
    # trust it; otherwise check category text, then last-resort the
    # business name. Only reject when *all* paths fail.
    if lead.niche:
        sigs = lead.signals or {}
        source_proven = sigs.get("category_match_source") in ("osm_tag",)
        if not source_proven:
            cat_ok = lead.category and category_matches_niche(lead.category, lead.niche)
            name_ok = category_matches_niche(lead.name, lead.niche)
            if lead.category and not cat_ok and not name_ok:
                return f"category {lead.category!r} doesn't match niche {lead.niche!r}"

    # Location alignment. We accept the lead if any of these hold:
    #   - the address contains a token from the queried location, or
    #   - the lead came in from inside the geocoded bounding box
    #     (signals.location_match_geo set by the source), or
    #   - we don't have an address at all (common for OSM nodes / DDG
    #     candidates) — better to keep the lead than silently drop it.
    if lead.location and lead.address:
        sigs = lead.signals or {}
        if not sigs.get("location_match_geo") and not location_matches(
            lead.address, lead.location
        ):
            return f"address doesn't include any token from location {lead.location!r}"

    if require_website:
        if not lead.website:
            return "no first-party website"
    else:
        # Inverted mode — user asked for offline businesses, so a verified
        # website disqualifies. We allow possible/unverified websites through
        # (they're labelled in signals); see runner verification step.
        if lead.website and (lead.signals or {}).get("website_confirmed"):
            return "has a verified first-party website (user asked for offline businesses)"

    # Must have at least one contactable channel.
    has_contact = bool(lead.phone) or bool(lead.email) or bool(lead.website)
    if not has_contact:
        return "no contact channel (no website, phone, or email)"

    if lead.phone and _is_spam_phone(lead.phone):
        return "phone matches known toll-free / spam range"

    if lead.rating is not None and lead.rating < 2.5 and (lead.reviews or 0) >= 10:
        return "rating below 2.5 with sufficient reviews"
    return None


def score_lead(lead: ScrapedLead, *, require_website: bool = True) -> tuple[int, str, dict[str, bool]]:
    """Return (0-100 score, tier letter, signal flags).

    Scoring philosophy: each axis caps. A single strong signal can't carry the
    score. Tier is derived from which axes are filled, not just the raw sum —
    so a "verified website + phone + matched category + good reputation" lead
    is solidly A even if a few minor signals are absent.
    """
    score = 0
    signals: dict[str, bool] = {}

    # Reachability — first-party website is the biggest single signal in
    # require_website mode. In offline mode, the website axis flips off.
    if lead.website and not is_aggregator(lead.website):
        if require_website:
            score += 25
            signals["own_website"] = True
        else:
            # Should already be hard-rejected by rejection_reason in this mode
            # but keep the flag for transparency in the UI.
            signals["website_unverified"] = True

    if lead.phone and not _is_spam_phone(lead.phone):
        score += 15
        signals["has_phone"] = True

    if lead.email:
        if _is_named_email(lead.email):
            score += 20
            signals["has_named_email"] = True
        else:
            score += 12
            signals["has_generic_email"] = True

    socials = lead.social_links or {}
    valid_socials = sum(1 for v in socials.values() if v)
    if valid_socials >= 2:
        score += 4
        signals["has_socials"] = True

    # Niche fit. If the source proved the match (OSM tag), credit it
    # without re-running the text comparison. Otherwise check category
    # text and the name as fallbacks.
    src_matched = (lead.signals or {}).get("category_match_source") in ("osm_tag",)
    if lead.niche and (
        src_matched
        or category_matches_niche(lead.category, lead.niche)
        or category_matches_niche(lead.name, lead.niche)
    ):
        score += 15
        signals["category_match"] = True

    # Locality — required if the user gave one.
    if lead.location and (
        location_matches(lead.address, lead.location)
        or (lead.signals or {}).get("location_match_geo")
    ):
        score += 10
        signals["location_match"] = True

    # Reputation
    rating_ok = lead.rating is not None and lead.rating >= 4.0
    reviews_ok = (lead.reviews or 0) >= 25
    if rating_ok and reviews_ok:
        score += 8
        signals["rating_strong"] = True
    if (lead.reviews or 0) >= 100:
        score += 5
        signals["reviews_high"] = True

    # Depth signals — small but they tip a B into an A.
    if lead.description and len(lead.description) >= 80:
        score += 3
        signals["has_description"] = True
    if lead.hours:
        score += 2
        signals["has_hours"] = True

    score = min(score, 100)
    tier = _tier_for(lead, score, signals, require_website=require_website)
    return score, tier, signals


def _tier_for(
    lead: ScrapedLead,
    score: int,
    signals: dict[str, bool],
    *,
    require_website: bool,
) -> str:
    """Derive A/B/C/D tier from the signal mix, not just the raw score.

    Rules (v2 of LEAD_GENERATION_FIX.md §5):
      A:  website + phone + email + category + reputation + location.
      B:  website + (phone or email) + category + location.
      C:  contactable + category + location, but missing some signals.
      D:  no usable signal mix at all — dropped.

    The numeric cliff is 25 (down from 40 in v1). v1's 40-cliff dropped
    most OSM-only leads — name + phone + tag-matched category + bbox
    location scored exactly 40, which is too thin a margin. We let tier
    decide and only D-tier gets removed.
    """
    if score < 25:
        return "D"

    has_phone = signals.get("has_phone", False)
    has_email = signals.get("has_named_email", False) or signals.get("has_generic_email", False)
    has_category = signals.get("category_match", False)
    has_location = signals.get("location_match", False)
    has_reputation = signals.get("rating_strong", False) or signals.get("reviews_high", False)

    if require_website:
        has_website = signals.get("own_website", False)
        if has_website and has_phone and has_email and has_category and has_location and has_reputation:
            return "A"
        if has_website and (has_phone or has_email) and has_category and has_location:
            return "B"
        return "C"
    else:
        # Offline mode — A is phone + email + category + reputation
        if has_phone and has_email and has_category and has_reputation:
            return "A"
        if has_phone and has_category and has_location:
            return "B"
        return "C"


def confidence_for(lead: ScrapedLead) -> float:
    """How sure we are about the lead's *contact info*.

    Independent of score. Reflects how many corroborating sources agree.
    """
    sources = set(lead.sources or [])
    if not sources:
        sources = {lead.source} if lead.source else set()

    base = 0.4 if sources else 0.0
    # Each additional independent source adds 0.2, capped at 1.0.
    bonus = 0.2 * max(0, len(sources) - 1)
    # Confirmed website (search verifier or domain probe agreed with Maps) +0.2.
    if (lead.signals or {}).get("website_confirmed"):
        bonus += 0.2
    if (lead.signals or {}).get("phone_verified"):
        bonus += 0.1
    return round(min(1.0, base + bonus), 2)


def filter_and_score(
    leads: list[ScrapedLead],
    min_score: int = 40,
    *,
    require_website: bool = True,
) -> tuple[list[ScrapedLead], list[ScrapedLead]]:
    """Annotate leads with score/tier/signals/confidence/rejection_reason.

    Returns (kept, dropped). kept is sorted by quality_score desc, then tier.
    """
    kept: list[ScrapedLead] = []
    dropped: list[ScrapedLead] = []
    seen_phones: set[str] = set()
    seen_domains: set[str] = set()

    for lead in leads:
        reason = rejection_reason(lead, require_website=require_website)
        if reason:
            lead.rejection_reason = reason
            dropped.append(lead)
            continue

        # De-dupe across this batch — same phone or same domain ⇒ drop.
        phone_key = re.sub(r"\D", "", lead.phone or "")[-10:] if lead.phone else None
        domain = _hostname(lead.website)
        domain = domain.removeprefix("www.") if domain else None

        if phone_key and phone_key in seen_phones:
            lead.rejection_reason = "duplicate phone of earlier lead"
            dropped.append(lead)
            continue
        if domain and domain in seen_domains:
            lead.rejection_reason = "duplicate domain of earlier lead"
            dropped.append(lead)
            continue

        score, tier, signals = score_lead(lead, require_website=require_website)
        lead.quality_score = score
        lead.tier = tier
        # Merge signals — preserve any added by upstream (website_confirmed, etc.)
        merged_signals = dict(lead.signals or {})
        merged_signals.update(signals)
        lead.signals = merged_signals
        lead.confidence = confidence_for(lead)

        if score < min_score or tier == "D":
            lead.rejection_reason = f"quality score {score} below threshold {min_score}"
            dropped.append(lead)
            continue

        if phone_key:
            seen_phones.add(phone_key)
        if domain:
            seen_domains.add(domain)
        kept.append(lead)

    # Sort: higher tier first (A > B > C), then higher score within tier.
    tier_rank = {"A": 0, "B": 1, "C": 2, "D": 3, None: 4}
    kept.sort(key=lambda l: (tier_rank.get(l.tier, 4), -(l.quality_score or 0)))
    return kept, dropped
