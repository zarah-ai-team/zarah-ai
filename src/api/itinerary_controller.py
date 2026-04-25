"""
Itinerary v2 API controller.
Mounts at /api/v2/itinerary — sits alongside existing v1 /api/chat routes.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.models.trip_requirements import TripRequest
from src.services.itinerary.itinerary_orchestrator import ItineraryOrchestrator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v2/itinerary", tags=["itinerary-v2"])

_orchestrator: Optional[ItineraryOrchestrator] = None


def _get_orchestrator() -> ItineraryOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = ItineraryOrchestrator()
    return _orchestrator


# ------------------------------------------------------------------ #
# Request schema                                                        #
# ------------------------------------------------------------------ #

class GenerateItineraryRequest(BaseModel):
    """
    Accepts either raw_text (paste a client email directly) or
    individual structured fields — or both for best results.

    client_type: one of corporate | leisure | mice | dmc | b2b | b2c
                 Adjusts hotel tier, guide inclusion, and meal level.
    client_id:   Optional reference to a saved client (cosmetic, not used in pricing).
    """
    raw_text:              Optional[str]        = None
    client_name:           Optional[str]        = None
    client_type:           Optional[str]        = None   # corporate|leisure|mice|dmc|b2b|b2c
    client_id:             Optional[str]        = None   # reference only
    origin:                Optional[str]        = None
    destinations:          Optional[List[str]]  = None
    route:                 Optional[str]        = None
    trip_start_date:       Optional[str]        = None
    total_nights:          Optional[int]        = None
    adults:                Optional[int]        = None
    seniors:               Optional[int]        = None
    children:              Optional[int]        = None
    room_config:           Optional[Dict[str, int]] = None
    hotel_category:        Optional[str]        = None
    transport_preference:  Optional[str]        = None
    driver_preference:     Optional[str]        = None
    pace:                  Optional[str]        = None
    walking_tolerance:     Optional[str]        = None
    guide_required:        Optional[bool]       = None
    meal_preferences:      Optional[List[str]]  = None
    mandatory_sightseeing: Optional[List[str]]  = None
    optional_excursions:   Optional[List[str]]  = None
    budget_preference:     Optional[str]        = None
    departure_details:     Optional[str]        = None
    session_id:            Optional[str]        = None


def _build_trip_request(body: GenerateItineraryRequest) -> TripRequest:
    return TripRequest(
        raw_text=body.raw_text,
        client_name=body.client_name,
        origin=body.origin,
        destinations=body.destinations,
        route=body.route,
        trip_start_date=body.trip_start_date,
        total_nights=body.total_nights,
        adults=body.adults,
        seniors=body.seniors,
        children=body.children,
        room_config=body.room_config,
        hotel_category=body.hotel_category,
        transport_preference=body.transport_preference,
        driver_preference=body.driver_preference,
        pace=body.pace,
        walking_tolerance=body.walking_tolerance,
        guide_required=body.guide_required,
        meal_preferences=body.meal_preferences,
        mandatory_sightseeing=body.mandatory_sightseeing,
        optional_excursions=body.optional_excursions,
        session_id=body.session_id,
    )


def _validate_body(body: GenerateItineraryRequest) -> None:
    if not body.raw_text and not body.destinations:
        raise HTTPException(
            status_code=422,
            detail=(
                "Provide at least one of: raw_text (client email/message) "
                "or destinations + total_nights + adults."
            ),
        )


# ------------------------------------------------------------------ #
# Primary endpoint                                                      #
# ------------------------------------------------------------------ #

@router.post("/generate", summary="Generate a full itinerary with costing")
async def generate_itinerary(body: GenerateItineraryRequest):
    """
    Primary itinerary generation endpoint (uses web research + KB + LLM).

    Returns a complete day-by-day JSON itinerary with KB-sourced costing.
    If the request fails, use /generate-backup for a degraded but guaranteed response.
    """
    _validate_body(body)
    trip_req = _build_trip_request(body)

    try:
        result = await _get_orchestrator().generate_itinerary(
            trip_req,
            client_type=body.client_type,
            use_web_research=True,
        )
        return result.model_dump()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Itinerary generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")


# ------------------------------------------------------------------ #
# Backup endpoint — no MCP, guaranteed response                        #
# ------------------------------------------------------------------ #

@router.post("/generate-backup", summary="Backup: KB-only itinerary (no web search)")
async def generate_itinerary_backup(body: GenerateItineraryRequest):
    """
    Backup / degraded-mode endpoint.

    Skips MCP web research entirely. Uses only the internal KB and LLM.
    Guaranteed to return a structured JSON itinerary even if the LLM
    partially fails — falls back to a template-based day plan.

    Use this if /generate times out or fails.
    """
    _validate_body(body)
    trip_req = _build_trip_request(body)

    try:
        result = await _get_orchestrator().generate_itinerary(
            trip_req,
            client_type=body.client_type,
            use_web_research=False,
        )
        resp = result.model_dump()
        resp["mode"] = "backup"
        resp["web_research_used"] = False
        return resp
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Backup generation failed: {e}", exc_info=True)
        # Last-resort: return KB cost data with a minimal template itinerary
        try:
            return await _kb_only_fallback(trip_req, body.client_type, str(e))
        except Exception as fb_err:
            logger.error(f"Fallback also failed: {fb_err}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Both primary and fallback generation failed: {str(e)}",
            )


async def _kb_only_fallback(
    trip_req: TripRequest, client_type: Optional[str], error_msg: str
) -> Dict[str, Any]:
    """Pure KB cost + minimal template itinerary — no LLM required."""
    from src.services.itinerary.request_normalizer import normalize_trip_request
    from src.services.costing.cost_calculator import calculate_full_trip_cost
    from src.services.costing.assumptions_engine import generate_assumptions
    from src.services.itinerary.itinerary_orchestrator import _CLIENT_TYPE_CONFIG
    from src.services.kb.kb_retriever import get_destination_context
    import uuid

    req = normalize_trip_request(trip_req, {})
    if client_type and client_type.lower() in _CLIENT_TYPE_CONFIG:
        req = _get_orchestrator()._apply_client_type(req, client_type.lower())

    nights_per_city: Dict[str, int] = {}
    n_dest = max(len(req.destinations), 1)
    base = req.total_nights // n_dest
    leftover = req.total_nights % n_dest
    for i, city in enumerate(req.destinations):
        nights_per_city[city] = base + (1 if i == 0 else 0) * leftover

    cost_bd = calculate_full_trip_cost(req, nights_per_city)
    assumptions = generate_assumptions(req, nights_per_city)
    pax = max(req.traveler_profile.total_adults, 1)

    # Build minimal template days
    days = []
    day_num = 1
    for city, nights in nights_per_city.items():
        ctx = get_destination_context(city, req)
        sight_opts = [o["name"] for o in ctx.sightseeing_options[:4]]
        for n in range(nights):
            is_arrival = (day_num == 1)
            is_last_city_last_night = (
                city == req.destinations[-1] and n == nights - 1
            )
            days.append({
                "day_number": day_num,
                "city": city,
                "title": f"{'Arrival in ' if is_arrival else ''}{city}" + (
                    " — Departure" if is_last_city_last_night else ""
                ),
                "morning": (
                    f"Arrive in {city}, check in to hotel, freshen up."
                    if is_arrival else
                    f"Morning sightseeing in {city}: {sight_opts[0] if sight_opts else 'city highlights'}."
                ),
                "afternoon": (
                    f"Afternoon leisure — explore the {ctx.hotel_areas[0].split('–')[0].strip() if ctx.hotel_areas else 'city centre'}."
                    if is_arrival else
                    f"Visit {sight_opts[1] if len(sight_opts) > 1 else city + ' landmarks'}. Rest break at café."
                ),
                "evening": (
                    f"Welcome dinner at a local restaurant near the hotel."
                    if is_arrival else
                    (
                        f"Pack up, farewell dinner. Departure transfer arranged."
                        if is_last_city_last_night else
                        f"Evening at leisure — optional {ctx.sightseeing_notes[2] if len(ctx.sightseeing_notes) > 2 else 'river cruise or local dining'}."
                    )
                ),
                "walking_level": req.walking_tolerance.value,
                "senior_friendly_notes": ctx.senior_notes[0] if ctx.senior_notes else None,
                "hotel": {
                    "name": "To be confirmed",
                    "area": ctx.hotel_areas[0].split("–")[0].strip() if ctx.hotel_areas else "City Centre",
                    "category": req.hotel_category.value.replace("_", " ").title(),
                    "notes": "",
                },
                "transport": {
                    "type": req.vehicle_type,
                    "description": "Private transfer" if is_arrival else "Private van with driver",
                    "duration": None,
                    "notes": req.driver_preference or "",
                },
                "meals": {
                    "breakfast": "Included at hotel",
                    "lunch": "Own account",
                    "dinner": "Included" if is_arrival or is_last_city_last_night else "Own account",
                },
                "estimated_day_cost": round(cost_bd.total / max(req.total_nights, 1), 2),
                "inclusions": ["Hotel accommodation", "Private transfer"],
                "exclusions": ["Flights", "Travel insurance", "Personal expenses"],
            })
            day_num += 1

    cost_summary = cost_bd.to_summary()
    return {
        "request_id": str(uuid.uuid4())[:12],
        "status": "partial",
        "mode": "fallback",
        "web_research_used": False,
        "llm_error": error_msg,
        "normalized_input": req.model_dump(exclude={"raw_input"}),
        "itinerary": {
            "title": f"{' → '.join(req.destinations)} Tour",
            "trip_overview": (
                f"{req.total_nights}-night tour across {', '.join(req.destinations)} "
                f"for {pax} travellers. Template itinerary — customise as needed."
            ),
            "assumptions": assumptions,
            "total_estimated_cost": cost_bd.total,
            "cost_per_person": round(cost_bd.total / pax, 2),
            "currency": "USD",
            "cost_breakdown_summary": cost_summary,
            "days": days,
            "optional_experiences": [],
            "important_notes": [
                "This is a template itinerary generated without LLM. Manual customisation required.",
                f"LLM error: {error_msg}",
            ],
            "missing_information": req.missing_fields,
            "confidence_summary": {
                "overall": 0.60, "costing": 0.80, "routing": 0.75,
                "hotel_suggestions": 0.40, "sightseeing": 0.60,
                "notes": ["Template-based — LLM generation unavailable."],
            },
            "sources_summary": ["kb.internal"],
        },
        "cost_breakdown": cost_summary,
        "assumptions": assumptions,
        "missing_fields": req.missing_fields,
        "research_sources": [],
        "kb_sources": [f"kb.pricing.{d.lower()}" for d in req.destinations],
        "generated_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "processing_time_ms": 0,
        "pipeline_stages": {},
    }


# ------------------------------------------------------------------ #
# Health + KB inspection                                               #
# ------------------------------------------------------------------ #

@router.get("/health", summary="KB and pipeline health check")
async def health():
    from src.services.kb.kb_loader import get_kb_loader
    import aiohttp

    kb = get_kb_loader()
    cities = list(kb.pricing_rules.get("hotels", {}).get("4_star_deluxe", {}).keys())

    # Check Ollama connectivity
    _env = os.getenv("APP_ENV", "dev").strip().lower()
    if _env == "dev":
        ollama_url = os.getenv("OLLAMA_BASE_URL_DEV", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    else:
        ollama_url = os.getenv("OLLAMA_BASE_URL_PROD", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    ollama_model = os.getenv("OLLAMA_MODEL", "llama3:latest")
    ollama_api_key = os.getenv("OLLAMA_API_KEY", "")
    ollama_ok = False
    ollama_error = None
    try:
        headers = {}
        if ollama_api_key:
            headers["Authorization"] = f"Bearer {ollama_api_key}"
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as sess:
            async with sess.get(f"{ollama_url}/api/tags") as resp:
                ollama_ok = resp.status == 200
    except Exception as e:
        ollama_error = str(e)

    return {
        "status": "ok" if ollama_ok else "degraded",
        "kb_loaded": kb.is_loaded,
        "kb_docs": len(kb.itinerary_docs),
        "kb_dataset_rows": len(kb.dataset),
        "kb_priced_cities": cities,
        "ollama_model": ollama_model,
        "ollama_url": ollama_url,
        "ollama_reachable": ollama_ok,
        "ollama_error": ollama_error,
        "eur_usd_rate": float(os.getenv("EUR_USD", "1.09")),
    }


@router.get("/kb/pricing/{city}", summary="Inspect KB pricing for a city")
async def kb_pricing(city: str):
    from src.services.kb.kb_loader import get_kb_loader
    kb = get_kb_loader()
    city_l = city.lower()
    eur_usd = float(os.getenv("EUR_USD", "1.09"))
    hotel_data = {k: v.get(city_l) for k, v in kb.pricing_rules.get("hotels", {}).items() if city_l in v}
    # Add USD equivalent
    for cat, rates in hotel_data.items():
        if rates:
            hotel_data[cat] = {**rates, "avg_usd": round(rates["avg"], 2)}
    return {
        "city": city,
        "eur_usd_rate": eur_usd,
        "hotels": hotel_data,
        "sightseeing": kb.pricing_rules.get("sightseeing", {}).get(city_l, {}),
        "meals_eur_per_pax_per_day": kb.pricing_rules.get("meals_per_pax_per_day_eur", {}).get(city_l, {}),
    }
