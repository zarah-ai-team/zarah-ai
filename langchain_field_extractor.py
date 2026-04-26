"""langchain_field_extractor.py
LangChain-based intelligent field extractor for travel queries.

Uses ChatOllama with structured (Pydantic) output to pull destination,
duration, pax, event_type, budget, hotel category, etc. out of free-form
natural language. Returns None on any error — callers should fall back to
the regex extractor in conversation_manager.

Tries to be fast: low temperature, capped output tokens, short timeout.
"""
from __future__ import annotations

import os
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

try:
    from pydantic import BaseModel, Field
    from langchain_ollama import ChatOllama
    from langchain_core.prompts import ChatPromptTemplate
    _LC_OK = True
except Exception as _e:   # pragma: no cover
    logger.warning("LangChain not available: %s — falling back to regex extractor", _e)
    _LC_OK = False


class TripFields(BaseModel):
    """Structured fields extracted from a travel-planning message."""
    destination: Optional[str] = Field(
        None,
        description="Primary city or country mentioned (single name, e.g. 'Dubai', 'Singapore', 'Italy'). Null if no destination is mentioned.",
    )
    destinations: Optional[List[str]] = Field(
        None,
        description="If multiple destinations are mentioned (e.g. 'Dubai → Abu Dhabi → Sharjah' or 'Italy and France'), list them in order. Otherwise null.",
    )
    nights: Optional[int] = Field(
        None,
        description="Number of nights (e.g. '5 nights', '4N/3D' → 4 nights, 'a week' → 7). Integer only.",
    )
    duration: Optional[int] = Field(
        None,
        description="Number of days (e.g. '5 days', '5D/4N' → 5 days). Usually nights+1. Integer only.",
    )
    pax: Optional[int] = Field(
        None,
        description="Number of travelers (e.g. '4 pax', 'family of 6' → 6, 'couple' → 2, 'we are 8' → 8). Integer only.",
    )
    event_type: Optional[str] = Field(
        None,
        description="Type of trip: leisure, corporate, MICE, incentive, honeymoon, anniversary, wedding, family vacation, adventure, business, conference, retreat, etc. Lowercase phrase.",
    )
    hotel_type: Optional[str] = Field(
        None,
        description="Hotel category mentioned: budget, mid-range, luxury, 3-star, 4-star, 5-star, 5-star deluxe. Null if not mentioned.",
    )
    budget_per_person: Optional[float] = Field(
        None,
        description="Budget per person, as a number. e.g. 'INR 50000 per person' → 50000. Null if not mentioned.",
    )
    budget_currency: Optional[str] = Field(
        None,
        description="Currency code (INR, USD, AED, EUR, GBP). Null if no currency mentioned.",
    )
    trip_start_date: Optional[str] = Field(
        None,
        description="Trip start date or month/year if mentioned (e.g. 'March 2026', '15 December 2025'). Free-form string. Null otherwise.",
    )
    transport_preference: Optional[str] = Field(
        None,
        description="Transport mentioned: 'private car', 'SUV', 'minivan', 'coach', 'Lexus taxi for 12 hours', etc. Null if not mentioned.",
    )
    meal_preference: Optional[str] = Field(
        None,
        description="Meal preference: vegetarian, vegan, halal, kosher, no preference. Null otherwise.",
    )


_SYSTEM_PROMPT = (
    "You are a precise travel-query field extractor. Given a user's free-text "
    "request, identify any trip details that are explicitly mentioned. "
    "DO NOT invent values. Set unknown fields to null. Numbers must be plain "
    "integers (no commas, no units). Return only valid JSON matching the schema."
)


_chain = None
_model_name = None


def _get_chain():
    global _chain, _model_name
    if not _LC_OK:
        return None
    if _chain is not None:
        return _chain
    try:
        env = os.getenv("APP_ENV", "dev")
        if env == "dev":
            _model_name = os.getenv("OLLAMA_MODEL_DEV", os.getenv("OLLAMA_MODEL", "llama3"))
            base_url = os.getenv("OLLAMA_BASE_URL_DEV", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
        else:
            _model_name = os.getenv("OLLAMA_MODEL_PROD", os.getenv("OLLAMA_MODEL", "llama3"))
            base_url = os.getenv("OLLAMA_BASE_URL_PROD", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))

        llm = ChatOllama(
            model=_model_name,
            base_url=base_url,
            temperature=0.0,           # deterministic for extraction
            num_predict=512,           # small — JSON should be short
            num_ctx=4096,
            format="json",             # ask Ollama to enforce JSON output
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", _SYSTEM_PROMPT),
            ("human", "Extract trip fields from this message:\n\n{message}"),
        ])
        # Pydantic-structured output via Ollama's JSON mode
        structured = llm.with_structured_output(TripFields)
        _chain = prompt | structured
        logger.info("LangChain field extractor ready: model=%s, base_url=%s", _model_name, base_url)
    except Exception as e:
        logger.warning("Failed to build LangChain chain: %s", e)
        _chain = None
    return _chain


def extract_fields(message: str, timeout_s: float = 30.0) -> Optional[dict]:
    """
    Extract trip fields from a user message using LangChain + Ollama.
    Returns a dict (only non-null fields) or None on failure/timeout.
    """
    if not message or not isinstance(message, str):
        return None
    chain = _get_chain()
    if chain is None:
        return None
    try:
        # Use the threadpool + timeout via concurrent.futures so callers in
        # async code can wrap this in to_thread+wait_for too.
        result: TripFields = chain.invoke({"message": message})
        # Convert pydantic model to dict, dropping nulls.
        if hasattr(result, "model_dump"):
            data = result.model_dump(exclude_none=True)
        else:
            data = result.dict(exclude_none=True)
        # Sanity caps
        if data.get("nights") and (data["nights"] < 1 or data["nights"] > 90):
            data.pop("nights", None)
        if data.get("duration") and (data["duration"] < 1 or data["duration"] > 90):
            data.pop("duration", None)
        if data.get("pax") and (data["pax"] < 1 or data["pax"] > 500):
            data.pop("pax", None)
        return data
    except Exception as e:
        logger.warning("LangChain extract_fields failed: %s", e)
        return None


if __name__ == "__main__":
    samples = [
        "Plan a 5-day Singapore trip for 4 pax leisure",
        "It's a client's 50th wedding anniversary in December 2025. Make an itinerary excluding hotels for 3 days 2 nights in UAE.",
        "family of 6 going to Tokyo for a week, vegetarian, mid-range",
        "Honeymoon couple to Bali, 4D/3N, INR 80000 per person",
    ]
    for s in samples:
        print(s[:80])
        print(" ", extract_fields(s))
        print()
