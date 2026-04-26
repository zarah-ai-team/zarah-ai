"""formal_request_parser.py
Parser for formal/structured travel request emails and messages.
Handles:
  - Simple key-value format:  Destination: Oman, Check-in: 14 Jan 2026
  - DMC/agency narrative format:  Prague: 4 Nights, Route: Budapest → Prague → Vienna
  - Mixed narrative with bullet-point details
"""
import re
from typing import Dict, Any, Optional, List
from datetime import datetime


# ─── Public API ────────────────────────────────────────────────────────────────

def is_formal_request(text: str) -> bool:
    """
    Detect formal/professional travel requests.
    Catches both structured key-value emails AND DMC-style narrative emails.
    """
    t = text.strip()

    # Hard signals (any one is sufficient)
    hard = [
        r"dear\s+[A-Za-z]+",                          # "Dear Yash"
        r"route\s*[:–\-]",                             # "Route: Budapest → Prague"
        r"[A-Za-z]+\s*:\s*\d+\s*nights?",             # "Prague: 4 Nights"
        r"\d+\s*nights?\s*/\s*\d+\s*days?",            # "6N/7D"
        r"suggestive\s+itinerary",                     # "Suggestive Itinerary"
        r"extension\s+trip",                           # "extension trip"
        r"senior\s+citizen",                           # "senior citizens"
        r"indian\s+driver",                            # "Indian driver"
        r"destination\s*[:=]",                         # structured key-value
        r"check\s*-?\s*in\s*[:=]",
        r"no\.\s*of\s*pax",
    ]
    for pattern in hard:
        if re.search(pattern, t, re.IGNORECASE):
            return True

    # Soft signals — need at least 3
    soft = [
        r"\d+\s*nights?",
        r"\bpax\b",
        r"\b(?:itinerary|costing|quotation|quote)\b",
        r"[A-Z][a-z]+\s*→\s*[A-Z][a-z]+",             # City → City
        r"\b(?:double room|twin room|suite)\b",
        r"\b(?:mercedes|viano|minivan|private van|coach)\b",
        r"\b(?:4\s*\*|5\s*\*|four star|five star|deluxe)\b",
        r"\b(?:guide|driver|transfer)\b",
        r"\b(?:sightseeing|excursion|landmark)\b",
    ]
    score = sum(1 for p in soft if re.search(p, t, re.IGNORECASE))
    return score >= 3


def parse_formal_request(text: str) -> Dict[str, Any]:
    """
    Parse a formal travel request and return a structured dict.
    Handles multi-destination, narrative, and key-value formats.
    """
    parsed: Dict[str, Any] = {}
    parsed["is_formal_request"] = True
    parsed["raw_text"] = text

    _extract_addressee(text, parsed)
    _extract_pax(text, parsed)
    _extract_route_and_nights(text, parsed)
    _extract_dates(text, parsed)
    _extract_hotel(text, parsed)
    _extract_transport(text, parsed)
    _extract_requirements(text, parsed)
    _extract_rooms(text, parsed)
    _extract_event_type(text, parsed)

    # Heuristic destination fallback — picks up "in UAE" / "to Dubai" / "in Italy"
    # when the structured extractors above find no Route: or City: N Nights pattern.
    if not parsed.get("destination") and not parsed.get("destinations"):
        _extract_destination_heuristic(text, parsed)

    return parsed


# Country / region aliases that the heuristic should accept as destinations
# even though they don't appear in the city template DB. These are normalised
# to a canonical title-case form.
_COUNTRY_ALIASES = {
    "uae": "UAE", "u.a.e": "UAE", "u.a.e.": "UAE", "emirates": "UAE",
    "uk": "UK", "u.k": "UK", "u.k.": "UK",
    "usa": "USA", "u.s.a": "USA", "u.s.a.": "USA", "us": "USA",
}


def _extract_destination_heuristic(text: str, out: Dict) -> None:
    """
    Last-resort destination extraction for narrative / email-style requests.

    Strategy: defer to the country-state-city DB resolver, which scans the
    ENTIRE text for known cities/countries and returns them in document order.
    This avoids brittle regex picks like "to Montjuïc Castle viewpoint" beating
    "in Barcelona" just because it appears earlier.
    """
    # 1. Authoritative path — resolver-backed destination scan.
    try:
        from destination_resolver import detect_route
        route = detect_route(text) or {}
        names = route.get("destinations") or []
        if names:
            out["destination"] = names[0]
            if len(names) > 1:
                out["destinations"] = names
                out["route"] = route.get("route_str") or " → ".join(names)
            else:
                out["destinations"] = [names[0]]
            return
    except Exception:
        pass

    # 2. Fallback — alias map for short tokens like "UAE" / "USA" that the DB
    #    might not have under those exact strings.
    for alias, canonical in _COUNTRY_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", text, re.IGNORECASE):
            out["destination"] = canonical
            out["destinations"] = [canonical]
            return


def format_parsed_request_summary(parsed: Dict[str, Any]) -> str:
    lines = ["Formal Request Summary:"]
    if parsed.get("contact_person"):
        lines.append(f"  Addressee     : {parsed['contact_person']}")
    if parsed.get("destinations"):
        lines.append(f"  Destinations  : {' → '.join(parsed['destinations'])}")
    if parsed.get("nights_per_city"):
        npc = parsed["nights_per_city"]
        lines.append(f"  Nights/City   : {', '.join(f'{c}: {n}N' for c,n in npc.items())}")
    if parsed.get("total_nights"):
        lines.append(f"  Total Nights  : {parsed['total_nights']}")
    if parsed.get("trip_start_date"):
        lines.append(f"  Start Date    : {parsed['trip_start_date']}")
    if parsed.get("pax"):
        s = f"  Pax           : {parsed['pax']} adults"
        if parsed.get("seniors"):
            s += f" (incl. {parsed['seniors']} senior citizens 60+)"
        lines.append(s)
    if parsed.get("room_config"):
        rc = parsed["room_config"]
        parts = [f"{v} {k}" for k, v in rc.items()]
        lines.append(f"  Rooms         : {', '.join(parts)}")
    if parsed.get("hotel_category"):
        lines.append(f"  Hotel         : {parsed['hotel_category']}")
    if parsed.get("transport_preference"):
        lines.append(f"  Transport     : {parsed['transport_preference']}")
    if parsed.get("driver_preference"):
        lines.append(f"  Driver        : {parsed['driver_preference']}")
    if parsed.get("guide_required"):
        lines.append(f"  Guide         : Required (senior-friendly pace)")
    if parsed.get("walking_tolerance"):
        lines.append(f"  Walking       : {parsed['walking_tolerance']}")
    if parsed.get("event_type"):
        lines.append(f"  Trip Type     : {parsed['event_type']}")
    return "\n".join(lines)


# ─── Internal extractors ───────────────────────────────────────────────────────

def _extract_addressee(text: str, out: Dict) -> None:
    m = re.search(r"dear\s+([A-Za-z]+)", text, re.IGNORECASE)
    if m:
        out["contact_person"] = m.group(1).strip()


def _extract_pax(text: str, out: Dict) -> None:
    # "4 adults (2 senior citizens)"
    m = re.search(r"(\d+)\s*adults?", text, re.IGNORECASE)
    if m:
        out["pax"] = int(m.group(1))
        out["adults"] = int(m.group(1))

    senior_m = re.search(r"(\d+)\s*senior\s*citizen", text, re.IGNORECASE)
    if senior_m:
        out["seniors"] = int(senior_m.group(1))
        out["senior_friendly"] = True
        out["walking_tolerance"] = "minimal"
        out["guide_required"] = True

    # Fallback: "X pax"
    if "pax" not in out:
        m2 = re.search(r"(\d+)\s*pax", text, re.IGNORECASE)
        if m2:
            out["pax"] = int(m2.group(1))
            out.setdefault("adults", int(m2.group(1)))


_NON_CITY_TERMS = {
    "total", "duration", "key", "requirement", "requirements",
    "plan", "overview", "option", "options", "day", "days",
    "night", "nights", "travel", "route", "extension", "hotel",
    "transport", "highlight", "highlights", "note", "notes",
    "detail", "details", "suggestive", "itinerary", "costing",
    "summary", "overview",
}


def _is_likely_city(name: str) -> bool:
    """Return False when the matched token looks like a label rather than a city name."""
    words = name.lower().split()
    if any(w in _NON_CITY_TERMS for w in words):
        return False
    if len(words) > 3:  # real city names are at most 3 words
        return False
    return True


def _extract_route_and_nights(text: str, out: Dict) -> None:
    """Extract multi-city route and nights per city."""
    nights_per_city: Dict[str, int] = {}
    destinations: List[str] = []

    # Pattern: "Prague: 4 Nights" / "Vienna: 2-3 Nights"
    city_night_matches = re.findall(
        r"([A-Z][a-zA-Zé\s]{2,20?})\s*:\s*(\d+)(?:\s*[-–]\s*(\d+))?\s*nights?",
        text, re.IGNORECASE
    )
    for city, n_min, n_max in city_night_matches:
        city = city.strip().title()
        if not _is_likely_city(city):
            continue
        nights = int(n_max) if n_max else int(n_min)
        nights_per_city[city] = nights
        if city not in destinations:
            destinations.append(city)

    # Pattern: "Route: Budapest → Prague → Vienna" or "Budapest > Prague > Vienna"
    route_m = re.search(
        r"route\s*[:–\-]\s*([A-Za-z\s]+(?:[→>–\-\/,]\s*[A-Za-z\s]+)+)",
        text, re.IGNORECASE
    )
    if route_m:
        raw_route = route_m.group(1)
        cities_in_route = re.split(r"[→>–\-\/,]", raw_route)
        ordered = [c.strip().title() for c in cities_in_route if c.strip()]
        # Merge: keep route order, fill in any cities not already in nights_per_city
        full_route = []
        for c in ordered:
            if c not in full_route:
                full_route.append(c)
        # If we got explicit nights from city: N Nights pattern, map them in route order
        if nights_per_city:
            out["nights_per_city"] = nights_per_city
            out["route"] = " → ".join(full_route)
            out["destinations"] = full_route
            # Use first city in route as main destination
            out["destination"] = full_route[0] if full_route else list(nights_per_city.keys())[0]
        else:
            out["route"] = " → ".join(full_route)
            out["destinations"] = full_route
            out["destination"] = full_route[0] if full_route else ""

    elif nights_per_city:
        out["nights_per_city"] = nights_per_city
        out["destinations"] = list(nights_per_city.keys())
        out["destination"] = out["destinations"][0]

    # Total nights — derive from per-city sum first
    total_nights = sum(nights_per_city.values()) if nights_per_city else None

    # Fallback 1: explicit "6–7 Nights" or "Total Duration: 7 Nights" range
    if not total_nights:
        m = re.search(r"total\s*(?:duration|nights?)[:\s]+(\d+)(?:\s*[-–]\s*(\d+))?\s*nights?", text, re.IGNORECASE)
        if m:
            total_nights = int(m.group(2)) if m.group(2) else int(m.group(1))
        else:
            m2 = re.search(r"(\d+)\s*[-–]\s*(\d+)\s*nights?", text, re.IGNORECASE)
            if m2:
                total_nights = int(m2.group(2))  # take upper bound of range
            else:
                m3 = re.search(r"(\d+)\s*nights?", text, re.IGNORECASE)
                if m3:
                    total_nights = int(m3.group(1))

    # Fallback 2: detect max "Day N:" heading (e.g. "Day 8: Departure") → total_days = max_day
    day_heading_nums = [int(d) for d in re.findall(r"\bday\s+(\d+)\s*[:\(]", text, re.IGNORECASE)]
    if day_heading_nums:
        max_day = max(day_heading_nums)
        derived_nights = max_day - 1
        # Prefer explicit per-city sum; use heading-derived value when it's larger/more reliable
        if not total_nights or abs(derived_nights - total_nights) <= 1:
            total_nights = derived_nights

    if total_nights:
        out["total_nights"] = total_nights
        out["nights"] = total_nights
        out["duration"] = total_nights + 1  # days = nights + 1


def _extract_dates(text: str, out: Dict) -> None:
    # "from 30th June" / "30 June" / "30th June 2026"
    m = re.search(
        r"(?:from\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)(?:\s+(\d{4}))?",
        text, re.IGNORECASE
    )
    if m:
        day = int(m.group(1))
        month_str = m.group(2)[:3].lower()
        months = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
                  "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
        month = months.get(month_str)
        year = int(m.group(3)) if m.group(3) else 2026
        if month:
            try:
                dt = datetime(year, month, day)
                out["trip_start_date"] = dt.strftime("%Y-%m-%d")
                out["checkin_date"] = dt.strftime("%Y-%m-%d")
            except Exception:
                pass


def _extract_hotel(text: str, out: Dict) -> None:
    # "4★ Deluxe City Centre OR 5★" / "4-star deluxe" / "5 star"
    if re.search(r"5\s*[★\*]|five.?star", text, re.IGNORECASE):
        out["hotel_category"] = "5-Star"
        out["hotel_type"] = "luxury"
    elif re.search(r"4\s*[★\*]\s*deluxe|four.?star.?deluxe", text, re.IGNORECASE):
        out["hotel_category"] = "4-Star Deluxe"
        out["hotel_type"] = "mid-range"
    elif re.search(r"4\s*[★\*]|four.?star", text, re.IGNORECASE):
        out["hotel_category"] = "4-Star"
        out["hotel_type"] = "mid-range"
    elif re.search(r"3\s*[★\*]|three.?star", text, re.IGNORECASE):
        out["hotel_category"] = "3-Star"
        out["hotel_type"] = "budget"

    # City centre preference
    if re.search(r"city\s*cent(?:re|er)", text, re.IGNORECASE):
        out["hotel_location_preference"] = "City Centre"


def _extract_transport(text: str, out: Dict) -> None:
    # Vehicle type
    for vehicle in ["Mercedes Viano", "Viano", "Mercedes", "Innova", "Tempo Traveller",
                    "minivan", "mini van", "private van", "coach", "bus"]:
        if re.search(re.escape(vehicle), text, re.IGNORECASE):
            out["transport_preference"] = f"Private {vehicle}"
            out["vehicle_type"] = vehicle
            break
    else:
        if re.search(r"private\s+(?:van|vehicle|car|transfer)", text, re.IGNORECASE):
            out["transport_preference"] = "Private Vehicle"

    # Driver preference
    if re.search(r"indian\s+driver", text, re.IGNORECASE):
        out["driver_preference"] = "Indian driver preferred"
    elif re.search(r"english.?speaking\s+driver", text, re.IGNORECASE):
        out["driver_preference"] = "English-speaking driver"

    # Duration of transport hire
    m = re.search(r"(\d+)\s*days?\s*(?:hire|rental|transfer)", text, re.IGNORECASE)
    if m:
        out["transport_days"] = int(m.group(1))


def _extract_rooms(text: str, out: Dict) -> None:
    rc: Dict[str, int] = {}
    patterns = [
        (r"(\d+)\s*double\s*rooms?", "double"),
        (r"(\d+)\s*twin\s*rooms?",   "twin"),
        (r"(\d+)\s*single\s*rooms?", "single"),
        (r"(\d+)\s*suite",           "suite"),
    ]
    for pat, room_type in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            rc[room_type] = int(m.group(1))
    if rc:
        out["room_config"] = rc
        out["rooms"] = sum(rc.values())


def _extract_requirements(text: str, out: Dict) -> None:
    if re.search(r"senior.?friendly|comfortable\s+pace|minimal\s+walking|easy\s+pac", text, re.IGNORECASE):
        out["senior_friendly"] = True
        out["walking_tolerance"] = "minimal"
    if re.search(r"guide\s+(?:required|needed|included|along)|local\s+guide|english.?speaking\s+guide", text, re.IGNORECASE):
        out["guide_required"] = True
    if re.search(r"comfort\s+stops?|enroute\s+stops?|rest\s+stops?", text, re.IGNORECASE):
        out["comfort_stops"] = True
    if re.search(r"river\s+cruise", text, re.IGNORECASE):
        out.setdefault("preferred_activities", []).append("River Cruise")
    if re.search(r"classical\s+concert|opera", text, re.IGNORECASE):
        out.setdefault("preferred_activities", []).append("Classical Concert")


def _extract_event_type(text: str, out: Dict) -> None:
    if re.search(r"incentive|mice|team.?build", text, re.IGNORECASE):
        out["event_type"] = "incentive"
        out["client_type"] = "mice"
    elif re.search(r"corporate|business\s+trip|company", text, re.IGNORECASE):
        out["event_type"] = "corporate"
        out["client_type"] = "corporate"
    else:
        out.setdefault("event_type", "leisure")
        out.setdefault("client_type", "leisure")
