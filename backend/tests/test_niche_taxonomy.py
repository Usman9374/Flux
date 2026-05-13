"""Tests for the niche taxonomy mapper.

The taxonomy is the foundation of the OSM source — if niche → tag
matching breaks here, OSM Overpass falls back to slow free-text name
queries that return very little. Cover the most common niches the user
is expected to type.
"""
from __future__ import annotations

import pytest

from app.scraper.niche_taxonomy import match_niche, synonyms_for


@pytest.mark.parametrize(
    "niche,expected_canonical,expected_tag_first",
    [
        ("dental clinic", "dentist", ("amenity", "dentist")),
        ("dentists in lahore", "dentist", ("amenity", "dentist")),
        ("restaurants without a website", "restaurant", ("amenity", "restaurant")),
        ("Indian restaurant", "restaurant", ("amenity", "restaurant")),
        ("law firm", "lawyer", ("office", "lawyer")),
        ("attorney", "lawyer", ("office", "lawyer")),
        ("hair salon", "salon", ("shop", "hairdresser")),
        ("barbershop", "salon", ("shop", "hairdresser")),
        ("gym", "gym", ("leisure", "fitness_centre")),
        ("hotel", "hotel", ("tourism", "hotel")),
        ("real estate agency", "real_estate", ("office", "estate_agent")),
        ("roofing contractor", "roofer", ("craft", "roofer")),
        ("plumber", "plumber", ("craft", "plumber")),
        ("car dealership", "car_dealer", ("shop", "car")),
        ("auto repair", "auto_repair", ("shop", "car_repair")),
        ("pharmacy", "pharmacy", ("amenity", "pharmacy")),
        ("daycare", "daycare", ("amenity", "childcare")),
        ("yoga studio", "yoga", ("leisure", "fitness_centre")),
    ],
)
def test_match_niche_recognized(niche, expected_canonical, expected_tag_first):
    m = match_niche(niche)
    assert m is not None, f"expected match for {niche!r}"
    assert m.canonical == expected_canonical
    assert m.tags[0] == expected_tag_first


@pytest.mark.parametrize(
    "niche",
    [
        "underwater basket weaving studio",
        "qzxqzx services",
        "",
        None,
    ],
)
def test_match_niche_unknown_returns_none(niche):
    assert match_niche(niche) is None


def test_synonyms_for_returns_tokens_for_known_niche():
    syns = synonyms_for("dental clinic")
    assert "dental" in syns
    assert "dentist" in syns


def test_synonyms_for_unknown_returns_empty():
    assert synonyms_for("totally invented xyz") == ()
