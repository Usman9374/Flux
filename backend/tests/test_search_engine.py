"""Tests for the DuckDuckGo HTML SERP parser and the homepage scorer.

These do not hit the network. We feed a saved snippet of DDG HTML into
`parse_ddg_results` and assert the right URLs come out, then exercise the
homepage scorer used by `verify_website` for a couple of canned cases.
"""
from __future__ import annotations

import pytest

from app.scraper.sources.search_engine import (
    SearchResult,
    _decode_ddg_url,
    _looks_like_homepage,
    _result_title_to_business_name,
    parse_ddg_results,
)


# A trimmed fixture from a real DDG HTML SERP. Keeps the relevant anchors,
# strips the JS/CSS so the test is readable.
_DDG_HTML = """
<div class="results">
  <div class="result results_links">
    <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fmonal.com.pk%2F&rut=abc">
      Monal Restaurant — Islamabad
    </a>
    <a class="result__snippet" href="https://monal.com.pk/">
      Pakistan's iconic hilltop restaurant in Islamabad — book a table now.
    </a>
  </div>
  <div class="result results_links">
    <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Ftripadvisor.com%2FRestaurant_Monal&rut=abc">
      Monal Restaurant - Reviews | Tripadvisor
    </a>
    <a class="result__snippet" href="x">Reviews and photos…</a>
  </div>
  <div class="result results_links">
    <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Ffacebook.com%2Fmonal&rut=abc">
      Monal | Facebook
    </a>
    <a class="result__snippet" href="x">Official Facebook page…</a>
  </div>
</div>
"""


def test_parse_ddg_results_extracts_decoded_urls():
    results = parse_ddg_results(_DDG_HTML, limit=5)
    assert len(results) == 3
    urls = [r.url for r in results]
    assert "https://monal.com.pk/" in urls
    assert any("tripadvisor" in u for u in urls)
    assert any("facebook.com" in u for u in urls)


def test_parse_ddg_results_titles_are_decoded():
    results = parse_ddg_results(_DDG_HTML, limit=5)
    assert "Monal Restaurant" in results[0].title


def test_parse_ddg_results_handles_empty_html():
    assert parse_ddg_results("", limit=5) == []
    assert parse_ddg_results("<html></html>", limit=5) == []


def test_decode_ddg_url_unwraps_l_redirect():
    encoded = "//duckduckgo.com/l/?uddg=https%3A%2F%2Facme.com%2Fpath&rut=x"
    assert _decode_ddg_url(encoded) == "https://acme.com/path"


def test_decode_ddg_url_passes_through_normal_url():
    assert _decode_ddg_url("https://example.com/") == "https://example.com/"


# ---------------- _looks_like_homepage ----------------


def test_looks_like_homepage_high_for_matching_domain():
    r = SearchResult(
        url="https://acmedental.com/",
        title="Acme Dental — Family Dentistry",
        snippet="Acme Dental in Austin offers…",
    )
    assert _looks_like_homepage(r, "Acme Dental") >= 0.7


def test_looks_like_homepage_zero_for_aggregator():
    r = SearchResult(
        url="https://facebook.com/AcmeDental",
        title="Acme Dental | Facebook",
        snippet="",
    )
    assert _looks_like_homepage(r, "Acme Dental") == 0.0


def test_looks_like_homepage_low_for_unrelated_domain():
    r = SearchResult(
        url="https://news-site.com/article/dentistry",
        title="Top dentists in 2024",
        snippet="",
    )
    assert _looks_like_homepage(r, "Acme Dental") < 0.45


# ---------------- title → business name heuristic ----------------


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Acme Dental — Family Dentistry · Austin", "Acme Dental"),
        ("Monal Restaurant | Islamabad", "Monal Restaurant"),
        ("OX and Grill - Karachi - Steakhouse", "OX and Grill"),
        ("", None),
    ],
)
def test_result_title_to_business_name(title, expected):
    assert _result_title_to_business_name(title) == expected
