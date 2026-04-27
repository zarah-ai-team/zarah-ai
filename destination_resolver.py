"""destination_resolver.py
Database-backed destination extraction using `country-state-city`.

Loads ~250 countries and ~147k cities into an in-memory lookup on first use,
then scans free-text queries for any matching name (1- to 4-word windows) and
returns them in document order. Supports multi-destination route detection
("Dubai → Abu Dhabi", "Italy and France", etc.).
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# These tokens are NEVER destinations, even if they collide with city/town names
# in the database (e.g. "Industry" is a town in California, "Plan" is a village
# in Spain, "Retreat" is a town in Jamaica). Without this list, queries like
# "Plan a trip" or "Estimate the cost" extract nonsense destinations.
_HARD_BLOCKLIST: Set[str] = {
    # Common ambiguous DB-collision city names
    "industry", "victory", "service", "average", "summary", "review",
    "retreat", "plan", "estimate", "request", "client", "guest", "person",
    "people", "group", "family", "couple", "trip", "tour", "travel",
    "journey", "route", "include", "exclude", "happy", "lovely", "luxury",
    "deluxe", "premium", "deals", "deal", "offer", "of", "and", "or",
    # English verbs + adjectives that double as obscure city names in the DB
    "going", "gone", "going", "coming", "headed", "heading",
    "fly", "flying", "drive", "driving", "walk", "walking",
    "long", "short", "big", "small", "quick", "fast", "slow",
    "solo", "alone", "together", "couple", "single",
    "year", "month", "week", "day", "hour", "minute", "second",
    # Pronouns / short fillers (DB also has these as obscure towns)
    "us", "we", "our", "ours", "they", "them", "their", "theirs",
    "him", "her", "his", "hers", "it", "its", "you", "your", "yours",
    # Time / date tokens
    "morning", "afternoon", "evening", "night", "today", "tomorrow",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
    # Trip-style tokens
    "leisure", "corporate", "incentive", "honeymoon", "anniversary",
    "wedding", "vacation", "holiday", "getaway",
    # Hotel/amenity descriptors that collide with obscure DB city names
    # (Star, ID; Date, Hokkaido; Beach, ND; Pool, Dorset; Spa, Belgium)
    "star", "date", "beach", "pool", "spa",
    # Meals / categories
    "breakfast", "lunch", "dinner", "meal", "vegetarian", "vegan", "halal",
    "kosher", "snack", "drink",
    # Transport / accommodation
    "hotel", "flight", "taxi", "car", "vehicle", "bus", "train", "metro",
    "lexus", "mercedes", "bmw", "ferrari",
    # Common verbs / fillers / pronouns
    "no", "yes", "ok", "okay", "thanks", "thank", "please", "kindly",
    "make", "build", "generate", "create", "prepare", "draft", "design",
    "give", "show", "tell", "send", "find", "share", "summarize", "calculate",
    "compute", "this", "that", "these", "those", "here", "there", "every",
    "all", "some", "any", "the", "a", "an", "for", "with", "from", "to",
    "in", "on", "at", "by", "during", "over", "between", "across",
}

# Suffixes commonly attached to administrative regions in the DB; strip these
# when indexing so "Abu Dhabi Emirate" can be matched simply as "Abu Dhabi".
_REGION_SUFFIXES = (
    " emirate", " emirates", " province", " state", " region", " district",
    " governorate", " county", " department", " prefecture", " municipality",
)

# Common acronyms / aliases that the underlying DB stores under longer names.
_ALIASES: Dict[str, str] = {
    "uae": "United Arab Emirates",
    "u.a.e": "United Arab Emirates",
    "u.a.e.": "United Arab Emirates",
    "usa": "United States",
    "u.s.a": "United States",
    "u.s.a.": "United States",
    "us": "United States",
    "uk": "United Kingdom",
    "u.k": "United Kingdom",
    "u.k.": "United Kingdom",
}


@lru_cache(maxsize=1)
def _build_index() -> Tuple[Dict[str, dict], Set[str]]:
    """Build a single lowercase → record index for cities + countries.

    Records look like:
      {"name": "Dubai", "kind": "city", "country_code": "AE"}
      {"name": "Singapore", "kind": "country", "country_code": "SG"}
    """
    index: Dict[str, dict] = {}
    blocked: Set[str] = set(_HARD_BLOCKLIST)
    try:
        from country_state_city import City, Country, State
    except Exception as e:
        logger.warning("country-state-city not available: %s — destination index empty", e)
        return index, blocked

    def _add(key: str, rec: dict) -> None:
        if not key or len(key) < 2 or key in blocked or key in index:
            return
        index[key] = rec

    for c in Country.get_countries():
        _add(c.name.strip().lower(), {"name": c.name, "kind": "country", "country_code": c.iso2})

    # Aliases (UAE → United Arab Emirates etc.)
    for alias, canonical in _ALIASES.items():
        if canonical.lower() in index:
            rec = dict(index[canonical.lower()])
            rec["name"] = alias.upper() if len(alias) <= 5 else canonical
            _add(alias, rec)

    # States/regions — strip "Emirate"/"Province"/"State" suffixes so the DB's
    # "Abu Dhabi Emirate" is matchable as just "Abu Dhabi".
    for s in State.get_states():
        raw = (s.name or "").strip()
        if not raw or len(raw) < 2:
            continue
        names_to_add = [raw]
        low = raw.lower()
        for suf in _REGION_SUFFIXES:
            if low.endswith(suf):
                names_to_add.append(raw[: -len(suf)].strip())
                break
        for name in names_to_add:
            _add(name.lower(), {"name": name, "kind": "city", "country_code": s.country_code})

    # Cities — many duplicates across countries; keep the FIRST occurrence so
    # well-known names like "Paris" → Paris, France, not Paris, Texas.
    for city in City.get_cities():
        name = (city.name or "").strip()
        if not name or len(name) < 3:
            continue
        _add(name.lower(), {"name": name, "kind": "city", "country_code": city.country_code})

    logger.info("destination_resolver index built: %d entries", len(index))
    return index, blocked


def _tokenize(text: str) -> List[Tuple[str, int, int]]:
    """Tokenise text preserving original case and span; returns list of
    (token, start, end). Strips punctuation but keeps the token's original
    string so we can preserve casing in the final output."""
    tokens: List[Tuple[str, int, int]] = []
    for m in re.finditer(r"[A-Za-z][A-Za-z'\.]*", text):
        tokens.append((m.group(0), m.start(), m.end()))
    return tokens


def find_destinations(text: str, max_window: int = 4) -> List[dict]:
    """
    Scan `text` for known destinations (cities or countries from the DB).

    Returns destinations in **document order**, deduped, with shape:
        {"name": "Dubai", "kind": "city", "country_code": "AE",
         "start": 12, "end": 17}

    Multi-word names ("Abu Dhabi", "New York", "Hong Kong") are matched
    greedily — the longest window match wins at each position.
    """
    if not text:
        return []
    index, blocked = _build_index()
    if not index:
        return []

    tokens = _tokenize(text)
    if not tokens:
        return []

    # 'consumed' marks token indices already absorbed by a longer match so we
    # don't return both "Hong" and "Hong Kong".
    consumed = [False] * len(tokens)
    found: List[dict] = []

    for i in range(len(tokens)):
        if consumed[i]:
            continue
        # Try longest window first
        for w in range(min(max_window, len(tokens) - i), 0, -1):
            window = " ".join(t[0] for t in tokens[i:i + w])
            key = window.lower()
            if key in blocked:
                continue
            rec = index.get(key)
            if not rec:
                continue
            start = tokens[i][1]
            end = tokens[i + w - 1][2]
            found.append({**rec, "start": start, "end": end})
            for j in range(i, i + w):
                consumed[j] = True
            break

    # Dedupe by name while preserving order
    seen: Set[str] = set()
    out: List[dict] = []
    for r in found:
        key = r["name"].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def detect_route(text: str) -> dict:
    """
    Detect destinations + the *nature of the route* from a free-text query.

    Returns:
        {
          "destinations": ["Dubai", "Abu Dhabi"],     # canonical names, ordered
          "primary":      "Dubai",
          "is_multi":     True,
          "route_str":    "Dubai → Abu Dhabi",
          "kind":         "city" | "country" | "mixed",
          "raw":          [<full records>],
        }
    """
    records = find_destinations(text)
    names = [r["name"] for r in records]
    kinds = {r["kind"] for r in records}
    kind = next(iter(kinds)) if len(kinds) == 1 else ("mixed" if kinds else "")
    return {
        "destinations": names,
        "primary": names[0] if names else None,
        "is_multi": len(names) > 1,
        "route_str": " → ".join(names),
        "kind": kind,
        "raw": records,
    }


def is_known_destination(name: str) -> bool:
    """O(1) check used by the conversation manager / formal parser."""
    if not name:
        return False
    index, blocked = _build_index()
    key = name.strip().lower()
    if key in blocked:
        return False
    return key in index


if __name__ == "__main__":
    samples = [
        "Estimate the total trip cost per person for this Dubai corporate retreat",
        "Plan a 5-day trip to Singapore for 4 pax leisure",
        "Make me a 10-day Italy + France trip",
        "3 nights in UAE then 2 nights in Oman for 4 pax",
        "Dubai → Abu Dhabi → Sharjah for 7 nights",
        "Anniversary trip in March 2026 to Tokyo, Kyoto, and Osaka",
    ]
    for s in samples:
        out = detect_route(s)
        print(f"  {s[:60]!r:65}")
        print(f"    -> {out['route_str']}  (kind={out['kind']}, multi={out['is_multi']})")
