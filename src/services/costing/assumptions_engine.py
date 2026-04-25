"""
Generates the operational assumptions set for a trip.
These are attached to the API response and injected into the LLM context
so the model can reference them rather than inventing caveats.
"""
from __future__ import annotations

import os
from typing import Dict, List

from src.models.trip_requirements import TripRequirements

_EUR_RATE = float(os.getenv("EUR_USD", "1.09"))


def generate_assumptions(req: TripRequirements, nights_per_city: Dict[str, int]) -> List[str]:
    a: List[str] = [
        "All costs are indicative estimates based on the internal KB pricing dataset. "
        "Final prices must be re-verified at booking time.",
        "Hotel rates are average market pricing; peak season (June–Aug) may add 15–25%.",
        "Private van rate includes driver, fuel, and highway tolls.",
        f"EUR → USD conversion applied at {_EUR_RATE:.4f} (verify before issuing quote).",
        "Guide fees are for a licensed English-speaking local guide (8-hour day).",
        "Meal costs are mid-range estimates excluding alcohol and room service.",
        f"Total trip duration: {req.total_nights} nights across {len(req.destinations)} destination(s).",
        "Visa, travel insurance, and international airfare are excluded.",
    ]

    if req.traveler_profile.is_senior_group:
        a.extend([
            f"Senior-friendly pacing: max 4–5 hours of activity per day for {req.traveler_profile.seniors_count} senior traveller(s).",
            "Rest periods scheduled between morning and afternoon activities.",
            "Wheelchair-accessible or low-walking routes prioritised at each site.",
            "All entrance tickets should be pre-booked with priority/accessible queues where available.",
        ])

    if req.transport_preference.value == "private_van":
        a.append(
            "Private van (Mercedes Viano class or equivalent): advance booking of 4–6 weeks recommended."
        )

    if req.driver_preference and "indian" in req.driver_preference.lower():
        a.append(
            "Indian-origin / Hindi-speaking driver: availability subject to confirmation; "
            "allow 3+ weeks lead time and may carry a 10–15% cost premium."
        )

    if req.guide_required:
        a.append(
            "Licensed local guide arranged per city on a day-hire basis. "
            "Indian-origin guide option requires 2+ weeks advance notice."
        )

    for city, nights in nights_per_city.items():
        if city.lower() == "prague" and nights > 0:
            a.append(
                "Prague: castle area entry by private car drop-off assumed to avoid steep climbs."
            )
        if city.lower() == "vienna" and nights > 0:
            a.append(
                "Vienna: Schönbrunn Palace and Hofburg visited with private van drop-off at main entrance."
            )
        if city.lower() == "budapest" and nights > 0:
            a.append(
                "Budapest: Buda Castle ascent via funicular (Sikló) — no hill walking required."
            )

    if req.missing_fields:
        a.append(
            f"The following fields were not provided and have been estimated: "
            f"{', '.join(req.missing_fields)}."
        )

    return a
