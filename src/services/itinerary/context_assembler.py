"""
Context assembler — merges KB data, web research, costs, and constraints into
a structured prompt context for the Ollama generation call.

Keeps token count under MAX_CONTEXT_CHARS by truncating lower-priority sections.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from src.models.costing import CostBreakdown
from src.models.trip_requirements import TripRequirements
from src.services.kb.kb_retriever import DestinationContext

logger = logging.getLogger(__name__)

MAX_CONTEXT_CHARS = 10_000   # ~2.5k tokens; keeps total input within num_ctx=8192


class KBContextPacket:
    """Structured context packet passed to the itinerary generator."""

    __slots__ = (
        "trip_summary", "traveler_profile", "route_plan",
        "hotel_plan", "transport_plan", "sightseeing_candidates",
        "cost_basis", "assumptions", "risk_notes", "web_research",
    )

    def __init__(self):
        for s in self.__slots__:
            setattr(self, s, "")

    def to_prompt_context(self) -> str:
        sections = [
            ("TRIP SUMMARY",                            self.trip_summary),
            ("TRAVELER PROFILE",                        self.traveler_profile),
            ("ROUTE PLAN",                              self.route_plan),
            ("HOTEL PLAN",                              self.hotel_plan),
            ("TRANSPORT PLAN",                          self.transport_plan),
            ("SIGHTSEEING CANDIDATES (use these only)", self.sightseeing_candidates),
            ("COST BASIS (use these numbers only)",     self.cost_basis),
            ("OPERATIONAL ASSUMPTIONS",                 self.assumptions),
            ("RISK NOTES",                              self.risk_notes),
            ("REAL-TIME WEB RESEARCH",                  self.web_research),
        ]
        parts: List[str] = []
        total = 0
        for title, content in sections:
            if not content:
                continue
            section = f"\n### {title}\n{content}"
            allowed = MAX_CONTEXT_CHARS - total
            if allowed <= 0:
                break
            parts.append(section[:allowed])
            total += len(section)
        return "\n".join(parts)


def assemble_context(
    req: TripRequirements,
    dest_contexts: Dict[str, DestinationContext],
    web_research: Any,                   # WebResearchResult | None
    cost_breakdown: CostBreakdown,
    nights_per_city: Dict[str, int],
    assumptions: List[str],
) -> KBContextPacket:
    pkt = KBContextPacket()

    # ── Trip summary ─────────────────────────────────────────────────
    pkt.trip_summary = (
        f"Client        : {req.client_name or 'Not specified'}\n"
        f"Route         : {' → '.join(req.destinations)}\n"
        f"Duration      : {req.total_nights} nights\n"
        f"Start date    : {req.trip_start_date or 'TBC'}\n"
        f"Origin        : {req.origin}\n"
        f"Nights/city   : {json.dumps(nights_per_city)}"
    )

    # ── Traveler profile ─────────────────────────────────────────────
    tp = req.traveler_profile
    pkt.traveler_profile = (
        f"Adults        : {tp.total_adults}\n"
        f"Seniors (60+) : {tp.seniors_count}\n"
        f"Children      : {tp.children_count}\n"
        f"Pace          : {req.pace.value}\n"
        f"Walking       : {req.walking_tolerance.value}\n"
        f"Senior-friendly required : {req.needs_senior_friendly}\n"
        f"Guide required: {req.guide_required}\n"
        f"Driver pref   : {req.driver_preference or 'standard'}"
    )

    # ── Route plan ───────────────────────────────────────────────────
    route_lines: List[str] = []
    for seg in req.route_segments:
        dur = f"~{seg.estimated_duration_hours:.1f}h" if seg.estimated_duration_hours else "duration TBC"
        dist = f", {seg.distance_km:.0f} km" if seg.distance_km else ""
        route_lines.append(f"  {seg.from_city} → {seg.to_city}: {dur} by {seg.travel_mode}{dist}")
    pkt.route_plan = "\n".join(route_lines) or "Single-city trip; no inter-city transfers."

    # ── Hotel plan ───────────────────────────────────────────────────
    hotel_lines: List[str] = []
    for city, nights in nights_per_city.items():
        ctx = dest_contexts.get(city)
        areas = ctx.hotel_areas if ctx else []
        cat_label = req.hotel_category.value.replace("_", " ").title()
        hotel_lines.append(
            f"  {city}: {nights}N, {cat_label}\n"
            f"    Recommended areas: {'; '.join(areas) or 'city centre preferred'}\n"
            f"    City-centre required: {req.needs_city_centre_hotel}"
        )
    pkt.hotel_plan = "\n".join(hotel_lines)

    # ── Transport plan ───────────────────────────────────────────────
    pkt.transport_plan = (
        f"Vehicle       : {req.vehicle_type}\n"
        f"Driver pref   : {req.driver_preference or 'standard'}\n"
        f"Total hire days: {req.total_nights}\n"
        f"Includes      : driver, fuel, highway tolls"
    )

    # ── Sightseeing candidates ────────────────────────────────────────
    sight_lines: List[str] = []
    for city, ctx in dest_contexts.items():
        if not ctx:
            continue
        sight_lines.append(f"\n  [{city}]")
        for opt in ctx.sightseeing_options:
            cost_str = f"€{opt['cost_eur']}/pp" if opt["cost_eur"] else "free"
            dur_str  = f" | {opt['hours']}h" if opt.get("hours") else ""
            note_str = f" ({opt['note']})" if opt.get("note") else ""
            sight_lines.append(f"    • {opt['name']}: {cost_str}{dur_str}{note_str}")
        if ctx.senior_notes:
            sight_lines.append("    Senior access notes:")
            for n in ctx.senior_notes:
                sight_lines.append(f"      – {n}")
        if ctx.sightseeing_notes:
            sight_lines.append("    Suggested sequence:")
            for n in ctx.sightseeing_notes:
                sight_lines.append(f"      – {n}")
    pkt.sightseeing_candidates = "\n".join(sight_lines)

    # ── Cost basis ────────────────────────────────────────────────────
    cost_lines: List[str] = []
    for line in cost_breakdown.all_lines():
        cost_lines.append(
            f"  [{line.source_type.value}|{line.confidence:.0%}] "
            f"{line.description}: ${line.total_cost:.0f} USD"
            + (f" | {line.notes}" if line.notes else "")
        )
    summary = cost_breakdown.to_summary()
    cost_lines.append(f"\n  TOTAL: ${summary['total']:.0f} USD for {req.traveler_profile.total_adults} persons")
    cost_lines.append(
        f"  Per person: ${summary['total'] / max(req.traveler_profile.total_adults, 1):.0f} USD"
    )
    pkt.cost_basis = "\n".join(cost_lines)

    # ── Assumptions ───────────────────────────────────────────────────
    pkt.assumptions = "\n".join(f"  – {a}" for a in assumptions)

    # ── Web research ──────────────────────────────────────────────────
    if web_research:
        pkt.web_research = web_research.to_context_string()[:6000]

    # ── Risk notes ────────────────────────────────────────────────────
    risks: List[str] = []
    if req.missing_fields:
        risks.append(f"Missing fields (estimated): {', '.join(req.missing_fields)}")
    if web_research and getattr(web_research, "failed_queries", []):
        risks.append(f"{len(web_research.failed_queries)} web queries unavailable — KB fallback used")
    pkt.risk_notes = "\n".join(f"  ⚠ {r}" for r in risks) or "  None identified."

    return pkt
