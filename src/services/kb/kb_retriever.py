"""
KB retrieval layer — destination context, senior notes, hotel areas, and
historical itinerary matching via TF-IDF.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from src.models.trip_requirements import TripRequirements
from src.services.kb.kb_loader import get_kb_loader

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# Static destination knowledge                                         #
# ------------------------------------------------------------------ #

_SENIOR_NOTES: Dict[str, List[str]] = {
    "prague": [
        "Prague Castle: access via private car drop-off at upper gate — avoids all steep climbs.",
        "Old Town Square is flat and within 10-min walk from most city-centre hotels.",
        "Vltava river cruise: entirely seated, scenic, highly recommended for seniors.",
        "Skip Vinohrady steps area; Malá Strana accessible by tram or van.",
        "Petřín Hill: cable car available — no walking required to reach the top.",
    ],
    "vienna": [
        "Schönbrunn Palace: private van drop-off at main entrance; gardens flat on central path.",
        "Hofburg Palace ground floor (Imperial Apartments) fully accessible, no stairs.",
        "Belvedere lower garden path is flat; upper terrace requires 10-min gentle walk.",
        "Vienna Ring Road highlights can be done as a drive-by tour from the van — zero walking.",
        "St. Stephen's Cathedral: exterior and main nave accessible; tower involves stairs.",
    ],
    "budapest": [
        "Buda Castle: funicular (Sikló) from Chain Bridge base — no walking up the hill.",
        "Fisherman's Bastion: elevator access available for most viewing platforms.",
        "Parliament tour: timed entry booking recommended; involves 1h standing inside.",
        "Danube evening cruise: entirely seated, excellent for seniors.",
        "Heroes' Square: flat open plaza, easy access from private van.",
    ],
}

_HOTEL_AREAS: Dict[str, List[str]] = {
    "prague": [
        "Staré Město (Old Town) – closest to all major attractions, flat streets.",
        "Malá Strana – scenic riverside area, quieter; some cobblestone lanes.",
        "Nové Město (New Town) – modern, wide pavements, good transport links.",
    ],
    "vienna": [
        "1st District (Innere Stadt) – walking distance to Hofburg, Ring Road, opera.",
        "Ringstrasse Area – prestigious boulevard, premium 5★ properties.",
        "3rd District (Landstrasse) – Belvedere area, quiet and upscale.",
    ],
    "budapest": [
        "Pest – V. District (City Centre): near Chain Bridge, Parliament, easy access.",
        "Buda – Castle District: scenic, quieter; van required to reach attractions.",
        "Andrássy Avenue area (VI. District): elegant boulevard, Heroes' Square nearby.",
    ],
}

_SIGHTSEEING_NOTES: Dict[str, List[str]] = {
    "prague": [
        "Morning: Prague Castle complex (arrive early, use car drop-off).",
        "Afternoon: Old Town Square + Astronomical Clock (short walk).",
        "Evening: Vltava river cruise (1h, fully seated).",
        "Day 2 option: Jewish Quarter (Josefov) — flat, guided walk ~2h.",
        "Optional: Kutná Hora day trip (1.5h from Prague, flat bone church visit).",
    ],
    "vienna": [
        "Morning: Schönbrunn Palace (private van entry).",
        "Afternoon: Hofburg Imperial Apartments + Spanish Riding School exterior.",
        "Ring Road drive-by: Opera, Parliament, Rathaus, Burgtheater (from van).",
        "Day 2: Belvedere Palace lower garden + gallery.",
        "Optional: Vienna Woods half-day excursion by van.",
    ],
    "budapest": [
        "Morning: Parliament exterior + Fisherman's Bastion (funicular up).",
        "Afternoon: Buda Castle (funicular, light walk inside courtyard).",
        "Evening: Danube cruise (1h, seated).",
        "Day 2: Pest side: Great Market Hall (flat), Heroes' Square.",
        "Optional: Puszta countryside day trip by van.",
    ],
}


class DestinationContext:
    def __init__(self, city: str):
        self.city = city
        self.senior_notes: List[str] = []
        self.hotel_areas: List[str] = []
        self.sightseeing_notes: List[str] = []
        self.sightseeing_options: List[Dict[str, Any]] = []
        self.known_prices: Dict[str, Any] = {}


def get_destination_context(city: str, req: TripRequirements) -> DestinationContext:
    ctx = DestinationContext(city)
    city_lower = city.lower()
    kb = get_kb_loader()

    ctx.senior_notes = _SENIOR_NOTES.get(city_lower, [])
    ctx.hotel_areas = _HOTEL_AREAS.get(city_lower, [])
    ctx.sightseeing_notes = _SIGHTSEEING_NOTES.get(city_lower, [])

    sight_kb = kb.pricing_rules.get("sightseeing", {}).get(city_lower, {})
    ctx.sightseeing_options = [
        {
            "name": k.replace("_", " ").title(),
            "cost_eur": v.get("cost_pp_eur", 0),
            "hours": v.get("hours"),
            "note": v.get("note"),
        }
        for k, v in sight_kb.items()
    ]

    ctx.known_prices = {
        "hotel_avg_usd": kb.pricing_rules.get("hotels", {})
            .get("4_star_deluxe", {}).get(city_lower, {}),
    }
    return ctx


def get_historical_matches(req: TripRequirements, top_k: int = 3) -> List[Dict]:
    docs = get_kb_loader().itinerary_docs
    if not docs:
        return []

    query = (
        " ".join(req.destinations)
        + f" {req.total_nights} nights"
        + f" {req.transport_preference.value}"
        + (" senior" if req.needs_senior_friendly else "")
    )

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np

        # Limit corpus size to keep vectorization fast
        max_docs = 30
        corpus = docs[:max_docs]
        texts = [d["text"][:1500] for d in corpus] + [query]
        vec = TfidfVectorizer(max_features=500, stop_words="english")
        matrix = vec.fit_transform(texts)
        sims = cosine_similarity(matrix[-1], matrix[:-1])[0]
        top_idx = np.argsort(sims)[::-1][:top_k]

        return [
            {"similarity": float(sims[i]), "excerpt": corpus[i]["text"][:400]}
            for i in top_idx if sims[i] > 0.05
        ]
    except Exception as e:
        logger.warning(f"Historical match failed: {e}")
        return []
