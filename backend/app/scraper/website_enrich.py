"""Lead website enrichment.

For each lead with a first-party website, fetch a small set of high-signal
URLs (homepage + /contact + /about) and extract:

  - email addresses (mailto: links and raw text)
  - social profile links (Facebook, Instagram, LinkedIn, X/Twitter, YouTube, TikTok)
  - a short description from <meta name="description"> or og:description
  - the page <title> as a fallback description

We use httpx for raw HTML fetches — no Playwright, no JS rendering. This
keeps enrichment around 1–3 seconds per lead even for slow sites, and the
whole batch runs in parallel so total wallclock is dominated by the slowest
lead, not the sum.

Resilience: any per-lead failure is swallowed silently. The lead just keeps
whatever fields it already had from the Maps scrape.
"""
from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Iterable
from urllib.parse import urljoin, urlparse

import httpx

from .types import ScrapedLead

log = logging.getLogger(__name__)

# Per-lead enrichment time budget. Slow sites get cut off rather than
# stalling the whole scrape.
_LEAD_TIMEOUT_S = 8.0
_REQUEST_TIMEOUT_S = 4.0
_CONCURRENCY = 8

# Pages we'll try in addition to the homepage. Order matters — first hit wins
# for fields like description.
_CONTACT_PATHS = ("/contact", "/contact-us", "/about", "/about-us")

_EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9_.+-])([A-Za-z0-9_.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)",
)

# Domains we recognize as social profiles. Map host → key in social_links.
_SOCIAL_HOSTS: dict[str, str] = {
    "facebook.com": "facebook",
    "m.facebook.com": "facebook",
    "fb.com": "facebook",
    "instagram.com": "instagram",
    "linkedin.com": "linkedin",
    "twitter.com": "twitter",
    "x.com": "twitter",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "tiktok.com": "tiktok",
    "pinterest.com": "pinterest",
}

# Emails we ignore — defaults from CMS templates and obvious dummies.
_EMAIL_IGNORE_PREFIXES = (
    "example@", "youremail@", "test@", "sample@", "name@",
    "user@", "email@",
)
_EMAIL_IGNORE_DOMAINS = (
    "example.com", "example.org", "domain.com", "yourdomain.com",
    "sentry.io", "wixpress.com", "wix.com",
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _normalize_url(url: str) -> str | None:
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        p = urlparse(url)
        if not p.netloc:
            return None
        return f"{p.scheme}://{p.netloc}{p.path or '/'}"
    except Exception:  # noqa: BLE001
        return None


def _is_useful_email(addr: str) -> bool:
    a = addr.lower()
    if a.startswith(_EMAIL_IGNORE_PREFIXES):
        return False
    if any(a.endswith("@" + d) for d in _EMAIL_IGNORE_DOMAINS):
        return False
    if a.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
        return False
    return True


def _extract_emails(html: str) -> list[str]:
    found = set()
    for match in _EMAIL_RE.findall(html):
        if _is_useful_email(match):
            found.add(match.lower())
    return sorted(found)


def _extract_socials(html: str, base_url: str) -> dict[str, str]:
    socials: dict[str, str] = {}
    # Pull every href/src=… that points at a known social host.
    for href in re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE):
        try:
            absolute = urljoin(base_url, href)
            host = (urlparse(absolute).hostname or "").lower().lstrip(".")
            host = host.removeprefix("www.")
            for known, key in _SOCIAL_HOSTS.items():
                if host == known or host.endswith("." + known):
                    # Skip "share" URLs that just point at the social homepage.
                    path = urlparse(absolute).path.strip("/")
                    if not path or path in {"sharer", "share", "intent"}:
                        continue
                    socials.setdefault(key, absolute.split("?", 1)[0])
                    break
        except Exception:  # noqa: BLE001
            continue
    return socials


def _extract_description(html: str) -> str | None:
    # og:description first — usually higher quality than meta description.
    for pat in (
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
    ):
        m = re.search(pat, html, flags=re.IGNORECASE)
        if m:
            text = " ".join(m.group(1).split())
            if len(text) >= 20:
                return text[:600]
    return None


def _extract_title(html: str) -> str | None:
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, flags=re.IGNORECASE)
    if not m:
        return None
    text = " ".join(m.group(1).split())
    return text[:300] if text else None


async def _fetch(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        r = await client.get(url, follow_redirects=True, timeout=_REQUEST_TIMEOUT_S)
    except Exception as e:  # noqa: BLE001
        log.debug("enrich fetch failed %s: %s", url, e)
        return None
    if r.status_code >= 400:
        return None
    ct = r.headers.get("content-type", "")
    if "html" not in ct and "xml" not in ct and ct:
        # Not HTML — skip parsing
        return None
    return r.text


def _merge_extraction(lead: ScrapedLead, html: str, base_url: str) -> None:
    """Pull whatever new info `html` has into `lead`. Existing values win."""
    if not lead.email:
        emails = _extract_emails(html)
        if emails:
            lead.email = emails[0]
    if not lead.description:
        desc = _extract_description(html) or _extract_title(html)
        if desc:
            lead.description = desc
    new_socials = _extract_socials(html, base_url)
    if new_socials:
        merged = dict(lead.social_links or {})
        for k, v in new_socials.items():
            merged.setdefault(k, v)
        lead.social_links = merged


async def _enrich_one(client: httpx.AsyncClient, lead: ScrapedLead) -> None:
    homepage = _normalize_url(lead.website or "")
    if not homepage:
        return
    base = f"{urlparse(homepage).scheme}://{urlparse(homepage).netloc}"

    async def _try(path_or_url: str) -> None:
        url = path_or_url if path_or_url.startswith("http") else urljoin(base + "/", path_or_url.lstrip("/"))
        html = await _fetch(client, url)
        if html:
            _merge_extraction(lead, html, url)

    try:
        await asyncio.wait_for(
            asyncio.gather(
                _try(homepage),
                _try(_CONTACT_PATHS[0]),
                _try(_CONTACT_PATHS[1]),
                _try(_CONTACT_PATHS[2]),
                _try(_CONTACT_PATHS[3]),
                return_exceptions=True,
            ),
            timeout=_LEAD_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        log.debug("enrich timeout for %s", lead.website)


async def enrich_leads(leads: Iterable[ScrapedLead]) -> None:
    """Fetch each lead's website and merge extracted fields in-place.

    Bounded concurrency keeps us from being an unintentional load test on
    small websites. Failures are silent — the lead just keeps its existing
    fields.
    """
    targets = [l for l in leads if l.website]
    if not targets:
        return

    sem = asyncio.Semaphore(_CONCURRENCY)
    limits = httpx.Limits(max_connections=_CONCURRENCY * 2, max_keepalive_connections=_CONCURRENCY)

    async with httpx.AsyncClient(headers=_HEADERS, limits=limits, http2=False) as client:
        async def worker(lead: ScrapedLead) -> None:
            async with sem:
                try:
                    await _enrich_one(client, lead)
                except Exception as e:  # noqa: BLE001
                    log.debug("enrich worker failed for %s: %s", lead.website, e)

        await asyncio.gather(*(worker(l) for l in targets), return_exceptions=True)

    log.info(
        "website enrichment: %d/%d leads now have email, %d have socials, %d have description",
        sum(1 for l in targets if l.email),
        len(targets),
        sum(1 for l in targets if l.social_links),
        sum(1 for l in targets if l.description),
    )
