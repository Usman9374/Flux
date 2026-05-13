"""Tests for the OSM source — Overpass JSON parsing + QL builder.

We don't hit the network here. Real Overpass + Nominatim integration is
tested by the acceptance run (LEAD_GENERATION_FIX.md §8). What we cover
here is the bits that *will* break if we're sloppy in code review:

  - QL builder includes the right tag clauses for known niches.
  - QL builder falls back to a name regex for unknown niches.
  - Element parser handles missing tags gracefully + dedupes.
"""
from __future__ import annotations

from app.scraper.niche_taxonomy import match_niche
from app.scraper.sources.osm import _build_overpass_ql, _parse_elements


def test_build_overpass_ql_uses_taxonomy_tags():
    bbox = (33.5, 33.8, 73.0, 73.3)  # Islamabad-ish
    ql = _build_overpass_ql(match_niche("dental clinic"), "dental clinic", bbox)
    assert '["amenity"="dentist"]' in ql
    assert '["healthcare"="dentist"]' in ql
    assert "(33.5,73.0,33.8,73.3)" in ql
    # Order: nodes, then ways, then relations — covers all three.
    assert ql.count("node[") >= 1
    assert ql.count("way[") >= 1
    assert ql.count("relation[") >= 1


def test_build_overpass_ql_falls_back_to_name_regex_for_unknown_niches():
    bbox = (40.0, 40.5, -74.0, -73.5)
    ql = _build_overpass_ql(None, "underwater basket weaving", bbox)
    assert '["name"~"underwater basket weaving",i]' in ql
    # No tag clauses
    assert '["amenity"=' not in ql


def test_build_overpass_ql_strips_unsafe_chars_from_name():
    bbox = (0.0, 1.0, 0.0, 1.0)
    ql = _build_overpass_ql(None, 'inject"breakout\\here', bbox)
    # Must not contain raw quote/backslash inside the regex literal.
    assert 'injectbreakouthere' in ql or 'inject' in ql
    assert '"breakout' not in ql


def _el(tags, *, type_="node", id_=1, lat=33.7, lon=73.1):
    return {"type": type_, "id": id_, "lat": lat, "lon": lon, "tags": tags}


def test_parse_elements_extracts_full_lead():
    elements = [
        _el({
            "name": "Smile Dental Clinic",
            "addr:housenumber": "12",
            "addr:street": "F-7 Markaz",
            "addr:city": "Islamabad",
            "addr:country": "PK",
            "phone": "+92 51 2345678",
            "contact:email": "info@smiledental.pk",
            "website": "https://smiledental.pk",
            "amenity": "dentist",
            "opening_hours": "Mo-Sa 09:00-21:00",
        })
    ]
    leads = _parse_elements(
        elements,
        niche_match=match_niche("dental clinic"),
        niche_text="dental clinic",
        location="Islamabad",
    )
    assert len(leads) == 1
    l = leads[0]
    assert l.name == "Smile Dental Clinic"
    assert l.website == "https://smiledental.pk"
    assert l.phone == "+92 51 2345678"
    assert l.email == "info@smiledental.pk"
    assert "Islamabad" in (l.address or "")
    assert l.hours == "Mo-Sa 09:00-21:00"
    assert l.source == "osm"
    assert "osm" in (l.sources or [])
    assert l.signals.get("category_match_source") == "osm_tag"
    assert l.signals.get("location_match_geo") is True


def test_parse_elements_skips_unnamed_and_dedupes():
    elements = [
        _el({"amenity": "restaurant"}, id_=1),  # no name → skipped
        _el({"name": "Cafe Foo", "amenity": "cafe", "addr:street": "Main St"}, id_=2),
        # Same name + street as id_=2 → deduped.
        _el({"name": "Cafe Foo", "amenity": "cafe", "addr:street": "Main St"}, id_=3),
        _el({"name": "Cafe Bar", "amenity": "cafe"}, id_=4),
    ]
    leads = _parse_elements(
        elements, niche_match=match_niche("cafe"), niche_text="cafe", location="Test"
    )
    names = [l.name for l in leads]
    assert names == ["Cafe Foo", "Cafe Bar"]


def test_parse_elements_normalizes_bare_domain_website():
    elements = [
        _el({"name": "Bare Domain Biz", "website": "example.com", "shop": "bakery"}),
    ]
    leads = _parse_elements(
        elements, niche_match=match_niche("bakery"), niche_text="bakery", location="X"
    )
    assert leads[0].website == "https://example.com"


def test_parse_elements_handles_partial_address():
    """A common OSM record: name + amenity + lat/lon, no addr:* tags."""
    elements = [
        _el({"name": "Streetside Stall", "amenity": "restaurant"}),
    ]
    leads = _parse_elements(
        elements, niche_match=match_niche("restaurant"),
        niche_text="restaurants", location="Karachi",
    )
    assert len(leads) == 1
    assert leads[0].address is None
    # Lead is still kept; the runner softens location_matches to allow this.
    assert leads[0].signals.get("location_match_geo") is True
