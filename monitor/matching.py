"""Give each package a stable identity and a comparable category.

- canonical_name: fuzzy-matched against names already stored for the same competitor,
  so a small title edit ("... 2026" -> "... 2027") is still the same offer.
- category: activity tags, so offers from different competitors can be compared.
"""
from __future__ import annotations

import re

from rapidfuzz import fuzz, process

SAME_OFFER_SCORE = 90

_ACTIVITIES = {
    "island_hopping": ("island hopping", "island-hopping", "pescador", "nalusuan", "hilutungan", "gilutongan", "caohagan"),
    "whale_shark": ("whale shark", "whaleshark", "oslob"),
    "canyoneering": ("canyoneering", "canyoning", "kawasan"),
    "sardine_run": ("sardine", "moalboal"),
    "sumilon": ("sumilon",),
    "city_tour": ("city tour",),
}
_NOISE = re.compile(r"\b(20\d\d|cebu|tours?|packages?|day|in|the|and|with|from|at|of|a)\b")


def normalize(name: str) -> str:
    text = name.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = _NOISE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def categorize(name: str) -> str:
    text = name.lower()
    tags = sorted(tag for tag, words in _ACTIVITIES.items() if any(w in text for w in words))
    return "+".join(tags) if tags else "other"


_VARIANT_WORDS = {"shared", "joiner", "private", "group", "premium", "vip", "overnight"}


def variant(name: str) -> frozenset[str]:
    """Words and numbers that make two similar names different products."""
    tokens = {t.removesuffix("s") if t.startswith("joiner") else t for t in normalize(name).split()}
    return frozenset(t for t in tokens if t in _VARIANT_WORDS or t.isdigit())


def match_existing(name: str, existing: list[str]) -> str | None:
    """Return the stored canonical name this one matches, or None if it is new."""
    # A shared tour and a private tour are never the same offer, however alike the names.
    existing = [e for e in existing if variant(e) == variant(name)]
    if not existing:
        return None
    target = normalize(name)
    best = process.extractOne(target, {e: normalize(e) for e in existing}, scorer=fuzz.token_sort_ratio)
    if best and best[1] >= SAME_OFFER_SCORE:
        return best[2]
    return None
