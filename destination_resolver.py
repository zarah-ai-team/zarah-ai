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

# Minimal blocklist — only words that are so common they collide every time
# AND are clearly never the user's intended destination. The country-anchor
# filter in find_destinations() handles the rest of the false-positive cleanup
# without needing a giant whitelist/blocklist of city names.
_HARD_BLOCKLIST: Set[str] = {
    # Pronouns / fillers — collide via tiny villages in the DB
    "us", "we", "our", "ours", "they", "them", "their", "theirs",
    "him", "her", "his", "hers", "it", "its", "you", "your", "yours",
    "the", "a", "an", "for", "with", "from", "of", "and", "or",
    # Verbs at sentence start that often capitalize as "Plan", "Estimate"
    "plan", "estimate", "summarize", "calculate", "review", "build",
    "make", "create", "generate", "prepare", "draft", "design", "include",
    "exclude", "send", "give", "share", "show", "tell",
    # Motion / travel verbs that double as obscure village names
    "going", "gone", "coming", "headed", "heading", "fly", "flying",
    "drive", "driving", "walk", "walking", "ride", "riding",
    # Generic travel nouns / fillers that the DB also stores as small villages
    "trip", "tour", "travel", "journey", "route", "destination",
    "hotel", "flight", "taxi", "vehicle", "bus", "train",
    "breakfast", "lunch", "dinner", "meal",
    "night", "day", "week", "month", "year",
    # Months — collide with cities like "March", "May", "August"
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
    # Time / date tokens
    "morning", "afternoon", "evening", "night", "today", "tomorrow",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
    # Trip-style tokens
    "leisure", "corporate", "incentive", "honeymoon", "anniversary",
    "wedding", "vacation", "holiday", "getaway",
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


# Major travel cities curated from the country-state-city package — used to
# allow short single-word capital/iconic destinations like "Tokyo", "Paris",
# "Dubai" that would otherwise be filtered out by the noise rules. Lowercase.
_MAJOR_SINGLE_WORD_CITIES: Set[str] = {
    # Asia
    "tokyo", "kyoto", "osaka", "seoul", "busan", "beijing", "shanghai",
    "bangkok", "phuket", "krabi", "singapore", "manila", "hanoi", "bali",
    "jakarta", "kathmandu", "thimphu", "colombo", "male", "maldives",
    # India
    "mumbai", "delhi", "bangalore", "chennai", "kolkata", "hyderabad",
    "pune", "jaipur", "udaipur", "agra", "varanasi", "amritsar", "shimla",
    "goa", "kochi", "munnar", "darjeeling", "leh",
    # Middle East
    "dubai", "doha", "muscat", "riyadh", "jeddah", "amman", "petra",
    "beirut", "cairo", "luxor", "istanbul", "ankara",
    # Europe
    "london", "paris", "rome", "venice", "florence", "milan", "naples",
    "madrid", "barcelona", "seville", "lisbon", "porto", "amsterdam",
    "berlin", "munich", "hamburg", "vienna", "salzburg", "zurich", "geneva",
    "bern", "interlaken", "prague", "budapest", "warsaw", "krakow",
    "athens", "santorini", "mykonos", "stockholm", "copenhagen", "oslo",
    "helsinki", "reykjavik", "moscow", "edinburgh", "glasgow", "dublin",
    # Americas
    "chicago", "miami", "boston", "seattle", "toronto", "vancouver",
    "montreal", "havana", "rio", "lima", "cusco", "quito",
    # Africa & Oceania
    "marrakech", "casablanca", "fes", "nairobi", "zanzibar",
    "sydney", "melbourne", "brisbane", "perth", "auckland", "queenstown",
}

# Words that look like single-word English nouns and are NEVER acceptable as a
# destination even if some obscure village happens to share the name.
_COMMON_ENGLISH_NOUNS: Set[str] = {
    "tower", "bridge", "abbey", "church", "cathedral", "temple", "mosque",
    "shrine", "monument", "statue", "fountain", "gate", "wall", "fort",
    "castle", "palace", "park", "garden", "square", "plaza", "circle",
    "street", "avenue", "lane", "road", "highway", "boulevard", "drive",
    "thames", "ben", "eye", "wheel", "arena", "stadium", "court", "field",
    "beach", "coast", "shore", "harbour", "harbor", "port", "dock", "pier",
    "lake", "river", "valley", "hill", "mountain", "peak", "ridge", "cliff",
    "forest", "wood", "park", "reserve",
    "tea", "coffee", "wine", "beer", "lunch", "dinner", "brunch",
    "free", "time", "early", "late", "morning", "afternoon", "evening",
    "date", "day", "night", "week", "weekend",
    "city", "town", "village", "centre", "center", "downtown", "old",
    "new", "north", "south", "east", "west", "central", "upper", "lower",
    "high", "low", "big", "small", "long", "short", "wide", "narrow",
    "hard", "soft", "fast", "slow", "quick", "easy",
    "gala", "show", "concert", "festival", "fair", "market",
    "bar", "pub", "club", "lounge", "rooftop", "cafe", "restaurant",
    "hotel", "flight", "taxi", "train", "metro", "bus", "boat", "ferry",
    "cruise",
    # Common short tokens that mis-match
    "hi", "ok", "okay", "yes", "no", "via", "and", "or", "the",
}


@lru_cache(maxsize=1)
def _build_index() -> Tuple[Dict[str, dict], Set[str]]:
    """Build a single lowercase → record index for cities + countries.

    Records look like:
      {"name": "Dubai", "kind": "city", "country_code": "AE"}
      {"name": "Singapore", "kind": "country", "country_code": "SG"}
    """
    index: Dict[str, dict] = {}
    blocked: Set[str] = set(_HARD_BLOCKLIST) | _COMMON_ENGLISH_NOUNS
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

    # Cities — strict filter:
    #   - Multi-word names (e.g. "New York", "Loch Lomond") accepted
    #   - Single-word names accepted ONLY if length ≥ 5 AND in our curated
    #     major-cities list, OR length ≥ 6 (longer single-word cities are
    #     usually real destinations, not common English words).
    # This filters out the ~140k tiny villages with names like "Tower", "Bridge",
    # "Ben", "Tea" that pollute itinerary parsing.
    for city in City.get_cities():
        name = (city.name or "").strip()
        if not name or len(name) < 3:
            continue
        key = name.lower()
        word_count = len(name.split())
        is_major = key in _MAJOR_SINGLE_WORD_CITIES
        is_long_unique = word_count == 1 and len(key) >= 7   # "Marrakech", "Edinburgh"
        is_multi_word = word_count >= 2                       # "Hong Kong", "Loch Lomond"
        if not (is_major or is_long_unique or is_multi_word):
            continue
        _add(key, {"name": name, "kind": "city", "country_code": city.country_code})

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
    Scan `text` for known destinations (cities, states, or countries from the
    country-state-city DB).

    Returns destinations in **document order**, deduped, with shape:
        {"name": "Dubai", "kind": "city", "country_code": "AE",
         "start": 12, "end": 17}

    Filtering policy (using the package's own data — no large hardcoded
    whitelist):
      1. Multi-word names ("Abu Dhabi", "New York") are matched greedily —
         longest window wins.
      2. The FIRST hit in document order anchors a "context country".
      3. Subsequent hits are KEPT only if they share the anchor's country, are
         themselves countries, or have a multi-word name. Single-word obscure
         village hits in unrelated countries (e.g. a Montenegrin town named
         "Bar" appearing because the user wrote "Bar Hopping") are dropped.
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
            found.append({**rec, "name_words": w, "start": start, "end": end})
            for j in range(i, i + w):
                consumed[j] = True
            break

    if not found:
        return []

    # ── Country-anchored filter ───────────────────────────────────────────
    # The first detected destination establishes the anchor country. Keep
    # later hits that fit any of:
    #    - same country as the anchor (sister cities of the main destination)
    #    - country-level hits anywhere (multi-country trips: "Italy and France")
    #    - multi-word matches (less likely to be false positives)
    anchor_cc = found[0].get("country_code") or ""
    anchor_kind = found[0].get("kind")
    out: List[dict] = []
    seen: Set[str] = set()
    for r in found:
        key = r["name"].lower()
        if key in seen:
            continue
        if out:
            cc = r.get("country_code") or ""
            kind = r.get("kind")
            words = r.get("name_words", 1)
            if not (
                cc == anchor_cc
                or kind == "country"
                or anchor_kind == "country"
                or words >= 2
            ):
                continue
        seen.add(key)
        # Strip the bookkeeping field before returning
        rec = {k: v for k, v in r.items() if k != "name_words"}
        out.append(rec)
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
