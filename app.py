# app.py
import os
import re
from dotenv import load_dotenv
load_dotenv()  # Must be called before any os.getenv() in any module

from fastapi import FastAPI, HTTPException, Request, Depends, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, Response
from pydantic import BaseModel
import uuid
import logging

from conversation_manager import ConversationManager, PROMPTS
from feature_extractor import FeatureExtractor
from ml_model import CostModel
from itinerary_matcher import ItineraryMatcher
from local_llm_client import LocalLLMClient
import json
import pathlib
from price_engine import PriceEngine
from price_engine import EXCHANGE_RATES
from wikipedia_lookup import get_top_attractions as get_attractions_for_destination
from hotel_api_client import HotelAPIClient
from real_time_search import get_travel_price_context
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from client_manager import (
    create_client,
    get_client,
    list_clients,
    update_client,
    delete_client,
    search_clients,
    add_itinerary_to_client,
    get_client_itineraries,
)
from itinerary_database import get_itinerary_template, list_available_destinations
from src.services.kb.document_processor import get_user_kb_docs
from formal_request_parser import (
    parse_formal_request,
    is_formal_request,
    format_parsed_request_summary,
)

# ─── Auth & storage imports ─────────────────────────────────────────────────
from auth import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    register_user,
    login_user,
    get_current_user,
)
from chat_store import (
    create_chat,
    get_chat,
    update_chat,
    upsert_chat,
    update_chat_metadata_from_fields,
    list_user_chats,
    delete_chat as delete_chat_session,
    update_chat_status,
)
from document_store import (
    save_document,
    list_documents,
    get_document_meta,
    get_document_path,
    delete_document,
)

app = FastAPI(title="Travel Itinerary Chatbot API")

# ── v2 itinerary pipeline ────────────────────────────────────────────────────
from src.api.itinerary_controller import router as itinerary_v2_router
app.include_router(itinerary_v2_router)
# ── v2 document management (S3 + KB) ─────────────────────────────────────────
from src.api.documents_v2_controller import router as documents_v2_router
app.include_router(documents_v2_router)
# ─────────────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger("uvicorn.error")


# Sanitize and validate realtime enrichment payloads coming from real_time_search.enrich_destination
def sanitize_realtime_payload(raw: dict) -> dict:
    """Ensure realtime payload has predictable structure and limit sizes for prompt injection.

    Returns a dict with keys: wikipedia (dict), attractions (list of strings), news (list of strings)
    """
    if not isinstance(raw, dict):
        return {"wikipedia": {}, "attractions": [], "news": []}

    wp = raw.get("wikipedia") if isinstance(raw.get("wikipedia"), dict) else {}
    # Trim extract to reasonable length
    if isinstance(wp.get("extract"), str):
        wp["extract"] = wp["extract"][:800]

    raw_attractions = raw.get("attractions") if isinstance(raw.get("attractions"), list) else []
    attractions = []
    for a in raw_attractions[:10]:
        if isinstance(a, dict):
            name = a.get("name") or a.get("title") or "Unknown"
            cat = a.get("category") or a.get("description") or "Attraction"
            desc = (a.get("description") or "")
            attractions.append(f"{name} ({cat})" + (f": {desc[:100]}" if desc else ""))
        else:
            attractions.append(str(a))

    raw_news = raw.get("news") if isinstance(raw.get("news"), list) else []
    news = []
    for n in raw_news[:5]:
        if isinstance(n, dict):
            title = n.get("title") or n.get("description") or "News"
            url = n.get("url") or ""
            news.append(f"{title} - {url}")
        else:
            news.append(str(n))

    return {"wikipedia": wp, "attractions": attractions, "news": news}

# In-memory session store for simplicity. In production replace with redis/db.
SESSIONS = {}

# ── Formal request clarification helpers ────────────────────────────────────

_FORMAL_FIELD_KEYS = [
    "destination", "destinations", "route", "nights_per_city",
    "trip_start_date", "checkin_date", "checkout_date",
    "total_nights", "nights", "duration",
    "pax", "adults", "seniors",
    "rooms", "room_config",
    "hotel_type", "hotel_category", "hotel_location_preference",
    "transport_preference", "vehicle_type", "driver_preference", "transport_days",
    "guide_required", "walking_tolerance", "senior_friendly",
    "comfort_stops", "preferred_activities",
    "event_type", "client_type", "trip_style",
    "contact_person", "raw_text",
]


def _get_missing_formal_fields(fields: dict) -> list:
    """Return list of (key, label) tuples for required fields not yet in `fields`."""
    missing = []
    if not (fields.get("destination") or fields.get("destinations")):
        missing.append(("destination", "destination(s) / cities to visit"))
    if not fields.get("pax"):
        missing.append(("pax", "number of pax (travelers)"))
    if not (fields.get("total_nights") or fields.get("nights") or fields.get("nights_per_city")):
        missing.append(("total_nights", "trip duration (number of nights)"))
    # Trip start date is REQUIRED so the LLM can use real future dates and
    # live searches reflect the actual travel window.
    if not (fields.get("trip_start_date") or fields.get("checkin_date")):
        missing.append(("trip_start_date", "trip start date (e.g. '15 March 2026')"))
    return missing


def _build_formal_clarification(fields: dict, missing: list) -> str:
    """Build a friendly clarification message asking for the FIRST missing field
    only (one at a time UX). Ordering: destination → pax → duration."""
    dest_str = ""
    if fields.get("destinations"):
        dest_str = " → ".join(fields["destinations"])
    elif fields.get("destination"):
        dest_str = fields["destination"]

    intro_parts = []
    if dest_str:
        intro_parts.append(f"the trip to **{dest_str}**")
    if fields.get("contact_person"):
        intro_parts.append(f"for **{fields['contact_person']}**")

    intro = (
        "I received your request for " + " ".join(intro_parts) + "."
        if intro_parts else "I received your travel request."
    )

    # Ask for ONE field at a time — pick by priority so the user never sees a
    # multi-question wall. Order: destination → pax → duration → start date.
    _PRIORITY = ["destination", "destinations", "pax", "total_nights", "nights", "trip_start_date"]
    first = None
    for key, label in missing:
        if key in _PRIORITY:
            if first is None or _PRIORITY.index(key) < _PRIORITY.index(first[0]):
                first = (key, label)
    if first is None and missing:
        first = missing[0]
    ask = (
        f"To build the itinerary, could you please tell me the **{first[1]}**?"
        if first else ""
    )

    already_have = []
    if dest_str:
        already_have.append(f"Destination: {dest_str}")
    if fields.get("pax"):
        already_have.append(f"Pax: {fields['pax']}")
    if fields.get("total_nights") or fields.get("nights"):
        n = fields.get("total_nights") or fields.get("nights")
        already_have.append(f"Nights: {n}")
    if fields.get("hotel_category"):
        already_have.append(f"Hotel: {fields['hotel_category']}")
    if fields.get("trip_start_date"):
        already_have.append(f"Travel date: {fields['trip_start_date']}")

    context_block = (
        "\n\nDetails I have so far:\n" + "\n".join(f"  - {x}" for x in already_have)
        if already_have else ""
    )

    return f"{intro}{context_block}\n\n{ask}"


# ── Confirmation flow helpers ─────────────────────────────────────────────────

_CONFIRM_WORDS = {
    "yes", "confirm", "proceed", "go ahead", "looks good", "correct", "ok", "okay",
    "generate", "create", "perfect", "great", "fine", "yep", "yup", "sure", "absolutely",
    "approved", "approve", "continue", "start", "build", "done", "right",
    "that's right", "that's correct", "all good", "sounds good",
}


def _is_past_date(value) -> bool:
    """True if value (ISO 'YYYY-MM-DD' or month-only) is strictly before today."""
    if not value:
        return False
    s = str(value).strip()
    today = datetime.utcnow().date()
    # ISO date
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", s)
    if m:
        try:
            d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
            return d < today
        except Exception:
            return False
    # "Month YYYY" — past only if year < current year, OR same year but month < current
    _MONTHS = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
        "jan":1,"feb":2,"mar":3,"apr":4,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
    }
    m2 = re.match(r"^([A-Za-z]+)\s+(\d{4})$", s)
    if m2:
        mo = _MONTHS.get(m2.group(1).lower())
        try:
            yr = int(m2.group(2))
            if mo:
                if yr < today.year:
                    return True
                if yr == today.year and mo < today.month:
                    return True
        except Exception:
            return False
    return False


_PAST_DATE_REPLY = (
    "Oops — that travel date is in the past, so I can't build an itinerary "
    "around it. Could you share a future trip start date? "
    "For example: \"15 June 2026\" or \"next month\"."
)


def _parse_user_date(text: str) -> Optional[str]:
    """
    Best-effort parse a user-supplied trip-start date into ISO 'YYYY-MM-DD'.
    Recognises ISO, '15 March 2026', 'March 15 2026', 'March 2026' (1st of month),
    'next month' (1st of next month), 'tomorrow', 'next week'. Returns None on
    failure so the caller can ask again.
    """
    if not text or not isinstance(text, str):
        return None
    t = text.strip().lower()
    today = datetime.utcnow().date()

    # Quick keywords
    if t in ("today",):
        return today.isoformat()
    if t in ("tomorrow",):
        return (today + timedelta(days=1)).isoformat()
    if "next week" in t:
        return (today + timedelta(days=7)).isoformat()
    if "next month" in t:
        from calendar import monthrange
        y = today.year + (1 if today.month == 12 else 0)
        m = 1 if today.month == 12 else today.month + 1
        # mid/start/end modifier
        if "mid" in t or "middle" in t:
            return datetime(y, m, max(1, monthrange(y, m)[1] // 2)).date().isoformat()
        if "end" in t or "last" in t:
            return datetime(y, m, monthrange(y, m)[1]).date().isoformat()
        return datetime(y, m, 1).date().isoformat()

    # ISO YYYY-MM-DD
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", text)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date().isoformat()
        except Exception:
            pass

    # DD/MM/YYYY or MM/DD/YYYY (assume DD/MM if first part > 12)
    m = re.search(r"\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\b", text)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            if a > 12:
                return datetime(y, b, a).date().isoformat()
            return datetime(y, a, b).date().isoformat()  # MM/DD/YYYY default
        except Exception:
            pass

    # "15 March 2026" / "March 15 2026" / "March 2026"
    _MONTHS = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
        "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    m = re.search(
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s*,?\s*(\d{4})?\b", text,
    )
    if m:
        try:
            d = int(m.group(1))
            mo = _MONTHS.get(m.group(2).lower())
            y = int(m.group(3) or today.year)
            if mo:
                # If year missing and the date is past, roll to next year
                cand = datetime(y, mo, d).date()
                if cand < today and not m.group(3):
                    cand = datetime(y + 1, mo, d).date()
                return cand.isoformat()
        except Exception:
            pass
    m = re.search(
        r"\b([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(\d{4})?\b", text,
    )
    if m:
        try:
            mo = _MONTHS.get(m.group(1).lower())
            d = int(m.group(2))
            y = int(m.group(3) or today.year)
            if mo:
                cand = datetime(y, mo, d).date()
                if cand < today and not m.group(3):
                    cand = datetime(y + 1, mo, d).date()
                return cand.isoformat()
        except Exception:
            pass

    # "March 2026" → 1st of that month
    m = re.search(r"\b([A-Za-z]+)\s+(\d{4})\b", text)
    if m:
        try:
            mo = _MONTHS.get(m.group(1).lower())
            y = int(m.group(2))
            if mo:
                return datetime(y, mo, 1).date().isoformat()
        except Exception:
            pass

    return None
_CONFIRM_PHRASES = [
    "go ahead", "looks good", "all good", "let's go", "lets go", "that's right",
    "that's correct", "yes please", "yes proceed", "yes go", "confirm and generate",
    "generate itinerary", "create itinerary", "build it", "sounds good", "sound good",
    "proceed with", "yes, proceed", "generate now", "make it", "confirm details",
]

def _is_user_confirming(message: str) -> bool:
    t = message.strip().lower()
    if t in _CONFIRM_WORDS:
        return True
    words = re.findall(r"\b\w+\b", t)
    if len(words) <= 5 and words and words[0] in _CONFIRM_WORDS:
        return True
    return any(ph in t for ph in _CONFIRM_PHRASES)


def _parse_simple_field_changes(message: str) -> dict:
    """Parse quick natural-language field edits like 'change pax to 6' or '10 nights'."""
    changes: Dict[str, Any] = {}
    m = message.lower()

    # Pax / adults — handles both "change pax to 10" and "10 pax"
    pax_m = re.search(r"(?:change|update|set|make)\s+(?:pax|people|travelers?)\s+(?:to|as)?\s*(\d+)", m)
    if not pax_m:
        pax_m = re.search(r"(\d+)\s*(?:pax|people|adults?|persons?|travelers?|guests?)", m)
    if pax_m:
        changes["pax"] = int(pax_m.group(1))

    # Seniors
    sen_m = re.search(r"(\d+)\s*senior", m)
    if sen_m:
        changes["seniors"] = int(sen_m.group(1))
        changes["senior_friendly"] = True

    # Nights — handles "change nights to 10" and "10 nights"
    nights_m = re.search(r"(?:change|update|set|make)\s+(?:nights?|duration)\s+(?:to|as)?\s*(\d+)", m)
    if not nights_m:
        nights_m = re.search(r"(\d+)\s*nights?", m)
    if nights_m:
        n = int(nights_m.group(1))
        changes["total_nights"] = n
        changes["nights"] = n
        changes["duration"] = n

    # Destination — "change destination to Vienna" / "go to Prague instead"
    dest_m = re.search(r"(?:change|update|set)\s+destination\s+(?:to|as)\s+([A-Za-z\s]+?)(?:\s*$|,)", m)
    if not dest_m:
        dest_m = re.search(r"(?:go to|travel to|visit)\s+([A-Za-z\s]+?)\s+instead", m)
    if dest_m:
        changes["destination"] = dest_m.group(1).strip().title()

    # Hotel category
    if re.search(r"(?:upgrade|change|update|set).*?5[\s\-]?star|5[\s\-]?star|five[\s\-]?star", m):
        changes["hotel_category"] = "5-Star"
    elif re.search(r"4[\s\-]?star\s*deluxe|four[\s\-]?star\s*deluxe", m):
        changes["hotel_category"] = "4-Star Deluxe"
    elif re.search(r"4[\s\-]?star|four[\s\-]?star", m):
        changes["hotel_category"] = "4-Star"

    # Start date — "start on 15 April" / "departure 10 May 2025"
    date_m = re.search(
        r"(?:start|depart|departure|from|on)\s+(?:on\s+)?(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december)(?:\s+(\d{4}))?",
        m
    )
    if date_m:
        _MONTHS = {"january":"01","february":"02","march":"03","april":"04","may":"05","june":"06",
                   "july":"07","august":"08","september":"09","october":"10","november":"11","december":"12"}
        _d, _mon, _yr = date_m.group(1), date_m.group(2), date_m.group(3) or "2025"
        changes["trip_start_date"] = f"{_yr}-{_MONTHS[_mon]}-{int(_d):02d}"

    # Senior-friendly if mentioned
    if re.search(r"senior.?friendly|minimal\s+walking|comfortable\s+pace", m):
        changes["senior_friendly"] = True
        changes["walking_tolerance"] = "minimal"

    return changes


def _build_confirmation_dict(fields: dict) -> dict:
    """Extract a clean summary dict from session fields for the confirmation card."""
    dests = fields.get("destinations") or []
    dest_str = " → ".join(dests) if dests else (fields.get("destination") or "")
    total_nights = fields.get("total_nights") or fields.get("nights") or fields.get("duration") or ""
    try:
        total_days = int(total_nights) + 1 if total_nights else ""
    except (ValueError, TypeError):
        total_days = ""
    return {
        "destination": dest_str,
        "route": fields.get("route") or "",
        "nights_per_city": fields.get("nights_per_city") or {},
        "total_nights": total_nights,
        "total_days": total_days,
        "start_date": fields.get("trip_start_date") or fields.get("checkin_date") or "",
        "pax": fields.get("pax") or "",
        "seniors": fields.get("seniors") or 0,
        "senior_friendly": bool(fields.get("senior_friendly")),
        "hotel_category": fields.get("hotel_category") or "",
        "hotel_location": fields.get("hotel_location_preference") or "",
        "room_config": fields.get("room_config") or {},
        "transport": fields.get("transport_preference") or "",
        "driver": fields.get("driver_preference") or "",
        "guide": bool(fields.get("guide_required")),
        "event_type": fields.get("event_type") or "leisure",
        "preferred_activities": fields.get("preferred_activities") or [],
        "walking_tolerance": fields.get("walking_tolerance") or "",
    }


def _build_confirmation_message(fields: dict) -> str:
    """Build the plain-text version of the confirmation prompt (stored in history)."""
    cd = _build_confirmation_dict(fields)
    lines = ["Here are the trip details I've captured. Please review and confirm, or tell me what to change:\n"]
    if cd["destination"]:
        lines.append(f"Destination: {cd['destination']}")
    if cd["route"]:
        lines.append(f"Route: {cd['route']}")
    if cd["nights_per_city"]:
        npc = ", ".join(f"{c}: {n} nights" for c, n in cd["nights_per_city"].items())
        lines.append(f"Nights per city: {npc}")
    if cd["total_nights"]:
        date_str = f" from {cd['start_date']}" if cd["start_date"] else ""
        lines.append(f"Duration: {cd['total_nights']} nights / {cd['total_days']} days{date_str}")
    if cd["pax"]:
        sen = f" (incl. {cd['seniors']} senior citizens 60+)" if cd["seniors"] else ""
        lines.append(f"Pax: {cd['pax']} adults{sen}")
    if cd["room_config"]:
        rc = ", ".join(f"{v} {k}" for k, v in cd["room_config"].items())
        lines.append(f"Rooms: {rc}")
    if cd["hotel_category"]:
        loc = f" — {cd['hotel_location']}" if cd["hotel_location"] else ""
        lines.append(f"Hotel: {cd['hotel_category']}{loc}")
    if cd["transport"]:
        lines.append(f"Transport: {cd['transport']}")
    if cd["driver"]:
        lines.append(f"Driver: {cd['driver']}")
    if cd["guide"]:
        lines.append("Guide: English-speaking local guide required")
    if cd["senior_friendly"]:
        lines.append("Special needs: Senior-friendly, comfortable pace, minimal walking")
    if cd["preferred_activities"]:
        lines.append(f"Preferred activities: {', '.join(cd['preferred_activities'])}")
    lines.append("\nReply 'confirm' to generate the itinerary, or tell me what to change (e.g. 'change pax to 6', 'upgrade to 5-star').")
    return "\n".join(lines)


conv_manager = ConversationManager()
feature_extractor = FeatureExtractor()
cost_model = CostModel()
matcher = None


class _DummyMatcher:
    """Fallback matcher used if the real matcher can't be constructed at import time."""
    past_texts: list = []

    def find_similar(self, *args, **kwargs):
        return []

    def summarize_matches(self, matches):
        return "No historical itineraries available."


def get_matcher() -> ItineraryMatcher:
    """Lazily instantiate and return a shared ItineraryMatcher instance.

    This avoids importing/initializing heavy dependencies (and broken third-party
    packages) during module import time. If construction fails we return a
    lightweight dummy matcher so the app can continue running.
    """
    global matcher
    if matcher is None:
        try:
            matcher = ItineraryMatcher()
        except Exception as e:
            logger.warning("ItineraryMatcher initialization failed: %s", e)
            logger.warning("If you see errors mentioning 'docx' or 'exceptions', ensure you have 'python-docx' installed and uninstall any broken 'docx' package")
            matcher = _DummyMatcher()
    return matcher
llm = LocalLLMClient()  # URL resolved from APP_ENV in local_llm_client.py
price_engine = PriceEngine()
# Hotel API client (can be disabled via HOTEL_API_ENABLED env var)
hotel_client = HotelAPIClient(provider=os.getenv("HOTEL_API_PROVIDER"))
# Toggle live hotel API calls. Default off because most providers require a paid API key.
# Set HOTEL_API_ENABLED=true (and HOTEL_API_PROVIDER + provider credentials) to enable.
HOTEL_API_ENABLED = os.getenv("HOTEL_API_ENABLED", "false").lower() in ("1", "true", "yes", "on")

class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str


@app.post("/api/chat")
async def chat(request: Request):
    """Chat endpoint accepts either a JSON object or plain/text body.

    This handler is tolerant of invalid JSON sent by some clients (e.g., using
    single quotes or Python-style dict literals). It will attempt several
    fallbacks before treating the body as plain text to avoid returning a
    JSON decode error to the client.
    """
    # Try to parse body as JSON robustly; fall back to plain text
    raw_body = await request.body()
    body_text = raw_body.decode("utf-8", errors="replace").strip()
    parsed = None
    try:
        parsed = await request.json()
    except Exception:
        # Attempt more tolerant parsing for common invalid-but-useful formats
        try:
            import ast

            maybe = ast.literal_eval(body_text) if body_text else None
            if isinstance(maybe, dict):
                parsed = maybe
        except Exception:
            parsed = None

    # Normalize input into 'session_id' and 'message'
    session_id = None
    message_text = None
    if isinstance(parsed, dict):
        session_id = parsed.get("session_id") or parsed.get("sid")
        message_text = parsed.get("message") or parsed.get("text")
    else:
        # Treat the raw body as the message (plain text)
        message_text = body_text

    # If JSON body had top-level string (e.g., just a JSON string), use it
    if message_text is None and isinstance(parsed, str):
        message_text = parsed

    # Protect against missing message
    if not message_text:
        raise HTTPException(status_code=400, detail="Request body must include a 'message' field or contain plain text message")

    # Create a lightweight object similar to previous ChatRequest for compatibility
    class _Req:
        def __init__(self, sid, msg):
            self.session_id = sid
            self.message = msg

    req = _Req(session_id, message_text)
    # initialize session if needed
    sid = req.session_id or str(uuid.uuid4())
    if sid not in SESSIONS:
        SESSIONS[sid] = {"fields": {}, "history": []}

    session = SESSIONS[sid]
    # prepare sanity checks log inside session for visibility
    session.setdefault("sanity_checks", [])

    # Try to extract username from Authorization header for chat persistence
    _chat_username = None
    try:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            from auth import decode_token
            _payload = decode_token(auth_header.split(" ", 1)[1])
            _chat_username = _payload.get("sub")
    except Exception:
        _chat_username = None

    def sc(msg: str):
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        entry = f"[{ts}] {msg}"
        try:
            session.setdefault("sanity_checks", []).append(entry)
        except Exception:
            pass
        logger.info(entry)

    def _make_smart_name(fields: dict, history: list) -> str:
        """Build a descriptive title from collected trip fields."""
        dest = (fields.get("destination") or "").strip()
        duration = fields.get("duration") or fields.get("nights")
        pax = fields.get("pax") or fields.get("people")
        trip_style = (fields.get("trip_style") or "").strip()

        parts = []
        if dest:
            dur_str = str(duration).strip() if duration else ""
            if dur_str:
                parts.append(f"{dur_str}N {dest}" if dur_str.isdigit() else f"{dest} · {dur_str}")
            else:
                parts.append(dest)
            if pax:
                parts.append(f"{pax} Pax")
            if trip_style:
                parts.append(trip_style.title())

        if parts:
            return " · ".join(parts)[:80]

        # Fallback: first user message snippet
        first_user = next((h.get("content", "") for h in history if h.get("role") == "user"), "")
        if first_user:
            return (first_user[:50] + "…") if len(first_user) > 50 else first_user
        return ""

    def _sync_chat_to_store():
        """Persist in-memory session to disk if user is authenticated (upsert)."""
        if not _chat_username:
            return
        try:
            smart_name = _make_smart_name(session.get("fields", {}), session.get("history", []))
            upsert_chat(_chat_username, sid, {
                "chat_name": smart_name or None,
                "fields": session.get("fields", {}),
                "history": session.get("history", []),
                "sanity_checks": session.get("sanity_checks", [])[-30:],
                "last_llm_raw": session.get("last_llm_raw"),
                "last_llm_prompt": session.get("last_llm_prompt"),
                # Persist transient flow state so reloading the chat restores
                # the confirmation card / pending-formal-request UI.
                "pending_confirmation": session.get("pending_confirmation"),
                "pending_formal_request": session.get("pending_formal_request"),
                "formal_request_detected": session.get("formal_request_detected", False),
            })
            update_chat_metadata_from_fields(_chat_username, sid, session.get("fields", {}))
        except Exception as e:
            logger.debug(f"Chat store sync failed: {e}")

    # Append message to history
    session["history"].append({"role": "user", "content": req.message})

    # ── Fast Ollama availability gate ──────────────────────────────────────
    # Skip the heavy pipeline (and the early LangChain extraction below) if
    # Ollama isn't reachable. Without this, the frontend would sit on the
    # loading pipeline for the full LOCAL_LLM_TIMEOUT (15 minutes) before
    # discovering the backend can't talk to the model. 2s health check is fast
    # enough to feel instantaneous and reliable on localhost.
    try:
        _llm_alive = await asyncio.wait_for(
            asyncio.to_thread(llm.is_available, 2.0),
            timeout=3.0,
        )
    except Exception:
        _llm_alive = False
    if not _llm_alive:
        sc("Ollama health check failed — refusing to call LLM")
        _err = (
            "I can't reach the LLM service right now. Please make sure Ollama is "
            "running (run `ollama serve` and `ollama list` to confirm the model is "
            "pulled), then try again."
        )
        session["history"].append({"role": "assistant", "content": _err})
        _sync_chat_to_store()
        raise HTTPException(
            status_code=503,
            detail={
                "error": "ollama_unavailable",
                "message": _err,
                "session_id": sid,
            },
        )

    # ── Early LLM extraction (fires on every non-trivial message) ──────────
    # Runs before any pipeline / formal-request branching so the LangChain
    # extractor's structured output (destination, duration, pax, event_type,
    # special requirements, AND the LLM-planned web search queries) is
    # available throughout the rest of the request. Skipped on tiny messages
    # ("hi", "yes", numeric replies) where regex/DB are equivalent and faster.
    try:
        if (
            len(req.message.split()) >= 4
            and not session.get("_skip_early_llm")
            and "_langchain_extract" in dir()
        ):
            pass  # placeholder; the actual call happens via conv_manager
    except Exception:
        pass

    try:
        from langchain_field_extractor import extract_fields as _early_lc_extract
        if len(req.message.split()) >= 4:
            _lc = await asyncio.wait_for(
                asyncio.to_thread(_early_lc_extract, req.message),
                timeout=25,
            )
            if isinstance(_lc, dict) and _lc:
                _fields = session.setdefault("fields", {})
                # Merge LLM-extracted fields without clobbering values the user
                # has already locked in (e.g. via confirmation card).
                for k, v in _lc.items():
                    if v in (None, "", []):
                        continue
                    if k == "search_queries":
                        # Stash LLM-planned web searches on session.fields so the
                        # Tavily step picks them up later in the same request.
                        existing = list(_fields.get("llm_search_queries") or [])
                        for q in v:
                            if isinstance(q, str) and q.strip() and q not in existing:
                                existing.append(q.strip())
                        _fields["llm_search_queries"] = existing[:6]
                        continue
                    if k == "must_visit_landmarks":
                        existing = list(_fields.get("preferred_activities") or [])
                        for a in v:
                            if isinstance(a, str) and a.strip() and a not in existing:
                                existing.append(a.strip())
                        if existing:
                            _fields["preferred_activities"] = existing
                        continue
                    if k == "special_requirements":
                        _fields.setdefault("special_requirements", v)
                        continue
                    if _fields.get(k) in (None, "", []):
                        _fields[k] = v
                sc(
                    "Early LLM extraction merged: "
                    + ", ".join(f"{k}={_lc.get(k)}" for k in ("destination","duration","pax","event_type") if _lc.get(k))
                    + (f" + {len(_lc.get('search_queries') or [])} planned queries" if _lc.get("search_queries") else "")
                )
    except asyncio.TimeoutError:
        sc("Early LLM extraction timed out (25s) — falling back to regex/DB")
    except Exception as _eex:
        logger.debug("Early LLM extraction skipped: %s", _eex)

    # ===== CONVERSATIONAL MODE =====
    # Only run the heavyweight itinerary-generation pipeline when the user clearly
    # asks for one. Otherwise reply conversationally so the bot feels human and
    # users can chat about destinations, ideas, etc. without triggering a 15-min
    # LLM build. A simple regex catches "generate / create / build / make / plan
    # /generate the / draft an itinerary".
    _GENERATE_INTENT_RE = re.compile(
        r"\b(?:generate|create|build|make|prepare|draft|design|put\s+together|plan|"
        r"organi[sz]e|arrange|book|quote|give\s+me|i\s+(?:want|need|would\s+like)|"
        r"can\s+you\s+(?:make|create|plan|build))\b"
        r"[^\.\?\!]{0,100}?"
        r"\b(?:itinerary|trip\s+plan|schedule|day-?by-?day|day\s*plan|"
        r"tour|holiday|vacation|getaway|travel\s+plan|package|programme|program)\b",
        re.IGNORECASE,
    )
    # Implicit generate-intent: a single message that already contains a destination
    # AND a duration AND pax (i.e. a fully-formed brief like "Singapore 5N 4 pax
    # leisure") should also kick off generation, even without a verb.
    def _looks_like_complete_brief(text: str) -> bool:
        t = text.lower()
        has_dest = bool(re.search(
            r"\b(to|in|at|for)\s+[A-Z]?[a-z]{2,}", text
        )) or bool(re.search(r"^\s*[A-Z][a-zA-Z]+(?:\s*[→>,/]\s*[A-Z][a-zA-Z]+)+", text))
        has_duration = bool(re.search(r"\b\d{1,2}\s*[-]?\s*(?:n(?:ights?)?|d(?:ays?)?)\b|\b\d{1,2}n[/\\\-]\d{1,2}d\b|\b\d{1,2}d[/\\\-]\d{1,2}n\b", t))
        has_pax = bool(re.search(r"\b\d{1,3}\s*(?:pax|people|adults?|travell?ers?|members?)\b|family\s+of\s+\d+|group\s+of\s+\d+|couple\b", t))
        return sum([has_dest, has_duration, has_pax]) >= 2
    # When the session already has a generated itinerary, follow-up messages
    # like "make it cheaper", "add a beach day", "change the hotel" are edit
    # requests — we send the existing itinerary + the new ask back to the LLM.
    _IMPROVE_INTENT_RE = re.compile(
        r"\b(?:improve|update|refine|tweak|adjust|edit|modify|change|swap|"
        r"replace|remove|drop|add|include|extend|shorten|cut|expand|"
        r"make\s+it|can\s+you|please|could\s+you|instead|switch)\b",
        re.IGNORECASE,
    )
    _has_existing_itinerary = bool(session.get("last_llm_raw"))
    _user_wants_improvement = (
        _has_existing_itinerary and bool(_IMPROVE_INTENT_RE.search(req.message))
        and not _GENERATE_INTENT_RE.search(req.message)
    )
    _user_asked_to_generate = (
        bool(_GENERATE_INTENT_RE.search(req.message))
        or _user_wants_improvement
        or _looks_like_complete_brief(req.message)
    )
    # Also treat formal/structured requests (Route:, City: N Nights, etc.) as
    # implicit generate intent — those are already DMC-style itinerary briefs.
    if not _user_asked_to_generate and is_formal_request(req.message):
        _user_asked_to_generate = True

    # If the chat is paused on a confirmation card, the user's reply is also
    # treated as generate-intent (they're answering the card, not chitchatting).
    if not _user_asked_to_generate and session.get("pending_confirmation"):
        _user_asked_to_generate = True
    if not _user_asked_to_generate and session.get("pending_formal_request"):
        _user_asked_to_generate = True

    # ─── ITINERARY IMPROVEMENT FAST-PATH ────────────────────────────────────
    # User has an existing itinerary AND is asking for changes. Send the old
    # itinerary + their change request to Ollama and return the updated JSON.
    # Skips the full enrichment pipeline since fields don't need re-extraction.
    if _user_wants_improvement:
        sc("Improvement mode: editing existing itinerary per user feedback")
        try:
            _existing = session.get("last_llm_raw") or ""
            _improve_system = (
                "You are Zarah, a senior DMC travel consultant. The user has an "
                "EXISTING itinerary and wants you to MODIFY it based on their feedback. "
                "Return ONLY a single valid JSON object matching the same schema as the "
                "original (title, destination, duration_days, pax, event_type, "
                "itinerary_summary, days[], hotels[], cost_breakdown, inclusions, "
                "exclusions, important_guidelines, notes). "
                "Preserve everything that wasn't touched by the user's request. "
                "Apply the requested changes faithfully. Recompute affected costs. "
                "Keep day count consistent unless the user explicitly asks to change "
                "duration. Output JSON only — no markdown, no prose."
            )
            _improve_user = (
                "EXISTING ITINERARY (the JSON the user already has):\n"
                f"```json\n{_existing[:12000]}\n```\n\n"
                f"USER'S CHANGE REQUEST:\n{req.message}\n\n"
                "Return the FULL updated itinerary JSON with the change applied."
            )
            _raw = await asyncio.wait_for(
                asyncio.to_thread(
                    llm.generate, _improve_system,
                    [{"role": "user", "content": _improve_user}],
                ),
                timeout=int(os.getenv("LOCAL_LLM_TIMEOUT", "900")),
            )
            # Try to parse — re-use the same JSON-substring helper used downstream
            def _strip_fences(t: str) -> str:
                if not isinstance(t, str): return t or ""
                t2 = t.strip()
                if t2.startswith("```"):
                    parts = t2.split("\n")
                    if parts and parts[0].startswith("```"):
                        parts = parts[1:]
                    if parts and parts[-1].startswith("```"):
                        parts = parts[:-1]
                    t2 = "\n".join(parts).strip()
                return t2
            def _extract_json_substring(t: str):
                t2 = _strip_fences(t)
                start = t2.find("{")
                if start == -1: return None
                depth = 0
                for i in range(start, len(t2)):
                    if t2[i] == "{": depth += 1
                    elif t2[i] == "}":
                        depth -= 1
                        if depth == 0: return t2[start:i+1]
                return None
            _itin_text = _extract_json_substring(_raw)
            _new_itinerary = None
            if _itin_text:
                try:
                    _new_itinerary = json.loads(_itin_text)
                except Exception as _je:
                    sc(f"Improvement JSON parse failed: {_je}")
            session["last_llm_raw"] = _raw
            session["history"].append({"role": "assistant_raw", "content": _raw})
            _sync_chat_to_store()
            return {
                "session_id": sid,
                "itinerary": _new_itinerary,
                "llm_raw": _raw,
                "improved": True,
                "fields": session.get("fields", {}),
            }
        except asyncio.TimeoutError:
            sc("Improvement LLM call timed out")
            session["history"].append({
                "role": "assistant",
                "content": "The improvement is taking longer than expected. Could you try a more focused change (e.g. \"swap day 3's hotel\" or \"replace lunch on day 2\")?",
            })
            _sync_chat_to_store()
            return {"session_id": sid, "reply": "Improvement timed out — try a smaller change.", "conversational": True}
        except Exception as _ie:
            logger.exception("Improvement flow failed; falling through to standard generation")
            sc(f"Improvement flow failed: {type(_ie).__name__}: {_ie}")
            # fall through to normal flow

    if not _user_asked_to_generate:
        sc("Conversational mode: progressive field collector")

        # Fast-path: common short greetings get a hardcoded reply so users aren't
        # waiting 30+ seconds on a CPU-bound llama call just to say hi back.
        # Greetings only fire when there are NO required fields yet — once the
        # user starts a real conversation, we move into field-collection mode.
        _msg_norm = re.sub(r"[^a-z]", "", req.message.lower())
        _GREETING_REPLIES = {
            "hi":      "Hi! I'm Zarah, your travel planning assistant. Where are we off to today?",
            "hello":   "Hello! Tell me about the trip you'd like to plan — destination, dates, who's travelling.",
            "hey":     "Hey there! What kind of trip can I help you build?",
            "yo":      "Hey! What kind of trip are we planning?",
            "hii":     "Hi! What kind of getaway are you thinking about?",
            "hellow":  "Hello! Tell me where and when you'd like to travel.",
            "namaste": "Namaste! Where would you like to travel next?",
            "thanks":  "Anytime! Let me know whenever you'd like me to plan another trip.",
            "thankyou":"You're welcome! Ready for the next trip whenever you are.",
        }
        _have_any_field = any(
            session.get("fields", {}).get(k)
            for k in ("destination", "destinations", "duration", "nights", "pax", "event_type")
        )
        if _msg_norm in _GREETING_REPLIES and not _have_any_field:
            _q = _GREETING_REPLIES[_msg_norm]
            session["history"].append({"role": "assistant", "content": _q})
            _sync_chat_to_store()
            return {"session_id": sid, "reply": _q, "conversational": True}

        # ── Progressive field collection ──────────────────────────────────────
        # Try to harvest fields from the current message and merge into session.
        try:
            _parsed = conv_manager.detect_fields_in_text(req.message) or {}
            for k, v in _parsed.items():
                if v in (None, "", []):
                    continue
                session.setdefault("fields", {})
                # Don't overwrite an already-good destination if the new pass found
                # something less specific; otherwise prefer the new value.
                if k not in session["fields"] or k in ("nights", "duration", "pax", "event_type"):
                    session["fields"][k] = v
        except Exception as _pe:
            logger.exception("Field detection in conversational mode failed")

        # If the user typed a one-shot answer to the previous question (e.g. last
        # bot turn was "How many travelers?" and the user replies "4"), grab a
        # bare number for whatever's currently missing.
        try:
            _missing_now = conv_manager.next_missing_field(session.get("fields", {}))
            if _missing_now in ("pax", "duration"):
                _num_m = re.search(r"\b(\d+)\b", req.message)
                if _num_m:
                    session.setdefault("fields", {})[_missing_now] = int(_num_m.group(1))
            elif _missing_now == "event_type":
                _stripped = req.message.strip().lower()
                # Accept short single-line answers as the event type
                if 0 < len(_stripped) <= 40 and "\n" not in _stripped:
                    session.setdefault("fields", {})["event_type"] = req.message.strip()
            elif _missing_now == "destination":
                # Only accept short destination-like answers (1-4 words, no digits)
                _stripped = req.message.strip()
                _words = _stripped.split()
                if 1 <= len(_words) <= 4 and not re.search(r"\d", _stripped) and len(_stripped) <= 40:
                    session.setdefault("fields", {})["destination"] = _stripped.strip(",.!?")
            elif _missing_now == "trip_start_date":
                # Parse the user's reply as a date. Try ISO first, then natural
                # language ("15 March 2026", "March 2026", "next month").
                _parsed_date = _parse_user_date(req.message)
                if _parsed_date:
                    if _is_past_date(_parsed_date):
                        session["history"].append({"role": "assistant", "content": _PAST_DATE_REPLY})
                        _sync_chat_to_store()
                        return {"session_id": sid, "reply": _PAST_DATE_REPLY, "conversational": True}
                    session.setdefault("fields", {})["trip_start_date"] = _parsed_date
                    session["fields"].setdefault("checkin_date", _parsed_date)
        except Exception:
            pass

        # ── Past-date guard ─────────────────────────────────────────────────
        # LangChain or regex extraction may have populated trip_start_date /
        # checkin_date from a past phrase (e.g. user said "Goa trip in
        # December 2024"). Catch those and ask the user to choose a future
        # date instead of silently building a backdated itinerary.
        _f = session.get("fields", {})
        for _k in ("trip_start_date", "checkin_date"):
            _v = _f.get(_k)
            if _v and _is_past_date(_v):
                # Strip the bad value so the bot re-asks naturally
                _f.pop("trip_start_date", None)
                _f.pop("checkin_date", None)
                session["history"].append({"role": "assistant", "content": _PAST_DATE_REPLY})
                _sync_chat_to_store()
                return {"session_id": sid, "reply": _PAST_DATE_REPLY, "conversational": True}

        # Re-evaluate after merges
        _missing = conv_manager.next_missing_field(session.get("fields", {}))
        if _missing == "client_status":
            _missing = None

        if _missing:
            # Conversational ask for the next single missing field. Phrase it
            # warmly with light context if we already have something.
            _have = session.get("fields", {})
            _ctx_bits = []
            if _have.get("destination"):  _ctx_bits.append(f"trip to {_have['destination']}")
            if _have.get("pax"):          _ctx_bits.append(f"{_have['pax']} travellers")
            if _have.get("duration") or _have.get("nights"):
                n = _have.get("duration") or _have.get("nights")
                _ctx_bits.append(f"{n} nights")
            if _have.get("event_type"):   _ctx_bits.append(f"{_have['event_type']} vibe")
            _ctx = ("Got it — " + ", ".join(_ctx_bits) + ". ") if _ctx_bits else ""
            _q = _ctx + (PROMPTS.get(_missing) or f"Could you share the {_missing}?")
            session["history"].append({"role": "assistant", "content": _q})
            _sync_chat_to_store()
            return {"session_id": sid, "reply": _q, "conversational": True}

        # All required fields collected — invite the user to generate. Set
        # pending_confirmation so a "yes" reply triggers the full pipeline.
        if not session.get("pending_confirmation"):
            _summary_card = _build_confirmation_dict(session["fields"])
            session["pending_confirmation"] = {"fields": dict(session["fields"])}
            _confirm_msg = _build_confirmation_message(session["fields"])
            session["history"].append({"role": "assistant", "content": _confirm_msg})
            _sync_chat_to_store()
            return {
                "session_id": sid,
                "need_confirmation": True,
                "confirmation_fields": _summary_card,
                "prompt": _confirm_msg,
                "collected": session["fields"],
            }

        # Already have a pending confirmation — fall through to standard flow
        # (which handles confirm/reject replies on the existing path).

    # ===== HANDLE PENDING CONFIRMATION RESPONSE =====
    # If we previously showed the user a trip-details confirmation card, handle their reply.
    _goto_generation = False
    if session.get("pending_confirmation"):
        if _is_user_confirming(req.message):
            sc("User confirmed trip details; proceeding to itinerary generation")
            session.pop("pending_confirmation", None)
            session["confirmation_acknowledged"] = True
            _goto_generation = True
        else:
            # User wants to change something — parse field edits and re-show confirmation
            _mod = {}
            try:
                _mod = parse_formal_request(req.message)
            except Exception:
                pass
            _simple = _parse_simple_field_changes(req.message)
            # Also run conv_manager detector for free-form edits ("12 pax", "5-star", etc.)
            try:
                _conv_edits = conv_manager.detect_fields_in_text(req.message)
            except Exception:
                _conv_edits = {}
            _merged = {**_conv_edits, **_mod, **_simple}  # simple wins over all
            _updated_keys = []
            for k, v in _merged.items():
                if k not in ("raw_text", "is_formal_request") and v not in (None, "", []):
                    session["fields"][k] = v
                    _updated_keys.append(k)
            sc(f"Confirmation: user requested field changes: {_updated_keys}")
            # Acknowledge change and re-show updated confirmation
            _ack = f"Got it! I've updated {', '.join(_updated_keys) if _updated_keys else 'your request'}. Here are the revised trip details:\n\n" if _updated_keys else ""
            _confirm_msg = _ack + _build_confirmation_message(session["fields"])
            session["pending_confirmation"] = {"fields": dict(session["fields"])}
            session["history"].append({"role": "assistant", "content": _confirm_msg})
            _sync_chat_to_store()
            return {
                "session_id": sid,
                "need_confirmation": True,
                "confirmation_fields": _build_confirmation_dict(session["fields"]),
                "prompt": _confirm_msg,
                "collected": session["fields"],
            }

    # ===== HANDLE FOLLOW-UP TO A PENDING FORMAL REQUEST =====
    # If the user previously sent a formal request that was missing required fields,
    # we stored it as pending_formal_request. Now we try to extract the missing info
    # from this follow-up message and merge it in.
    if not _goto_generation and session.get("pending_formal_request"):
        sc("Handling follow-up reply to pending formal request; extracting missing fields")
        _pending_fields = dict(session["pending_formal_request"].get("partial_fields", {}))

        # Parse the follow-up to pick up any newly provided fields
        try:
            _followup_parsed = parse_formal_request(req.message)
            for k in _FORMAL_FIELD_KEYS:
                v = _followup_parsed.get(k)
                if v is not None and v != "" and v != [] and k not in _pending_fields:
                    _pending_fields[k] = v
            sc(f"Follow-up merged; pax={_pending_fields.get('pax')} dest={_pending_fields.get('destination')} nights={_pending_fields.get('total_nights')}")
        except Exception as _fe:
            sc(f"Follow-up parse error: {_fe}")

        session.pop("pending_formal_request", None)
        session["fields"] = {}
        for k in _FORMAL_FIELD_KEYS:
            v = _pending_fields.get(k)
            if v is not None and v != "" and v != []:
                session["fields"][k] = v

        # Check again — if still missing, ask once more
        _still_missing = _get_missing_formal_fields(session["fields"])
        if _still_missing:
            sc(f"Still missing after follow-up: {[l for _,l in _still_missing]}")
            session["pending_formal_request"] = {"partial_fields": dict(session["fields"])}
            _q = _build_formal_clarification(session["fields"], _still_missing)
            session["history"].append({"role": "assistant", "content": _q})
            _sync_chat_to_store()
            return {"session_id": sid, "need_more": True, "prompt": _q, "collected": session["fields"]}

        # All required fields now present — mark as formal and fall through to generation
        session["formal_request_detected"] = True
        sc("All required fields confirmed after follow-up; proceeding to generation")

    # ===== CHECK FOR FORMAL REQUEST =====
    # Detect and parse formal/DMC-style travel request emails.
    # When detected: wipe stale session fields, extract all fields, show confirmation.
    elif not _goto_generation and is_formal_request(req.message):
        sc("Detected formal request format; extracting all fields and generating itinerary")
        parsed_formal = parse_formal_request(req.message)
        sc(f"Formal parsed: destinations={parsed_formal.get('destinations')} nights={parsed_formal.get('total_nights')} pax={parsed_formal.get('pax')}")

        # Reset session fields for this fresh request (avoids stale destination contamination)
        session["fields"] = {}
        session["formal_request_detected"] = True
        session["formal_parsed"] = parsed_formal

        # Merge ALL parsed fields into session
        for k in _FORMAL_FIELD_KEYS:
            v = parsed_formal.get(k)
            if v is not None and v != "" and v != []:
                session["fields"][k] = v

        # Check for missing required fields before proceeding to generation
        _missing_formal = _get_missing_formal_fields(session["fields"])
        if _missing_formal:
            sc(f"Formal request missing fields: {[l for _,l in _missing_formal]}")
            session["pending_formal_request"] = {"partial_fields": dict(session["fields"])}
            session["formal_request_detected"] = False
            _clarification = _build_formal_clarification(session["fields"], _missing_formal)
            session["history"].append({"role": "assistant", "content": _clarification})
            _sync_chat_to_store()
            return {"session_id": sid, "need_more": True, "prompt": _clarification, "collected": session["fields"]}

        # Fall through to the main itinerary-generation pipeline below
        # (confirmation will be shown by the universal gate further below)
        # (skip the conv_manager update — we already have all fields)

    # If the incoming message is JSON, parse and merge into session fields (the client sends structured JSON)
    # Skip JSON/conv-manager handling when a formal request was just detected or confirmation acknowledged
    parsed_json = None
    if not _goto_generation and not session.get("formal_request_detected"):
        try:
            parsed_json = json.loads(req.message)
        except Exception:
            parsed_json = None

    if isinstance(parsed_json, dict):
        # Merge parsed keys into session fields
        session_fields_before = dict(session.get("fields", {}))
        session.setdefault("fields", {}).update(parsed_json)
        session["history"].append({"role": "user", "content": json.dumps(parsed_json)})
        sc(f"Parsed incoming JSON and merged fields: keys={list(parsed_json.keys())}")

        # Check for next missing field
        missing = conv_manager.next_missing_field(session["fields"])
        # `client_status` is optional for itinerary generation; skip asking for it
        if missing == "client_status":
            missing = None

        if missing:
            prompt = PROMPTS.get(missing, f"Please provide {missing}")
            session["history"].append({"role": "assistant", "content": prompt})
            _sync_chat_to_store()
            return {"session_id": sid, "need_more": True, "prompt": prompt, "collected": session["fields"]}
        # else, proceed to generate itinerary
    elif not _goto_generation and not session.get("formal_request_detected"):
        # Update conversation manager with new message (standard conversation flow)
        update_result = conv_manager.update(session, req.message)

        if update_result.get("need_more"):
            # Build a safe prompt fallback if the updater returned a retry_field instead of an explicit prompt
            if update_result.get("prompt"):
                prompt_text = update_result.get("prompt")
            elif update_result.get("retry_field"):
                retry = update_result.get("retry_field")
                prompt_text = PROMPTS.get(retry, f"Please provide {retry}")
            else:
                prompt_text = "Please provide the requested information."
            # If the prompt requests client status (optional), skip it and proceed
            if "client status" in prompt_text.lower() or prompt_text.strip().lower().startswith("what's the client status"):
                sc("Skipping optional 'client_status' prompt and proceeding")
                # Do not return a prompt for an optional field; continue to generate itinerary
            else:
                # Return the next question to ask
                session["history"].append({"role": "assistant", "content": prompt_text})
                _sync_chat_to_store()
                return {"session_id": sid, "need_more": True, "prompt": prompt_text, "collected": session["fields"]}

    # All required fields are collected; proceed to feature extraction, ML prediction and matching
    fields = session["fields"]

    # Sanitize fields: remove any values that look like error messages (from a prior failed LLM call
    # that got stored back into the session as a destination or other field)
    _error_markers = ("⚠️", "Cannot connect", "returned 404", "connection refused", "LLM", "Ollama at")
    _bad_keys = [k for k, v in fields.items() if isinstance(v, str) and any(m in v for m in _error_markers)]
    for _k in _bad_keys:
        sc(f"Removing corrupted field '{_k}' (looks like an error message)")
        fields.pop(_k, None)

    # ── Mandatory-field gate ────────────────────────────────────────────────────
    # Final check that all required fields (destination, duration, pax, event_type)
    # are present before showing the confirmation card / calling the LLM. The
    # earlier flows (formal request, JSON body, free-text via conv_manager) each
    # gate on this, but a session can still reach this point with partial data
    # (e.g. user editing fields from the confirmation card). Without this gate
    # the LLM gets called with missing inputs and produces malformed itinerary
    # JSON ("Expecting ',' delimiter" parse failures).
    if not _goto_generation:
        _missing = conv_manager.next_missing_field(fields)
        if _missing == "client_status":
            _missing = None
        if _missing:
            _prompt = PROMPTS.get(_missing, f"Please provide {_missing}.")
            session["history"].append({"role": "assistant", "content": _prompt})
            _sync_chat_to_store()
            return {"session_id": sid, "need_more": True, "prompt": _prompt, "collected": fields}
    # ── End mandatory-field gate ────────────────────────────────────────────────

    # ── Universal confirmation gate ─────────────────────────────────────────────
    # Before calling the LLM, always show the user a summary card to review and
    # confirm (or edit) the extracted trip details. This gate fires for BOTH
    # formal requests (already handled above) AND conversational flow.
    # It is bypassed only when _goto_generation=True (user just confirmed).
    if not _goto_generation and (fields.get("destination") or fields.get("destinations")):
        _confirm_msg = _build_confirmation_message(fields)
        session["pending_confirmation"] = {"fields": dict(fields)}
        session["history"].append({"role": "assistant", "content": _confirm_msg})
        _sync_chat_to_store()
        return {
            "session_id": sid,
            "need_confirmation": True,
            "confirmation_fields": _build_confirmation_dict(fields),
            "prompt": _confirm_msg,
            "collected": fields,
        }
    # ── End confirmation gate ───────────────────────────────────────────────────

    # ── Look up stored client record to enrich system prompt with client-type context ──
    _client_record = None
    _client_type_str = None
    try:
        _cid = fields.get("client_id") or fields.get("client_name")
        if _cid:
            from client_manager import search_clients, load_clients
            load_clients()
            _results = search_clients(str(_cid))
            if _results:
                _client_record = _results[0]
                _client_type_str = (_client_record.get("client_type") or "").strip().lower()
                sc(f"Found client record: company='{_client_record.get('company_name')}' type='{_client_type_str}'")
    except Exception as _ce:
        sc(f"Client lookup failed (non-fatal): {_ce}")
    # Fall back to a client_type field passed directly in the session (e.g. from frontend or formal request)
    if not _client_type_str:
        _direct_ct = (fields.get("client_type") or fields.get("trip_style") or "").strip().lower()
        _known_types = {"corporate", "mice", "leisure", "dmc", "b2b", "b2c"}
        if _direct_ct in _known_types:
            _client_type_str = _direct_ct
            sc(f"Using client_type from session field: '{_client_type_str}'")

    # Normalize and infer currency and budget semantics from session history
    budget_pp = fields.get("budget_per_person")
    budget_currency = fields.get("budget_currency")
    # If user mentioned INR in any history message, prefer INR
    if not budget_currency:
        for h in session.get("history", []):
            if isinstance(h, dict) and h.get("role") == "user" and isinstance(h.get("content"), str):
                if "inr" in h["content"].lower() or "₹" in h["content"]:
                    budget_currency = "INR"
                    fields["budget_currency"] = "INR"
                    break
    # If budget looks like a small number but currency is INR, treat <1000 as thousands (e.g., 50 -> 50,000)
    if budget_currency == "INR" and budget_pp is not None:
        try:
            bpf = float(budget_pp)
            if bpf < 1000:
                # Heuristic: assume user may have used shorthand like '50' for 50k INR
                # We'll scale and also keep original for transparency
                fields.setdefault("_budget_original", bpf)
                fields["budget_per_person"] = int(bpf * 1000)
                budget_pp = fields["budget_per_person"]
        except Exception:
            pass

    # ── Past-date guard before generation ──────────────────────────────────
    # Final defence — even if an earlier path missed it, we never run the heavy
    # itinerary pipeline against a backdated trip.
    for _dk in ("trip_start_date", "checkin_date"):
        _dv = fields.get(_dk)
        if _dv and _is_past_date(_dv):
            sc(f"Past trip date detected ({_dk}={_dv}); rejecting before generation")
            fields.pop("trip_start_date", None)
            fields.pop("checkin_date", None)
            session["history"].append({"role": "assistant", "content": _PAST_DATE_REPLY})
            _sync_chat_to_store()
            return {
                "session_id": sid,
                "need_more": True,
                "prompt": _PAST_DATE_REPLY,
                "collected": fields,
            }

    # ── Destination sanity check ────────────────────────────────────────────────
    # Catches both kinds of bad data:
    #   (a) the entire user request stored as `destination` (legacy bug)
    #   (b) a single-word noun like "Estimate" that slipped through the old
    #       permissive heuristic.
    # Recovery strategy: re-run the resolver on the destination value AND on
    # every user message in history; first valid hit wins. If nothing recovers,
    # bounce to the user with a clarifying question.
    try:
        from destination_resolver import is_known_destination as _dest_known
    except Exception:
        _dest_known = None

    _dest_val = (fields.get("destination") or "").strip()
    _looks_bogus = (
        not _dest_val
        or len(_dest_val) > 60
        or any(ch in _dest_val for ch in ".!?")
        or len(_dest_val.split()) > 4
        or re.search(r"\d", _dest_val)
        or (_dest_known is not None and not _dest_known(_dest_val))
    )
    if _dest_val and _looks_bogus:
        sc(f"destination='{_dest_val}' looks bogus — attempting recovery")
        # Try re-extracting from the destination string itself first, then from
        # the most recent user messages in history.
        _candidates: List[str] = [_dest_val]
        for h in reversed(session.get("history", [])):
            if isinstance(h, dict) and h.get("role") == "user" and isinstance(h.get("content"), str):
                _candidates.append(h["content"])
                if len(_candidates) >= 6:
                    break
        _better = None
        for cand in _candidates:
            try:
                _re_extracted = conv_manager.detect_fields_in_text(cand)
                _b = _re_extracted.get("destination")
                if _b and (_dest_known is None or _dest_known(_b)):
                    _better = _b
                    # Also pull in the route if available
                    if _re_extracted.get("destinations"):
                        fields["destinations"] = _re_extracted["destinations"]
                    if _re_extracted.get("route"):
                        fields["route"] = _re_extracted["route"]
                    break
            except Exception:
                continue
        if _better:
            fields["destination"] = _better
            sc(f"Recovered destination='{_better}' (was '{_dest_val}')")
        else:
            fields.pop("destination", None)
            fields.pop("destinations", None)
            _ask = (
                "I couldn't pin down the destination from your previous request — "
                "could you tell me just the city or country? For example: 'Singapore' "
                "or 'Dubai → Abu Dhabi'."
            )
            session["history"].append({"role": "assistant", "content": _ask})
            _sync_chat_to_store()
            return {"session_id": sid, "need_more": True, "prompt": _ask, "collected": fields}

    features = feature_extractor.extract(fields)

    predicted_cost = cost_model.predict_cost(features)

    # Find similar past itineraries (used internally to inform the LLM)
    m = get_matcher()
    matches = m.find_similar(fields, text_summary=features.get("text_summary"))
    kb_summary = m.summarize_matches(matches) if matches else None

    # Retrieve user-uploaded and indexed KB documents relevant to this trip
    _kb_query = " ".join(filter(None, [
        str(fields.get("destination") or ""),
        str(fields.get("trip_style") or ""),
        str(fields.get("event_type") or ""),
    ])).strip()
    try:
        user_kb_entries = await asyncio.to_thread(get_user_kb_docs, _kb_query, 3) if _kb_query else []
    except Exception as _e:
        sc(f"KB doc lookup failed: {_e}")
        user_kb_entries = []
    # Load full text for each entry (cap at 2500 chars each)
    user_kb_texts: list = []
    for _entry in user_kb_entries:
        _txt_path = _entry.get("full_text_path")
        if _txt_path:
            try:
                _txt = pathlib.Path(_txt_path).read_text(encoding="utf-8", errors="replace")
                user_kb_texts.append(f"[{_entry.get('filename','doc')}]\n{_txt[:2500]}")
            except Exception:
                if _entry.get("text_preview"):
                    user_kb_texts.append(f"[{_entry.get('filename','doc')}]\n{_entry['text_preview']}")
        elif _entry.get("text_preview"):
            user_kb_texts.append(f"[{_entry.get('filename','doc')}]\n{_entry['text_preview']}")
    sc(f"Loaded {len(user_kb_texts)} user KB documents for query='{_kb_query}'")

    # Filter nights_per_city to only include real destination cities (not labels like "Total Duration").
    # Computed early because the price-context task below depends on it.
    _known_dest_set = {d.lower() for d in (fields.get("destinations") or []) if d}
    _raw_npc = fields.get("nights_per_city") or {}
    _nights_per_city = {
        city: nights for city, nights in _raw_npc.items()
        if not _known_dest_set or city.lower() in _known_dest_set
    }

    # Start parallel tasks: attractions lookup and real-time enrichment.
    # For multi-destination trips, use a combined query (all cities).
    _all_dests = fields.get("destinations") or []
    if _all_dests and isinstance(_all_dests, list):
        dest_for_lookup = ", ".join(_all_dests)
    else:
        dest_for_lookup = fields.get("destination") or ""
    attractions_task = asyncio.to_thread(get_attractions_for_destination, dest_for_lookup)
    realtime_task = asyncio.to_thread(llm.enrich_with_realtime_data, dest_for_lookup)
    sc(f"Started enrichment for destination(s)='{dest_for_lookup}'")

    # Start real-time price context fetch in parallel (free APIs — EUR rate + hotel estimates)
    _price_dests = _all_dests if _all_dests else ([fields["destination"]] if fields.get("destination") else [])
    price_ctx_task = asyncio.to_thread(
        get_travel_price_context,
        _price_dests,
        fields.get("hotel_category") or "4-Star",
        fields.get("trip_start_date") or fields.get("checkin_date") or "",
        int(fields.get("pax") or 2),
        _nights_per_city,
    ) if _price_dests else None


    # Prepare hotel prefetch task (best-effort) if destination info is present
    hotels_suggestions = []
    include_hotels = not fields.get("exclude_hotels", False) and HOTEL_API_ENABLED
    hotel_task = None
    if HOTEL_API_ENABLED:
        try:
            # Auto-fill checkin/checkout dates for 'next month' requests
            from datetime import date, timedelta
            today = date.today()
            checkin_raw = str(fields.get("checkin_date") or "").lower()
            checkout_raw = str(fields.get("checkout_date") or "").lower()
            if "next month" in checkin_raw or "next month" in checkout_raw:
                # Estimate first and last day of next month
                year = today.year + (1 if today.month == 12 else 0)
                month = 1 if today.month == 12 else today.month + 1
                first_day = date(year, month, 1)
                # Find last day of next month
                if month == 12:
                    next_month_first = date(year + 1, 1, 1)
                else:
                    next_month_first = date(year, month + 1, 1)
                last_day = next_month_first - timedelta(days=1)

                # Choose range based on modifier words
                modifier = ""
                if "mid" in checkin_raw or "mid" in checkout_raw or "middle" in checkin_raw or "middle" in checkout_raw:
                    modifier = "mid"
                elif any(x in checkin_raw for x in ["start", "begin", "first"]) or any(x in checkout_raw for x in ["start", "begin", "first"]):
                    modifier = "start"
                elif any(x in checkin_raw for x in ["end", "last"]) or any(x in checkout_raw for x in ["end", "last"]):
                    modifier = "end"

                if modifier == "mid":
                    mid_day = first_day + timedelta(days=(last_day.day // 2) - 1)
                    checkin_dt = mid_day
                    checkout_dt = mid_day + timedelta(days=3)
                    if checkout_dt > last_day:
                        checkout_dt = last_day
                elif modifier == "start":
                    checkin_dt = first_day
                    checkout_dt = first_day + timedelta(days=3)
                    if checkout_dt > last_day:
                        checkout_dt = last_day
                elif modifier == "end":
                    checkout_dt = last_day
                    checkin_dt = last_day - timedelta(days=3)
                    if checkin_dt < first_day:
                        checkin_dt = first_day
                else:
                    checkin_dt = first_day
                    checkout_dt = last_day

                fields["checkin_date"] = checkin_dt.isoformat()
                fields["checkout_date"] = checkout_dt.isoformat()

            # If user provided a month name like 'March 2026', convert to concrete dates using duration
            months_map = {m.lower(): i for i, m in enumerate(["January","February","March","April","May","June","July","August","September","October","November","December"], start=1)}
            def _parse_month_phrase(s: str):
                if not s:
                    return None
                for mon_name in months_map:
                    if mon_name in s:
                        # try to extract year
                        ym = None
                        m = __import__('re').search(r"\b" + mon_name + r"\s+(\d{4})\b", s, __import__('re').IGNORECASE)
                        if m:
                            ym = int(m.group(1))
                        else:
                            ym = today.year
                        return (months_map[mon_name], ym)
                return None

            # prefer explicit checkin_date phrase first
            if ("next month" not in checkin_raw and "next month" not in checkout_raw):
                parsed = _parse_month_phrase(checkin_raw) or _parse_month_phrase(checkout_raw)
                if parsed:
                    mon, yr = parsed
                    # default check-in: 15th of the month
                    try:
                        checkin_dt = date(yr, mon, 15)
                    except Exception:
                        checkin_dt = date(yr, mon, 1)
                    # compute nights from duration if available
                    try:
                        dur = int(fields.get("duration") or 4)
                        nights = max(1, dur - 1)
                    except Exception:
                        nights = 3
                    checkout_dt = checkin_dt + timedelta(days=nights)
                    # cap to month's last day
                    # compute last day of month
                    if mon == 12:
                        next_month_first = date(yr + 1, 1, 1)
                    else:
                        next_month_first = date(yr, mon + 1, 1)
                    last_day = next_month_first - timedelta(days=1)
                    if checkout_dt > last_day:
                        checkout_dt = last_day
                    fields["checkin_date"] = checkin_dt.isoformat()
                    fields["checkout_date"] = checkout_dt.isoformat()

            required_hotel_params = ["destination", "checkin_date", "checkout_date", "dest_id"]
            missing_params = [p for p in required_hotel_params if not fields.get(p)]
            if include_hotels and not missing_params:
                hotel_query = {
                    "adults_number": str(fields.get("adults_number", fields.get("pax", 2))),
                    "children_number": str(fields.get("children_number", 0)),
                    "units": fields.get("units", "metric"),
                    "page_number": str(fields.get("page_number", 0)),
                    "checkin_date": fields.get("checkin_date"),
                    "checkout_date": fields.get("checkout_date"),
                    "categories_filter_ids": fields.get("categories_filter_ids", "class::2,class::4,free_cancellation::1"),
                    "children_ages": fields.get("children_ages", ""),
                    "dest_type": fields.get("dest_type", "city"),
                    "dest_id": str(fields.get("dest_id", "-553173")),
                    "order_by": fields.get("order_by", "popularity"),
                    "include_adjacency": str(fields.get("include_adjacency", True)).lower(),
                    "room_number": str(fields.get("room_number", 1)),
                    "filter_by_currency": fields.get("filter_by_currency", "AED"),
                    "locale": fields.get("locale", "en-gb"),
                }
                sc(f"Started hotel prefetch for destination='{fields.get('destination')}', query={hotel_query}")
                hotel_task = asyncio.to_thread(
                    hotel_client.search_hotels,
                    destination=fields.get("destination"),
                    checkin=hotel_query["checkin_date"],
                    checkout=hotel_query["checkout_date"],
                    adults=int(hotel_query["adults_number"]),
                    children=int(hotel_query["children_number"]),
                    children_ages=hotel_query["children_ages"],
                    units=hotel_query["units"],
                    page_number=int(hotel_query["page_number"]),
                    categories_filter_ids=hotel_query["categories_filter_ids"],
                    dest_type=hotel_query["dest_type"],
                    dest_id=int(hotel_query["dest_id"]),
                    order_by=hotel_query["order_by"],
                    include_adjacency=hotel_query["include_adjacency"] == "true",
                    room_number=int(hotel_query["room_number"]),
                    filter_by_currency=hotel_query["filter_by_currency"],
                    locale=hotel_query["locale"],
                    limit=5,
                )
            elif include_hotels and missing_params:
                sc(f"Hotel API not called due to missing params: {missing_params}")
        except Exception as e:
            hotel_task = None
            sc(f"Failed to start hotel prefetch: {e}")
    else:
        hotel_task = None
        sc("Hotel API disabled via HOTEL_API_ENABLED flag; skipping hotel prefetch")

    # Build system prompt for LLM — request JSON output matching the schema
    ferrari_requested = False
    ferrari_locations = ["abu dhabi", "united arab emirates", "uae", "abudhabi"]
    def _dest_allows_ferrari(dest: str) -> bool:
        if not dest:
            return False
        d = str(dest).lower()
        return any(loc in d for loc in ferrari_locations)

    for h in session.get("history", []):
        if isinstance(h, dict) and isinstance(h.get("content"), str) and "ferrari world" in h["content"].lower():
            # only consider Ferrari if destination is a known Ferrari World location
            if _dest_allows_ferrari(fields.get("destination")):
                ferrari_requested = True
                break

    if not ferrari_requested and fields.get("event_type"):
        if "ferrari world" in str(fields.get("event_type")).lower() and _dest_allows_ferrari(fields.get("destination")):
            ferrari_requested = True
    # Build client-type-specific instructions for the system prompt
    _CLIENT_TYPE_INSTRUCTIONS: dict = {
        "corporate": (
            "CLIENT TYPE: Corporate.\n"
            "- Prioritise 5-star or 4-star-deluxe hotels in the CBD or top business district.\n"
            "- Include professional guide for every sightseeing day.\n"
            "- Schedule team-building or networking dinners at Michelin-starred or top-rated restaurants.\n"
            "- All transport: luxury sedan or premium SUV with a dedicated driver.\n"
            "- Include conference/meeting room and AV setup costs if >1 day stay.\n"
            "- Meals: breakfast and dinner fully hosted; lunches at premium restaurants.\n"
        ),
        "mice": (
            "CLIENT TYPE: MICE (Meetings, Incentives, Conferences, Events).\n"
            "- Include a dedicated event-coordinator day with venue inspection options.\n"
            "- Suggest suitable conference/banquet venues with capacity and rates.\n"
            "- Group activities must be team-building focused (cooking class, escape room, treasure hunt, etc.).\n"
            "- Gala dinner on the final evening with recommended themes and décor notes.\n"
            "- Transport: coach or fleet of minivans for group movement with coordinated timings.\n"
            "- Include a daily run-of-show summary for each event day.\n"
        ),
        "leisure": (
            "CLIENT TYPE: Leisure.\n"
            "- Focus on relaxation, local culture, and unique experiences.\n"
            "- Include spa sessions, sunset cruises, or local market visits where appropriate.\n"
            "- Balance activities with free time — at least one leisurely half-day per city.\n"
            "- Hotels: boutique or well-reviewed 4-star properties in scenic or vibrant areas.\n"
            "- Meals: mix of local street-food experiences and fine-dining recommendations.\n"
            "- Pace should be comfortable — no back-to-back full-day tours.\n"
        ),
        "dmc": (
            "CLIENT TYPE: DMC / B2B partner.\n"
            "- Provide net rates and operator-level cost breakdown (not retail).\n"
            "- List all services as line items with per-unit and per-group rates.\n"
            "- Include preferred local vendor notes (transport, guides, restaurants).\n"
            "- Structure itinerary for easy repackaging — clear inclusions/exclusions per service.\n"
        ),
        "b2b": (
            "CLIENT TYPE: B2B (trade/agent partner).\n"
            "- Provide operator-level net pricing with markup space built in.\n"
            "- Clearly separate per-pax and per-group costs.\n"
            "- Include flexible add-on options that the agent can upsell.\n"
        ),
        "b2c": (
            "CLIENT TYPE: B2C (direct consumer).\n"
            "- Friendly, inspiring tone in activity descriptions.\n"
            "- Highlight value-for-money choices alongside premium options.\n"
            "- Include practical tips (booking windows, what to pack, visa notes).\n"
        ),
    }
    _ct_instructions = _CLIENT_TYPE_INSTRUCTIONS.get(_client_type_str or "", "")
    if _client_record:
        _ct_instructions += (
            f"Client company: {_client_record.get('company_name', '')}. "
            f"Industry: {_client_record.get('industry', '')}. "
            f"Notes: {_client_record.get('notes', '') or 'none'}.\n"
        )

    _is_multi_dest = bool(fields.get("destinations") and len(fields.get("destinations", [])) > 1)
    _has_seniors = bool(fields.get("seniors") or fields.get("senior_friendly"))

    # _nights_per_city and _known_dest_set were computed earlier (before the price-context task).

    # Compute total days early so it can feed both system_prompt and user prompt
    _total_nights_raw = fields.get("total_nights") or fields.get("nights") or fields.get("duration")
    try:
        _total_nights_int = int(_total_nights_raw) if _total_nights_raw else None
    except (ValueError, TypeError):
        _total_nights_int = None
    # Cross-check with nights_per_city sum
    _npc_sum = sum(_nights_per_city.values()) if _nights_per_city else 0
    if _npc_sum > 0 and (_total_nights_int is None or abs(_npc_sum - _total_nights_int) <= 1):
        _total_nights_int = _npc_sum
    _num_days = _total_nights_int + 1 if _total_nights_int else None

    _route_str = fields.get("route") or ""
    _room_cfg = fields.get("room_config") or {}
    _transport_pref = fields.get("transport_preference") or ""
    _driver_pref = fields.get("driver_preference") or ""
    _guide_req = fields.get("guide_required") or False

    _senior_rule = (
        "- This group includes senior citizens (60+). All activities must be low-exertion with minimal walking.\n"
        "- Plan comfort stops every 90 minutes during transfers.\n"
        "- Avoid steep climbs, long queues, or physically demanding excursions.\n"
        "- Prefer seated experiences: river cruises, classical concerts, scenic drives, museum visits.\n"
    ) if _has_seniors else ""

    # Build per-city day ranges for multi-destination trips
    _day_range_str = ""
    if _is_multi_dest and _nights_per_city and _num_days:
        _route_cities = fields.get("destinations") or list(_nights_per_city.keys())
        _day_ptr = 1
        _range_parts = []
        for _i, _city in enumerate(_route_cities):
            _n = _nights_per_city.get(_city, 0)
            if _n == 0:
                _range_parts.append(f"Day {_day_ptr}: {_city} (transit/arrival day)")
                _day_ptr += 1
            else:
                _is_last = (_i == len(_route_cities) - 1)
                _city_days = _n + (1 if _is_last else 1)  # arrival + n nights; last city gets +1 for departure
                _end = min(_day_ptr + _city_days - 1, _num_days)
                if _day_ptr == _end:
                    _range_parts.append(f"Day {_day_ptr}: {_city} ({_n} nights)")
                else:
                    _range_parts.append(f"Days {_day_ptr}–{_end}: {_city} ({_n} nights)")
                _day_ptr = _end + 1
        _day_range_str = "; ".join(_range_parts)

    # Build a per-day date table anchored to the user-supplied trip start so the
    # LLM can populate the "date" field for each day with REAL future dates.
    _per_day_dates: List[str] = []
    _trip_start_iso = ""
    try:
        _start_raw = fields.get("trip_start_date") or fields.get("checkin_date") or ""
        # Accept either ISO or any prose; defer to _parse_user_date for prose.
        _parsed_start = None
        if isinstance(_start_raw, str) and re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", _start_raw.strip()):
            try:
                _parsed_start = datetime.strptime(_start_raw.strip(), "%Y-%m-%d").date()
            except Exception:
                _parsed_start = None
        if _parsed_start is None and _start_raw:
            _maybe = _parse_user_date(str(_start_raw))
            if _maybe:
                try:
                    _parsed_start = datetime.strptime(_maybe, "%Y-%m-%d").date()
                except Exception:
                    pass
        if _parsed_start and _num_days:
            _trip_start_iso = _parsed_start.isoformat()
            for _i in range(_num_days):
                _d = _parsed_start + timedelta(days=_i)
                _per_day_dates.append(_d.strftime("%a, %d %b %Y"))   # e.g. "Sat, 15 Mar 2026"
    except Exception:
        _per_day_dates = []
    _date_table_str = ""
    if _per_day_dates:
        _date_table_str = (
            "- REAL DATES (use these EXACTLY as the 'date' for each day; do NOT pick "
            "your own dates):\n"
            + "\n".join(f"    Day {i+1}: {d}" for i, d in enumerate(_per_day_dates))
            + "\n"
        )

    _multi_dest_rule = (
        f"- This is a MULTI-DESTINATION trip: {_route_str}.\n"
        f"- Nights per city: "
        + ", ".join(f"{c}: {n} nights" for c, n in _nights_per_city.items())
        + ".\n"
        + (f"- Day distribution: {_day_range_str}.\n" if _day_range_str else "")
        + "- Label each day with its city in the 'city' field (e.g., 'Budapest', 'Prague').\n"
        "- Do NOT mix activities from different cities on the same day.\n"
    ) if _is_multi_dest else ""

    _transport_rule = (
        f"- Transport: {_transport_pref}. Specify the actual vehicle type used in the destination "
        f"(NOT a single hardcoded model like Toyota Innova) — pick what fits {{pax_for_transport}} "
        f"travellers from realistic locally-available options (sedan, SUV, minivan, mini-coach, "
        f"premium chauffeured car, etc.). Provide daily hire rate and total hire cost.\n"
    ).replace("{pax_for_transport}", str(int(fields.get("pax") or 2))) if _transport_pref else (
        "- Transport: Private vehicle/car appropriate for the destination and group size. "
        "Choose from realistic locally-operated options (sedan, SUV, minivan, mini-coach, premium "
        "chauffeured car). Do NOT default to Toyota Innova or any single brand. Specify vehicle "
        "type and daily rate.\n"
    )

    _driver_rule = f"- Driver: {_driver_pref}.\n" if _driver_pref else ""
    _guide_rule = "- Include a local English-speaking guide for all sightseeing days; specify daily guide fee.\n" if _guide_req else ""

    _room_rule = ""
    if _room_cfg:
        _room_rule = (
            "- Room configuration: "
            + ", ".join(f"{v} {k} room(s)" for k, v in _room_cfg.items())
            + ". Reflect this in hotel costs.\n"
        )

    # ── Currency selection ─────────────────────────────────────────────────
    # Pick the currency the LLM should quote everything in. Order of priority:
    #   1. Explicit user-provided budget_currency
    #   2. Country-of-destination heuristic (UAE/Oman → AED, Eurozone → EUR,
    #      UK → GBP, India → INR, USA → USD)
    #   3. INR default (most users are Indian agencies)
    _country_currency_map = {
        "AE": "AED", "OM": "AED", "QA": "AED", "BH": "AED", "SA": "AED", "KW": "AED",
        "US": "USD", "CA": "USD",
        "GB": "GBP",
        "IN": "INR", "LK": "INR", "NP": "INR", "BT": "INR",
        "JP": "USD", "TH": "USD", "ID": "USD", "MY": "USD", "SG": "USD", "VN": "USD",
        "CN": "USD", "KR": "USD", "PH": "USD",
        # Eurozone
        "FR": "EUR", "DE": "EUR", "IT": "EUR", "ES": "EUR", "PT": "EUR",
        "NL": "EUR", "BE": "EUR", "AT": "EUR", "GR": "EUR", "IE": "EUR", "FI": "EUR",
    }
    _currency_code = (fields.get("budget_currency") or "").upper().strip()
    if _currency_code not in {"INR", "USD", "EUR", "GBP", "AED"}:
        _currency_code = ""
    if not _currency_code:
        try:
            from destination_resolver import find_destinations as _find_dests
            _resolved = _find_dests(
                str(fields.get("destination") or "")
                + " " + " ".join(fields.get("destinations") or [])
            ) or []
            for _r in _resolved:
                cc = (_r.get("country_code") or "").upper()
                if cc in _country_currency_map:
                    _currency_code = _country_currency_map[cc]
                    break
        except Exception:
            pass
    if not _currency_code:
        _currency_code = "INR"
    _currency_label = {
        "INR": "Indian Rupees",
        "USD": "US Dollars",
        "EUR": "Euros",
        "GBP": "British Pounds",
        "AED": "UAE Dirhams",
    }.get(_currency_code, _currency_code)
    _currency_round = {
        "INR": "nearest 500",
        "USD": "nearest 5",
        "EUR": "nearest 5",
        "GBP": "nearest 5",
        "AED": "nearest 25",
    }.get(_currency_code, "nearest sensible unit")
    fields["effective_currency"] = _currency_code

    # ── Pax-aware transport sizing rule ───────────────────────────────────
    _pax_int = int(fields.get("pax") or 2)
    if _pax_int <= 3:
        _transport_sizing_rule = (
            "Choose a private SEDAN or premium chauffeured car (3 pax max). "
            "A standard car is the right vehicle here — do NOT scale up to a coach."
        )
    elif _pax_int <= 6:
        _transport_sizing_rule = (
            "Choose a private SUV or MPV (e.g. 6-7 seater). A regular car is too small. "
            "Avoid coaches — over-scaling wastes the client's budget."
        )
    elif _pax_int <= 10:
        _transport_sizing_rule = (
            "Choose a MINIVAN / passenger van (10-12 seater) — a regular car or SUV "
            "cannot fit this group. Do NOT use a sedan or SUV here."
        )
    elif _pax_int <= 18:
        _transport_sizing_rule = (
            "Choose a MINI-COACH or 14-18 seater bus — a minivan is too tight, "
            "a full coach is over-spec. Quote per day in local rates."
        )
    elif _pax_int <= 30:
        _transport_sizing_rule = (
            "Choose a STANDARD COACH (25-30 seater air-conditioned). A minivan or "
            "SUV is wholly inadequate at this group size."
        )
    else:
        _transport_sizing_rule = (
            f"Choose a LARGE COACH or multiple coaches as appropriate for {_pax_int} pax. "
            "Provide per-coach hire rate AND total. Cars/vans/SUVs are not viable."
        )

    system_prompt = (
        "You are a senior travel consultant at a professional DMC/MICE agency. "
        "Produce a COMPLETE, DETAILED, PROFESSIONAL day-by-day itinerary based on the trip details provided.\n\n"
        + (_ct_instructions + "\n" if _ct_instructions else "")
        + "OUTPUT FORMAT: Return ONLY a single valid JSON object. No markdown fences, no prose, no commentary outside the JSON.\n\n"
        "JSON SCHEMA (follow exactly):\n"
        "{\n"
        '  "title": "Descriptive, evocative trip title",\n'
        '  "destination": "Primary destination or route string",\n'
        '  "duration_days": <number>,\n'
        '  "pax": <number>,\n'
        '  "event_type": "leisure | corporate | MICE | incentive | extension",\n'
        '  "itinerary_summary": "4-6 sentence narrative summary describing the KIND of trip (e.g. romantic escape, cultural immersion, high-energy MICE programme, family adventure) and the EXPERIENCE the traveller will have at this destination — sensory highlights, the trip\'s character and pace, what they will feel/see/taste, and what makes this destination memorable for this type of group. Write in evocative, present-tense prose.",\n'
        '  "days": [\n'
        '    {\n'
        '      "day": <number>,\n'
        '      "city": "City name for this day",\n'
        '      "date": "Day name, DD Mon YYYY (e.g. \\"Sat, 15 Mar 2026\\") — use the date TABLE provided in the user prompt; never make up dates",\n'
        '      "summary": "One-line evocative theme for the day (e.g. \'Ancient temples, spice markets & sunset dhow cruise\')",\n'
        '      "morning": "07:30 – Breakfast at [specific hotel restaurant or local café] ([cuisine], approx INR [X]/person). 09:00 – Depart hotel by private [vehicle type] (approx [X] min drive). 09:30 – Arrive at [Landmark/Venue]; guided tour covering [specific features, historical context]; entry fee INR [X]/person; approx [X] hrs. 11:30 – Walk to [next venue or market]; highlights include [specific stalls/items/sights]. 12:30 – Lunch at [Restaurant Name], [locality]; signature dishes: [dish1, dish2]; approx INR [X]/person.",\n'
        '      "afternoon": "14:00 – Transfer to [Venue/Area] (approx [X] min). 14:30 – [Activity at Venue]; entry INR [X]; duration approx [X] hrs; [specific things to see/do]. 16:30 – [Next activity or leisure time — specific venue, what to look for]. 17:30 – Return transfer to hotel; freshen up.",\n'
        '      "evening": "19:00 – Depart for [cultural show / sunset point / dinner venue] (approx [X] min). 19:30 – [Evening activity — name, description, ticket cost INR [X] if applicable]. 20:30 – Dinner at [Restaurant Name], [locality]; [cuisine type]; recommended dishes: [dish1, dish2]; approx INR [X]/person. 22:30 – Return to hotel.",\n'
        '      "transport_note": "Private [vehicle type appropriate for the destination, group size, and trip style — e.g. private car, sedan, SUV, minivan, luxury coach, premium chauffeured car, electric/hybrid, etc.] for the full day — INR [X] including driver and fuel. Choose the vehicle based on what is actually offered locally and the pax count; do NOT default to a single brand or model.",\n'
        '      "hotel": {"name": "Hotel name", "area": "Locality/district", "category": "4-Star / 5-Star Deluxe"}\n'
        '    }\n'
        '  ],\n'
        '  "hotels": [\n'
        '    {"city": "City name", "name": "Hotel name", "area": "Locality", "category": "4-Star", "price_per_night_inr": "INR amount per room per night"}\n'
        '  ],\n'
        '  "cost_breakdown": {\n'
        '    "accommodation": "INR total for all rooms all nights",\n'
        '    "transport": "INR total for all vehicle hire including driver",\n'
        '    "meals": "INR total for all included meals",\n'
        '    "sightseeing_and_activities": "INR total for all entry fees and guided tours",\n'
        '    "guide_fees": "INR total if guide included",\n'
        '    "miscellaneous": "INR total for tips, porterage, contingency",\n'
        '    "grand_total_per_person": "INR per person",\n'
        '    "grand_total_group": "INR for full group"\n'
        '  },\n'
        '  "inclusions": ["Accommodation as per plan", "Private vehicle with driver for all transfers", "..."],\n'
        '  "exclusions": ["International/domestic airfare", "Visa fees", "Travel insurance", "Meals not mentioned", "Personal expenses", "Tips and gratuities"],\n'
        '  "important_guidelines": ["Carry valid passport/ID at all times", "..."],\n'
        '  "notes": "Any relevant operational notes, seasonal advice, or special instructions"\n'
        "}\n\n"
        "STRICT RULES:\n"
        + (f"- CRITICAL: Generate EXACTLY {_num_days} day objects in the 'days' array. Set duration_days={_num_days}. Do NOT generate fewer or more days under any circumstances.\n" if _num_days else "")
        + "- itinerary_summary MUST be a 4-6 sentence narrative paragraph capturing the trip's character (kind of trip) and the experience the traveller will have at this destination. Do NOT skip this field, do NOT leave it empty, do NOT replace it with a list.\n"
        + f"- morning, afternoon, and evening MUST each be a full multi-sentence paragraph with: exact timings (HH:MM format), real venue/restaurant names, {_currency_code} entry costs, travel durations, and at least 2-3 distinct activities per period.\n"
        "- Do NOT use vague filler like 'visit a local market' — name the actual market, what is sold there, and the cost.\n"
        + f"- Every meal must name the specific restaurant and 1-2 signature dishes with approximate per-person cost in {_currency_code}.\n"
        + f"- transport_note MUST appear on every day with the specific vehicle type and {_currency_code} daily cost.\n"
        + f"- All monetary values must be in {_currency_code} ({_currency_label}). Round to {_currency_round}.\n"
        + f"- PAX-AWARE TRANSPORT (group size = {_pax_int}). {_transport_sizing_rule} The transport_note for every day must reflect this vehicle class. Use real, currently-available local operators when known; if not, describe the vehicle class and a realistic daily rate based on the live price context provided in the user prompt.\n"
        "- cost_breakdown must cover ALL days and ALL pax combined.\n"
        + _multi_dest_rule
        + _senior_rule
        + _transport_rule
        + _driver_rule
        + _guide_rule
        + _room_rule
        + ("- Include a full-day Ferrari World plan on the appropriate day (tickets, rides, dining).\n" if ferrari_requested else "")
        + "- Do NOT invent Ferrari World plans unless destination is Abu Dhabi and explicitly requested.\n"
        "- COUNTRY-LEVEL DESTINATIONS: If the destination is a country rather than a specific city (e.g. 'Japan', 'France', 'Italy', 'Thailand'), build a smart multi-city itinerary covering 2-4 representative cities suited to the trip type, duration, and traveller profile. Choose iconic plus complementary cities (e.g. Japan → Tokyo + Kyoto + Osaka; Italy → Rome + Florence + Venice). Distribute days sensibly across cities, label each day with its city, and add inter-city transfers (rail/road/flight) with timings and costs. Set destination string to the country and populate destinations array with the chosen cities.\n"
        "- Do NOT include raw document text or verbatim historical content.\n"
        "- Output pure JSON only. No text before or after the JSON object."
    )

    # Build user prompt — no formatting instructions here (system prompt owns those).
    # NOTE: price_ctx is initially heuristic-only here; we recompute it later with
    # the live Tavily/Wikipedia text mined for prices (see "Recompute price_ctx" below).
    try:
        price_ctx = price_engine.estimate_total(fields, int(fields.get("pax", 1)))
        sc(f"Computed price context (heuristic) for pax={fields.get('pax', 1)}")
    except Exception as e:
        price_ctx = {}
        logger.exception("Price context computation failed")
        sc(f"Price context computation failed: {type(e).__name__}: {e}")

    # Build a clean, readable summary of confirmed trip fields
    def _fmt_fields_for_prompt(f: dict) -> str:
        lines = []
        dests = f.get("destinations")
        if dests and isinstance(dests, list):
            lines.append(f"Route: {' → '.join(dests)}")
        elif f.get("destination"):
            lines.append(f"Destination: {f['destination']}")
        _nights_val = f.get("total_nights") or f.get("nights") or f.get("duration")
        if _nights_val:
            try:
                nd = int(_nights_val)
                lines.append(f"Duration: {nd} nights / {nd + 1} days")
            except Exception:
                lines.append(f"Duration: {_nights_val} nights")
        if f.get("nights_per_city"):
            npc = ", ".join(f"{c}: {n} nights" for c, n in f["nights_per_city"].items())
            lines.append(f"Nights per city: {npc}")
        if f.get("pax"):
            sen = f" (incl. {f['seniors']} senior citizens 60+)" if f.get("seniors") else ""
            lines.append(f"Travelers: {f['pax']} adults{sen}")
        if f.get("hotel_category"):
            loc = f" — {f['hotel_location_preference']}" if f.get("hotel_location_preference") else ""
            lines.append(f"Hotel: {f['hotel_category']}{loc}")
        if f.get("trip_start_date"):
            lines.append(f"Start date: {f['trip_start_date']}")
        if f.get("event_type"):
            lines.append(f"Trip type: {f['event_type']}")
        if f.get("transport_preference"):
            lines.append(f"Transport: {f['transport_preference']}")
        if f.get("room_config"):
            rc = ", ".join(f"{v} {k} room(s)" for k, v in f["room_config"].items())
            lines.append(f"Room config: {rc}")
        if f.get("guide_required"):
            lines.append("Guide: English-speaking local guide required")
        if f.get("preferred_activities"):
            lines.append(f"Activities requested: {', '.join(f['preferred_activities'])}")
        if f.get("budget_per_person"):
            lines.append(f"Budget: {f.get('budget_currency','INR')} {f['budget_per_person']}/person")
        return "\n".join(lines)

    _raw_req = fields.get("raw_text", "")
    _fields_summary = _fmt_fields_for_prompt(fields)

    user_prompt = "CONFIRMED TRIP DETAILS:\n" + _fields_summary
    if predicted_cost:
        user_prompt += f"\n\nML cost estimate: USD {predicted_cost:.0f}"
    if price_ctx:
        user_prompt += f"\nCost reference: {price_ctx}"
    if kb_summary:
        user_prompt += f"\n\nHistorical reference (anonymized):\n{kb_summary}"
    if _raw_req:
        user_prompt += f"\n\nOriginal client request (read for any additional context or specific requests):\n{_raw_req}"
    if _num_days:
        user_prompt += f"\n\nCRITICAL REQUIREMENT: Generate EXACTLY {_num_days} day objects (one per day, {_total_nights_int} nights). Do NOT stop early."
    if _date_table_str:
        user_prompt += (
            "\n\nDATES — assign these EXACT real dates to each day's 'date' field. "
            "Do NOT use yesterday or backdated values; do NOT invent your own dates. "
            "These are the actual future travel dates:\n"
            + _date_table_str
        )
    user_prompt += "\n\nReturn a single valid JSON object matching the schema in the system prompt. Output JSON only — no prose, no markdown fences."
    # We will NOT return raw match lists in the API response — the LLM can use the knowledge quietly.
    include_matches_in_response = False

    # First fetch real-time data (Wikipedia, Attractions, News) — fetch each with a timeout
    # so we can inject it into the LLM prompt before calling the LLM. Add sanity checks.
    try:
        # Per-task timeouts to avoid blocking the whole request.
        # Bumped from 5s/4s — Wikipedia + Overpass routinely take 2-4s and were
        # failing the budget under load. Errors below now log full stack traces
        # via logger.exception so the terminal shows the real cause.
        try:
            realtime_raw = await asyncio.wait_for(realtime_task, timeout=15)
        except asyncio.TimeoutError:
            sc("realtime_task timed out after 15s")
            realtime_raw = {}
        except Exception as e:
            logger.exception("realtime_task failed")
            sc(f"realtime_task failed: {type(e).__name__}: {e}")
            realtime_raw = {}

        try:
            attractions_raw = await asyncio.wait_for(attractions_task, timeout=120)
        except asyncio.TimeoutError:
            sc("attractions_task timed out after 120s")
            attractions_raw = []
        except Exception as e:
            logger.exception("attractions_task failed")
            sc(f"attractions_task failed: {type(e).__name__}: {e}")
            attractions_raw = []

        # Sanitize the payloads
        realtime_data = sanitize_realtime_payload(realtime_raw or {})
        if isinstance(attractions_raw, dict):
            enrich = {"city_summary": attractions_raw.get("city_summary"), "attractions": attractions_raw.get("attractions", [])}
        else:
            enrich = {"city_summary": None, "attractions": attractions_raw or []}

        sc(f"Pre-gathered real-time data sanity: wiki={'yes' if realtime_data.get('wikipedia') else 'no'}; attractions={len(enrich.get('attractions', []))}; news={len(realtime_data.get('news', []))}")

        # Await price context task (with timeout so it never blocks)
        _live_price_ctx: Dict[str, Any] = {}
        if price_ctx_task:
            try:
                _live_price_ctx = await asyncio.wait_for(price_ctx_task, timeout=20)
                sc(f"Price context fetched: cities={list(_live_price_ctx.get('per_city', {}).keys())}")
            except asyncio.TimeoutError:
                sc("price_ctx_task timed out after 20s")
            except Exception as _pe:
                logger.exception("price_ctx_task failed")
                sc(f"price_ctx_task failed: {type(_pe).__name__}: {_pe}")
    except Exception as e:
        logger.error("Failed to pre-gather real-time data: %s", e)
        realtime_data = {"wikipedia": {}, "attractions": [], "news": []}
        enrich = {"city_summary": None, "attractions": []}
        _live_price_ctx = {}
        sc(f"Real-time pre-gather failed: {e}")

    # Now enrich user_prompt with the actual real-time data we fetched
    realtime_context = ""
    if realtime_data:
        if realtime_data.get('wikipedia'):
            realtime_context += f"\nWikipedia Summary:\n{realtime_data['wikipedia'].get('extract', '')[:300]}..."
        if realtime_data.get('attractions') and len(realtime_data['attractions']) > 0:
            realtime_context += f"\n\nNearby Attractions from OpenStreetMap:\n" + "\n".join([f"- {a}" for a in realtime_data['attractions'][:5]])
        if realtime_data.get('news') and len(realtime_data['news']) > 0:
            realtime_context += f"\n\nRecent News:\n" + "\n".join([f"- {n}" for n in realtime_data['news'][:3]])

    # Add Google real-time search results (with hard 5s timeout so it never blocks LLM call)
    try:
        from real_time_search import google_destination_info
        dest_for_google = fields.get("destination", "")
        if dest_for_google:
            google_info = await asyncio.wait_for(
                asyncio.to_thread(google_destination_info, dest_for_google), timeout=5
            )
            if google_info:
                google_links = []
                for category in ["travel_tips", "things_to_do", "general"]:
                    for item in google_info.get(category, [])[:2]:
                        google_links.append(f"- {item.get('title', '')} ({item.get('url', '')})")
                if google_links:
                    realtime_context += f"\n\nGoogle Search Results:\n" + "\n".join(google_links[:4])
                    sc(f"Added {len(google_links)} Google search results to context")
    except asyncio.TimeoutError:
        sc("Google search timed out after 5s; skipping")
    except Exception as e:
        sc(f"Google search enrichment failed: {e}")

    # ── Tavily MCP web search ─────────────────────────────────────────────────
    # Always runs regardless of KB state. Searches per-city for multi-destination trips.
    # This is the primary real-time enrichment source when KB data is empty or sparse.
    try:
        from src.services.mcp.mcp_client import get_mcp_client, MCPError as _MCPError

        _search_cities = (
            fields.get("destinations") or
            ([fields.get("destination")] if fields.get("destination") else [])
        )
        _has_kb = bool(kb_summary)
        _max_cities = 3

        # Build a date hint for price queries (current month/year if no trip date set)
        from datetime import date as _date
        _trip_when = (
            str(fields.get("trip_start_date") or fields.get("checkin_date") or "").strip()
            or _date.today().strftime("%B %Y")
        )
        _pax_hint = fields.get("pax") or 2
        _hotel_cat = fields.get("hotel_category") or "4-star"

        # LLM-planned search queries — populated by the early LangChain extraction
        # step. Each query was proposed by the model based on the user's exact
        # request, so they're more relevant than generic "{city} attractions".
        _llm_search_queries: list = list(fields.get("llm_search_queries") or [])
        if _llm_search_queries:
            sc(f"Using {len(_llm_search_queries)} LLM-planned search queries")

        if _search_cities:
            async def _tavily_city(city: str) -> str:
                try:
                    _cli = await asyncio.wait_for(get_mcp_client(), timeout=10)
                    # Standard 3 queries per city: attractions, prices, dining.
                    _q_attr = f"top tourist attractions things to do {city} travel itinerary tips"
                    _q_price = (
                        f"{_hotel_cat} hotel price per night {city} {_trip_when} "
                        f"average daily cost meals food activities transport for {_pax_hint} travelers"
                    )
                    _q_dining = f"best restaurants local experiences {city} for tourists"

                    _r_attr = await asyncio.wait_for(_cli.search_web(_q_attr, depth="basic"), timeout=12)
                    _r_price = await asyncio.wait_for(_cli.search_web(_q_price, depth="basic"), timeout=12)
                    _r_dining = ""
                    if not _has_kb:
                        _r_dining = await asyncio.wait_for(_cli.search_web(_q_dining, depth="basic"), timeout=12)

                    # LLM-planned queries: scope each to this city only if it
                    # doesn't already mention a city, so the result is relevant.
                    _r_llm_blocks = []
                    for _llm_q in _llm_search_queries[:3]:    # cap at 3 to keep costs sane
                        try:
                            scoped = _llm_q if city.lower() in _llm_q.lower() else f"{_llm_q} {city}"
                            _r = await asyncio.wait_for(_cli.search_web(scoped, depth="basic"), timeout=12)
                            if _r:
                                _r_llm_blocks.append(f"Q: {scoped}\n{_r[:600]}")
                        except Exception:
                            continue

                    parts = []
                    if _r_attr:
                        parts.append(f"Attractions & Activities:\n{_r_attr[:700]}")
                    if _r_price:
                        parts.append(f"Live Prices & Costs:\n{_r_price[:800]}")
                    if _r_dining:
                        parts.append(f"Dining & Local Experiences:\n{_r_dining[:500]}")
                    if _r_llm_blocks:
                        parts.append("LLM-targeted research:\n" + "\n\n".join(_r_llm_blocks))
                    return f"[{city}]\n" + "\n".join(parts) if parts else ""
                except asyncio.TimeoutError:
                    sc(f"Tavily: timeout for {city}")
                    return ""
                except Exception as _ce:
                    sc(f"Tavily: {city} error: {_ce}")
                    return ""

            _tavily_coros = [_tavily_city(c) for c in _search_cities[:_max_cities]]
            _tavily_results = await asyncio.gather(*_tavily_coros, return_exceptions=True)
            _tavily_blocks = [r for r in _tavily_results if isinstance(r, str) and r.strip()]

            if _tavily_blocks:
                realtime_context += "\n\nWeb Search Results (Tavily):\n" + "\n\n".join(_tavily_blocks)
                sc(f"Tavily: injected {len(_tavily_blocks)} city block(s) into prompt")
            else:
                sc("Tavily: no usable results returned")

            # Recompute price_ctx now that we have live Tavily prose. The price engine
            # mines numeric prices from this text and blends them with the heuristic
            # range (live data weighted 70%) — gives destination-aware pricing instead
            # of one-size-fits-all baselines.
            try:
                price_ctx = price_engine.estimate_total(
                    fields,
                    int(fields.get("pax", 1)),
                    live_text=realtime_context,
                )
                sc(
                    f"Recomputed price context with live data: "
                    f"mined={price_ctx.get('live_prices_mined', 0)} prices, "
                    f"hotel_source={price_ctx.get('accommodation_range', {}).get('source', 'n/a')}"
                )
            except Exception as _pe:
                logger.exception("Live price recomputation failed (keeping heuristic price_ctx)")
                sc(f"Live price recomputation failed: {type(_pe).__name__}: {_pe}")
        else:
            sc("Tavily: no destination to search")
    except asyncio.TimeoutError:
        sc("Tavily: outer timeout")
    except Exception as _te:
        sc(f"Tavily search block failed: {_te}")

    # Build user KB reference block
    kb_docs_used = len(user_kb_texts)
    user_kb_section = ""
    if user_kb_texts:
        user_kb_section = "\n\nUser Knowledge Base (uploaded pricing/hotel documents):\n" + "\n---\n".join(user_kb_texts) + "\n"
        sc(f"Injecting {kb_docs_used} KB document(s) into LLM prompt")
    elif not user_kb_entries:
        sc("No indexed KB documents found for this trip; proceeding without KB context")

    # Rebuild user_prompt with real-time context injected
    _client_type_line = (
        f"Client type: {_client_type_str.upper()}. Apply the corresponding service tier and itinerary style.\n"
        if _client_type_str else ""
    )

    # Build structured trip details block for formal/multi-destination requests
    _trip_detail_lines = []
    if fields.get("destinations"):
        _trip_detail_lines.append(f"Destinations (in order): {' -> '.join(fields['destinations'])}")
    elif fields.get("destination"):
        _trip_detail_lines.append(f"Destination: {fields['destination']}")
    if fields.get("route"):
        _trip_detail_lines.append(f"Route: {fields['route']}")
    if _nights_per_city:
        _trip_detail_lines.append(f"Nights per city: {', '.join(f'{c}: {n}N' for c,n in _nights_per_city.items())}")
    if fields.get("total_nights"):
        _trip_detail_lines.append(f"Total nights: {fields['total_nights']}")
    if fields.get("trip_start_date"):
        _trip_detail_lines.append(f"Travel date: {fields['trip_start_date']}")
    if fields.get("pax"):
        senior_note = f" (including {fields['seniors']} senior citizens 60+)" if fields.get("seniors") else ""
        _trip_detail_lines.append(f"Pax: {fields['pax']} adults{senior_note}")
    if _room_cfg:
        _trip_detail_lines.append(f"Room configuration: {', '.join(f'{v} {k}' for k,v in _room_cfg.items())}")
    if fields.get("hotel_category"):
        _trip_detail_lines.append(f"Hotel category: {fields['hotel_category']}")
    if _transport_pref:
        _trip_detail_lines.append(f"Transport: {_transport_pref}")
    if _driver_pref:
        _trip_detail_lines.append(f"Driver: {_driver_pref}")
    if _guide_req:
        _trip_detail_lines.append("Guide: English-speaking local guide required")
    if fields.get("walking_tolerance"):
        _trip_detail_lines.append(f"Walking tolerance: {fields['walking_tolerance']}")
    if fields.get("preferred_activities"):
        _trip_detail_lines.append(f"Preferred activities: {', '.join(fields['preferred_activities'])}")

    _trip_details_block = (
        "TRIP DETAILS:\n" + "\n".join(f"  {l}" for l in _trip_detail_lines) + "\n"
        if _trip_detail_lines else f"User request:\n{fields}\n"
    )

    _base_requirements = (
        "Requirements:\n"
        "- Return exactly one JSON object and nothing else.\n"
        + (f"- The 'days' array MUST have EXACTLY {_num_days} entries ({_total_nights_int} nights + 1 arrival/departure day). This is non-negotiable.\n" if _num_days else "")
        + "- Every day MUST have morning, afternoon, AND evening — each a detailed multi-sentence paragraph with HH:MM timings, real venue names, INR costs, and travel durations.\n"
        "- Name specific restaurants for every meal — include 1-2 signature dishes and approx cost per person.\n"
        "- Every day MUST have transport_note with the vehicle type and daily INR hire cost.\n"
        "- The itinerary_summary field must be 4-6 sentences capturing the kind of trip (theme/character) and the experience the traveller will have at this destination — sensory highlights, pace, and what makes it memorable.\n"
        "- cost_breakdown must be realistic and cover ALL days and ALL pax.\n"
        + ("- Include a full-day Ferrari World plan only when explicitly requested and destination is Abu Dhabi.\n" if ferrari_requested else "")
        + "Return a single JSON object exactly matching the schema in the system prompt."
    )
    # Include the original raw request so the LLM picks up details our extractor
    # may have missed (specific landmarks, mood, preferences, allergies, etc).
    # If formal_request_parser already stored a clean raw_text, prefer that.
    # Otherwise stitch together every user message in the session history — this
    # covers the conversational/free-text path where raw_text is never set.
    _raw_request_text = fields.get("raw_text") or ""
    if not _raw_request_text:
        _user_msgs = [
            (h.get("content") or "").strip()
            for h in session.get("history", [])
            if isinstance(h, dict) and h.get("role") == "user" and h.get("content")
        ]
        # Drop confirmation acknowledgements ("yes", "confirm", JSON blobs) so we
        # only feed the LLM substantive trip-related prose.
        _filtered = [
            m for m in _user_msgs
            if not (
                m.startswith("{") or m.startswith("[")
                or m.lower() in {"yes", "confirm", "confirmed", "ok", "okay", "go", "proceed"}
            )
        ]
        _raw_request_text = "\n---\n".join(_filtered).strip()

    _raw_request_block = (
        "ORIGINAL CLIENT REQUEST(S) — read carefully for any additional context, "
        "preferred activities, special occasions, dietary needs, mood, or other instructions "
        "that may not appear in the structured trip details above. Extract anything relevant "
        "even if it isn't in the field summary:\n"
        f"{_raw_request_text}\n\n"
    ) if _raw_request_text else ""

    # Build live price context block from real-time search results
    _live_price_block = ""
    if _live_price_ctx and _live_price_ctx.get("per_city"):
        _price_lines = ["REAL-TIME PRICE CONTEXT (use these figures for accurate cost estimation):"]
        _eur_inr = _live_price_ctx.get("eur_to_inr", 90)
        _price_lines.append(f"  EUR→INR rate: {_eur_inr:.1f}")
        for _city, _cdata in _live_price_ctx["per_city"].items():
            _ppn = _cdata.get("hotel_per_night_inr")
            _htotal = _cdata.get("hotel_total_inr")
            _nights_c = _cdata.get("nights", "?")
            _rooms_c = _cdata.get("rooms_estimated", 1)
            if _ppn:
                _price_lines.append(f"  {_city}: hotel ~INR {_ppn:,}/night/room")
            if _htotal:
                _price_lines.append(f"    → Total hotel ({_nights_c}N × {_rooms_c} room(s)): INR {_htotal:,}")
        _van_cost = _live_price_ctx.get("transport_per_day_inr")
        _meal_cost = _live_price_ctx.get("meals_per_person_per_day_inr")
        _sight_cost = _live_price_ctx.get("sightseeing_per_person_per_day_inr")
        if _van_cost:
            _price_lines.append(f"  Private van hire: ~INR {_van_cost:,}/day")
        if _meal_cost:
            _price_lines.append(f"  Meals per person/day: ~INR {_meal_cost:,}")
        if _sight_cost:
            _price_lines.append(f"  Sightseeing per person/day: ~INR {_sight_cost:,}")
        _notes = _live_price_ctx.get("notes", [])
        if _notes:
            _price_lines.append(f"  Sources: {'; '.join(_notes[:3])}")
        _price_lines.append("  NOTE: Use these INR figures in cost_breakdown; do NOT invent generic USD costs.")
        _live_price_block = "\n".join(_price_lines) + "\n"

    if kb_summary:
        user_prompt = (
            f"{_client_type_line}"
            f"{_trip_details_block}"
            f"{_raw_request_block}"
            f"{_live_price_block}"
            f"Predicted cost (total): ${predicted_cost:.2f} USD\n"
            f"Estimated costs (derived): {price_ctx}\n"
            f"Historical data (anonymized): {kb_summary}\n"
            f"City summary (from Wikipedia): {enrich.get('city_summary', 'N/A')}\n"
            f"Top attractions: {enrich.get('attractions', [])}\n"
            f"Real-time enrichment:{realtime_context}\n"
            f"{user_kb_section}"
            f"{_base_requirements}"
        )
    else:
        user_prompt = (
            f"{_client_type_line}"
            f"{_trip_details_block}"
            f"{_raw_request_block}"
            f"{_live_price_block}"
            f"Predicted cost (total): ${predicted_cost:.2f} USD\n"
            f"Estimated costs (derived): {price_ctx}\n"
            f"City summary (from Wikipedia): {enrich.get('city_summary', 'N/A')}\n"
            f"Top attractions: {enrich.get('attractions', [])}\n"
            f"Real-time enrichment:{realtime_context}\n"
            f"{user_kb_section}"
            f"{_base_requirements}"
        )

    # ── Call LLM ──
    # attractions_task and realtime_task were already awaited above — do NOT re-add them to gather.
    _app_env_chat = os.getenv("APP_ENV", "dev").strip().lower()
    if _app_env_chat == "dev":
        _llm_model = os.getenv("OLLAMA_MODEL_DEV", os.getenv("OLLAMA_MODEL", "llama3:8b"))
    else:
        _llm_model = os.getenv("OLLAMA_MODEL_PROD", os.getenv("OLLAMA_MODEL", "llama3"))
    sc(f"Calling LLM: model={_llm_model}, base_url={llm.base_url}")
    try:
        raw = await asyncio.to_thread(
            llm.generate,
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            model=_llm_model,
        )
    except Exception as e:
        logger.error("LLM call failed: %s", e)
        sc(f"LLM call exception: {e}")
        err_str = str(e)
        if "Connection refused" in err_str or "Failed to establish" in err_str or "Cannot connect" in err_str:
            hint = (
                f"Cannot connect to Ollama at {llm.base_url} — connection refused. "
                "Fix on your EC2: (1) sudo systemctl stop ollama; "
                "OLLAMA_HOST=0.0.0.0 ollama serve & — "
                "then open port 11434 in your EC2 security group inbound rules."
            )
        elif "404" in err_str:
            hint = (
                f"Ollama at {llm.base_url} returned 404 — model endpoint not found. "
                f"Run: ollama pull {_llm_model} on the server."
            )
        else:
            hint = f"Ollama at {llm.base_url} error: {e}"
        raise HTTPException(status_code=503, detail=hint)

    if not raw:
        logger.error("LLM returned empty response")
        sc("LLM returned empty response")
        raise HTTPException(status_code=503, detail=f"LLM at {llm.base_url} returned an empty response. Try: ollama pull {_llm_model}")

    hotel_prefetch_result = None
    if HOTEL_API_ENABLED and hotel_task is not None:
        try:
            hotel_prefetch_result = await asyncio.wait_for(hotel_task, timeout=10)
        except Exception:
            hotel_prefetch_result = None

    sc(f"LLM ok; attractions: {'yes' if enrich.get('attractions') else 'no'}; realtime: {'yes' if realtime_data.get('wikipedia') or realtime_data.get('attractions') else 'no'}")

    # Store raw LLM output and the prompt in the session for debugging
    # Store raw LLM output and the prompt in the session for debugging and return raw output
    try:
        session["last_llm_raw"] = raw
        session["last_llm_prompt"] = user_prompt
        session["history"].append({"role": "assistant_raw", "content": raw if isinstance(raw, str) else str(raw)})
        sc("Stored raw LLM output in session")
    except Exception:
        logger.debug("Failed to store raw llm output in session")

    # Return the raw LLM output in a single field as requested (do not attempt to parse into JSON)
    # Try to extract a JSON substring from the raw output (so we can return only the itinerary if present)
    def _strip_fences(text: str) -> str:
        t = text.strip()
        if t.startswith("```"):
            parts = t.split("\n")
            if parts and parts[0].startswith("```"):
                parts = parts[1:]
            if parts and parts[-1].startswith("```"):
                parts = parts[:-1]
            t = "\n".join(parts).strip()
        return t

    def _extract_json_substring(text: str) -> str | None:
        if not isinstance(text, str):
            return None
        t = _strip_fences(text)
        start = t.find("{")
        if start == -1:
            return None
        depth = 0
        for i in range(start, len(t)):
            if t[i] == "{":
                depth += 1
            elif t[i] == "}":
                depth -= 1
                if depth == 0:
                    return t[start:i+1]
        return None

    itinerary_text = None
    itinerary_obj = None
    try:
        itinerary_text = _extract_json_substring(raw)
        sc(f"Extracted JSON substring from LLM raw: {'found' if itinerary_text else 'none'}")
        if itinerary_text:
            try:
                itinerary_obj = json.loads(itinerary_text)
                sc("Parsed itinerary JSON successfully")
            except Exception as e:
                itinerary_obj = None
                sc(f"Failed to parse extracted itinerary JSON: {e}")
    except Exception as e:
        itinerary_text = None
        sc(f"Error while extracting JSON substring: {e}")
    # If LLM did not return a valid JSON itinerary, attempt a tolerant/beautified fallback
    if itinerary_obj is None:
        # Try best-effort to beautify and return the extracted JSON substring, and attach any live hotels we prefetched.
        beautified_itinerary = None
        if itinerary_text:
            try:
                # Try to parse and pretty-print if possible
                parsed_try = json.loads(itinerary_text)
                beautified_itinerary = json.dumps(parsed_try, ensure_ascii=False, indent=2)
            except Exception:
                # Could not parse fully; fall back to returning the raw extracted substring
                beautified_itinerary = itinerary_text

        # Attempt to use prefetched hotel results (if available) or fetch now (best-effort)
        hotels_for_return = []
        try:
            if HOTEL_API_ENABLED:
                if 'hotel_prefetch_result' in locals() and hotel_prefetch_result:
                    hotels_for_return = hotel_prefetch_result
                elif include_hotels and fields.get("destination"):
                    # Try a synchronous fetch (best-effort)
                    try:
                        hotels_for_return = hotel_client.search_hotels(fields.get("destination"), checkin=fields.get("checkin_date"), checkout=fields.get("checkout_date"), adults=int(fields.get("pax", 1)), limit=5)
                    except Exception:
                        hotels_for_return = []
            else:
                hotels_for_return = []
        except Exception:
            hotels_for_return = []

        # Enrich hotels with USD/INR as in debug endpoint
        enriched_hotels = []
        for h in (hotels_for_return or []):
            try:
                price = h.get("price_per_night")
                cur = (h.get("currency") or "USD").upper()
                usd = None
                inr = None
                if price is not None:
                    try:
                        usd = price_engine.convert_to_usd(float(price), cur)
                    except Exception:
                        usd = None
                    try:
                        inr_per_usd = 1.0 / float(EXCHANGE_RATES.get("INR_USD", 0.012))
                        inr = round((usd or 0.0) * inr_per_usd, 2) if usd is not None else None
                    except Exception:
                        inr = None
                enriched_hotels.append({
                    "name": h.get("name", "Hotel"),
                    "price_per_night": price,
                    "currency": cur,
                    "price_per_night_usd": usd,
                    "price_per_night_in_inr": (f"₹{inr:,}" if inr is not None else None),
                })
            except Exception:
                continue
        sc(f"Built enriched_hotels for fallback response: count={len(enriched_hotels)}")

        # Return a fallback response containing the beautified itinerary and live hotel info for debugging/consumption
        session.pop("formal_request_detected", None)
        session.pop("formal_parsed", None)
        _sync_chat_to_store()
        return {
            "session_id": sid,
            "itinerary_beautified": beautified_itinerary,
            "hotels": enriched_hotels,
            "llm_raw": raw,
            "predicted_cost": predicted_cost,
            "predicted_cost_unit": "USD",
            "fields": fields,
            "historical_data_used": bool(kb_summary),
            "kb_docs_used": kb_docs_used,
            "kb_warning": None if kb_docs_used > 0 else "No indexed documents found. Upload and index pricing/hotel documents to improve itinerary accuracy.",
        }

    # Use the LLM-provided itinerary to query live hotel prices (no mocks)
    # Determine destination, pax and nights from itinerary or session fields
    dest = itinerary_obj.get("destination") or fields.get("destination")
    pax = int(itinerary_obj.get("pax") or itinerary_obj.get("people") or fields.get("pax") or fields.get("people", 1))
    # prefer explicit duration_days in itinerary
    nights = itinerary_obj.get("duration_days") or fields.get("nights") or max(int(fields.get("duration", 1)) - 1, 1)
    try:
        nights = int(nights)
    except Exception:
        nights = max(int(fields.get("duration", 1)) - 1, 1)

    include_hotels = not fields.get("exclude_hotels", False) and not itinerary_obj.get("exclude_hotels", False) and HOTEL_API_ENABLED
    hotel_suggestions = []
    if include_hotels:
        # Build all mandatory params for RapidAPI hotel search
        hotel_params = {
            "destination": dest,
            "checkin": fields.get("checkin_date"),
            "checkout": fields.get("checkout_date"),
            "adults": pax,
            "children": fields.get("children_number", 0),
            "children_ages": fields.get("children_ages", ""),
            "units": fields.get("units", "metric"),
            "page_number": fields.get("page_number", 0),
            "categories_filter_ids": fields.get("categories_filter_ids", "class::2,class::4,free_cancellation::1"),
            "dest_type": fields.get("dest_type", "city"),
            "dest_id": fields.get("dest_id", -553173),
            "order_by": fields.get("order_by", "popularity"),
            "include_adjacency": fields.get("include_adjacency", True),
            "room_number": fields.get("room_number", 1),
            "filter_by_currency": fields.get("filter_by_currency", "AED"),
            "locale": fields.get("locale", "en-gb"),
            "limit": 5,
        }
        sc(f"Hotel API request params: {hotel_params}")
        try:
            hotel_suggestions = hotel_client.search_hotels(
                destination=hotel_params["destination"],
                checkin=hotel_params["checkin"],
                checkout=hotel_params["checkout"],
                adults=hotel_params["adults"],
                children=hotel_params["children"],
                children_ages=hotel_params["children_ages"],
                units=hotel_params["units"],
                page_number=hotel_params["page_number"],
                categories_filter_ids=hotel_params["categories_filter_ids"],
                dest_type=hotel_params["dest_type"],
                dest_id=hotel_params["dest_id"],
                order_by=hotel_params["order_by"],
                include_adjacency=hotel_params["include_adjacency"],
                room_number=hotel_params["room_number"],
                filter_by_currency=hotel_params["filter_by_currency"],
                locale=hotel_params["locale"],
                limit=hotel_params["limit"],
            )
            sc(f"Fetched {len(hotel_suggestions)} hotels for destination='{dest}' (pax={pax}, nights={nights})")
        except Exception as e:
            logger.error("Hotel API failed: %s", e)
            sc(f"Hotel API error: {e}")
            raise HTTPException(status_code=502, detail=f"Hotel API error: {e}")

    if include_hotels and not hotel_suggestions:
        raise HTTPException(status_code=502, detail="Hotel API returned no results. Ensure HOTEL_API_PROVIDER and RAPIDAPI_* env vars are configured and the provider supports the destination.")

    # Attach hotels and compute accommodation estimate in USD using PriceEngine conversions
    try:
        # store hotels in itinerary under 'hotels'
        itinerary_obj["hotels"] = hotel_suggestions
        sc(f"Attached {len(hotel_suggestions)} hotels to itinerary")

        # compute accommodation estimate using the top choice if available
        if hotel_suggestions:
            top = hotel_suggestions[0]
            p = top.get("price_per_night")
            cur = (top.get("currency") or "").upper()
            # approximate number of rooms: 1 room per 2 adults
            rooms = max(1, (pax + 1) // 2)
            if p is not None:
                try:
                    # convert to USD using PriceEngine helper
                    per_night_usd = price_engine.convert_to_usd(float(p), cur)
                    accommodation_usd = round(per_night_usd * nights * rooms, 2)
                    sc(f"Computed accommodation estimate: per_night_usd={per_night_usd} rooms={rooms} nights={nights} total_usd={accommodation_usd}")
                except Exception:
                    accommodation_usd = None
            else:
                accommodation_usd = None
        else:
            accommodation_usd = None
    except Exception:
        accommodation_usd = None

    # store updated session fields and assistant raw output
    try:
        session["last_llm_raw"] = raw
        session["last_llm_prompt"] = user_prompt
        session["history"].append({"role": "assistant_raw", "content": raw if isinstance(raw, str) else str(raw)})
    except Exception:
        logger.debug("Failed to store raw llm output in session")

    response = {
        "session_id": sid,
        "itinerary": itinerary_obj,
        "llm_raw": raw,
        "predicted_cost": predicted_cost,
        "predicted_cost_unit": "USD",
        "fields": fields,
        "historical_data_used": bool(kb_summary),
        "estimated_accommodation_usd": accommodation_usd,
        "kb_docs_used": kb_docs_used,
        "kb_warning": None if kb_docs_used > 0 else "No indexed documents found. Upload and index pricing/hotel documents to improve itinerary accuracy.",
    }

    # Generation finished. We do NOT mark the chat as "completed" automatically —
    # the user controls status (Saved / Not Started / In Progress / Completed) from
    # the Itinerary Management dropdown. Auto-marking would override their choice.

    # Clear formal request flag so follow-up messages go through the normal conv_manager flow
    session.pop("formal_request_detected", None)
    session.pop("formal_parsed", None)

    _sync_chat_to_store()
    return response


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/auth/register", tags=["Auth"])
async def api_register(req: RegisterRequest):
    """Register a new user account."""
    user = register_user(req)
    return {"success": True, "user": user}


@app.post("/api/auth/login", tags=["Auth"])
async def api_login(req: LoginRequest):
    """Login and receive a JWT token."""
    token_resp = login_user(req)
    return token_resp.model_dump()


@app.get("/api/auth/me", tags=["Auth"])
async def api_me(current_user: dict = Depends(get_current_user)):
    """Get current authenticated user info."""
    return {"user": current_user}


# ═══════════════════════════════════════════════════════════════════════════════
# CHAT SESSION MANAGEMENT ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

class NewChatRequest(BaseModel):
    chat_name: str = ""


class UpdateChatMetadataRequest(BaseModel):
    chat_name: Optional[str] = None
    itinerary_name: Optional[str] = None
    group_client_name: Optional[str] = None
    travel_dates: Optional[str] = None
    travelers_max: Optional[int] = None
    duration: Optional[str] = None
    estimated_cost: Optional[str] = None
    status: Optional[str] = None
    saved_itinerary: Optional[dict] = None


@app.post("/api/chats", tags=["Chats"])
async def api_create_chat(req: NewChatRequest, current_user: dict = Depends(get_current_user)):
    """Create a new chat session."""
    username = current_user["username"]
    chat = create_chat(username, chat_name=req.chat_name)
    # Also create an in-memory SESSIONS entry so /api/chat can use it
    SESSIONS[chat["session_id"]] = {
        "fields": {},
        "history": [],
        "sanity_checks": [],
    }
    return {"success": True, "chat": {
        "session_id": chat["session_id"],
        "chat_name": chat["chat_name"],
        "created_at": chat["created_at"],
        "metadata": chat["metadata"],
    }}


@app.get("/api/chats", tags=["Chats"])
async def api_list_chats(current_user: dict = Depends(get_current_user)):
    """List all chat sessions for the authenticated user."""
    username = current_user["username"]
    chats = list_user_chats(username)
    return {"chats": chats}


@app.get("/api/chats/{session_id}", tags=["Chats"])
async def api_get_chat(session_id: str, current_user: dict = Depends(get_current_user)):
    """Load an existing chat session by session_id (requires JWT)."""
    username = current_user["username"]
    chat = get_chat(username, session_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    # Restore in-memory session if not present (including transient flow state)
    if session_id not in SESSIONS:
        SESSIONS[session_id] = {
            "fields": chat.get("fields", {}),
            "history": chat.get("history", []),
            "sanity_checks": chat.get("sanity_checks", []),
            "pending_confirmation": chat.get("pending_confirmation"),
            "pending_formal_request": chat.get("pending_formal_request"),
            "formal_request_detected": chat.get("formal_request_detected", False),
        }
    # If the chat is paused on a confirmation card, attach the structured dict the
    # frontend needs to re-render it (otherwise the card text comes back as plain prose).
    pending = chat.get("pending_confirmation")
    if pending and pending.get("fields"):
        chat["pending_confirmation_card"] = _build_confirmation_dict(pending["fields"])
    return {"chat": chat}


@app.get("/api/chats/{session_id}/metadata", tags=["Chats"])
async def api_get_chat_metadata(session_id: str, current_user: dict = Depends(get_current_user)):
    """Get chat metadata (Chat Name, Itinerary Name, Group/Client Name, Travel Dates, Travelers MAX, Duration, Estimated Cost, Status)."""
    username = current_user["username"]
    chat = get_chat(username, session_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return {
        "session_id": session_id,
        "chat_name": chat.get("chat_name", ""),
        "metadata": chat.get("metadata", {}),
    }


@app.put("/api/chats/{session_id}/metadata", tags=["Chats"])
async def api_update_chat_metadata(session_id: str, req: UpdateChatMetadataRequest, current_user: dict = Depends(get_current_user)):
    """Update chat metadata."""
    username = current_user["username"]
    chat = get_chat(username, session_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    meta_updates = {}
    if req.chat_name is not None:
        chat["chat_name"] = req.chat_name
    if req.itinerary_name is not None:
        meta_updates["itinerary_name"] = req.itinerary_name
    if req.group_client_name is not None:
        meta_updates["group_client_name"] = req.group_client_name
    if req.travel_dates is not None:
        meta_updates["travel_dates"] = req.travel_dates
    if req.travelers_max is not None:
        meta_updates["travelers_max"] = req.travelers_max
    if req.duration is not None:
        meta_updates["duration"] = req.duration
    if req.estimated_cost is not None:
        meta_updates["estimated_cost"] = req.estimated_cost
    if req.status is not None:
        valid_statuses = {
            "saved", "not_started", "in_progress", "completed",
            "draft", "cancelled",   # legacy values kept for back-compat
        }
        if req.status not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {sorted(valid_statuses)}")
        meta_updates["status"] = req.status

    if req.saved_itinerary is not None:
        itin = req.saved_itinerary
        # Auto-fill metadata fields from the itinerary if not already provided
        if not meta_updates.get("itinerary_name"):
            meta_updates["itinerary_name"] = itin.get("title") or (f"{itin['destination']} Trip" if itin.get("destination") else None)
        if not meta_updates.get("travelers_max") and itin.get("pax"):
            try:
                meta_updates["travelers_max"] = int(itin["pax"])
            except (ValueError, TypeError):
                pass
        if not meta_updates.get("duration") and itin.get("duration_days"):
            meta_updates["duration"] = f"{itin['duration_days']} days"
        # Pull the group-total cost into metadata.estimated_cost so the
        # itinerary list shows a real number instead of "—".
        if not meta_updates.get("estimated_cost"):
            cb = itin.get("cost_breakdown") or {}
            grand = cb.get("grand_total_group") or cb.get("grand_total_per_person") or itin.get("total_cost")
            if grand:
                meta_updates["estimated_cost"] = str(grand)

    updates = {}
    if meta_updates:
        updates["metadata"] = meta_updates
    if req.chat_name is not None:
        updates["chat_name"] = req.chat_name
        updates["name_auto"] = False  # User explicitly set a name — stop auto-updates
    if req.saved_itinerary is not None:
        updates["saved_itinerary"] = req.saved_itinerary
    updated = update_chat(username, session_id, updates)
    # Mirror saved itineraries into the KB corpus.
    if req.saved_itinerary is not None:
        try:
            _persist_saved_itinerary_to_kb(
                session_id, req.saved_itinerary,
                meta_updates.get("itinerary_name") or req.chat_name,
            )
        except Exception as _ke:
            logger.warning("KB mirror of saved itinerary failed: %s", _ke)
    return {"success": True, "metadata": updated.get("metadata", {})}


def _persist_saved_itinerary_to_kb(session_id: str, itinerary: dict, name: Optional[str]) -> None:
    """Write a saved itinerary to data/itineraries/saved/ AND immediately
    reload the KB doc index so the next chat request can use this itinerary
    as retrieval context — the model 'learns' from saved trips in real time
    without requiring a backend restart."""
    if not isinstance(itinerary, dict):
        return
    saved_dir = pathlib.Path("data") / "itineraries" / "saved"
    saved_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", (name or "itinerary"))[:60].strip("_") or "itinerary"
    out_path = saved_dir / f"{session_id}-{slug}.json"
    out_path.write_text(json.dumps(itinerary, ensure_ascii=False, indent=2), encoding="utf-8")
    # Hot-reload the KB doc index so the new itinerary is searchable instantly.
    try:
        from src.services.kb.kb_loader import get_kb_loader
        get_kb_loader().reload_docs()
    except Exception as _ke:
        logger.debug("KB hot-reload after save failed (non-fatal): %s", _ke)


@app.delete("/api/chats/{session_id}", tags=["Chats"])
async def api_delete_chat(session_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a chat session."""
    username = current_user["username"]
    success = delete_chat_session(username, session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Chat not found")
    # Also remove from in-memory
    SESSIONS.pop(session_id, None)
    return {"success": True, "message": "Chat deleted"}


@app.delete("/api/chats", tags=["Chats"])
async def api_clear_all_chats(
    keep_saved: bool = True,
    current_user: dict = Depends(get_current_user),
):
    """
    Clear ALL chat history for the current user.
    - keep_saved=true (default): retains chats that have a saved itinerary so
      Itinerary Management isn't wiped accidentally.
    - keep_saved=false: wipes everything, including saved itineraries.
    """
    username = current_user["username"]
    chats = list_user_chats(username)
    deleted, kept = 0, 0
    for c in chats:
        sid = c.get("session_id")
        if not sid:
            continue
        if keep_saved and c.get("has_saved_itinerary"):
            kept += 1
            continue
        if delete_chat_session(username, sid):
            deleted += 1
            SESSIONS.pop(sid, None)
    return {"success": True, "deleted": deleted, "kept_saved": kept}


# ═══════════════════════════════════════════════════════════════════════════════
# DOCUMENT UPLOAD & RETRIEVAL ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/documents/upload", tags=["Documents"])
async def api_upload_document(
    file: UploadFile = File(...),
    session_id: str = Form(""),
    description: str = Form(""),
    current_user: dict = Depends(get_current_user),
):
    """Upload a document (PDF, DOCX, image, etc.). Optionally link to a chat session."""
    username = current_user["username"]
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(content) > 50 * 1024 * 1024:  # 50MB limit
        raise HTTPException(status_code=413, detail="File too large (max 50MB)")

    meta = await save_document(
        username=username,
        filename=file.filename or "unnamed",
        content=content,
        content_type=file.content_type or "",
        session_id=session_id,
        description=description,
    )
    return {"success": True, "document": meta}


@app.get("/api/documents", tags=["Documents"])
async def api_list_documents(
    session_id: str = "",
    current_user: dict = Depends(get_current_user),
):
    """List all documents for the authenticated user. Optionally filter by session_id."""
    username = current_user["username"]
    docs = list_documents(username, session_id=session_id)
    return {"documents": docs}


@app.get("/api/documents/{doc_id}", tags=["Documents"])
async def api_get_document(doc_id: str, current_user: dict = Depends(get_current_user)):
    """Download/load a document by ID."""
    username = current_user["username"]
    meta = get_document_meta(username, doc_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Document not found")
    file_path = get_document_path(username, doc_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="Document file missing")
    return FileResponse(
        path=file_path,
        filename=meta.get("original_filename", "document"),
        media_type=meta.get("content_type", "application/octet-stream"),
    )


@app.get("/api/documents/{doc_id}/meta", tags=["Documents"])
async def api_get_document_meta(doc_id: str, current_user: dict = Depends(get_current_user)):
    """Get document metadata without downloading the file."""
    username = current_user["username"]
    meta = get_document_meta(username, doc_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"document": meta}


@app.delete("/api/documents/{doc_id}", tags=["Documents"])
async def api_delete_document(doc_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a document."""
    username = current_user["username"]
    success = delete_document(username, doc_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"success": True, "message": "Document deleted"}


@app.get("/")
async def root():
    """Root endpoint: brief info and link to docs."""
    return JSONResponse({"message": "Travel Itinerary Chatbot API", "docs": "/docs", "health": "/health"})


@app.get("/health")
async def health():
    """Health endpoint reporting LLM, data and model status."""
    # LLM health (quick ping)
    llm_status = llm.ping()

    # Data counts
    try:
        m_for_stats = get_matcher()
        historical_count = len(m_for_stats.past_texts) if hasattr(m_for_stats, "past_texts") else 0
    except Exception:
        historical_count = 0

    # Model loaded?
    model_loaded = bool(getattr(cost_model, "model", None))

    return JSONResponse({
        "status": "ok",
        "llm": llm_status,
        "historical_itineraries_loaded": historical_count,
        "cost_model_loaded": model_loaded,
    })


@app.get("/debug/session/{session_id}")
async def debug_session(session_id: str):
    """Return the in-memory session state for debugging (fields and history).

    NOTE: This endpoint exposes session contents in cleartext; use only in development.
    """
    s = SESSIONS.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    # Do not reveal raw assistant LLM outputs if they are large; return a compact view
    compact_history = []
    for h in s.get("history", []):
        if isinstance(h, dict):
            content = h.get("content")
            if isinstance(content, str) and len(content) > 1000:
                content = content[:1000] + "..."
            compact_history.append({"role": h.get("role"), "content": content})
        else:
            compact_history.append(h)
    return JSONResponse({
        "session_id": session_id,
        "fields": s.get("fields", {}),
        "history": compact_history,
        "sanity_checks": s.get("sanity_checks", [])
    })


@app.get("/debug/llm_raw/{session_id}")
async def debug_llm_raw(session_id: str):
    """Return the last raw LLM prompt and response stored for this session (dev only)."""
    s = SESSIONS.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    raw = s.get("last_llm_raw")
    prompt = s.get("last_llm_prompt")
    if raw is None and prompt is None:
        raise HTTPException(status_code=404, detail="No LLM data recorded for this session")
    # Truncate large content for safety
    def _trunc(x):
        if x is None:
            return None
        if isinstance(x, str) and len(x) > 5000:
            return x[:5000] + "..."
        return x

    return JSONResponse({"session_id": session_id, "llm_prompt": _trunc(prompt), "llm_raw": _trunc(raw)})


@app.get("/debug/llm/{session_id}")
async def debug_llm(session_id: str):
    """Developer debug: return a beautified view of the last LLM prompt/response

    This endpoint will also attempt to extract a JSON itinerary from the raw LLM output,
    parse it, and (if possible) augment it with live hotel data from the configured
    hotel provider. The augmented itinerary is returned both as a parsed object and as
    a prettified JSON string for easy reading.
    """
    s = SESSIONS.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    raw = s.get("last_llm_raw")
    prompt = s.get("last_llm_prompt")
    if raw is None and prompt is None:
        raise HTTPException(status_code=404, detail="No LLM data recorded for this session")

    def _strip_fences(text: str) -> str:
        t = text.strip()
        if t.startswith("```"):
            parts = t.split("\n")
            if parts and parts[0].startswith("```"):
                parts = parts[1:]
            if parts and parts[-1].startswith("```"):
                parts = parts[:-1]
            t = "\n".join(parts).strip()
        return t

    def _extract_json_substring(text: str) -> str | None:
        if not isinstance(text, str):
            return None
        t = _strip_fences(text)
        start = t.find("{")
        if start == -1:
            return None
        depth = 0
        for i in range(start, len(t)):
            if t[i] == "{":
                depth += 1
            elif t[i] == "}":
                depth -= 1
                if depth == 0:
                    return t[start:i+1]
        return None

    extracted = None
    parsed = None
    beautified = None
    live_hotels = None
    try:
        extracted = _extract_json_substring(raw)
        if extracted:
            parsed = json.loads(extracted)
    except Exception:
        parsed = None

    # If we have a parsed itinerary, try to augment with live hotel data (best-effort)
    if parsed:
        try:
            # Determine whether hotels should be included (disabled when HOTEL_API_ENABLED=False)
            fields = s.get("fields", {})
            include_hotels = not fields.get("exclude_hotels", False) and not parsed.get("exclude_hotels", False) and HOTEL_API_ENABLED
            if include_hotels:
                dest = parsed.get("destination") or fields.get("destination")
                pax = int(parsed.get("pax") or parsed.get("people") or fields.get("pax") or fields.get("people", 1))
                nights = parsed.get("duration_days") or fields.get("nights") or max(int(fields.get("duration", 1)) - 1, 1)
                try:
                    nights = int(nights)
                except Exception:
                    nights = max(int(fields.get("duration", 1)) - 1, 1)

                try:
                    # Attempt live hotel search (raises if provider not configured)
                    if HOTEL_API_ENABLED:
                        hotels = hotel_client.search_hotels(dest, checkin=fields.get("checkin_date"), checkout=fields.get("checkout_date"), adults=pax, limit=5)
                    else:
                        hotels = []
                except Exception as e:
                    hotels = []
                    logger.debug("Live hotel search failed while augmenting debug itinerary: %s", e)

                # Enrich hotel records with USD and INR prices for readability
                enriched = []
                for h in hotels:
                    price = h.get("price_per_night")
                    cur = (h.get("currency") or "USD").upper()
                    usd = None
                    inr = None
                    if price is not None:
                        # convert to USD using PriceEngine
                        try:
                            usd = price_engine.convert_to_usd(float(price), cur)
                        except Exception:
                            usd = None
                        # derive INR via exchange rates (INR_USD = 1 INR -> x USD). usd -> INR = usd / (INR_USD)
                        try:
                            inr_per_usd = 1.0 / float(EXCHANGE_RATES.get("INR_USD", 0.012))
                            inr = round((usd or 0.0) * inr_per_usd, 2) if usd is not None else None
                        except Exception:
                            inr = None

                    enriched.append({
                        "name": h.get("name", "Hotel"),
                        "price_per_night": price,
                        "currency": cur,
                        "price_per_night_usd": usd,
                        "price_per_night_in_inr": (f"₹{inr:,}" if inr is not None else None),
                    })

                # attach enriched hotels into the parsed itinerary for reading convenience
                parsed["hotels"] = enriched
                live_hotels = enriched

        except Exception as e:
            logger.debug("Failed to augment parsed itinerary with live hotels: %s", e)

    # Prepare prettified string of the parsed itinerary if available
    try:
        if parsed is not None:
            beautified = json.dumps(parsed, ensure_ascii=False, indent=2)
        else:
            beautified = None
    except Exception:
        beautified = None

    def _trunc(x):
        if x is None:
            return None
        if isinstance(x, str) and len(x) > 10000:
            return x[:10000] + "..."
        return x

    return JSONResponse({
        "session_id": session_id,
        "llm_prompt": _trunc(prompt),
        "llm_raw": _trunc(raw),
        "extracted_json": extracted,
        "parsed_itinerary": parsed,
        "beautified_itinerary": beautified,
        "live_hotels": live_hotels,
    })


# ============= CLIENT MANAGEMENT ENDPOINTS =============


class Contact(BaseModel):
    full_name: str
    email: str
    phone: Optional[str] = None


class ClientRequest(BaseModel):
    company_name: str
    client_type: str  # Corporate, Leisure, MICE, DMC
    status: str = "lead"  # lead, active, inactive, prospect
    full_name: str = ""
    email: str = ""
    phone: str = ""
    secondary_contact: Optional[Contact] = None
    country: str = ""
    city: str = ""
    address: str = ""
    industry: str = "Other"  # Automotive, Technology, Finance, Hospitality, Retail, Manufacturing, Other
    lead_source: str = ""  # Website, Referral, Social Media, Cold Call, Event, etc.
    notes: str = ""

    class Config:
        json_schema_extra = {
            "example": {
                "company_name": "Acme Corp",
                "client_type": "Corporate",
                "status": "lead",
                "full_name": "John Doe",
                "email": "john@example.com",
                "phone": "+123456789",
                "secondary_contact": {"full_name": "Jane Doe", "email": "jane@example.com", "phone": "+987654321"},
                "country": "India",
                "city": "Mumbai",
                "address": "123 Main Street",
                "industry": "Technology",
                "lead_source": "Website",
                "notes": "Important client",
            }
        }


class ClientUpdateRequest(BaseModel):
    company_name: Optional[str] = None
    client_type: Optional[str] = None
    status: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    secondary_contact: Optional[Contact] = None
    country: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    industry: Optional[str] = None
    lead_source: Optional[str] = None
    notes: Optional[str] = None


@app.post("/api/clients", tags=["Clients"])
async def create_new_client(req: ClientRequest):
    """Create a new client with full details."""
    try:
        # Build primary_contact from the flat fields
        primary_contact = {
            "full_name": req.full_name,
            "email": req.email,
            "phone": req.phone,
        }
        client = create_client(
            company_name=req.company_name,
            client_type=req.client_type,
            status=req.status,
            primary_contact=primary_contact,
            country=req.country,
            city=req.city,
            address=req.address,
            industry=req.industry,
            lead_source=req.lead_source,
            notes=req.notes,
            secondary_contact=req.secondary_contact.model_dump() if req.secondary_contact else None,
        )
        return {"success": True, "client": client}
    except Exception as e:
        logger.error(f"Client creation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/clients", tags=["Clients"])
async def list_all_clients():
    """List all clients."""
    try:
        clients = list_clients()
        return {"clients": clients}
    except Exception as e:
        logger.error(f"Client listing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/clients/search", tags=["Clients"])
async def search_clients_by_query(q: str):
    """Search clients by name, email, or industry."""
    if not q:
        raise HTTPException(status_code=400, detail="Search query required")
    try:
        results = search_clients(q)
        return {"results": results}
    except Exception as e:
        logger.error(f"Client search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/clients/{client_id}", tags=["Clients"])
async def get_client_details(client_id: str):
    """Get client details by ID."""
    client = get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return {"client": client}


@app.put("/api/clients/{client_id}", tags=["Clients"])
async def update_client_details(client_id: str, req: ClientUpdateRequest):
    """Update client details (company_name, client_type, status, full_name, email, phone, secondary_contact, country, city, address, industry, lead_source, notes)."""
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    # Handle secondary_contact serialization
    if "secondary_contact" in updates and updates["secondary_contact"] is not None:
        if hasattr(updates["secondary_contact"], "model_dump"):
            updates["secondary_contact"] = updates["secondary_contact"].model_dump()
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    try:
        client = update_client(client_id, updates)
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
        return {"success": True, "client": client}
    except Exception as e:
        logger.error(f"Client update failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/clients/{client_id}", tags=["Clients"])
async def delete_client_record(client_id: str):
    """Delete a client."""
    try:
        success = delete_client(client_id)
        if not success:
            raise HTTPException(status_code=404, detail="Client not found")
        return {"success": True, "message": "Client deleted"}
    except Exception as e:
        logger.error(f"Client deletion failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/clients/{client_id}/itineraries", tags=["Clients"])
async def get_client_itinerary_list(client_id: str):
    """Get all itineraries linked to a client."""
    client = get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    itineraries = get_client_itineraries(client_id)
    return {"client_id": client_id, "itineraries": itineraries}


@app.post("/api/clients/{client_id}/itineraries")
async def link_itinerary_to_client(client_id: str, itinerary_id: str):
    """Link an itinerary to a client."""
    try:
        client = add_itinerary_to_client(client_id, itinerary_id)
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
        return {"success": True, "message": "Itinerary linked to client", "client": client}
    except Exception as e:
        logger.error(f"Itinerary linking failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


class SaveItineraryRequest(BaseModel):
    session_id: Optional[str] = None
    itinerary: dict
    name: Optional[str] = None
    status: Optional[str] = "saved"


@app.post("/api/itineraries", tags=["Itineraries"])
async def api_save_itinerary(req: SaveItineraryRequest, current_user: dict = Depends(get_current_user)):
    """
    Save an itinerary against a chat session. Creates the chat record if no
    session_id is provided. Returns the session_id and the saved itinerary so
    the frontend can immediately list it under /api/itineraries.
    """
    username = current_user["username"]
    sid = req.session_id
    if not sid:
        sid = str(uuid.uuid4())
        upsert_chat(username, sid, {
            "chat_name": req.name or req.itinerary.get("title") or "Itinerary",
            "fields": {},
            "history": [],
        })
    name = (
        req.name
        or req.itinerary.get("title")
        or (f"{req.itinerary['destination']} Trip" if req.itinerary.get("destination") else None)
        or "Itinerary"
    )
    cb = req.itinerary.get("cost_breakdown") or {}
    grand_total = (
        cb.get("grand_total_group")
        or cb.get("grand_total_per_person")
        or req.itinerary.get("total_cost")
    )
    meta = {
        "itinerary_name": name,
        "status": req.status or "saved",
    }
    if grand_total:
        meta["estimated_cost"] = str(grand_total)
    if req.itinerary.get("pax"):
        try:
            meta["travelers_max"] = int(req.itinerary["pax"])
        except (ValueError, TypeError):
            pass
    if req.itinerary.get("duration_days"):
        meta["duration"] = f"{req.itinerary['duration_days']} days"
    if req.itinerary.get("trip_start_date"):
        meta["travel_dates"] = str(req.itinerary["trip_start_date"])
    updates = {
        "saved_itinerary": req.itinerary,
        "metadata": meta,
    }
    if name:
        updates["chat_name"] = name
    chat = update_chat(username, sid, updates)
    # Mirror the saved itinerary into data/itineraries/saved/<sid>.json so the
    # KB loader picks it up the next time it runs — letting future trips
    # benefit from this user's accumulated itinerary corpus.
    try:
        _persist_saved_itinerary_to_kb(sid, req.itinerary, name)
    except Exception as _ke:
        logger.warning("KB mirror of saved itinerary failed: %s", _ke)
    return {
        "session_id": sid,
        "saved": True,
        "itinerary_name": name,
        "itinerary": req.itinerary,
        "chat": chat,
    }


@app.get("/api/itineraries/{session_id}/download", tags=["Itineraries"])
async def api_download_itinerary_doc(
    session_id: str,
    format: str = "docx",
    current_user: dict = Depends(get_current_user),
):
    """Return the saved itinerary as a downloadable Word (.docx) document."""
    username = current_user["username"]
    chat = get_chat(username, session_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    itinerary = chat.get("saved_itinerary")
    if not itinerary:
        raise HTTPException(status_code=404, detail="No saved itinerary on this session")
    if format.lower() not in ("docx", "doc"):
        raise HTTPException(status_code=400, detail="Only docx is supported via this endpoint")

    try:
        from docx import Document
        from docx.shared import Pt, RGBColor, Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"python-docx not available: {e}")

    doc = Document()

    # ── Title ─────────────────────────────────────────────────────────────
    title_text = (
        itinerary.get("title")
        or (f"{itinerary['destination']} Trip" if itinerary.get("destination") else "Itinerary")
    )
    h = doc.add_heading(title_text, level=0)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # ── Metadata block ────────────────────────────────────────────────────
    meta_p = doc.add_paragraph()
    meta_bits = []
    if itinerary.get("destination"):    meta_bits.append(f"Destination: {itinerary['destination']}")
    if itinerary.get("duration_days"):  meta_bits.append(f"Duration: {itinerary['duration_days']} days")
    if itinerary.get("pax"):            meta_bits.append(f"Pax: {itinerary['pax']}")
    if itinerary.get("event_type"):     meta_bits.append(f"Trip type: {itinerary['event_type']}")
    if itinerary.get("trip_start_date"): meta_bits.append(f"Start: {itinerary['trip_start_date']}")
    meta_p.add_run("  •  ".join(meta_bits)).italic = True

    # ── Summary ───────────────────────────────────────────────────────────
    summary = itinerary.get("itinerary_summary") or itinerary.get("overview")
    if summary:
        doc.add_heading("Itinerary Summary", level=1)
        doc.add_paragraph(summary)

    # ── Day-by-day ────────────────────────────────────────────────────────
    days = itinerary.get("days") or []
    if days:
        doc.add_heading("Day-by-day plan", level=1)
        for d in days:
            if not isinstance(d, dict):
                continue
            day_no = d.get("day", "")
            date_str = d.get("date", "")
            city = d.get("city", "")
            day_summary = d.get("summary", "")
            head = f"Day {day_no}"
            if date_str: head += f" — {date_str}"
            if city:     head += f" ({city})"
            doc.add_heading(head, level=2)
            if day_summary:
                p = doc.add_paragraph()
                p.add_run(day_summary).italic = True

            for label_key in (("Morning", "morning"), ("Afternoon", "afternoon"), ("Evening", "evening")):
                label, key = label_key
                content = d.get(key)
                if not content:
                    continue
                p = doc.add_paragraph()
                run = p.add_run(f"{label}: ")
                run.bold = True
                p.add_run(str(content))

            if d.get("transport_note"):
                p = doc.add_paragraph()
                run = p.add_run("Transport: ")
                run.bold = True
                p.add_run(str(d["transport_note"]))

            hotel = d.get("hotel") or {}
            if hotel.get("name"):
                p = doc.add_paragraph()
                run = p.add_run("Hotel: ")
                run.bold = True
                p.add_run(
                    f"{hotel.get('name','')} ({hotel.get('category','')}) — {hotel.get('area','')}"
                )

    # ── Hotels list ───────────────────────────────────────────────────────
    hotels = itinerary.get("hotels") or []
    if hotels:
        doc.add_heading("Hotels", level=1)
        for h in hotels:
            if isinstance(h, dict):
                doc.add_paragraph(
                    f"{h.get('city','')}: {h.get('name','')} ({h.get('category','')}) — "
                    f"{h.get('price_per_night_inr','')} per night",
                    style="List Bullet",
                )

    # ── Cost breakdown ────────────────────────────────────────────────────
    cb = itinerary.get("cost_breakdown") or {}
    if cb:
        doc.add_heading("Cost breakdown", level=1)
        for k, v in cb.items():
            if v in (None, "", []):
                continue
            p = doc.add_paragraph(style="List Bullet")
            run = p.add_run(f"{k.replace('_', ' ').title()}: ")
            run.bold = True
            p.add_run(str(v))

    # ── Inclusions / Exclusions / Guidelines ──────────────────────────────
    for heading, key in (
        ("Inclusions", "inclusions"),
        ("Exclusions", "exclusions"),
        ("Important guidelines", "important_guidelines"),
    ):
        items = itinerary.get(key) or []
        if items:
            doc.add_heading(heading, level=1)
            for it in items:
                doc.add_paragraph(str(it), style="List Bullet")

    # ── Notes ─────────────────────────────────────────────────────────────
    if itinerary.get("notes"):
        doc.add_heading("Notes", level=1)
        doc.add_paragraph(str(itinerary["notes"]))

    # Stream the file back
    import io
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", title_text)[:60].strip("_") or "itinerary"
    headers = {
        "Content-Disposition": f'attachment; filename="{safe_name}.docx"',
    }
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers,
    )


@app.get("/api/itineraries", tags=["Itineraries"])
async def api_list_itineraries(current_user: dict = Depends(get_current_user)):
    """
    List every saved itinerary for the current user — flat shape with the
    embedded itinerary JSON included so the frontend can render previews
    without a second fetch per row.
    """
    username = current_user["username"]
    chats = list_user_chats(username)
    saved = [c for c in chats if c.get("has_saved_itinerary")]
    out = []
    for c in saved:
        full = get_chat(username, c["session_id"]) or {}
        meta = full.get("metadata", {}) or {}
        itin = full.get("saved_itinerary") or {}
        cb = (itin.get("cost_breakdown") or {}) if isinstance(itin, dict) else {}
        # Prefer the explicit metadata.estimated_cost; fall back to the saved
        # itinerary's grand_total_group → grand_total_per_person → total_cost
        # so itineraries saved before the cost-mapping was added still display.
        cost = (
            meta.get("estimated_cost")
            or cb.get("grand_total_group")
            or cb.get("grand_total_per_person")
            or itin.get("total_cost")
            or ""
        )
        out.append({
            "session_id": c["session_id"],
            "name": meta.get("itinerary_name") or c.get("chat_name") or "Itinerary",
            "status": meta.get("status") or "saved",
            "destination": itin.get("destination"),
            "duration_days": itin.get("duration_days"),
            "pax": itin.get("pax"),
            "travel_dates": meta.get("travel_dates") or itin.get("trip_start_date") or "",
            "estimated_cost": str(cost) if cost else "",
            "itinerary": itin or None,
            "created_at": c.get("created_at"),
            "updated_at": c.get("updated_at"),
        })
    out.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return {"itineraries": out, "count": len(out)}


@app.get("/api/itineraries/templates/destinations")
async def get_available_destinations():
    """Get list of destinations with real-world itinerary templates."""
    try:
        destinations = list_available_destinations()
        return {"destinations": destinations}
    except Exception as e:
        logger.error(f"Destinations listing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/itineraries/templates/{destination}")
async def get_template_itinerary(destination: str, duration: str = None):
    """Get a real-world itinerary template for a destination."""
    try:
        template = get_itinerary_template(destination, duration)
        if not template:
            raise HTTPException(status_code=404, detail=f"No template found for {destination}")
        return {"template": template}
    except Exception as e:
        logger.error(f"Template retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/itinerary-files", tags=["Admin"])
async def list_itinerary_files():
    """List all files in the data/itineraries directory (admin use)."""
    from pathlib import Path
    itinerary_dir = Path("data/itineraries")
    files = []
    if itinerary_dir.exists():
        for f in sorted(itinerary_dir.iterdir()):
            if f.is_file() and not f.name.startswith("."):
                stat = f.stat()
                files.append({
                    "doc_id": f.name,
                    "filename": f.name,
                    "file_size": stat.st_size,
                    "uploaded_at": datetime.fromtimestamp(stat.st_mtime).isoformat() + "Z",
                    "kb_status": "indexed",
                    "source": "library",
                })
    return {"documents": files, "total": len(files)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
 
