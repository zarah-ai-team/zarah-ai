"""
Deterministic pricing engine.
All costs come from the KB (kb_loader.pricing_rules).
Every CostLine carries source_type and confidence so the LLM never needs to invent prices.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from src.models.costing import CostBreakdown, CostLine, SourceType
from src.models.trip_requirements import HotelCategory, TripRequirements
from src.services.kb.kb_loader import get_kb_loader

logger = logging.getLogger(__name__)

EUR_TO_USD = float(os.getenv("EUR_USD", "1.09"))


def _eur(amount: float) -> float:
    return round(amount * EUR_TO_USD, 2)


# ------------------------------------------------------------------ #
# Public retrieval functions                                           #
# ------------------------------------------------------------------ #

def get_hotel_cost(city: str, category: HotelCategory, nights: int, rooms: int) -> CostLine:
    rules = get_kb_loader().pricing_rules.get("hotels", {})
    city_lower = city.lower()
    city_data = rules.get(category.value, {}).get(city_lower)

    if city_data:
        nightly_usd = city_data["avg"]
        total = round(nightly_usd * nights * rooms, 2)
        return CostLine(
            category="accommodation",
            description=f"{city} – {category.value.replace('_', ' ').title()} ({nights}N × {rooms} rooms)",
            unit_cost=nightly_usd,
            quantity=float(nights * rooms),
            total_cost=total,
            currency="USD",
            source_type=SourceType.KB_EXACT,
            source_ref=f"kb.hotels.{category.value}.{city_lower}",
            confidence=0.85,
            notes=f"${nightly_usd}/night/room (KB avg; verify for travel dates & seasonality)",
        )

    # Fallback rates when city isn't in KB
    fallback = {
        HotelCategory.THREE_STAR:     90,
        HotelCategory.FOUR_STAR:     150,
        HotelCategory.FOUR_STAR_DELUXE: 180,
        HotelCategory.FIVE_STAR:     350,
    }
    nightly_usd = fallback.get(category, 150)
    return CostLine(
        category="accommodation",
        description=f"{city} – {category.value.replace('_', ' ').title()} ({nights}N × {rooms} rooms)",
        unit_cost=nightly_usd,
        quantity=float(nights * rooms),
        total_cost=round(nightly_usd * nights * rooms, 2),
        currency="USD",
        source_type=SourceType.FALLBACK_RULE,
        confidence=0.55,
        notes=f"Estimated ${nightly_usd}/night/room — {city} not in KB",
    )


def get_transport_cost(
    route_segments: List[Any],
    total_days: int,
) -> List[CostLine]:
    rules = get_kb_loader().pricing_rules.get("transport", {})
    lines: List[CostLine] = []

    # Inter-city transfers
    for seg in route_segments:
        key = f"{seg.from_city.lower()}_{seg.to_city.lower()}"
        rev = f"{seg.to_city.lower()}_{seg.from_city.lower()}"
        transfer_rules = rules.get("inter_city_transfer", {})
        data = transfer_rules.get(key) or transfer_rules.get(rev)

        if data:
            cost_usd = _eur(data["cost_eur"])
            lines.append(CostLine(
                category="transport",
                description=f"Private transfer: {seg.from_city} → {seg.to_city}",
                unit_cost=cost_usd,
                quantity=1.0,
                total_cost=cost_usd,
                currency="USD",
                source_type=SourceType.KB_EXACT,
                source_ref=f"kb.transport.inter_city.{key}",
                confidence=0.82,
                notes=f"€{data['cost_eur']} @ EUR/USD={EUR_TO_USD}",
            ))
        else:
            est_usd = _eur(370)
            lines.append(CostLine(
                category="transport",
                description=f"Private transfer: {seg.from_city} → {seg.to_city}",
                unit_cost=est_usd,
                quantity=1.0,
                total_cost=est_usd,
                currency="USD",
                source_type=SourceType.FALLBACK_RULE,
                confidence=0.50,
                notes="Estimated €370 — route not in KB",
            ))

    # Daily private van cost
    daily_eur = rules.get("private_van_per_day_eur", 280)
    daily_usd = _eur(daily_eur)
    lines.append(CostLine(
        category="transport",
        description=f"Private van w/ driver — {total_days} days",
        unit_cost=daily_usd,
        quantity=float(total_days),
        total_cost=round(daily_usd * total_days, 2),
        currency="USD",
        source_type=SourceType.KB_EXACT,
        source_ref="kb.transport.private_van_per_day_eur",
        confidence=0.85,
        notes=f"€{daily_eur}/day incl. driver, fuel, tolls",
    ))

    return lines


def get_sightseeing_cost(city: str, activities: List[str], pax: int) -> List[CostLine]:
    rules = get_kb_loader().pricing_rules.get("sightseeing", {}).get(city.lower(), {})
    lines: List[CostLine] = []

    for activity in activities:
        key = _match_activity(activity, rules)
        if key:
            data = rules[key]
            cost_eur = data.get("cost_pp_eur", 0)
            cost_usd = _eur(cost_eur)
            total = round(cost_usd * pax, 2)
            lines.append(CostLine(
                category="sightseeing",
                description=f"{key.replace('_', ' ').title()} – {city} ({pax} pax)",
                unit_cost=cost_usd,
                quantity=float(pax),
                total_cost=total,
                currency="USD",
                source_type=SourceType.KB_EXACT,
                source_ref=f"kb.sightseeing.{city.lower()}.{key}",
                confidence=0.80,
                notes=data.get("note") or f"€{cost_eur}/person",
            ))
        else:
            est_usd = _eur(25)
            lines.append(CostLine(
                category="sightseeing",
                description=f"{activity} – {city} ({pax} pax)",
                unit_cost=est_usd,
                quantity=float(pax),
                total_cost=round(est_usd * pax, 2),
                currency="USD",
                source_type=SourceType.FALLBACK_RULE,
                confidence=0.50,
                notes="Estimated €25/person — activity not in KB",
            ))

    return lines


def get_guide_cost(city: str, days: int, full_day: bool = True) -> CostLine:
    rules = get_kb_loader().pricing_rules.get("guides", {})
    rate_eur = rules.get("full_day_eur" if full_day else "half_day_eur", 200)
    daily_usd = _eur(rate_eur)
    note_suffix = rules.get("note", "")

    return CostLine(
        category="guide_fees",
        description=f"Licensed guide – {city} ({days}{'d' if days > 1 else ' day'})",
        unit_cost=daily_usd,
        quantity=float(days),
        total_cost=round(daily_usd * days, 2),
        currency="USD",
        source_type=SourceType.KB_EXACT,
        source_ref=f"kb.guides.{'full' if full_day else 'half'}_day",
        confidence=0.80,
        notes=note_suffix,
    )


def get_meal_cost(city: str, days: int, pax: int, level: str = "mid") -> CostLine:
    rules = get_kb_loader().pricing_rules.get("meals_per_pax_per_day_eur", {})
    city_rates = rules.get(city.lower()) or rules.get("_default", {"mid": 35})
    daily_eur = city_rates.get(level, 35)
    daily_usd = _eur(daily_eur)
    total = round(daily_usd * days * pax, 2)

    return CostLine(
        category="meals",
        description=f"Meals – {city} ({days}d × {pax} pax, {level})",
        unit_cost=daily_usd,
        quantity=float(days * pax),
        total_cost=total,
        currency="USD",
        source_type=SourceType.KB_EXACT if city.lower() in rules else SourceType.FALLBACK_RULE,
        confidence=0.72,
        notes=f"€{daily_eur}/person/day (excl. alcohol, room service)",
    )


def get_misc_cost(days: int, pax: int) -> CostLine:
    daily_eur = get_kb_loader().pricing_rules.get("misc_per_pax_per_day_eur", 15)
    daily_usd = _eur(daily_eur)
    total = round(daily_usd * days * pax, 2)
    return CostLine(
        category="miscellaneous",
        description=f"Misc (tips, water, city tax) – {days}d × {pax} pax",
        unit_cost=daily_usd,
        quantity=float(days * pax),
        total_cost=total,
        currency="USD",
        source_type=SourceType.FALLBACK_RULE,
        confidence=0.70,
        notes=f"€{daily_eur}/person/day",
    )


# ------------------------------------------------------------------ #
# Internal helpers                                                      #
# ------------------------------------------------------------------ #

def _match_activity(activity: str, rules: Dict[str, Any]) -> Optional[str]:
    if not rules:
        return None
    al = activity.lower().replace(" ", "_")
    # 1. Exact key match
    if al in rules:
        return al
    # 2. Activity name contains key name (e.g. "prague_castle_tour" → "prague_castle")
    for key in rules:
        if key in al or al in key:
            return key
    # 3. All significant words in activity appear in key (avoid "palace" matching wrong entry)
    al_words = set(al.replace("_", " ").split()) - {"the", "a", "an", "of", "in", "and"}
    for key in rules:
        key_words = set(key.replace("_", " ").split())
        if al_words and al_words.issubset(key_words):
            return key
    return None
