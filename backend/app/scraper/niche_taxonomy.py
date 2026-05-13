"""Niche string -> OSM tag mapping + display synonyms.

Keeps `osm.py` free of business-logic guesswork. When a user types
"dental clinic" we want the OSM query to look for `amenity=dentist`
and `healthcare=dentist`, not a free-text name match.

Anything we can't map falls through to a free-text `name~"<niche>"`
search in OSM. That's a worse query, but it returns *something* — the
v1 pipeline returned nothing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class NicheMatch:
    """Recognized niche -> OSM tag plan + canonical display name."""
    canonical: str           # human label, e.g. "dentist"
    tags: tuple[tuple[str, str], ...]  # OSM (key, value) pairs to OR over
    synonyms: tuple[str, ...]  # tokens that count as a category match


# Order matters: more specific entries first so "dental clinic" matches
# `dentist` before falling through to the generic `clinic` entry.
_TAXONOMY: list[tuple[tuple[str, ...], NicheMatch]] = [
    # ---- food / hospitality ----
    (("restaurant", "restaurants", "dining", "eatery", "diner"),
     NicheMatch("restaurant",
                (("amenity", "restaurant"), ("amenity", "fast_food")),
                ("restaurant", "fast food", "diner", "eatery"))),
    (("cafe", "café", "coffee", "coffee shop", "coffeehouse"),
     NicheMatch("cafe",
                (("amenity", "cafe"),),
                ("cafe", "coffee"))),
    (("bakery", "bakeries"),
     NicheMatch("bakery",
                (("shop", "bakery"),),
                ("bakery",))),
    (("bar", "pub", "pubs", "tavern"),
     NicheMatch("bar",
                (("amenity", "bar"), ("amenity", "pub")),
                ("bar", "pub", "tavern"))),
    (("hotel", "hotels", "lodging"),
     NicheMatch("hotel",
                (("tourism", "hotel"), ("tourism", "guest_house")),
                ("hotel", "lodging", "guest house"))),

    # ---- healthcare ----
    (("dental", "dentist", "dentists", "orthodontist"),
     NicheMatch("dentist",
                (("amenity", "dentist"), ("healthcare", "dentist")),
                ("dental", "dentist", "orthodontist"))),
    (("doctor", "doctors", "physician", "gp", "general practitioner"),
     NicheMatch("doctor",
                (("amenity", "doctors"), ("healthcare", "doctor")),
                ("doctor", "physician", "clinic"))),
    (("clinic", "clinics", "medical clinic", "polyclinic"),
     NicheMatch("clinic",
                (("amenity", "clinic"), ("healthcare", "clinic")),
                ("clinic", "polyclinic", "medical"))),
    (("hospital", "hospitals"),
     NicheMatch("hospital",
                (("amenity", "hospital"),),
                ("hospital",))),
    (("pharmacy", "chemist", "drugstore"),
     NicheMatch("pharmacy",
                (("amenity", "pharmacy"), ("healthcare", "pharmacy")),
                ("pharmacy", "chemist", "drugstore"))),
    (("optician", "optometrist", "eye doctor"),
     NicheMatch("optician",
                (("shop", "optician"), ("healthcare", "optometrist")),
                ("optician", "optometrist"))),
    (("veterinarian", "vet", "vets", "animal hospital"),
     NicheMatch("veterinarian",
                (("amenity", "veterinary"),),
                ("vet", "veterinary", "animal"))),
    (("physiotherapist", "physio", "physical therapy"),
     NicheMatch("physio",
                (("healthcare", "physiotherapist"),),
                ("physio", "physical therapy"))),

    # ---- professional services ----
    (("law firm", "lawyer", "lawyers", "attorney", "advocate", "barrister", "solicitor"),
     NicheMatch("lawyer",
                (("office", "lawyer"),),
                ("law", "lawyer", "attorney", "legal"))),
    (("accountant", "accounting", "tax preparer", "tax preparation", "cpa"),
     NicheMatch("accountant",
                (("office", "accountant"), ("office", "tax_advisor")),
                ("accounting", "accountant", "tax", "cpa"))),
    (("real estate", "realtor", "real estate agent", "estate agent", "property dealer"),
     NicheMatch("real_estate",
                (("office", "estate_agent"),),
                ("real estate", "realtor", "estate agent", "property"))),
    (("insurance", "insurance agent", "insurance broker"),
     NicheMatch("insurance",
                (("office", "insurance"),),
                ("insurance",))),
    (("architect", "architecture firm"),
     NicheMatch("architect",
                (("office", "architect"),),
                ("architect",))),
    (("marketing agency", "marketing", "advertising agency", "ad agency"),
     NicheMatch("marketing",
                (("office", "advertising_agency"), ("office", "marketing")),
                ("marketing", "advertising", "agency"))),
    (("consultant", "consulting", "consultancy"),
     NicheMatch("consulting",
                (("office", "consulting"),),
                ("consulting", "consultant"))),

    # ---- trades ----
    (("roofing", "roofer", "roof repair"),
     NicheMatch("roofer",
                (("craft", "roofer"),),
                ("roofing", "roofer"))),
    (("plumber", "plumbing"),
     NicheMatch("plumber",
                (("craft", "plumber"),),
                ("plumber", "plumbing"))),
    (("electrician", "electrical contractor"),
     NicheMatch("electrician",
                (("craft", "electrician"),),
                ("electrician", "electrical"))),
    (("hvac", "heating", "air conditioning", "ac repair"),
     NicheMatch("hvac",
                (("craft", "hvac"),),
                ("hvac", "heating", "air conditioning"))),
    (("painter", "painting contractor"),
     NicheMatch("painter",
                (("craft", "painter"),),
                ("painter", "painting"))),
    (("carpenter", "carpentry"),
     NicheMatch("carpenter",
                (("craft", "carpenter"),),
                ("carpenter", "carpentry"))),
    (("contractor", "general contractor", "builder"),
     NicheMatch("contractor",
                (("office", "construction_company"), ("craft", "builder")),
                ("contractor", "construction", "builder"))),

    # ---- automotive ----
    (("auto repair", "mechanic", "car repair", "garage"),
     NicheMatch("auto_repair",
                (("shop", "car_repair"),),
                ("auto repair", "mechanic", "garage"))),
    (("car dealer", "car dealership", "auto dealer", "used cars"),
     NicheMatch("car_dealer",
                (("shop", "car"),),
                ("car dealer", "dealership"))),
    (("gas station", "petrol", "petrol pump", "fuel station"),
     NicheMatch("gas_station",
                (("amenity", "fuel"),),
                ("gas station", "petrol", "fuel"))),

    # ---- beauty / fitness ----
    (("salon", "hair", "hairdresser", "hair salon", "barber", "barbershop"),
     NicheMatch("salon",
                (("shop", "hairdresser"), ("shop", "beauty")),
                ("salon", "hair", "barber", "beauty"))),
    (("spa", "med spa", "massage"),
     NicheMatch("spa",
                (("leisure", "spa"), ("shop", "beauty")),
                ("spa", "massage"))),
    (("gym", "fitness", "fitness center", "fitness centre", "personal trainer"),
     NicheMatch("gym",
                (("leisure", "fitness_centre"), ("sport", "fitness")),
                ("gym", "fitness"))),
    (("yoga", "yoga studio"),
     NicheMatch("yoga",
                (("leisure", "fitness_centre"), ("sport", "yoga")),
                ("yoga",))),

    # ---- retail / misc ----
    (("supermarket", "grocery", "grocery store"),
     NicheMatch("supermarket",
                (("shop", "supermarket"), ("shop", "convenience")),
                ("supermarket", "grocery"))),
    (("clothing store", "boutique", "fashion store"),
     NicheMatch("clothing",
                (("shop", "clothes"), ("shop", "boutique")),
                ("clothing", "boutique", "fashion"))),
    (("jewelry", "jeweller", "jeweler"),
     NicheMatch("jewelry",
                (("shop", "jewelry"),),
                ("jewelry", "jeweller"))),
    (("bookstore", "book store"),
     NicheMatch("bookstore",
                (("shop", "books"),),
                ("bookstore", "books"))),
    (("furniture store", "furniture"),
     NicheMatch("furniture",
                (("shop", "furniture"),),
                ("furniture",))),
    (("hardware store", "hardware"),
     NicheMatch("hardware",
                (("shop", "hardware"), ("shop", "doityourself")),
                ("hardware",))),
    (("pet store", "pet shop"),
     NicheMatch("pet_store",
                (("shop", "pet"),),
                ("pet store", "pet shop"))),

    # ---- finance ----
    (("bank", "banks", "bank branch"),
     NicheMatch("bank",
                (("amenity", "bank"),),
                ("bank",))),
    (("atm", "atms"),
     NicheMatch("atm",
                (("amenity", "atm"),),
                ("atm",))),

    # ---- education / childcare ----
    (("school", "schools"),
     NicheMatch("school",
                (("amenity", "school"),),
                ("school",))),
    (("preschool", "kindergarten"),
     NicheMatch("kindergarten",
                (("amenity", "kindergarten"),),
                ("preschool", "kindergarten"))),
    (("daycare", "child care", "childcare", "nursery"),
     NicheMatch("daycare",
                (("amenity", "childcare"), ("amenity", "kindergarten")),
                ("daycare", "childcare", "nursery"))),
    (("driving school",),
     NicheMatch("driving_school",
                (("amenity", "driving_school"),),
                ("driving school",))),

    # ---- travel ----
    (("travel agency", "travel agent"),
     NicheMatch("travel_agency",
                (("shop", "travel_agency"), ("office", "travel_agent")),
                ("travel agency", "travel agent"))),
]


_DEFAULT_RADIUS_KM = 25.0


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def match_niche(niche: str | None) -> NicheMatch | None:
    """Match a free-text niche to a taxonomy entry, or None.

    Match is case-insensitive and ignores punctuation. We scan keyword
    lists in the order they appear above (most specific first). Returns
    the first match. If nothing matches, the caller falls back to a
    free-text Overpass `name` search.
    """
    if not niche:
        return None
    n = _normalize(niche)
    for keywords, match in _TAXONOMY:
        for kw in keywords:
            if re.search(rf"\b{re.escape(kw)}\b", n):
                return match
    return None


def synonyms_for(niche: str | None) -> tuple[str, ...]:
    """Return tokens that count as a category match for this niche.

    Used by `quality.category_matches_niche` to soften the match: a Maps
    `category` of "Indian restaurant" should still match a niche of
    "restaurants in Islamabad".
    """
    m = match_niche(niche)
    if m:
        return m.synonyms
    return ()


def default_radius_km() -> float:
    return _DEFAULT_RADIUS_KM


__all__ = [
    "NicheMatch",
    "match_niche",
    "synonyms_for",
    "default_radius_km",
]
