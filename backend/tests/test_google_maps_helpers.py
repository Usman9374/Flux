"""Tests for `google_maps.country_hint` — the location → `gl=` mapping.

Critical for stability: sending `gl=us` for a Pakistan/UK/India query causes
Google to serve the consent loop aggressively and rate-limit harder. We
verify the lookup picks up the country from a few representative location
strings.
"""
from __future__ import annotations

import pytest

from app.scraper.sources.google_maps import country_hint


@pytest.mark.parametrize(
    "location,expected",
    [
        ("Islamabad", "pk"),
        ("Islamabad, Pakistan", "pk"),
        ("Karachi, PK", "pk"),  # token fallback
        ("Lahore", "pk"),
        ("Mumbai", "in"),
        ("Mumbai, India", "in"),
        ("London", "gb"),
        ("London, United Kingdom", "gb"),
        ("Dublin, Ireland", "ie"),
        ("Toronto, Canada", "ca"),
        ("Sydney, Australia", "au"),
        ("Dubai, UAE", "ae"),
        ("Austin, TX", "us"),
        ("San Francisco, CA, USA", "us"),
        # Unknown defaults to US (matches Google's default).
        ("Atlantis", "us"),
        ("", "us"),
    ],
)
def test_country_hint(location, expected):
    assert country_hint(location) == expected
