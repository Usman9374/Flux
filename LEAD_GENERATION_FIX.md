# Flux Lead-Generation Overhaul — v2

> Read the whole file before changing code. v1 of this doc tried to make the
> Google-Maps-only pipeline behave like Apollo by piling more verification on
> top of it. That doesn't work, and the real reason is in §0. v2 tears out
> the Maps dependency, replaces it with multiple cooperating HTTP sources,
> and simplifies the filter so we stop returning empty.

---

## 0. Why "0 leads" is the steady-state today

The current pipeline depends on Playwright launching Chromium and scraping
Google Maps from the production dyno (Render). Three things make that
configuration fail almost every time in production:

1. **Google blocks data-center IPs aggressively.** When Maps is hit from a
   Render IP it serves the consent loop indefinitely, returns an empty
   feed, or 429s. Local dev works because home/office IPs are not flagged;
   production silently returns 0 results.
2. **Chromium on a 512 MB Render dyno is fragile.** The launch races OOM,
   and when it survives the page navigations exceed the 90 s wall clock.
   Every per-stage timeout fires and the run ends with `partial=True` and
   `kept=0`.
3. **Even when scraping works, the filter throws everything away.**
   `quality.py` requires (a) the niche tokens to appear in the Maps
   `category` text, (b) the location tokens to appear in the address text,
   (c) at least one contact channel, and (d) a quality score ≥ 40. A real
   lead with a complete-but-differently-worded category ("Indian
   restaurant" vs. "restaurants in Islamabad") is rejected, and there is
   nothing to fall back to.

Two secondary problems make every failure look like a deeper bug:

4. **DuckDuckGo HTML is the only fallback** and it's just used to "verify"
   the offline-mode lead, never to generate leads on its own. So when
   Maps is empty, backfill is empty too.
5. **`min_quality_score=40` is the default everywhere** (backend +
   frontend). After the strict hard rejects, almost nothing scores ≥ 40
   from a single source. The relaxed-filter floor only activates if
   `raw_count > 0`, but the typical failure mode is `raw_count == 0`.

Result: Render → Maps → 0 cards → 0 verified → 0 kept. Every time.

---

## 1. The fix in one sentence

Stop relying on browser scraping as the primary source. Make the primary
source pure-HTTP — **OpenStreetMap Overpass + Nominatim** — and treat
Google Maps as one of several optional, best-effort enrichments. Soften the
filter so the work the sources did isn't immediately discarded.

---

## 2. Source mix

| Source | Transport | Role | Required |
|---|---|---|---|
| **OSM Overpass** | HTTPS GET (no key) | Primary — POIs in a bounding box, with `name`, `addr:*`, `contact:phone`, `contact:website`, `contact:email`, `opening_hours` | yes |
| **Nominatim** | HTTPS GET (no key) | Geocode the user's `location` string into a bounding box for Overpass | yes |
| **DuckDuckGo HTML** | HTTPS POST | Backfill candidate names/websites; verify "no website" claim | yes |
| **Google Maps (Playwright)** | Browser | Optional best-effort. If Playwright isn't installed, or Chromium fails to launch, or a navigation throws, log + skip — never abort the run | no |
| **Website fetch** | httpx | Per-lead enrichment of the homepage / `/contact` / `/about` for email + socials + description | yes |

The pipeline must produce a lead set even when only OSM and DDG are
available. Render in production currently has no working Playwright path;
we still need to ship leads from there.

---

## 3. Pipeline contract

```
parse_intent(niche)
  ↓
geocode(location)               → bounding box + country code
  ↓
parallel:
  ├─ osm_search(niche, bbox)    → ScrapedLead[]
  ├─ ddg_search(niche, location)→ ScrapedLead[]
  └─ gmaps_scrape(niche, loc)   → ScrapedLead[]   (best-effort)
  ↓
merge + dedupe (by lower(name) + city + phone/domain)
  ↓
verify_offline_mode (only if require_website=False)
  ↓
filter_and_score                → annotate tier/score/signals
  ↓
enrich_websites (top N kept)    → email, socials, description
  ↓
final_floor                      → if kept==0 and any source returned
                                   ANY rows, keep the top 5 by raw signal
                                   strength with `relaxed_filter=True`
```

Key rules:

- **Zero is unacceptable** when any source returned any rows. Floor to top
  5 by `(has_phone, has_website, rating, reviews)` and surface
  `relaxed_filter=True` so the UI can say "showing best available".
- **Source labels are visible.** Each lead carries `lead.sources = ["osm",
  "duckduckgo", ...]` so the user (and we) can see where it came from.
- **Default `min_quality_score=0`.** The tier (A/B/C/D) does the
  filtering. Hard rejects still drop garbage. The score is a sort key, not
  a cliff.

---

## 4. OSM mapping

`backend/app/scraper/niche_taxonomy.py` maps free-text niches → OSM
tag-value pairs. Examples:

| Niche keyword | OSM tags |
|---|---|
| restaurant, food, dining | `amenity=restaurant`, `amenity=fast_food`, `amenity=cafe` |
| dental, dentist | `amenity=dentist`, `healthcare=dentist` |
| doctor, clinic | `amenity=doctors`, `amenity=clinic`, `healthcare=doctor` |
| hospital | `amenity=hospital` |
| pharmacy, chemist | `amenity=pharmacy`, `healthcare=pharmacy` |
| law firm, lawyer, attorney | `office=lawyer` |
| accountant, accounting | `office=accountant` |
| salon, hair, barber | `shop=hairdresser`, `shop=beauty` |
| gym, fitness | `leisure=fitness_centre`, `sport=fitness` |
| hotel | `tourism=hotel` |
| cafe, coffee | `amenity=cafe` |
| bakery | `shop=bakery` |
| roofer, roofing | `craft=roofer` |
| plumber, plumbing | `craft=plumber` |
| hvac, heating, ac | `craft=hvac` |
| electrician | `craft=electrician` |
| real estate, realtor | `office=estate_agent` |
| auto repair, mechanic | `shop=car_repair`, `amenity=car_repair` |
| car dealer, dealership | `shop=car` |
| gas station, petrol | `amenity=fuel` |
| bank | `amenity=bank` |
| school | `amenity=school` |
| nursery, daycare, childcare | `amenity=childcare`, `amenity=kindergarten` |
| veterinarian, vet | `amenity=veterinary` |

Anything we can't map falls back to a free-text Overpass `name~"<niche>"`
search. That returns less, but it returns *something*.

The Overpass query is bounded by the geocoded bbox + a 50 km radius around
the centroid. Nominatim's `boundingbox` is reused directly. We honor the
public-instance fair-use policy: User-Agent identifies the app, requests
are rate-limited per call, and we cache by `(niche, location)` for 10
minutes inside the process.

---

## 5. Soften the filter

The current `quality.py` is correct in spirit but too strict in practice.
The v2 changes:

1. **Category match.** When the lead came from OSM and the OSM tag is in
   the niche's taxonomy entry, treat the niche as matched — don't run the
   token comparison again. (OSM already proved the match by tag.)
2. **Location match.** If the lead has no parsed address but has a phone
   with a country code that matches the queried country, accept the
   location. If the lead came from OSM and was inside the queried bbox,
   accept the location. Don't reject solely on missing-address.
3. **Contact channel.** Keep the rule: at least one of website/phone/email
   is required. (No exception. A lead with none of those isn't a lead.)
4. **Min score default = 0.** Tier A/B/C/D handles the ranking; only D is
   dropped at the end.
5. **De-dupe is unchanged.** Same phone/domain/normalized-name within a
   batch → drop.

---

## 6. Hard reject list (still strict)

Anything matching any of these is dropped before scoring:

- Empty or 1-character name
- "Permanently closed" / "Temporarily closed"
- Website is a known aggregator/social profile (per `AGGREGATOR_DOMAINS`)
- No contact channel at all
- Rating < 2.5 with ≥ 10 reviews
- Toll-free / spam phone prefix
- Duplicate of an already-kept lead

---

## 7. UI / progress

The job-and-poll flow already in `routes/scrape.py` and `ScrapeForm.jsx`
is fine — keep it. Only the defaults change:

- Default `min_quality_score = 0` in the form (was 40). The slider stays
  but defaults out of the way.
- Show source pills next to each lead (`OSM`, `DDG`, `Maps`).
- Show the empty-state with the actual reason — "OSM returned 0 in this
  area; try a broader niche or a nearby city" — instead of a silent
  spinner-to-zero.

---

## 8. Acceptance

After the rewrite, a clean prod scrape MUST satisfy:

- `restaurants in Islamabad` → ≥ 10 leads from OSM alone, ≥ 5 with phone.
- `dentists in Lahore` → ≥ 10 leads.
- `roofing contractor in Austin, TX` → ≥ 5 leads.
- `restaurants without a website in Islamabad` → ≥ 5 leads, none with a
  verified first-party homepage.
- A query for a nonsense niche → `kept=[]`, clear message, no 500.
- No run takes more than the configured wall-clock.
- No run exits with `kept=0` when *any* source returned ≥ 1 row — the
  relaxed-filter floor must catch it.

---

## 9. What NOT to change

- Auth, Firebase, persistence, Vercel/Render config — out of scope.
- The job-progress + SSE machinery — works, leave it.
- The `AGGREGATOR_DOMAINS` list — already correct after the v1 fix that
  separated platform homepages from customer subdomains.

---

## 10. Order

1. `niche_taxonomy.py` — small map, foundation for everything else.
2. `sources/osm.py` — Nominatim + Overpass + parser → ScrapedLead.
3. `runner.py` — parallel sources + merge + floor.
4. `quality.py` — soften category/location, default min_score=0.
5. `schemas.py` + `types.py` — defaults.
6. Frontend — default `minScore=0`, source pills.
7. Tests for the taxonomy + the OSM parser fixtures.
8. Build + deploy.
