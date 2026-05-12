"""DuckDuckGo HTML search source.

Two jobs:
  1. **Website verification** for the "without website" mode (§4 of
     LEAD_GENERATION_FIX.md). For each Maps lead with no website surfaced,
     run a query like `"{business name}" {location}` and look at the top
     non-aggregator results. If any look like a homepage that matches the
     business name fuzzily, the lead is reclassified as having a website.
  2. **Backfill** when Maps returns a thin or empty result set. We parse
     business-name candidates from the SERP itself.

No API key needed. We hit the HTML endpoint (`html.duckduckgo.com/html/`),
which is reasonably stable and rate-tolerant. If it ever changes shape, the
extractor degrades to an empty list rather than throwing.

Bing / SerpAPI are optional upgrades when a key is configured (see config.py)
but DuckDuckGo HTML covers the no-key default. We do NOT use Google directly
— it's much more aggressive about captchas for non-rendered fetches.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from html import unescape
from urllib.parse import parse_qs, quote_plus, urljoin, urlparse

import httpx

from ..quality import is_aggregator

log = logging.getLogger(__name__)

_DDG_HTML = "https://html.duckduckgo.com/html/"
_TIMEOUT_S = 8.0
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Confidence thresholds (§4 of LEAD_GENERATION_FIX.md)
_CONFIRM_THRESHOLD = 0.8     # ≥ 0.8 → "actually has a website" — reject from offline mode
_POSSIBLE_THRESHOLD = 0.5    # 0.5-0.8 → keep but flag as unverified
# Below 0.5 → ignore, treat as offline.


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str
    snippet: str


@dataclass(frozen=True)
class WebsiteVerdict:
    """Result of running a website-verification search for one business."""
    url: str | None       # the best-matching candidate, if any
    confidence: float     # 0.0 - 1.0
    sources_seen: int     # number of non-aggregator results we inspected


def _fuzzy(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _slug(name: str) -> str:
    """Strip the business name down to alphanumeric tokens for matching."""
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def _decode_ddg_url(href: str) -> str:
    """DDG wraps result URLs in `/l/?uddg=…`. Unwrap them."""
    if href.startswith("//"):
        href = "https:" + href
    if not href.startswith("http"):
        href = urljoin(_DDG_HTML, href)
    try:
        q = parse_qs(urlparse(href).query)
        if "uddg" in q:
            from urllib.parse import unquote
            return unquote(q["uddg"][0])
    except Exception as e:  # noqa: BLE001
        log.debug("ddg url decode failed for %r: %s", href, e)
    return href


# Extract result blocks from the HTML SERP. DDG HTML's anchors with class
# "result__a" are the result titles; we walk back to the surrounding block
# to grab the snippet.
_RESULT_BLOCK_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
    r'(.*?)(?=<a[^>]+class="result__a"|</div>\s*<!-- result -->|\Z)',
    re.IGNORECASE | re.DOTALL,
)
_SNIPPET_RE = re.compile(
    r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")


def _strip_tags(text: str) -> str:
    return unescape(_TAG_STRIP_RE.sub("", text or "")).strip()


def parse_ddg_results(html: str, *, limit: int = 10) -> list[SearchResult]:
    """Extract (url, title, snippet) tuples from a DuckDuckGo HTML SERP.

    Tolerant to layout drift — anything we can't parse becomes an empty list,
    not an exception.
    """
    out: list[SearchResult] = []
    for m in _RESULT_BLOCK_RE.finditer(html):
        href = _decode_ddg_url(m.group(1))
        title = _strip_tags(m.group(2))
        tail = m.group(3) or ""
        snippet_match = _SNIPPET_RE.search(tail)
        snippet = _strip_tags(snippet_match.group(1)) if snippet_match else ""
        if not href.startswith("http"):
            continue
        out.append(SearchResult(url=href, title=title, snippet=snippet))
        if len(out) >= limit:
            break
    return out


async def _fetch_html(client: httpx.AsyncClient, url: str, *, params: dict | None = None) -> str | None:
    try:
        r = await client.get(url, params=params, timeout=_TIMEOUT_S, follow_redirects=True)
    except Exception as e:  # noqa: BLE001
        log.warning("search fetch failed %s: %s", url, e)
        return None
    if r.status_code >= 400:
        log.warning("search returned HTTP %s for %s", r.status_code, url)
        return None
    return r.text


async def ddg_search(client: httpx.AsyncClient, query: str, *, limit: int = 10) -> list[SearchResult]:
    """Run a single DuckDuckGo HTML query and return up to `limit` results."""
    html = await _fetch_html(client, _DDG_HTML, params={"q": query})
    if not html:
        return []
    return parse_ddg_results(html, limit=limit)


def _looks_like_homepage(result: SearchResult, business_name: str) -> float:
    """Return a 0-1 score for "this result is the business's homepage"."""
    if is_aggregator(result.url):
        return 0.0

    host = urlparse(result.url).hostname or ""
    host = host.removeprefix("www.")
    if not host:
        return 0.0

    # Path depth — bare homepage scores higher than a /products/x deep link.
    path = (urlparse(result.url).path or "/").rstrip("/")
    depth = len([p for p in path.split("/") if p])
    depth_score = 1.0 if depth == 0 else 0.85 if depth == 1 else 0.6 if depth == 2 else 0.4

    # Name vs domain ratio.
    biz = _slug(business_name)
    domain_root = host.split(".")[0]
    name_in_domain = max(_fuzzy(biz, domain_root), _fuzzy(biz, host.replace(".", " ")))
    name_in_title = _fuzzy(biz, _slug(result.title))

    # Title containing the business name verbatim is very strong evidence.
    contains = 1.0 if biz and biz in _slug(result.title) else 0.0

    score = (0.45 * name_in_domain) + (0.35 * name_in_title) + (0.10 * contains) + (0.10 * depth_score)
    return round(min(1.0, score), 3)


async def verify_website(
    client: httpx.AsyncClient,
    business_name: str,
    location: str | None,
) -> WebsiteVerdict:
    """Run a SERP query and return the most likely homepage + confidence.

    Used to confirm or refute the "has no website" verdict from Maps. See §4
    of LEAD_GENERATION_FIX.md.
    """
    if not business_name:
        return WebsiteVerdict(url=None, confidence=0.0, sources_seen=0)

    q = f'"{business_name}"'
    if location:
        q += f" {location}"
    results = await ddg_search(client, q, limit=10)
    if not results:
        return WebsiteVerdict(url=None, confidence=0.0, sources_seen=0)

    # Inspect the top 5 non-aggregator results. Pick the highest-confidence
    # homepage match.
    inspected = 0
    best: tuple[float, str | None] = (0.0, None)
    for r in results[:8]:
        if is_aggregator(r.url):
            continue
        inspected += 1
        s = _looks_like_homepage(r, business_name)
        if s > best[0]:
            best = (s, r.url)
        if inspected >= 5:
            break

    return WebsiteVerdict(url=best[1], confidence=best[0], sources_seen=inspected)


def _result_title_to_business_name(title: str) -> str | None:
    """Heuristic: clean a SERP title down to a probable business name.

    DDG titles often look like "Business Name - Tagline · Location". We split
    on common separators and keep the longest meaningful left chunk.
    """
    if not title:
        return None
    parts = re.split(r"\s*[\|–—·\-:•]\s*", title)
    parts = [p.strip() for p in parts if p and len(p.strip()) >= 3]
    if not parts:
        return None
    # The first part is usually the business name on most SERPs.
    candidate = parts[0]
    # Drop trailing "in {city}", "near you" etc.
    candidate = re.sub(r"\s+(?:in|near|at|on|of)\s+.+$", "", candidate, flags=re.IGNORECASE)
    candidate = candidate.strip(' "')
    if len(candidate) < 3:
        return None
    return candidate


async def backfill_candidates(
    client: httpx.AsyncClient,
    niche: str,
    location: str,
    *,
    limit: int = 10,
) -> list[dict]:
    """Pull a thin list of candidate businesses from a SERP query.

    Used when Maps returns < N results. Each candidate has `name`, `website`
    (the SERP result domain), and a `source = "duckduckgo"` tag. The caller
    is expected to enrich + score them like any other lead.
    """
    q = f"{niche} in {location}"
    results = await ddg_search(client, q, limit=limit * 2)
    out: list[dict] = []
    seen_hosts: set[str] = set()
    for r in results:
        if is_aggregator(r.url):
            continue
        host = (urlparse(r.url).hostname or "").lower().removeprefix("www.")
        if not host or host in seen_hosts:
            continue
        seen_hosts.add(host)
        name = _result_title_to_business_name(r.title)
        if not name:
            continue
        # Reconstruct a clean homepage URL (drop any path/query so enrichment
        # hits the front page first).
        homepage = f"{urlparse(r.url).scheme or 'https'}://{host}"
        out.append({
            "name": name,
            "website": homepage,
            "snippet": r.snippet,
            "source": "duckduckgo",
        })
        if len(out) >= limit:
            break
    return out


async def verify_many(
    business_names: list[tuple[str, str | None]],
    *,
    concurrency: int = 4,
) -> list[WebsiteVerdict]:
    """Run verify_website for many leads in parallel. Order is preserved."""
    if not business_names:
        return []
    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(headers=_HEADERS, http2=False) as client:
        async def worker(name: str, location: str | None) -> WebsiteVerdict:
            async with sem:
                try:
                    return await verify_website(client, name, location)
                except Exception as e:  # noqa: BLE001
                    log.warning("verify_website failed for %r: %s", name, e)
                    return WebsiteVerdict(url=None, confidence=0.0, sources_seen=0)

        return list(await asyncio.gather(*(worker(n, l) for n, l in business_names)))


__all__ = [
    "SearchResult",
    "WebsiteVerdict",
    "ddg_search",
    "parse_ddg_results",
    "verify_website",
    "verify_many",
    "backfill_candidates",
    "_CONFIRM_THRESHOLD",
    "_POSSIBLE_THRESHOLD",
]
