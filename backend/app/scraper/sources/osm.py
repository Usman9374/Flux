"""OpenStreetMap source — Nominatim geocoding + Overpass POI search.

Why OSM is the primary source (per LEAD_GENERATION_FIX.md §2):

- Pure HTTP. No browser, no Playwright, no Chromium memory profile.
- No API key. Works from any IP, including data-center IPs that Google
  blocks.
- Returns structured tags (name, contact:phone, contact:website, addr:*,
  opening_hours) that map cleanly onto our ScrapedLead schema.
- Worldwide coverage. The dataset is patchy in some regions — that's why
  we still run DDG/Maps in parallel — but it's the only source that
  returns *anything* reliably from production.

Two stages:
  1. `geocode(location)` → bbox + country code via Nominatim
  2. `overpass_search(niche, bbox)` → POI list

We honor public-instance fair use: identifying User-Agent, ≤ 1 concurrent
overpass query per process, single-call timeouts, and an in-process LRU
cache keyed by (niche, location) for 10 minutes.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from ..niche_taxonomy import NicheMatch, default_radius_km, match_niche
from ..types import ScrapedLead

log = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)

# Nominatim/Overpass policy says we need a real User-Agent identifying
# the app + a contact. This is sent on every request.
_HEADERS = {
    "User-Agent": "FluxLeadGen/1.0 (https://github.com/Usman9374/flux; contact: support@flux.local)",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}

# Per-call timeouts. Overpass is the slow one — heavy queries can take
# 20s+. We cap at the first 30s and move on; the parallel sources will
# still produce something.
_NOMINATIM_TIMEOUT_S = 8.0
_OVERPASS_TIMEOUT_S = 30.0
_OVERPASS_QUERY_TIMEOUT_S = 25  # passed to the [timeout:N] header in QL

# In-process cache. Light TTL so a re-run within a few minutes doesn't
# re-query OSM. Cleared on process restart.
_CACHE_TTL_S = 600.0
_cache: dict[tuple, tuple[float, list[ScrapedLead]]] = {}
_geocode_cache: dict[str, tuple[float, "Geocoded | None"]] = {}

# Single inflight overpass query per process — public instance is shared
# infrastructure, queueing is the polite thing to do.
_overpass_lock = asyncio.Lock()


@dataclass(frozen=True)
class Geocoded:
    display_name: str
    lat: float
    lon: float
    bbox: tuple[float, float, float, float]  # (south, north, west, east)
    country_code: str | None


# ---------- Nominatim ----------


async def geocode(client: httpx.AsyncClient, location: str) -> Geocoded | None:
    """Geocode a free-text location to a bounding box. Cached for 10 minutes.

    Returns None if Nominatim is unreachable or the location can't be
    resolved. The caller should fall through to a name-only Overpass
    query in that case.
    """
    key = location.strip().lower()
    if not key:
        return None
    now = time.time()
    cached = _geocode_cache.get(key)
    if cached and (now - cached[0]) < _CACHE_TTL_S:
        return cached[1]

    params = {
        "q": location,
        "format": "json",
        "limit": 1,
        "addressdetails": 1,
    }
    try:
        r = await client.get(
            NOMINATIM_URL,
            params=params,
            headers=_HEADERS,
            timeout=_NOMINATIM_TIMEOUT_S,
            follow_redirects=True,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("nominatim geocode failed for %r: %s", location, e)
        return None
    if r.status_code >= 400:
        log.warning("nominatim returned HTTP %s for %r", r.status_code, location)
        return None
    try:
        data = r.json()
    except json.JSONDecodeError as e:
        log.warning("nominatim returned non-JSON for %r: %s", location, e)
        return None
    if not isinstance(data, list) or not data:
        _geocode_cache[key] = (now, None)
        return None

    item = data[0]
    try:
        bb = item["boundingbox"]  # [south, north, west, east] as strings
        lat = float(item["lat"])
        lon = float(item["lon"])
        bbox = (float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3]))
    except (KeyError, ValueError, TypeError) as e:
        log.warning("nominatim payload missing fields for %r: %s", location, e)
        return None
    cc = ((item.get("address") or {}).get("country_code") or "").lower() or None

    geo = Geocoded(
        display_name=item.get("display_name") or location,
        lat=lat,
        lon=lon,
        bbox=bbox,
        country_code=cc,
    )
    _geocode_cache[key] = (now, geo)
    return geo


# ---------- Overpass ----------


def _build_overpass_ql(
    niche_match: NicheMatch | None,
    niche_text: str,
    bbox: tuple[float, float, float, float],
) -> str:
    """Construct an Overpass QL query string for nodes/ways/relations.

    If we have a taxonomy match, OR over each (key, value) pair. Otherwise
    fall back to a name regex (slower, but it returns something).
    """
    south, north, west, east = bbox
    bbox_clause = f"({south},{west},{north},{east})"
    parts: list[str] = []
    if niche_match and niche_match.tags:
        for k, v in niche_match.tags:
            for elem in ("node", "way", "relation"):
                parts.append(f'  {elem}["{k}"="{v}"]{bbox_clause};')
    else:
        # Free-text fallback. Quote the whole niche; OSM regex is
        # case-insensitive when prefixed with `~,i`.
        safe = re.sub(r'["\\]', "", niche_text)[:80]
        for elem in ("node", "way", "relation"):
            parts.append(f'  {elem}["name"~"{safe}",i]{bbox_clause};')

    body = "\n".join(parts)
    return (
        f"[out:json][timeout:{_OVERPASS_QUERY_TIMEOUT_S}];\n"
        f"(\n{body}\n);\n"
        "out center 200;"
    )


def _addr_from_tags(tags: dict[str, str]) -> str | None:
    parts: list[str] = []
    for key in ("addr:housenumber", "addr:street", "addr:city",
                "addr:postcode", "addr:state", "addr:country"):
        v = tags.get(key)
        if v:
            parts.append(v)
    if not parts:
        return None
    return ", ".join(parts)


def _website_from_tags(tags: dict[str, str]) -> str | None:
    for k in ("website", "contact:website", "url"):
        v = tags.get(k)
        if v:
            v = v.strip()
            if v.startswith(("http://", "https://")):
                return v
            if v.startswith("//"):
                return "https:" + v
            if "." in v and " " not in v:
                return "https://" + v
    return None


def _phone_from_tags(tags: dict[str, str]) -> str | None:
    for k in ("phone", "contact:phone", "contact:mobile", "mobile"):
        v = tags.get(k)
        if v:
            return v.strip().split(";", 1)[0].strip()
    return None


def _email_from_tags(tags: dict[str, str]) -> str | None:
    for k in ("email", "contact:email"):
        v = tags.get(k)
        if v and "@" in v:
            return v.strip().split(";", 1)[0].strip()
    return None


def _socials_from_tags(tags: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    pairs = (
        ("facebook", ("facebook", "contact:facebook")),
        ("instagram", ("instagram", "contact:instagram")),
        ("twitter", ("twitter", "contact:twitter")),
        ("linkedin", ("linkedin", "contact:linkedin")),
        ("youtube", ("youtube", "contact:youtube")),
        ("tiktok", ("tiktok", "contact:tiktok")),
    )
    for key, candidates in pairs:
        for c in candidates:
            v = tags.get(c)
            if v:
                v = v.strip()
                if not v.startswith("http"):
                    v = "https://" + v.lstrip("/")
                out[key] = v
                break
    return out


def _category_from_tags(tags: dict[str, str], niche_match: NicheMatch | None) -> str | None:
    """Best-effort 'Maps category' analogue derived from OSM tags."""
    if niche_match:
        return niche_match.canonical.replace("_", " ").title()
    for k in ("amenity", "shop", "office", "craft", "healthcare", "leisure", "tourism", "sport"):
        v = tags.get(k)
        if v:
            return v.replace("_", " ").title()
    return None


def _parse_elements(
    elements: list[dict[str, Any]],
    *,
    niche_match: NicheMatch | None,
    niche_text: str,
    location: str,
) -> list[ScrapedLead]:
    out: list[ScrapedLead] = []
    seen_keys: set[tuple[str, str | None]] = set()
    for el in elements:
        tags = el.get("tags") or {}
        name = (tags.get("name") or tags.get("name:en") or "").strip()
        if not name or len(name) < 2:
            continue
        # Dedupe across node/way/relation copies of the same place.
        dedupe_key = (name.lower(), (tags.get("addr:street") or "").lower() or None)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)

        center = el.get("center") or {}
        lat = el.get("lat") if "lat" in el else center.get("lat")
        lon = el.get("lon") if "lon" in el else center.get("lon")
        osm_id = f"{el.get('type', 'n')[0]}{el.get('id')}"
        map_url = (
            f"https://www.openstreetmap.org/{el.get('type','node')}/{el.get('id')}"
            if el.get("id") is not None else None
        )

        lead = ScrapedLead(
            name=name,
            website=_website_from_tags(tags),
            phone=_phone_from_tags(tags),
            email=_email_from_tags(tags),
            address=_addr_from_tags(tags),
            location=location,
            niche=niche_text,
            category=_category_from_tags(tags, niche_match),
            description=tags.get("description") or tags.get("note"),
            hours=tags.get("opening_hours"),
            social_links=_socials_from_tags(tags),
            map_url=map_url,
            source="osm",
            source_url=map_url,
            sources=["osm"],
        )
        # Mark that OSM proved the niche match (the tag matched the niche).
        if niche_match is not None:
            lead.signals = {**(lead.signals or {}), "category_match_source": "osm_tag"}
        if lat is not None and lon is not None:
            sigs = dict(lead.signals or {})
            sigs["osm_lat"] = lat
            sigs["osm_lon"] = lon
            sigs["osm_id"] = osm_id
            sigs["location_match_geo"] = True
            lead.signals = sigs
        out.append(lead)
    return out


async def _overpass_post(client: httpx.AsyncClient, ql: str) -> dict[str, Any] | None:
    """POST to Overpass with mirror fallback. Returns parsed JSON or None."""
    last_err: Exception | None = None
    for url in OVERPASS_URLS:
        try:
            r = await client.post(
                url,
                content=ql.encode("utf-8"),
                headers={**_HEADERS, "Content-Type": "text/plain; charset=utf-8"},
                timeout=_OVERPASS_TIMEOUT_S,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("overpass POST %s failed: %s", url, e)
            last_err = e
            continue
        if r.status_code >= 400:
            log.warning("overpass %s returned HTTP %s", url, r.status_code)
            last_err = RuntimeError(f"HTTP {r.status_code}")
            continue
        try:
            return r.json()
        except json.JSONDecodeError as e:
            log.warning("overpass %s returned non-JSON: %s", url, e)
            last_err = e
            continue
    log.warning("all overpass mirrors failed: %s", last_err)
    return None


async def search(
    client: httpx.AsyncClient,
    niche: str,
    location: str,
    *,
    limit: int = 30,
    geocoded: Geocoded | None = None,
) -> list[ScrapedLead]:
    """Run the full OSM lookup. Cached per (niche, location).

    `geocoded` may be supplied if the caller already geocoded the location
    (saves one Nominatim hit). If it's None, we geocode here.
    """
    cache_key = (niche.strip().lower(), location.strip().lower(), limit)
    now = time.time()
    cached = _cache.get(cache_key)
    if cached and (now - cached[0]) < _CACHE_TTL_S:
        return list(cached[1])

    if geocoded is None:
        geocoded = await geocode(client, location)
    if geocoded is None:
        log.info("osm: geocode failed for %r — skipping", location)
        return []

    niche_match = match_niche(niche)
    ql = _build_overpass_ql(niche_match, niche, geocoded.bbox)
    log.info("overpass query: niche=%r tags=%s bbox=%s",
             niche,
             [f"{k}={v}" for k, v in (niche_match.tags if niche_match else [])] or "name~",
             geocoded.bbox)

    async with _overpass_lock:
        data = await _overpass_post(client, ql)
    if data is None:
        return []

    elements = data.get("elements") or []
    leads = _parse_elements(
        elements, niche_match=niche_match, niche_text=niche, location=location
    )
    leads = leads[:limit]
    _cache[cache_key] = (now, list(leads))
    log.info("osm: %d leads (%d raw elements)", len(leads), len(elements))
    return leads


__all__ = [
    "Geocoded",
    "geocode",
    "search",
]
