import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

REQUIRED_FIELDS = ["origin", "destinations", "total_nights", "adults"]

# Known road-segment data for Europe (distance_km, duration_hours)
KNOWN_ROUTES: Dict[Tuple[str, str], Dict] = {
    ("budapest", "prague"):  {"distance_km": 525, "duration_hours": 5.5},
    ("prague",   "vienna"):  {"distance_km": 330, "duration_hours": 4.0},
    ("budapest", "vienna"):  {"distance_km": 245, "duration_hours": 2.75},
    ("vienna",   "salzburg"):{"distance_km": 300, "duration_hours": 3.0},
    ("prague",   "berlin"):  {"distance_km": 350, "duration_hours": 3.75},
    ("vienna",   "bratislava"):{"distance_km": 80, "duration_hours": 1.0},
}

CITY_ALIASES: Dict[str, str] = {
    "buda": "Budapest", "buda pest": "Budapest",
    "praga": "Prague",  "prag": "Prague",
    "wien":  "Vienna",  "vien": "Vienna",
    "brno":  "Brno",
}


def validate_trip_request(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    for f in REQUIRED_FIELDS:
        if not data.get(f):
            errors.append(f"Missing required field: {f}")

    if data.get("adults", 0) < 1:
        errors.append("adults must be >= 1")
    if data.get("total_nights", 0) < 1:
        errors.append("total_nights must be >= 1")
    if data.get("seniors", 0) > data.get("adults", 0):
        errors.append("seniors count cannot exceed adults")

    return len(errors) == 0, errors


def normalize_city_name(city: str) -> str:
    lower = city.lower().strip()
    return CITY_ALIASES.get(lower, city.strip().title())


def infer_route_segments(cities: List[str]) -> List[Dict]:
    segments = []
    for i in range(len(cities) - 1):
        a, b = cities[i].lower(), cities[i + 1].lower()
        info = KNOWN_ROUTES.get((a, b)) or KNOWN_ROUTES.get((b, a)) or {}
        segments.append({
            "from_city": cities[i],
            "to_city": cities[i + 1],
            "travel_mode": "private_van",
            "distance_km": info.get("distance_km"),
            "duration_hours": info.get("duration_hours"),
        })
    return segments


def parse_date_string(s: str) -> Optional[date]:
    if not s:
        return None
    # Strip ordinal suffixes (1st, 2nd, 3rd, 30th)
    s_clean = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", s.strip())
    formats = [
        "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
        "%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s_clean, fmt).date()
        except ValueError:
            continue
    return None
