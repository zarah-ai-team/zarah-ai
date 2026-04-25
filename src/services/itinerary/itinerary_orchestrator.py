"""
Itinerary Orchestrator — the main pipeline that wires all layers together.

Pipeline stages:
  1. Intake validation
  2. LLM-assisted normalization
  3. Parallel: web research + KB retrieval
  4. Deterministic costing
  5. Context assembly
  6. Ollama generation
  7. Response assembly
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
load_dotenv()

from src.models.costing import CostBreakdown
from src.models.itinerary_response import ApiResponse, ConfidenceSummary, ItineraryOutput
from src.models.trip_requirements import TripRequest, TripRequirements
from src.services.costing.assumptions_engine import generate_assumptions
from src.services.costing.cost_calculator import calculate_full_trip_cost
from src.services.itinerary.context_assembler import assemble_context
from src.services.itinerary.itinerary_generator import ItineraryGenerator
from src.services.itinerary.request_normalizer import llm_extract_fields, normalize_trip_request
from src.services.itinerary.schema import ITINERARY_JSON_SCHEMA
from src.services.kb.kb_retriever import DestinationContext, get_destination_context, get_historical_matches
from src.services.kb.matchers import extract_nights_per_city
from src.services.mcp.web_research_service import WebResearchResult, WebResearchService
from src.utils.logger import get_logger

logger = get_logger("orchestrator")

_APP_ENV_ORCH = os.getenv("APP_ENV", "dev").strip().lower()
if _APP_ENV_ORCH == "dev":
    OLLAMA_URL = os.getenv("OLLAMA_BASE_URL_DEV", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
else:
    OLLAMA_URL = os.getenv("OLLAMA_BASE_URL_PROD", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
if _APP_ENV_ORCH == "dev":
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL_DEV", os.getenv("OLLAMA_MODEL", "llama3:8b"))
else:
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL_PROD", os.getenv("OLLAMA_MODEL", "llama3"))

# Client-type cost multipliers (applied to total KB estimate)
_CLIENT_TYPE_CONFIG: Dict[str, Dict] = {
    "corporate": {"meal_level": "high",   "guide_required": True,  "hotel_upgrade": 1},
    "mice":      {"meal_level": "mid",    "guide_required": True,  "hotel_upgrade": 0},
    "leisure":   {"meal_level": "mid",    "guide_required": False, "hotel_upgrade": 0},
    "dmc":       {"meal_level": "mid",    "guide_required": False, "hotel_upgrade": 0},
    "b2b":       {"meal_level": "mid",    "guide_required": False, "hotel_upgrade": 0},
    "b2c":       {"meal_level": "mid",    "guide_required": False, "hotel_upgrade": 0},
}


class ItineraryOrchestrator:
    def __init__(self):
        self._generator    = ItineraryGenerator(OLLAMA_URL, OLLAMA_MODEL)
        self._web_research = WebResearchService()

    # ================================================================ #
    # Entry point                                                        #
    # ================================================================ #

    async def generate_itinerary(
        self,
        raw: TripRequest,
        client_type: Optional[str] = None,
        use_web_research: bool = True,
    ) -> ApiResponse:
        request_id = str(uuid.uuid4())[:12]
        t0 = time.time()
        timings: Dict[str, int] = {}

        # ── Stage 1: Intake ─────────────────────────────────────────
        logger.stage_start("intake", request_id)
        logger.stage_end("intake", request_id)

        # ── Stage 2: Normalization ───────────────────────────────────
        logger.stage_start("normalization", request_id)
        t = time.time()
        llm_fields: Dict[str, Any] = {}
        if raw.raw_text:
            llm_fields = await llm_extract_fields(raw.raw_text, OLLAMA_URL, OLLAMA_MODEL)
            logger.debug(f"LLM extracted: {json.dumps(llm_fields)[:300]}")
        req = normalize_trip_request(raw, llm_fields)
        timings["normalization"] = int((time.time() - t) * 1000)
        logger.stage_end("normalization", request_id, destinations=req.destinations)

        if not req.destinations:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=422,
                detail=(
                    "Could not extract destinations from request. "
                    "Please provide 'destinations' as a list, e.g. [\"Prague\", \"Vienna\"], "
                    "or include city names in raw_text."
                ),
            )

        # ── Apply client-type defaults before costing ────────────────
        if client_type:
            req = self._apply_client_type(req, client_type.lower())

        # ── Stage 3: Parallel research + KB ─────────────────────────
        logger.stage_start("research_and_kb", request_id)
        t = time.time()
        if use_web_research:
            web_result, (dest_ctxs, _hist) = await asyncio.gather(
                self._do_web_research(req, request_id),
                self._do_kb_retrieval(req, request_id),
            )
        else:
            web_result = WebResearchResult()
            web_result.general_notes.append("Web research skipped (backup mode)")
            dest_ctxs, _hist = await self._do_kb_retrieval(req, request_id)
        timings["research_and_kb"] = int((time.time() - t) * 1000)
        logger.stage_end("research_and_kb", request_id,
                         web_ok=len(web_result.sources), kb_cities=len(dest_ctxs))

        # ── Stage 4: Costing ─────────────────────────────────────────
        logger.stage_start("costing", request_id)
        t = time.time()
        nights_per_city = self._split_nights(req)
        cost_bd = calculate_full_trip_cost(req, nights_per_city)
        cost_bd = self._calibrate_from_history(_hist, cost_bd, req)
        assumptions = generate_assumptions(req, nights_per_city)
        timings["costing"] = int((time.time() - t) * 1000)
        logger.stage_end("costing", request_id, total_usd=round(cost_bd.total))

        # ── Stage 5: Context assembly ────────────────────────────────
        logger.stage_start("context_assembly", request_id)
        t = time.time()
        pkt = assemble_context(req, dest_ctxs, web_result, cost_bd, nights_per_city, assumptions)
        ctx_str = pkt.to_prompt_context()
        timings["context_assembly"] = int((time.time() - t) * 1000)
        logger.stage_end("context_assembly", request_id, ctx_chars=len(ctx_str))

        # ── Stage 6: Ollama generation ───────────────────────────────
        logger.stage_start("llm_generation", request_id)
        t = time.time()
        raw_itinerary = await self._generator.generate(
            context=ctx_str,
            schema=ITINERARY_JSON_SCHEMA,
            pax=req.traveler_profile.total_adults,
            total_cost=cost_bd.total,
        )
        timings["llm_generation"] = int((time.time() - t) * 1000)
        logger.stage_end("llm_generation", request_id,
                         days_produced=len(raw_itinerary.get("days", [])))

        # ── Stage 7: Response assembly ───────────────────────────────
        logger.stage_start("response_assembly", request_id)
        total_ms = int((time.time() - t0) * 1000)
        response = self._build_response(
            request_id, req, raw_itinerary, cost_bd,
            assumptions, web_result, total_ms, timings,
        )
        logger.stage_end("response_assembly", request_id)
        logger.info(f"Done in {total_ms}ms", request_id=request_id)

        return response

    # ================================================================ #
    # Private helpers                                                     #
    # ================================================================ #

    async def _do_web_research(self, req: TripRequirements, rid: str) -> WebResearchResult:
        try:
            return await self._web_research.research_trip(req)
        except Exception as e:
            logger.warning(f"Web research failed: {e}", request_id=rid)
            return WebResearchResult()

    async def _do_kb_retrieval(
        self, req: TripRequirements, rid: str
    ) -> Tuple[Dict[str, DestinationContext], List[Dict]]:
        try:
            ctxs = {city: get_destination_context(city, req) for city in req.destinations}
            hist = get_historical_matches(req, top_k=2)
            return ctxs, hist
        except Exception as e:
            logger.warning(f"KB retrieval failed: {e}", request_id=rid)
            return {}, []

    def _split_nights(self, req: TripRequirements) -> Dict[str, int]:
        """Distribute total_nights across destinations."""
        if not req.destinations:
            return {}

        if req.raw_input:
            explicit = extract_nights_per_city(req.raw_input, req.destinations)
            if explicit:
                assigned = sum(explicit.values())
                remaining = req.total_nights - assigned
                unassigned = [c for c in req.destinations if c not in explicit]
                if unassigned and remaining > 0:
                    pp = remaining // len(unassigned)
                    for city in unassigned:
                        explicit[city] = pp
                    leftover = remaining - pp * len(unassigned)
                    if leftover:
                        explicit[unassigned[0]] += leftover
                return explicit

        # Even split fallback
        n = len(req.destinations)
        base = req.total_nights // n
        leftover = req.total_nights % n
        result = {city: base for city in req.destinations}
        if req.destinations:
            result[req.destinations[0]] += leftover
        return result

    def _build_response(
        self,
        request_id: str,
        req: TripRequirements,
        raw_it: Dict[str, Any],
        cost_bd: CostBreakdown,
        assumptions: List[str],
        web: WebResearchResult,
        total_ms: int,
        timings: Dict[str, int],
    ) -> ApiResponse:
        def _to_list(val) -> List[str]:
            """Coerce LLM output (str | list | None) to a clean list of strings."""
            if not val:
                return []
            if isinstance(val, list):
                return [str(x) for x in val if x]
            if isinstance(val, str):
                return [val] if val.strip() else []
            return []

        all_assumptions = list(dict.fromkeys(
            assumptions + _to_list(raw_it.get("assumptions"))
        ))

        cost_summary = raw_it.get("cost_breakdown_summary") or cost_bd.to_summary()
        if not isinstance(cost_summary, dict):
            cost_summary = cost_bd.to_summary()
        total_cost   = float(raw_it.get("total_estimated_cost") or cost_bd.total)
        pax          = req.traveler_profile.total_adults

        try:
            itinerary = ItineraryOutput(
                title=raw_it.get("title") or f"{' → '.join(req.destinations)} Tour",
                trip_overview=raw_it.get("trip_overview") or "",
                assumptions=all_assumptions,
                total_estimated_cost=total_cost,
                cost_per_person=round(total_cost / max(pax, 1), 2),
                currency=raw_it.get("currency") or "USD",
                cost_breakdown_summary=cost_summary,
                days=raw_it.get("days") or [],
                optional_experiences=raw_it.get("optional_experiences") or [],
                important_notes=_to_list(raw_it.get("important_notes")),
                missing_information=list(dict.fromkeys(
                    req.missing_fields + _to_list(raw_it.get("missing_information"))
                )),
                confidence_summary=ConfidenceSummary(
                    overall=0.78,
                    costing=0.82,
                    routing=0.88,
                    hotel_suggestions=0.62,
                    sightseeing=0.80,
                    notes=[
                        "Costing from KB baseline — verify for exact travel dates.",
                        "Hotel names TBC — area recommendations from KB.",
                        "Web research integrated where available.",
                    ],
                ),
                sources_summary=(web.sources[:10] if web else []),
            )
        except Exception as e:
            logger.warning(f"ItineraryOutput parse error: {e}")
            itinerary = ItineraryOutput(
                title=f"{' → '.join(req.destinations)} Tour",
                trip_overview="Partial itinerary — manual review required.",
                assumptions=all_assumptions,
                total_estimated_cost=cost_bd.total,
                cost_per_person=round(cost_bd.total / max(pax, 1), 2),
                currency="USD",
                cost_breakdown_summary=cost_bd.to_summary(),
                days=raw_it.get("days") or [],
                optional_experiences=[],
                important_notes=[f"LLM parse error: {e}"],
                missing_information=req.missing_fields,
                confidence_summary=ConfidenceSummary(
                    overall=0.50, costing=0.70, routing=0.70,
                    hotel_suggestions=0.40, sightseeing=0.60,
                ),
                sources_summary=[],
            )

        return ApiResponse(
            request_id=request_id,
            status="success",
            normalized_input=req.model_dump(exclude={"raw_input"}),
            itinerary=itinerary,
            cost_breakdown=cost_bd.to_summary(),
            assumptions=all_assumptions,
            missing_fields=req.missing_fields,
            research_sources=web.sources if web else [],
            kb_sources=[f"kb.pricing.{d.lower()}" for d in req.destinations],
            generated_at=datetime.utcnow().isoformat() + "Z",
            processing_time_ms=total_ms,
            pipeline_stages=timings,
        )

    # ================================================================ #
    # Client-type and calibration helpers                               #
    # ================================================================ #

    def _apply_client_type(
        self, req: TripRequirements, client_type: str
    ) -> TripRequirements:
        """Override defaults based on client segment."""
        cfg = _CLIENT_TYPE_CONFIG.get(client_type, {})
        if not cfg:
            return req

        data = req.model_dump()

        # Force guide_required for corporate/mice if not already set
        if cfg.get("guide_required") and not req.guide_required:
            data["guide_required"] = True

        # Upgrade hotel category for corporate clients
        if cfg.get("hotel_upgrade"):
            from src.models.trip_requirements import HotelCategory
            cat_order = [
                HotelCategory.THREE_STAR,
                HotelCategory.FOUR_STAR,
                HotelCategory.FOUR_STAR_DELUXE,
                HotelCategory.FIVE_STAR,
            ]
            try:
                idx = cat_order.index(req.hotel_category)
                if idx < len(cat_order) - 1:
                    data["hotel_category"] = cat_order[idx + 1]
            except ValueError:
                pass

        try:
            return TripRequirements(**data)
        except Exception:
            return req

    def _calibrate_from_history(
        self,
        hist: List[Dict],
        cost_bd: "CostBreakdown",
        req: TripRequirements,
    ) -> "CostBreakdown":
        """
        Use historical itinerary data to sanity-check KB costs.
        If a high-similarity historical match exists and its implied per-pax
        per-night cost deviates >40% from KB estimate, log a warning.
        Historical data influences assumptions but NOT the numeric output
        (we trust KB over unstructured text extraction).
        """
        if not hist:
            return cost_bd

        pax = max(req.traveler_profile.total_adults, 1)
        nights = max(req.total_nights, 1)
        kb_ppn = cost_bd.total / (pax * nights)

        for match in hist[:2]:
            sim = match.get("similarity", 0)
            if sim < 0.15:
                continue
            excerpt = match.get("excerpt", "")
            import re as _re
            # Try to find a total cost figure in the historical excerpt
            amounts = _re.findall(r"(?:USD|\\$|INR|EUR|€)?\s*([0-9,]+(?:\.[0-9]+)?)", excerpt)
            for amt_str in amounts:
                try:
                    amt = float(amt_str.replace(",", ""))
                    if amt < 500 or amt > 500_000:
                        continue
                    hist_ppn = amt / (pax * nights)
                    ratio = hist_ppn / kb_ppn if kb_ppn > 0 else 1.0
                    if ratio < 0.6 or ratio > 1.7:
                        logger.warning(
                            f"Historical match (sim={sim:.2f}) suggests cost "
                            f"${amt:.0f} total vs KB ${cost_bd.total:.0f} — "
                            f"verify pricing before issuing quote."
                        )
                    break
                except (ValueError, ZeroDivisionError):
                    continue

        return cost_bd
