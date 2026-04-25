"""
Request normalization layer.

Extraction priority (highest → lowest):
  1. Explicit structured fields passed directly in the API request
  2. Regex / rule-based extraction from raw_text  (no LLM needed)
  3. LLM-assisted extraction via Ollama            (enhancement only)
  4. Sensible defaults

This means every request works even if Ollama is offline or slow.
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
load_dotenv()

_OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")

from src.models.trip_requirements import (
    HotelCategory, Pace, RoomConfig, RouteSegment,
    TransportPreference, TravelerProfile,
    TripRequest, TripRequirements, WalkingTolerance,
)
from src.services.kb.matchers import (
    KNOWN_CITIES,
    detect_senior_constraints,
    extract_client_name,
    extract_destinations_from_text,
    extract_nights_per_city,
    extract_pax,
    extract_room_config,
    extract_sightseeing,
    extract_start_date,
    extract_total_nights,
    match_hotel_category,
    match_transport_preference,
    match_vehicle_type,
)
from src.utils.validators import infer_route_segments, normalize_city_name, parse_date_string

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# LLM-assisted extraction (async, optional enhancement)               #
# ------------------------------------------------------------------ #

async def llm_extract_fields(raw_text: str, ollama_url: str, model: str) -> Dict[str, Any]:
    """
    Ask Ollama to extract fields from free text.
    Returns {} on any failure — callers must not depend on this succeeding.
    """
    try:
        import aiohttp
        from src.services.itinerary.schema import NORMALIZATION_PROMPT

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": NORMALIZATION_PROMPT + raw_text}],
            "stream": False,
            "options": {"temperature": 0.05, "num_predict": 900},
        }
        headers = {"Content-Type": "application/json"}
        if _OLLAMA_API_KEY:
            headers["Authorization"] = f"Bearer {_OLLAMA_API_KEY}"
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as sess:
            async with sess.post(f"{ollama_url}/api/chat", json=payload) as resp:
                resp.raise_for_status()
                data = await resp.json()
                content = data.get("message", {}).get("content", "")
                result = _parse_json_safe(content)
                logger.debug(f"LLM extracted {len(result)} fields")
                return result
    except Exception as e:
        logger.info(f"LLM extraction unavailable ({type(e).__name__}) — using regex only")
        return {}


# ------------------------------------------------------------------ #
# Main normalizer                                                       #
# ------------------------------------------------------------------ #

def normalize_trip_request(
    raw: TripRequest,
    llm_fields: Optional[Dict[str, Any]] = None,
) -> TripRequirements:
    """
    Produces a canonical TripRequirements from any combination of:
    - raw.raw_text  (free-form client email / chat message)
    - raw.*         (explicit structured fields from API caller)
    - llm_fields    (optional LLM extraction result)
    """
    text = raw.raw_text or ""

    # ── Step 1: Regex extraction from raw text ───────────────────────
    regex_fields = _regex_extract(text) if text else {}

    # ── Step 2: Three-way merge (explicit > LLM > regex) ─────────────
    merged = _merge(raw, llm_fields or {}, regex_fields)

    # ── Step 3: Parse each field into typed values ────────────────────
    constraints = detect_senior_constraints(text)
    destinations = _resolve_destinations(merged, text)
    route_segs = infer_route_segments(destinations)
    traveler = _parse_traveler(merged)
    rooms = _parse_rooms(merged, text)
    hotel_cat = _parse_hotel_cat(merged)
    transport = _parse_transport(merged)
    start_date = _resolve_date(merged)
    total_nights = _resolve_nights(merged, destinations)
    mandatory, optional_exc = _resolve_sightseeing(merged, text)
    driver_pref = _resolve_driver(merged, constraints)

    missing: List[str] = []
    if not destinations:
        missing.append("destinations")
    if total_nights == 0:
        missing.append("total_nights")
    if traveler.total_adults == 0:
        missing.append("adults")

    return TripRequirements(
        request_id=str(uuid.uuid4())[:12],
        client_name=merged.get("client_name") or extract_client_name(text),
        origin=str(merged.get("origin") or "India"),
        destinations=destinations,
        route_segments=[
            RouteSegment(
                from_city=s["from_city"],
                to_city=s["to_city"],
                travel_mode=transport.value,
                estimated_duration_hours=s.get("duration_hours"),
                distance_km=s.get("distance_km"),
            )
            for s in route_segs
        ],
        trip_start_date=start_date,
        total_nights=total_nights,
        traveler_profile=traveler,
        room_config=rooms,
        hotel_category=hotel_cat,
        transport_preference=transport,
        vehicle_type=match_vehicle_type(text),
        driver_preference=driver_pref,
        pace=Pace.RELAXED if (
            constraints["needs_comfortable_pace"] or constraints["has_seniors"]
        ) else Pace.MODERATE,
        walking_tolerance=(
            WalkingTolerance.MINIMAL
            if (constraints["needs_minimal_walking"] or constraints["has_seniors"])
            else WalkingTolerance.MODERATE
        ),
        guide_required=bool(
            merged.get("guide_required") or constraints["guide_required"]
        ),
        mandatory_sightseeing=mandatory,
        optional_excursions=optional_exc,
        needs_senior_friendly=constraints["has_seniors"],
        needs_minimal_walking=constraints["needs_minimal_walking"] or constraints["has_seniors"],
        needs_private_transport=transport == TransportPreference.PRIVATE_VAN,
        needs_city_centre_hotel=constraints["city_centre_hotel"],
        raw_input=text or None,
        missing_fields=missing,
        assumptions_made=_build_assumptions_list(merged, regex_fields, llm_fields or {}),
    )


# ------------------------------------------------------------------ #
# Regex extraction pass                                                 #
# ------------------------------------------------------------------ #

def _regex_extract(text: str) -> Dict[str, Any]:
    """Extract all fields from raw text using pure regex — no LLM."""
    adults, seniors, children = extract_pax(text)
    mandatory, optional_exc = extract_sightseeing(text)

    return {
        "destinations":          extract_destinations_from_text(text),
        "total_nights":          extract_total_nights(text),
        "adults":                adults,
        "seniors":               seniors,
        "children":              children,
        "trip_start_date":       extract_start_date(text),
        "hotel_category":        match_hotel_category(text),
        "transport_preference":  match_transport_preference(text),
        "room_config":           extract_room_config(text),
        "guide_required":        bool(re.search(
            r"\bguide\b|\bguided\b|with\s+a?\s*guide|tour\s+guide|local\s+guide",
            text, re.IGNORECASE
        )),
        "mandatory_sightseeing": mandatory,
        "optional_excursions":   optional_exc,
    }


# ------------------------------------------------------------------ #
# Three-way merge                                                       #
# ------------------------------------------------------------------ #

def _merge(
    raw: TripRequest,
    llm: Dict[str, Any],
    regex: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Merge priority: explicit API fields > LLM > regex
    For list fields (destinations, sightseeing), prefer whichever source
    has more items.
    """
    merged: Dict[str, Any] = {}

    # Start from regex (lowest priority)
    for k, v in regex.items():
        if v is not None and v != [] and v != {}:
            merged[k] = v

    # LLM overrides regex for scalar fields; for lists, take the longer one
    for k, v in llm.items():
        if v is None:
            continue
        existing = merged.get(k)
        if isinstance(v, list) and isinstance(existing, list):
            merged[k] = v if len(v) >= len(existing) else existing
        elif v not in ([], {}, ""):
            merged[k] = v

    # Explicit API fields always win (even over LLM)
    explicit_fields = (
        "client_name", "origin", "trip_start_date", "total_nights",
        "adults", "seniors", "children", "budget_preference",
        "transport_preference", "hotel_category", "guide_required",
        "driver_preference",
    )
    for field in explicit_fields:
        val = getattr(raw, field, None)
        if val is not None:
            merged[field] = val

    # Explicit list fields
    for field in ("destinations", "mandatory_sightseeing", "optional_excursions", "meal_preferences"):
        val = getattr(raw, field, None)
        if val:
            merged[field] = val

    # Explicit room_config
    if raw.room_config:
        merged["room_config"] = raw.room_config

    return merged


# ------------------------------------------------------------------ #
# Field resolvers                                                       #
# ------------------------------------------------------------------ #

def _resolve_destinations(merged: Dict, text: str) -> List[str]:
    raw = merged.get("destinations") or []
    if isinstance(raw, str):
        raw = re.split(r"[,→\-–>]+", raw)
    cities = [normalize_city_name(str(d).strip()) for d in raw if str(d).strip()]

    # Remove obvious non-cities that slipped through
    cities = [c for c in cities if c.lower() not in {
        "surface", "road", "air", "train", "night", "day",
    }]
    return list(dict.fromkeys(cities))  # deduplicate, preserve order


def _parse_traveler(merged: Dict) -> TravelerProfile:
    adults  = int(merged.get("adults")   or 2)
    seniors = int(merged.get("seniors")  or 0)
    kids    = int(merged.get("children") or 0)
    return TravelerProfile(
        total_adults=max(adults, seniors),  # seniors are subset of adults
        seniors_count=min(seniors, max(adults, seniors)),
        children_count=kids,
    )


def _parse_rooms(merged: Dict, text: str) -> RoomConfig:
    rc = merged.get("room_config") or {}
    if isinstance(rc, dict):
        cfg = RoomConfig(
            double_rooms=int(rc.get("double") or 0),
            twin_rooms=int(rc.get("twin") or 0),
            triple_rooms=int(rc.get("triple") or 0),
            single_rooms=int(rc.get("single") or 0),
        )
        if cfg.total_rooms > 0:
            return cfg
    return RoomConfig(double_rooms=1, twin_rooms=1)


def _parse_hotel_cat(merged: Dict) -> HotelCategory:
    mapping = {
        "4_star_deluxe": HotelCategory.FOUR_STAR_DELUXE,
        "5_star":        HotelCategory.FIVE_STAR,
        "4_star":        HotelCategory.FOUR_STAR,
        "3_star":        HotelCategory.THREE_STAR,
    }
    return mapping.get(str(merged.get("hotel_category") or ""), HotelCategory.FOUR_STAR_DELUXE)


def _parse_transport(merged: Dict) -> TransportPreference:
    mapping = {
        "private_van":     TransportPreference.PRIVATE_VAN,
        "private_car":     TransportPreference.PRIVATE_CAR,
        "shared_transfer": TransportPreference.SHARED_TRANSFER,
        "sic":             TransportPreference.SIC,
    }
    return mapping.get(str(merged.get("transport_preference") or ""), TransportPreference.PRIVATE_VAN)


def _resolve_date(merged: Dict) -> Optional[object]:
    raw = merged.get("trip_start_date")
    if not raw:
        return None
    if hasattr(raw, "year"):
        return raw
    return parse_date_string(str(raw))


def _resolve_nights(merged: Dict, destinations: List[str]) -> int:
    n = merged.get("total_nights")
    if n:
        return max(1, int(n))
    # Try summing per-city nights if available
    npc = merged.get("nights_per_city") or {}
    if npc and isinstance(npc, dict):
        total = sum(int(v) for v in npc.values())
        if total > 0:
            return total
    return max(1, len(destinations) * 2) if destinations else 7


def _resolve_sightseeing(merged: Dict, text: str) -> tuple:
    mandatory = _as_list(merged.get("mandatory_sightseeing"))
    optional  = _as_list(merged.get("optional_excursions"))
    return mandatory, optional


def _resolve_driver(merged: Dict, constraints: Dict) -> Optional[str]:
    explicit = merged.get("driver_preference")
    if explicit:
        return str(explicit)
    if constraints.get("indian_driver"):
        return "Indian driver preferred"
    return None


def _build_assumptions_list(
    merged: Dict, regex: Dict, llm: Dict
) -> List[str]:
    notes: List[str] = []
    if not llm:
        notes.append("LLM unavailable — all fields extracted via regex rules")
    if merged.get("total_nights") != regex.get("total_nights") and llm.get("total_nights"):
        notes.append("total_nights sourced from LLM extraction")
    return notes


# ------------------------------------------------------------------ #
# Utilities                                                             #
# ------------------------------------------------------------------ #

def _as_list(val: Any) -> List[str]:
    if not val:
        return []
    if isinstance(val, list):
        return [str(v) for v in val if str(v).strip()]
    if isinstance(val, str):
        return [val] if val.strip() else []
    return []


def _parse_json_safe(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return {}
