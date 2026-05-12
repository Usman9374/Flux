# Flux Lead-Generation Overhaul — Implementation Prompt

> **Read this whole file before writing any code.** This is not a request for cosmetic tweaks. The current lead pipeline is unfit for purpose and must be rebuilt around the contract defined here. Treat every section as a hard requirement unless it is explicitly labelled "Nice to have".

---

## 0. Context — what is broken today

Flux is a B2B prospecting tool, advertised as "Apollo-style apollo.io btw". Today the scraper is a single-source Google Maps crawler with a cosmetic progress bar. Real user complaints, verbatim:

1. **"It always gets stuck at 92%."** The UI animates to 92 and waits on a single blocking `POST /api/scrape` that can take minutes. There is no real progress signal, no streaming, and no early partial results.
2. **"It took so long and gave me two restaurants."** Final kept count is frequently `0` or `1–2` out of `max_results=20`. The user asked for *"restaurants in Islamabad without a website"* and got Serena Hotels (a five-star international chain, has a website) and OX and Grill (well-established, has a website). Both should have been rejected by the inverted filter. They were not.
3. **"It gives me random baseless websites."** Aggregator/social profile URLs and unrelated domains slip through as `lead.website`.
4. **"Sometimes it just gives me 0 results."** Either the Maps page never loaded, the consent screen blocked, or every lead was filtered out by an over-tight `min_quality_score`. The user gets nothing back and no explanation.
5. **"It's not fetching the tier properly."** (User said "tier" — assume they mean *category* / *niche fit* / *quality tier*.) Leads come back with no clear category match, no quality grade visible in the UI, and no way to tell why a given lead was kept.

The bar to clear is **Apollo.io**: every row returned must be a real, contactable, on-target business — not a directory entry, not a chain branch, not a closed venue, not a random listing that happens to contain one of the search words.

---

## 1. Files you will touch

You may add files. Do **not** delete files without understanding their callers first.

Backend:
- `backend/app/scraper/runner.py` — orchestration; needs streaming + fallback logic.
- `backend/app/scraper/sources/google_maps.py` — selectors + website detection are too brittle.
- `backend/app/scraper/quality.py` — scoring and intent parsing; inverted-website mode is broken in practice.
- `backend/app/scraper/website_enrich.py` — needs to also *confirm* that a lead has no website before we trust the "no website" verdict.
- `backend/app/scraper/types.py` — extend the data model (tier, confidence, source attribution).
- `backend/app/routes/scrape.py` — switch to a job + polling or SSE/WebSocket pattern.
- `backend/app/schemas.py` — add the new fields to API output.
- `backend/app/scraper/sources/` — **add new source modules** (see §6).

Frontend:
- `frontend/src/components/ScrapeForm.jsx` — replace fake 92% animation with real progress.
- Wherever leads are rendered — surface tier, confidence, signals, and rejection reasons (for transparency / debugging).

Do not change `firestore.rules`, auth, or unrelated routes.

---

## 2. The non-negotiable contract

A lead returned to the user **MUST** satisfy all of these:

1. **It is a real, currently-operating business** — not "permanently closed", not "temporarily closed".
2. **It is contactable** — at least one of: first-party website, business phone, or business email. A lead with none of these is worthless. Reject it.
3. **It matches the requested niche** — the `category` field on the Maps card, or the homepage `<title>`/`<meta description>`, must contain at least one niche token (after stop-word removal). A query for "restaurants" must not return a hotel unless the hotel's primary Maps category is `Restaurant`.
4. **It matches the requested location** — the address must contain a token from the location string OR fall inside the Maps viewport that was queried. No leads from a different city.
5. **It is not a directory/aggregator** — the website field, if present, must not resolve to any host in `AGGREGATOR_DOMAINS`. Hard reject. No exceptions.
6. **Intent is respected.** When the user types "without website" / "no website" / "offline only" / a similar phrase, the *only* leads returned are those that genuinely have no first-party website. See §4 for the verification procedure — the current implementation trusts the absence of a Maps detail field, which is exactly why Serena and OX and Grill slipped through.
7. **Every field is either correct or absent.** A wrong website is worse than no website. If detection confidence is low, leave the field blank and set `signals.website_confidence = "low"`. Never invent or guess a URL.

If you cannot satisfy a rule for a given lead, drop it. Quality over volume.

---

## 3. Lead schema — what every row must look like

Extend `ScrapedLead` with the following. Existing fields stay.

```python
@dataclass
class ScrapedLead:
    # --- identity ---
    name: str
    category: str | None           # primary Maps category (e.g. "Restaurant")
    niche: str | None              # the cleaned user query
    location: str | None           # the cleaned user location

    # --- contact (required: at least one of website/phone/email) ---
    website: str | None
    phone: str | None              # E.164 where possible
    email: str | None
    social_links: dict[str, str]   # {"facebook": "...", "instagram": "..."}

    # --- presence ---
    address: str | None
    plus_code: str | None
    hours: str | None
    map_url: str | None            # canonical Google Maps URL (was: source_url)

    # --- reputation ---
    rating: float | None
    reviews: int | None
    years_in_business: int | None  # if available from listing or homepage footer

    # --- content for outreach ---
    description: str | None        # max 600 chars, plain text
    tagline: str | None            # short one-liner if extractable

    # --- scoring + transparency (NEW) ---
    quality_score: int | None      # 0-100, see §5
    tier: str | None               # "A" | "B" | "C" — see §5
    confidence: float | None       # 0.0-1.0, how sure we are about the contact info
    signals: dict[str, Any]        # boolean flags used in scoring; ALSO surface in UI
    rejection_reason: str | None   # populated only for dropped leads; useful for debugging
    sources: list[str]             # ["google_maps", "homepage", "facebook_about"]
    fetched_at: datetime           # UTC; required for staleness checks later
```

Persist all of this. Surface `tier`, `confidence`, the top 3 `signals`, and (in admin views) `rejection_reason`.

---

## 4. Intent parsing — fix "without website" properly

The current `parse_intent` in [quality.py](backend/app/scraper/quality.py) detects the phrase fine. The bug is downstream: a lead's `website` field is set from `a[data-item-id="authority"]` on the Maps detail panel. **If that selector misses (it does, frequently — Google A/Bs the panel), the lead ends up with `website=None` and passes the inverted filter as a false positive.** That is exactly how Serena and OX and Grill came through.

### Required fix

When `require_website=False` (user asked for offline businesses), a lead may only be kept if **all** of the following hold:

1. The Maps detail panel did not surface a website URL.
2. **A search-engine verification step** ran for this business and returned no plausible first-party site.
3. (Optional but recommended) A direct domain probe of `{slugified_name}.com` / `{slugified_name}.co` / `{slugified_name}.{tld_of_country}` returned 404 / NXDOMAIN, not 200.

The verification step:

- Query DuckDuckGo HTML (or Bing, or SerpAPI if a key is configured) with `"{business name}" {location}`.
- Parse the first 5 result URLs.
- For each, strip aggregator domains. If any non-aggregator domain remains AND its homepage `<title>` or visible `<h1>` contains a fuzzy match for the business name (Levenshtein ratio ≥ 0.75), treat that as the business's website. **Lead is rejected from `require_website=False` mode and re-tagged as "actually has a website".**

Confidence threshold for "actually has a website":
- `confidence ≥ 0.8` → reject from offline mode.
- `confidence 0.5–0.8` → keep, but set `signals.possible_website` to the URL and `signals.website_unverified=True`. User sees both.
- `confidence < 0.5` → keep as offline lead.

### Why we can't skip this

Maps frequently lists the website on cards but not in the detail panel, and vice versa. A chain (Serena Hotels) sometimes has the website surfaced only at the parent-brand page, not the branch listing. A purely scraper-based test is not enough. **Without the search verification step, "without website" mode is unusable.** It is the single biggest user complaint. Fix it first.

---

## 5. Scoring & tiering — replace the current scorer

Current scorer in [quality.py:130](backend/app/scraper/quality.py) is additive and ceiling-bound, which causes two failure modes:
- Leads with strong reputation but poor reachability score equal to leads with poor reputation but strong reachability — the user can't tell them apart.
- The `min_quality_score=35` default is met by garbage (just having a name + phone + address).

Replace it with a **tiered + weighted** scheme:

```
tier A (90+): own website + phone + email + matched category + rating ≥ 4.0 with ≥ 25 reviews + location match.
tier B (65-89): own website + at least one of phone/email + matched category + location match.
tier C (40-64): contactable + matched category, but missing reputation OR missing one contact channel.
< 40: drop.
```

For `require_website=False` mode the website axis flips: tier A requires phone + email + matched category + reputation. No website allowed at all.

Scoring rules:

| Signal | Weight | Notes |
|---|---|---|
| First-party website (verified, non-aggregator) | 25 | 0 if `require_website=False` and a site is detected → rejected outright. |
| Business phone (E.164-able, not toll-free spam list) | 15 | Must be reachable. Drop if it matches known spam ranges. |
| Direct email (info@, contact@, name@) | 20 | Generic `info@` worth less than a named mailbox; weight 12 vs 20. |
| Category exact-match (Maps category contains niche token) | 15 | Required, not optional. 0 if no overlap → reject. |
| Location match (city/area token in address, OR within ~25km of geocoded query) | 10 | Required, 0 → reject. |
| Rating ≥ 4.0 AND reviews ≥ 25 | 8 | Strong reputation signal. |
| Reviews ≥ 100 | 5 | Independent of rating — longevity. |
| Socials present (≥ 2 platforms, business handles, not share buttons) | 4 |  |
| Description ≥ 80 chars from `<meta>` or Maps editorial | 3 |  |
| Hours present | 2 |  |

Hard rejects (score forced to 0 → dropped, with reason):
- Name length < 3.
- Aggregator/social-only website.
- Permanently/temporarily closed.
- Category no-overlap with niche.
- Location no-overlap with location.
- Rating < 2.5 with ≥ 10 reviews.
- Duplicate of an already-kept lead (same phone, or same normalized domain, or fuzzy name match within same address).

`confidence` is independent of score and reflects how sure we are about the *contact info*: number of corroborating sources for the website (Maps + homepage `<link rel="canonical">` + Facebook About + Bing result all agreeing → 1.0; only Maps card → 0.4).

---

## 6. Sources — Google Maps alone is not enough

A second source is required to (a) verify websites for the "without website" flow and (b) backfill when Maps returns a thin or no result set. Add at least one of these, behind a feature flag if API keys are needed:

1. **Search-engine fallback** (`sources/search_engine.py`). DuckDuckGo HTML is no-auth and free; use it as the default. Bing Web Search API and SerpAPI are upgrades when keys are present (`config.py`). For each business name from Maps, run one query to verify the website. Also: when Maps returns < 5 results for a query, run a fresh search-engine query and parse out business names + URLs to backfill.
2. **OpenStreetMap / Nominatim + Overpass** (`sources/osm.py`). Free, no key, decent for "X near Y" listings. Use for the **backfill** path when Maps fails or is throttled. OSM data has fewer websites but more obscure local businesses — exactly what "without website" mode wants.
3. **Facebook page resolution** (best-effort). For each lead without a website, search Facebook for the business name + city and capture the public page URL + email if visible in the About section. Treat this as enrichment, not a primary source. Rate-limit aggressively and stop on captcha. Skip in headless mode if Facebook starts demanding login.

Wire it up so every keep candidate is enriched by *at least two independent sources* before it is returned. Track which sources contributed in `lead.sources`.

---

## 7. Reliability — no more "0 out of 20" with no explanation

Make the pipeline degrade gracefully.

1. **Per-stage timeouts with partial returns.** If Maps scroll succeeds but detail-panel enrichment times out, return what we have with a `partial=True` flag and `tier` recalculated from what's known. Never silently produce zero results when there are raw cards in hand.
2. **Floor for kept results.** If `kept_count == 0` after final filtering, automatically re-run the filter with relaxed `min_score` (drop one tier at a time down to C) and surface the result with a flag `signals.relaxed_filter=True` so the UI can say "no A-tier leads found, showing best available". Never return zero unless `raw_count` is also zero.
3. **Maps consent loop.** The current consent handler tries three button labels and then gives up. Add a 5s retry, then a region-spoof retry (`?hl=en&gl=us` → `?hl=en&gl={country_code(location)}`). If the country code is wrong for the location (we send `gl=us` for a query in Islamabad) Maps rate-limits and serves the consent loop more aggressively. Pick `gl` from the location string when possible.
4. **Selector drift telemetry.** If `_CARDS_JS` returns < 3 cards on a query that worked yesterday, log a `SELECTOR_DRIFT` warning with the page HTML's hash and the URL. Don't crash. Don't return empty silently.
5. **Retry topology.** Currently `with_retries` wraps the whole scrape. Move retries to per-stage: scroll feed, extract cards, enrich one detail, verify website. A single bad detail page should not nuke the whole run.
6. **Hard wall-clock cap.** A scrape may not exceed 90 seconds end-to-end by default (configurable via the request). If it does, return whatever is ready and mark `partial=True`. Stuck-at-92%-forever is unacceptable.

---

## 8. Progress reporting — kill the fake 92%

Replace the cosmetic interval in [ScrapeForm.jsx:33-39](frontend/src/components/ScrapeForm.jsx#L33-L39).

Backend pattern:
- `POST /api/scrape` becomes `POST /api/scrape/jobs` → returns `{ job_id }` immediately.
- Worker runs the pipeline and emits status updates to a Redis pub/sub channel or, simpler for now, an in-memory dict keyed by job_id (single-process Render dyno — acceptable for v1).
- Client opens `GET /api/scrape/jobs/{job_id}/events` (SSE) and receives a stream of:
  ```json
  {"stage": "searching", "progress": 0.05, "message": "Querying Google Maps…"}
  {"stage": "scrolling", "progress": 0.25, "raw_count": 14}
  {"stage": "enriching_details", "progress": 0.55, "enriched": 8, "total": 14}
  {"stage": "verifying_websites", "progress": 0.78}
  {"stage": "scoring", "progress": 0.92}
  {"stage": "done", "progress": 1.0, "result": { ... full ScrapeResultOut ... }}
  ```
- Frontend's progress bar reads the `progress` field. No more synthetic 92%.

If implementing SSE feels like scope creep, the minimum viable alternative is polling: `GET /api/scrape/jobs/{job_id}` every 1s returning the latest status. Either is fine. The fake animation is not.

Also: the frontend must stream kept leads into the table as they come in, not all-at-once at the end. A user watching "found 6/20" make progress is a different product than a user watching a spinner.

---

## 9. UI/UX requirements

For every returned lead, surface:
- Tier badge (A / B / C with distinct colors).
- Why-kept: 3 strongest signals as small chips ("rating 4.6 · 230 reviews", "verified website", "category match: Restaurant").
- Contact channels as clickable: `tel:`, `mailto:`, website opens in new tab.
- Map link (the Google Maps URL) so the user can verify.

For every dropped lead (in an admin "show dropped" toggle):
- The `rejection_reason`. Builds trust and helps debug.

In the form:
- A live preview of intent parsing: when the user types "restaurants in Islamabad without a website", show "Searching: restaurants in Islamabad · Mode: offline businesses only".
- The `min_quality_score` slider should show a description per tier band, not a raw number.

---

## 10. Limits & what NOT to do

- **Do not** add LLM calls into the hot path. The verification step is regex + fuzzy match + HTTP. An LLM in the loop is too slow and too expensive for what is a deterministic problem.
- **Do not** rely solely on Google Places API instead of scraping — it costs real money per request and Flux's pitch is that we extract data Apollo's clients pay for. Keep scraping as the default; allow Places API as an optional accelerator behind an env flag.
- **Do not** widen `AGGREGATOR_DOMAINS` so aggressively that legitimate sites on Wix or Squarespace are dropped. Right now `wixsite.com` and `squarespace.com` are blanket-blocked. Replace with a check on path depth: `*.wixsite.com/business-name` is a real business homepage; bare `wixsite.com` is the platform itself. Only block the platform.
- **Do not** silently catch every exception. Existing code is full of `except Exception: pass` — keep them narrow and `log.warning` at minimum. We cannot debug a pipeline that swallows errors.
- **Do not** ship without tests. At minimum: a fixture-based test for `parse_intent`, a unit test for `is_aggregator`, a unit test for the new scorer that asserts tier boundaries, and an offline-fixture test that feeds a saved Maps HTML page to the parser and asserts ≥ N cards extracted. Use `pytest`. Live-scrape tests gated behind an env flag.
- **Do not** persist leads that failed the contract in §2. The DB should only contain things the user could realistically contact today.
- **Do not** invent contact data. Empty fields are honest. Wrong fields destroy trust.

---

## 11. Acceptance tests

After your changes, these queries must produce results matching the expectations. Run them against the live system, capture the output, and include it in your PR description.

| Query | Location | Expected behaviour |
|---|---|---|
| `restaurants without a website` | `Islamabad` | ≥ 5 leads, **none** with a working homepage URL. Spot-check: no Serena, no OX and Grill, no Monal, no Tuscany Courtyard. Each lead has a phone. |
| `dental clinic` | `Lahore` | ≥ 10 tier-B-or-better leads. Each has a working website (HTTP 200 within 5s). No `facebook.com/...` as the website. Category contains "dental" or "dentist". |
| `roofing contractor` | `Austin, TX` | ≥ 10 leads. ≥ 50% have an email after enrichment. None located outside Texas. |
| `law firm` | `Karachi` | ≥ 8 leads. Each has rating ≥ 3.5 OR reviews ≥ 25. None marked closed. |
| Same query twice in 10 minutes |  | Second run uses cache; returns in < 5s. Cache key includes niche + location + intent flags. |
| Force-fail: query a nonsense niche `"qzxqzx services"` in `Paris` |  | Returns `kept=[]` with `raw_count` populated and a clear message; does not hang, does not throw 500. |
| Wall-clock | any | Default scrape finishes in ≤ 90s. Progress bar reflects real progress. No stalls at 92%. |

If any of these regress against current behaviour without good reason, the change is not done.

---

## 12. Order of operations (suggested)

You do not have to follow this order, but it is the order that gets value to the user fastest.

1. Fix the "without website" verification (§4). One scraper change, one new module, biggest user-visible win.
2. Replace the scorer with tiers (§5). Surfaces value to the user immediately.
3. Add the search-engine source for verification + backfill (§6).
4. Add real progress reporting + job polling (§8).
5. Add per-stage timeouts and the "never return zero" floor (§7).
6. Add the new schema fields and surface them in the UI (§3, §9).
7. Write the acceptance tests (§11). Run them. Iterate.

---

## 13. Definition of done

- All seven §11 queries pass.
- No `except Exception: pass` introduced by this change.
- New tests added and green.
- The progress bar never advances without a backend signal.
- A code reader who has never seen the project can run a single command, point Flux at "restaurants without a website in Islamabad", and get a screen of real, contactable, offline-only restaurants in under two minutes.

If you find a §1–§11 requirement that is wrong or impossible, stop and flag it in the PR description. Do not silently work around it.
