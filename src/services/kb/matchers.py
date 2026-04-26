"""
Regex-based matchers for extracting structured values from free-form client text.
All functions are pure and unit-testable — no I/O, no LLM dependency.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

# ── Known world tourism cities (normalised Title Case) ─────────────────────
# Used for destination detection in free text.
KNOWN_CITIES: Dict[str, str] = {
    # Central & Eastern Europe
    "budapest": "Budapest", "prague": "Prague", "vienna": "Vienna",
    "wien": "Vienna", "praga": "Prague", "prag": "Prague",
    "bratislava": "Bratislava", "warsaw": "Warsaw", "krakow": "Krakow",
    "cracow": "Krakow", "wroclaw": "Wroclaw", "gdansk": "Gdansk",
    "zagreb": "Zagreb", "dubrovnik": "Dubrovnik", "split": "Split",
    "Ljubljana": "Ljubljana", "bled": "Bled", "sarajevo": "Sarajevo",
    "bucharest": "Bucharest", "sofia": "Sofia", "belgrade": "Belgrade",
    "tallinn": "Tallinn", "riga": "Riga", "vilnius": "Vilnius",
    "helsinki": "Helsinki", "stockholm": "Stockholm", "oslo": "Oslo",
    "copenhagen": "Copenhagen",
    # Western Europe
    "paris": "Paris", "london": "London", "amsterdam": "Amsterdam",
    "brussels": "Brussels", "zurich": "Zurich", "geneva": "Geneva",
    "bern": "Bern", "basel": "Basel", "interlaken": "Interlaken",
    "lucerne": "Lucerne", "grindelwald": "Grindelwald", "zermatt": "Zermatt",
    "rome": "Rome", "milan": "Milan", "venice": "Venice", "florence": "Florence",
    "naples": "Naples", "amalfi": "Amalfi", "cinque terre": "Cinque Terre",
    "barcelona": "Barcelona", "madrid": "Madrid", "seville": "Seville",
    "granada": "Granada", "malaga": "Malaga", "valencia": "Valencia",
    "lisbon": "Lisbon", "porto": "Porto", "algarve": "Algarve",
    "berlin": "Berlin", "munich": "Munich", "frankfurt": "Frankfurt",
    "hamburg": "Hamburg", "cologne": "Cologne", "heidelberg": "Heidelberg",
    "salzburg": "Salzburg", "innsbruck": "Innsbruck", "hallstatt": "Hallstatt",
    "reykjavik": "Reykjavik",
    # Middle East
    "dubai": "Dubai", "abu dhabi": "Abu Dhabi", "sharjah": "Sharjah",
    "doha": "Doha", "riyadh": "Riyadh", "muscat": "Muscat",
    "amman": "Amman", "petra": "Petra", "jerusalem": "Jerusalem",
    "tel aviv": "Tel Aviv", "beirut": "Beirut", "istanbul": "Istanbul",
    # Asia
    "singapore": "Singapore", "bangkok": "Bangkok", "phuket": "Phuket",
    "chiang mai": "Chiang Mai", "krabi": "Krabi", "koh samui": "Koh Samui",
    "bali": "Bali", "jakarta": "Jakarta", "yogyakarta": "Yogyakarta",
    "kuala lumpur": "Kuala Lumpur", "kl": "Kuala Lumpur", "penang": "Penang",
    "hong kong": "Hong Kong", "macau": "Macau",
    "tokyo": "Tokyo", "osaka": "Osaka", "kyoto": "Kyoto", "hiroshima": "Hiroshima",
    "seoul": "Seoul", "busan": "Busan",
    "beijing": "Beijing", "shanghai": "Shanghai", "guangzhou": "Guangzhou",
    "taipei": "Taipei",
    "colombo": "Colombo", "kandy": "Kandy", "sigiriya": "Sigiriya",
    "kathmandu": "Kathmandu", "pokhara": "Pokhara",
    "male": "Maldives", "maldives": "Maldives",
    "yangon": "Yangon", "bagan": "Bagan", "mandalay": "Mandalay",
    "hanoi": "Hanoi", "ho chi minh": "Ho Chi Minh City", "saigon": "Ho Chi Minh City",
    "da nang": "Da Nang", "hoi an": "Hoi An", "halong bay": "Halong Bay",
    "siem reap": "Siem Reap", "phnom penh": "Phnom Penh",
    "dhaka": "Dhaka",
    # Indian subcontinent
    "delhi": "Delhi", "new delhi": "Delhi", "mumbai": "Mumbai",
    "bombay": "Mumbai", "goa": "Goa", "jaipur": "Jaipur",
    "agra": "Agra", "varanasi": "Varanasi", "udaipur": "Udaipur",
    "jodhpur": "Jodhpur", "amritsar": "Amritsar", "shimla": "Shimla",
    "manali": "Manali", "leh": "Leh", "ladakh": "Ladakh",
    "kerala": "Kerala", "kochi": "Kochi", "munnar": "Munnar",
    "bangalore": "Bengaluru", "bengaluru": "Bengaluru",
    "hyderabad": "Hyderabad", "chennai": "Chennai",
    "kolkata": "Kolkata", "calcutta": "Kolkata",
    # Africa
    "cairo": "Cairo", "luxor": "Luxor", "aswan": "Aswan",
    "marrakech": "Marrakech", "casablanca": "Casablanca", "fez": "Fez",
    "nairobi": "Nairobi", "mombasa": "Mombasa", "zanzibar": "Zanzibar",
    "cape town": "Cape Town", "johannesburg": "Johannesburg", "durban": "Durban",
    "victoria falls": "Victoria Falls",
    # Americas
    "new york": "New York", "los angeles": "Los Angeles", "chicago": "Chicago",
    "san francisco": "San Francisco", "las vegas": "Las Vegas",
    "miami": "Miami", "orlando": "Orlando", "washington": "Washington DC",
    "toronto": "Toronto", "vancouver": "Vancouver", "montreal": "Montreal",
    "cancun": "Cancun", "mexico city": "Mexico City",
    "rio de janeiro": "Rio de Janeiro", "rio": "Rio de Janeiro",
    "sao paulo": "São Paulo", "buenos aires": "Buenos Aires",
    "lima": "Lima", "cusco": "Cusco", "machu picchu": "Machu Picchu",
    # Pacific
    "sydney": "Sydney", "melbourne": "Melbourne", "brisbane": "Brisbane",
    "cairns": "Cairns", "gold coast": "Gold Coast",
    "auckland": "Auckland", "queenstown": "Queenstown", "christchurch": "Christchurch",
    "fiji": "Fiji",
    # Countries used as destinations
    "switzerland": "Switzerland", "maldives": "Maldives",
    "bhutan": "Bhutan", "nepal": "Nepal",
    "oman": "Oman", "jordan": "Jordan",
    "kenya": "Kenya", "tanzania": "Tanzania",
    "egypt": "Egypt", "morocco": "Morocco",
}

# Words that are NOT destinations despite being capitalised
_STOP_WORDS = {
    "tour", "trip", "night", "nights", "day", "days", "hotel", "hotels",
    "package", "itinerary", "room", "rooms", "double", "twin", "single",
    "adult", "adults", "senior", "seniors", "child", "children", "infant",
    "star", "deluxe", "luxury", "budget", "meal", "breakfast", "lunch",
    "dinner", "transfer", "transport", "guide", "sightseeing", "excursion",
    "optional", "mandatory", "departure", "arrival", "flight", "visa",
    "insurance", "need", "please", "dear", "yash", "sir", "madam",
    "regards", "thanks", "hello", "hi", "kindly", "request", "support",
    "suggestive", "extension", "plan", "overview", "requirement",
    "preferably", "preferred", "similar", "approximately", "approx",
    "surface", "road", "drive", "fly", "train", "coach", "bus", "van",
    "mercedes", "viano", "innova", "toyota", "private", "shared",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
    "indian", "hindi", "english", "driver", "speaking",
    "comfortable", "relaxed", "minimal", "walking", "pacing", "pace",
    "accessible", "wheelchair", "friendly",
    "centre", "center", "central", "city",
}


# ── Destination detection ───────────────────────────────────────────────────

def extract_destinations_from_text(text: str) -> List[str]:
    """
    Finds all travel destinations mentioned in text.

    Primary:   KNOWN_CITIES lookup (reliable — no false positives)
    Secondary: Route arrow ordering (Budapest → Prague → Vienna)

    We intentionally do NOT accept arbitrary proper nouns because
    that produces too many false positives (e.g. "Yash", "Indian", "Schönbrunn").
    """
    found: Dict[str, int] = {}   # canonical_name → first char position
    text_lower = text.lower()

    # ── Primary: scan all known cities (longest first avoids partial matches) ──
    for city_key in sorted(KNOWN_CITIES.keys(), key=lambda x: -len(x)):
        pattern = r"\b" + re.escape(city_key) + r"\b"
        m = re.search(pattern, text_lower)
        if m:
            canonical = KNOWN_CITIES[city_key]
            # Deduplicate (e.g. "Wien" and "Vienna" both → "Vienna")
            if not any(v.lower() == canonical.lower() for v in found):
                found[canonical] = m.start()

    if not found:
        return []

    # Sort by first appearance
    ordered = [city for city, _ in sorted(found.items(), key=lambda x: x[1])]

    # ── Secondary: try to re-order by explicit route arrow ────────────────────
    route_order = _extract_route_order(text, ordered)
    if route_order:
        return route_order

    return ordered


def _extract_route_order(text: str, cities: List[str]) -> List[str]:
    """
    If the text contains a 'Route: A → B → C' or 'A → B → C' line,
    return cities in that travel order. Only returns a value if ALL
    found cities appear in the arrow chain (no silent drops).
    """
    # Look for explicit "Route:" line first
    for pattern in [
        r"route\s*[:–\-]\s*(.+?)(?:\n|$)",
        r"([A-Z][a-z]+(?:\s*[→\-–>]+\s*[A-Z][a-z]+){2,})",
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            continue
        segment = m.group(1)
        parts = re.split(r"[→\-–>]|\bto\b|\bvia\b", segment, flags=re.IGNORECASE)
        route_cities: List[str] = []
        text_lower = text.lower()
        for part in parts:
            part_lower = part.strip().lower()
            for city_key in sorted(KNOWN_CITIES.keys(), key=lambda x: -len(x)):
                if re.search(r"\b" + re.escape(city_key) + r"\b", part_lower):
                    canonical = KNOWN_CITIES[city_key]
                    if canonical in cities and canonical not in route_cities:
                        route_cities.append(canonical)
                    break
        # Accept if it covers at least the majority of found cities
        if len(route_cities) >= max(len(cities) - 1, 1):
            # Add any cities not in the route at the end
            for c in cities:
                if c not in route_cities:
                    route_cities.append(c)
            return route_cities

    return []


# ── Pax extraction ─────────────────────────────────────────────────────────

_WORD_NUMS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12,
}


def _word_or_digit(s: str) -> Optional[int]:
    s = s.strip().lower()
    if s.isdigit():
        return int(s)
    return _WORD_NUMS.get(s)


def extract_pax(text: str) -> Tuple[int, int, int]:
    """Returns (total_adults, seniors, children)."""
    t = text.lower()
    adults = 0
    seniors = 0
    children = 0

    # "4 adults (2 senior citizens)" | "4 adults, 2 seniors"
    m = re.search(
        r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+adults?",
        t
    )
    if m:
        adults = _word_or_digit(m.group(1)) or 0

    # "2 senior citizens" | "2 seniors" | "2 sr citizens"
    m = re.search(
        r"(\d+|one|two|three|four|five|six)\s+senior(?:\s+citizen)?s?",
        t
    )
    if m:
        seniors = _word_or_digit(m.group(1)) or 0

    # "group of 4" | "4 pax" | "party of 6"
    if adults == 0:
        m = re.search(
            r"(?:group|party|total)\s+of\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)",
            t
        )
        if m:
            adults = _word_or_digit(m.group(1)) or 0

    if adults == 0:
        m = re.search(
            r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+pax",
            t
        )
        if m:
            adults = _word_or_digit(m.group(1)) or 0

    # "2 children" | "1 child" | "1 infant" | "2 kids"
    m = re.search(
        r"(\d+|one|two|three|four)\s+(?:child(?:ren)?|infant|kid)",
        t
    )
    if m:
        children = _word_or_digit(m.group(1)) or 0

    # Fallback: if only pax number found with no "adults" keyword
    if adults == 0:
        m = re.search(
            r"(?:for|total)\s+(\d+)\s+(?:person|people|travell?er)",
            t
        )
        if m:
            adults = int(m.group(1))

    # Ensure seniors <= adults
    if seniors > adults > 0:
        adults = seniors
    if adults == 0:
        adults = 2  # sensible default

    return adults, min(seniors, adults), children


# ── Nights / duration extraction ────────────────────────────────────────────

def extract_total_nights(text: str) -> Optional[int]:
    t = text.lower()

    # Priority 1: explicit "total duration / total nights" line
    m = re.search(r"total\s+(?:duration|nights?)\s*[:–\-]\s*(\d+)(?:\s*[-–]\s*\d+)?", t)
    if m:
        return int(m.group(1))

    # Priority 2: "XN/YD" tour-code format
    m = re.search(r"(\d+)\s*n\s*/\s*(\d+)\s*d\b", t)
    if m:
        return int(m.group(1))

    # Priority 3: sum of per-city nights if multiple cities stated
    # e.g. "Prague: 4 nights ... Vienna: 3 nights" → 7
    city_nights = re.findall(r"[a-z]+\s*[:–\-]\s*(\d+)\s*(?:[-–]\s*\d+\s*)?nights?", t)
    if len(city_nights) >= 2:
        total = sum(int(n) for n in city_nights)
        if total >= 3:
            return total

    # Priority 4: plain "X nights" (take the LARGEST single mention)
    all_mentions = re.findall(r"(\d+)\s*(?:[-–]\s*\d+\s*)?nights?", t)
    if all_mentions:
        return max(int(n) for n in all_mentions)

    # Priority 5: "X days" → X-1 nights
    m = re.search(r"(\d+)\s+days?", t)
    if m:
        return max(1, int(m.group(1)) - 1)

    # Word numbers: "seven nights"
    for word, val in _WORD_NUMS.items():
        if re.search(rf"\b{word}\s+nights?\b", t):
            return val

    return None


def extract_nights_per_city(text: str, destinations: List[str]) -> Dict[str, int]:
    result: Dict[str, int] = {}
    t = text.lower()
    for city in destinations:
        cl = city.lower()
        patterns = [
            rf"{re.escape(cl)}\s*[:–\-]\s*(\d+)(?:\s*[-–]\s*\d+)?\s*nights?",
            rf"(\d+)(?:\s*[-–]\s*\d+)?\s*nights?\s+(?:in\s+|at\s+)?{re.escape(cl)}",
            rf"{re.escape(cl)}[^\n.]*?(\d+)\s*nights?",
        ]
        for pat in patterns:
            m = re.search(pat, t)
            if m:
                result[city] = int(m.group(1))
                break
    return result


# ── Date extraction ────────────────────────────────────────────────────────

_MONTHS = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
_ORDINAL = r"\d{1,2}(?:st|nd|rd|th)?"


def extract_start_date(text: str) -> Optional[str]:
    """Returns ISO date string or None."""
    patterns = [
        # "from 30th June 2025" | "from 30 June"
        rf"(?:from|starting|start\s+date)\s+({_ORDINAL}\s+{_MONTHS}\s*(?:\d{{4}})?)",
        # "check-in 30 June" | "departing 30th June 2025"
        rf"(?:check[\s-]?in|depart\w*|arriv\w*|travel\s+date)\s+(?:on\s+)?({_ORDINAL}\s+{_MONTHS}\s*(?:\d{{4}})?)",
        # Day 1 (30 June): pattern
        rf"[Dd]ay\s+1\s*\({_ORDINAL}\s+({_MONTHS})\)",
        # "Day 1 (30 June): Budapest" - capture the date part
        rf"[Dd]ay\s+1\s*\(({_ORDINAL}\s+{_MONTHS}(?:\s+\d{{4}})?)\)",
        # Full date with year: "30th June 2025" | "June 30, 2025"
        rf"({_ORDINAL}\s+{_MONTHS}\s+\d{{4}})",
        # ISO / slash formats
        r"(\d{4}-\d{2}-\d{2})",
        r"(\d{2}/\d{2}/\d{4})",
    ]
    from src.utils.validators import parse_date_string
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            # If year is missing, assume current or next occurrence
            if not re.search(r"\d{4}", raw):
                from datetime import date
                year = date.today().year
                raw = f"{raw} {year}"
            d = parse_date_string(raw)
            if d:
                return d.isoformat()
    return None


# ── Room config extraction ─────────────────────────────────────────────────

def extract_room_config(text: str) -> Dict[str, int]:
    t = text.lower()
    config: Dict[str, int] = {"double": 0, "twin": 0, "triple": 0, "single": 0}

    for room_type in ("double", "twin", "triple", "single"):
        m = re.search(
            rf"(\d+)\s+{room_type}\s+room|{room_type}\s+room\s*[x×]\s*(\d+)|(\d+)\s*x\s*{room_type}",
            t
        )
        if m:
            val = int(next(g for g in m.groups() if g is not None))
            config[room_type] = val

    # "1 double + 1 twin" pattern
    m = re.search(r"(\d+)\s+double\s*[+&and,]+\s*(\d+)\s+twin", t)
    if m:
        config["double"] = int(m.group(1))
        config["twin"] = int(m.group(2))

    # If nothing found but pax is 2 or more, default
    if all(v == 0 for v in config.values()):
        config["double"] = 1

    return config


# ── Client name extraction ─────────────────────────────────────────────────

def extract_client_name(text: str) -> Optional[str]:
    # "for Mr/Mrs/Ms XYZ" | "booking for ABC"
    m = re.search(
        r"(?:for|client|guest|travell?er|passenger)\s+(?:Mr\.?\s+|Mrs\.?\s+|Ms\.?\s+|Dr\.?\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        text
    )
    if m:
        return m.group(1)
    # "Dear Yash" → not client name, that's the agent
    return None


# ── Sightseeing / excursion extraction ────────────────────────────────────

def extract_sightseeing(text: str) -> Tuple[List[str], List[str]]:
    """Returns (mandatory_sightseeing, optional_excursions)."""
    t = text.lower()
    mandatory: List[str] = []
    optional: List[str] = []

    # Optional excursion markers
    opt_m = re.search(
        r"optional(?:\s+excursion)?s?\s*[:\-–]?\s*(.+?)(?:\n|$)",
        t
    )
    if opt_m:
        parts = re.split(r"[,;/]", opt_m.group(1))
        optional = [p.strip().title() for p in parts if len(p.strip()) > 2]

    # Sightseeing line
    sight_m = re.search(
        r"sightseeing\s*[:\-–]\s*(.+?)(?:\n|$)",
        t
    )
    if sight_m:
        line = sight_m.group(1)
        # Remove constraint/modifier phrases
        line = re.sub(
            r"comfortable\s+pace|minimal\s+walking|senior[\s-]friendly|"
            r"along\s+with\s+guide|with\s+guide|guided|relaxed|easy\s+pace|\balong\b",
            "", line, flags=re.IGNORECASE
        )
        parts = re.split(r"[,;/]", line)
        _noise = {"along", "also", "and", "or", "with", "plus", "the", "a", "an"}
        mandatory = [
            p.strip().title() for p in parts
            if len(p.strip()) > 2 and p.strip().lower() not in _noise
        ]

    return mandatory, optional


# ── Hotel category ─────────────────────────────────────────────────────────

def match_hotel_category(text: str) -> Optional[str]:
    t = text.lower()
    # Check most specific first; "4★ Deluxe OR 5★" → prefer 4★ Deluxe
    if re.search(r"4\s*[★*]\s*deluxe|four[\s-]star\s+deluxe|4-star\s+deluxe", t):
        return "4_star_deluxe"
    if re.search(r"5\s*[★*]|five[\s-]star|luxury\s+hotel", t):
        return "5_star"
    if re.search(r"4\s*[★*]|four[\s-]star|\bdeluxe\b", t):
        return "4_star_deluxe"
    if re.search(r"3\s*[★*]|three[\s-]star", t):
        return "3_star"
    if re.search(r"2\s*[★*]|two[\s-]star|budget\s+hotel", t):
        return "3_star"
    return None


# ── Transport ──────────────────────────────────────────────────────────────

def match_transport_preference(text: str) -> Optional[str]:
    t = text.lower()
    if re.search(r"private\s+(?:van|transfer|vehicle|cab|taxi|coach)", t):
        return "private_van"
    if re.search(r"private\s+car|self[\s-]drive", t):
        return "private_car"
    if re.search(r"\bsic\b|seat[\s-]in[\s-]coach|shared\s+(?:transfer|coach|bus|shuttle)", t):
        return "shared_transfer"
    return None


def match_vehicle_type(text: str) -> str:
    """
    Return a vehicle description based on what the user actually requested.
    Only echoes a specific brand/model when the user explicitly named one;
    otherwise returns a generic, destination-agnostic description so the LLM
    is free to pick something locally appropriate.
    """
    t = text.lower()
    # Brand-specific matches ONLY trigger when the user typed the brand.
    if "viano" in t:
        return "Mercedes Viano or similar"
    if "sprinter" in t:
        return "Mercedes Sprinter or similar"
    if "innova" in t:
        return "Toyota Innova or similar"
    if "hiace" in t:
        return "Toyota HiAce or similar"
    if "fortuner" in t:
        return "Toyota Fortuner or similar"
    if "tempo" in t or "traveller" in t:
        return "Tempo Traveller or similar"
    # Generic class hints
    if "luxury" in t or "premium" in t:
        return "Premium chauffeured vehicle"
    if "coach" in t or "bus" in t:
        return "Air-conditioned coach"
    if "minivan" in t or "minibus" in t:
        return "Minivan (locally available class)"
    if "suv" in t:
        return "Private SUV"
    if "sedan" in t:
        return "Private sedan"
    if "car" in t or "taxi" in t:
        return "Private car with driver"
    # No specific request — let downstream pick. No hardcoded brand default.
    return "Private vehicle (size and class chosen for the destination and pax)"


# ── Constraints ────────────────────────────────────────────────────────────

def detect_senior_constraints(text: str) -> Dict[str, bool]:
    t = text.lower()
    return {
        "has_seniors":            bool(re.search(r"\bsenior\b|60\s*\+|elderly|aged\s+6\d", t)),
        "needs_minimal_walking":  bool(re.search(r"minimal\s+walk|less\s+walk|no\s+walk|low[\s-]walk|easy\s+walk", t)),
        "needs_comfortable_pace": bool(re.search(r"comfort\w*\s+pace|relaxed\s+pace|slow\s+pace|easy\s+pace|leisurely", t)),
        "needs_accessibility":    bool(re.search(r"wheelchair|accessib|mobility\s+issue", t)),
        "city_centre_hotel":      bool(re.search(r"city\s+cent(?:re|er)|central\s+(?:hotel|location)|near\s+(?:city\s+)?cent", t)),
        "guide_required":         bool(re.search(r"\bguide\b|\bguided\b|with\s+a\s+guide|local\s+guide|tour\s+guide", t)),
        "indian_driver":          bool(re.search(r"indian\s+driver|hindi.*driver|indian.*speaking\s+driver|preferably\s+indian", t)),
    }
