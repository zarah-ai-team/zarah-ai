"""
Deterministic cost calculator.
Combines per-city hotel/meal costs, inter-city transport, guide fees, and misc
into a single CostBreakdown — all priced from the KB, never from the LLM.
"""
from __future__ import annotations

import logging
from typing import Dict, List

from src.models.costing import CostBreakdown
from src.models.trip_requirements import TripRequirements
from src.services.kb.pricing_engine import (
    get_guide_cost,
    get_hotel_cost,
    get_meal_cost,
    get_misc_cost,
    get_sightseeing_cost,
    get_transport_cost,
)

logger = logging.getLogger(__name__)


def calculate_full_trip_cost(
    req: TripRequirements,
    nights_per_city: Dict[str, int],
) -> CostBreakdown:
    bd = CostBreakdown()
    pax = req.traveler_profile.total_adults
    rooms = req.room_config.total_rooms or 2   # default 2 rooms if not set

    # ── Accommodation ────────────────────────────────────────────────
    for city, nights in nights_per_city.items():
        if nights > 0:
            bd.accommodation.append(
                get_hotel_cost(city, req.hotel_category, nights, rooms)
            )

    # ── Transport (inter-city + daily van) ───────────────────────────
    bd.transport.extend(
        get_transport_cost(req.route_segments, req.total_nights)
    )

    # ── Sightseeing ──────────────────────────────────────────────────
    for city, nights in nights_per_city.items():
        if nights <= 0:
            continue
        # Use mandatory sightseeing if specified for this city, else generic list
        city_activities = [
            s for s in req.mandatory_sightseeing
            if city.lower() in s.lower()
        ]
        if not city_activities:
            # Pull names from KB sightseeing options for the city
            from src.services.kb.kb_loader import get_kb_loader
            kb_opts = (
                get_kb_loader()
                .pricing_rules.get("sightseeing", {})
                .get(city.lower(), {})
            )
            city_activities = list(kb_opts.keys())[:4]  # top-4 KB items
        if not city_activities:
            city_activities = [f"General sightseeing in {city}"]

        bd.sightseeing.extend(get_sightseeing_cost(city, city_activities, pax))

    # ── Guide fees ───────────────────────────────────────────────────
    if req.guide_required:
        for city, nights in nights_per_city.items():
            if nights > 0:
                guide_days = max(1, nights - 1)  # one free evening assumed
                bd.guide_fees.append(get_guide_cost(city, guide_days, full_day=True))

    # ── Meals ────────────────────────────────────────────────────────
    for city, nights in nights_per_city.items():
        if nights > 0:
            bd.meals.append(get_meal_cost(city, nights, pax, "mid"))

    # ── Miscellaneous ────────────────────────────────────────────────
    bd.miscellaneous.append(get_misc_cost(req.total_nights, pax))

    logger.info(f"Cost calculation complete | total=${bd.total:.0f} USD")
    return bd
