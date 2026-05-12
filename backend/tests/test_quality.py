"""Tests for the lead-quality scorer and intent parser.

These are pure-Python tests with no I/O. They cover the contract in
LEAD_GENERATION_FIX.md §4 (intent parsing), §5 (tier boundaries), and §6
(aggregator-vs-platform-vs-customer-subdomain).
"""
from __future__ import annotations

import pytest

from app.scraper.quality import (
    QueryIntent,
    category_matches_niche,
    filter_and_score,
    is_aggregator,
    location_matches,
    parse_intent,
    rejection_reason,
    score_lead,
)
from app.scraper.types import ScrapedLead


# ---------------- parse_intent ----------------


@pytest.mark.parametrize(
    "niche,expected_require,expected_cleaned",
    [
        ("dental clinic", True, "dental clinic"),
        ("restaurants in Islamabad without a website", False, "restaurants in Islamabad"),
        ("dentists without website", False, "dentists"),
        ("law firm with no website", False, "law firm with"),
        ("plumbers — offline only", False, "plumbers"),
        ("cafés that don't have a website", False, "cafés that"),
        # Confirms a niche-clean of empty falls back to the original.
        ("offline only", False, "offline only"),
    ],
)
def test_parse_intent(niche, expected_require, expected_cleaned):
    intent = parse_intent(niche)
    assert isinstance(intent, QueryIntent)
    assert intent.require_website is expected_require
    assert intent.cleaned_niche == expected_cleaned


def test_parse_intent_mode_label_reflects_choice():
    online = parse_intent("dentists")
    offline = parse_intent("dentists without website")
    assert "first-party websites" in online.mode_label
    assert "offline" in offline.mode_label


# ---------------- is_aggregator ----------------


@pytest.mark.parametrize(
    "url,expected",
    [
        # Pure directories / socials — blocked.
        ("https://facebook.com/somepage", True),
        ("https://www.yelp.com/biz/some-restaurant", True),
        ("https://tripadvisor.com/Restaurant_Review-foo.html", True),
        ("https://google.com/maps/place/foo", True),
        # Real businesses — kept.
        ("https://acmehvac.com", False),
        ("https://www.example-restaurant.com/menu", False),
        # Platform customer subdomains — kept (fix from v1).
        ("https://mybiz.wixsite.com/mybiz", False),
        ("https://mybiz.squarespace.com/", False),
        ("https://biz.shopify.com/products/foo", False),
        # Bare platforms — blocked.
        ("https://wixsite.com", True),
        ("https://wix.com", True),
        ("https://squarespace.com", True),
        # Empty / malformed inputs — never throw.
        (None, False),
        ("", False),
        ("not-a-url", False),
    ],
)
def test_is_aggregator(url, expected):
    assert is_aggregator(url) is expected


# ---------------- category / location matching ----------------


def test_category_matches_niche_uses_tokenization():
    assert category_matches_niche("Dentist", "dental clinic") is True
    assert category_matches_niche("Dental clinic", "dentists in lahore") is True
    # Stop words don't trigger a match by themselves.
    assert category_matches_niche("Restaurant", "the best in town") is False


def test_location_matches_token_based():
    assert location_matches("Plot 12, F-7 Markaz, Islamabad", "Islamabad") is True
    assert location_matches("San Francisco, CA", "Austin, TX") is False
    assert location_matches(None, "Lahore") is False


# ---------------- rejection_reason ----------------


def make_lead(**overrides) -> ScrapedLead:
    base = dict(
        name="Acme Dental Clinic",
        website="https://acmedental.com",
        phone="+1 555 1234567",
        email="contact@acmedental.com",
        niche="dental clinic",
        location="Austin, TX",
        address="123 Main St, Austin, TX",
        category="Dental clinic",
        rating=4.5,
        reviews=120,
    )
    base.update(overrides)
    return ScrapedLead(**base)


def test_rejection_reason_blocks_aggregator_website():
    lead = make_lead(website="https://facebook.com/acme")
    assert rejection_reason(lead) == "website is a directory/social profile, not first-party"


def test_rejection_reason_blocks_no_website_when_required():
    lead = make_lead(website=None)
    assert rejection_reason(lead, require_website=True) == "no first-party website"


def test_rejection_reason_blocks_verified_website_in_offline_mode():
    lead = make_lead()
    lead.signals = {"website_confirmed": True}
    assert "verified first-party website" in (rejection_reason(lead, require_website=False) or "")


def test_rejection_reason_allows_unverified_website_in_offline_mode():
    lead = make_lead(website=None, phone="+1 555 1234567")
    lead.signals = {"possible_website": "https://maybe.com", "website_unverified": True}
    assert rejection_reason(lead, require_website=False) is None


def test_rejection_reason_blocks_low_rating_with_many_reviews():
    lead = make_lead(rating=1.8, reviews=30)
    assert "rating below 2.5" in (rejection_reason(lead) or "")


def test_rejection_reason_blocks_category_mismatch():
    # Coffee shop returned for a "dental clinic" query — must be dropped.
    lead = make_lead(name="Sunny Coffee", category="Coffee shop")
    reason = rejection_reason(lead)
    assert reason and "doesn't match niche" in reason


def test_rejection_reason_allows_niche_in_name_when_no_category():
    # Maps sometimes returns no category but the name carries the niche.
    lead = make_lead(category=None, name="Smile Dental")
    assert rejection_reason(lead) is None


def test_rejection_reason_blocks_location_mismatch():
    lead = make_lead(address="456 Market St, San Francisco, CA")
    reason = rejection_reason(lead)
    assert reason and "doesn't include any token from location" in reason


# ---------------- score_lead / tiers ----------------


def test_score_lead_assigns_tier_a_for_full_signal_set():
    lead = make_lead()
    score, tier, signals = score_lead(lead, require_website=True)
    assert tier == "A"
    assert score >= 90
    for key in ("own_website", "has_phone", "category_match", "location_match", "rating_strong"):
        assert signals[key] is True


def test_score_lead_drops_to_b_without_reputation():
    lead = make_lead(rating=None, reviews=None)
    score, tier, _ = score_lead(lead, require_website=True)
    assert tier == "B"
    assert 65 <= score < 90


def test_score_lead_drops_to_c_without_category_or_location():
    # Site + phone + email present but category and location both missing
    # ⇒ falls out of B (which requires both) and lands in C.
    lead = make_lead(category=None, address=None)
    score, tier, _ = score_lead(lead, require_website=True)
    assert tier == "C"


def test_score_lead_offline_mode_a_tier_requires_phone_email_reputation():
    lead = make_lead(website=None, email="info@dentalcare.com")
    score, tier, signals = score_lead(lead, require_website=False)
    assert tier == "A"
    # Website axis is off in offline mode.
    assert "own_website" not in signals


def test_score_lead_spam_phone_isnt_counted():
    # Toll-free number is filtered.
    lead = make_lead(phone="+1 800 555 1234", email=None)
    score, tier, signals = score_lead(lead, require_website=True)
    assert "has_phone" not in signals


# ---------------- filter_and_score (dedupe + sort) ----------------


def test_filter_and_score_dedupe_by_phone():
    a = make_lead(name="Acme A")
    b = make_lead(name="Acme B")  # same phone
    kept, dropped = filter_and_score([a, b], min_score=0)
    assert len(kept) == 1
    assert any("duplicate phone" in (l.rejection_reason or "") for l in dropped)


def test_filter_and_score_dedupe_by_domain():
    a = make_lead(name="Acme HQ", website="https://shared.com", phone="+1 555 1111")
    b = make_lead(name="Acme Branch", website="https://shared.com", phone="+1 555 2222")
    kept, dropped = filter_and_score([a, b], min_score=0)
    assert len(kept) == 1
    assert any("duplicate domain" in (l.rejection_reason or "") for l in dropped)


def test_filter_and_score_sorts_a_before_c():
    a_tier = make_lead()  # tier A
    c_tier = make_lead(
        name="Other Clinic",
        phone="+1 555 9999",
        email=None,
        website="https://other.com",
        rating=None,
        reviews=None,
    )
    kept, _ = filter_and_score([c_tier, a_tier], min_score=0)
    assert kept[0].name == a_tier.name
    assert kept[0].tier == "A"


def test_filter_and_score_drops_below_min_score():
    weak = make_lead(
        name="Marginal",
        website="https://marginal.com",
        phone=None,
        email=None,
        rating=None,
        reviews=None,
    )
    kept, dropped = filter_and_score([weak], min_score=60)
    assert weak in dropped
    assert weak.rejection_reason and "below threshold" in weak.rejection_reason


# ---------------- The "Serena Hotels" / "OX and Grill" regression ----------------


def test_chain_with_verified_website_rejected_from_offline_mode():
    """Reproduce the v1 bug: a chain that has a website but Maps didn't surface
    it slips into offline mode. With the new pipeline, the search verifier
    promotes the website and the lead is correctly dropped from `require_website=False`.
    """
    lead = ScrapedLead(
        name="OX and Grill",
        website=None,
        phone="+92 21 1234567",
        niche="restaurant",
        location="Karachi",
        category="Restaurant",  # matches the niche
        address="Clifton, Karachi",
    )
    # Simulate the verifier finding the chain's homepage with high confidence.
    lead.website = "https://oxandgrill.com"
    lead.signals = {"website_confirmed": True}
    reason = rejection_reason(lead, require_website=False)
    assert reason and "verified first-party website" in reason


def test_hotel_rejected_from_restaurant_query_regardless_of_website():
    """Serena Hotels for a "restaurant" query gets dropped on category mismatch
    even before the website verifier runs."""
    lead = ScrapedLead(
        name="Serena Hotels",
        website=None,
        phone="+92 51 287 4000",
        niche="restaurant",
        location="Islamabad",
        category="Hotel",
        address="Khayaban-e-Suhrwardy, Islamabad",
    )
    reason = rejection_reason(lead, require_website=False)
    assert reason and "doesn't match niche" in reason
