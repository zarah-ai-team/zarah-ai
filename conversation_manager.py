"""conversation_manager.py
Handles multi-turn conversation and collecting required fields.
"""
import re
from typing import Dict, Any
from llm_field_extractor import extract_fields_via_llm
from itinerary_database import list_available_destinations


# Heuristic blacklist of common non-location nouns that may be capitalized
_DEST_BLACKLIST = set([
    "meal", "breakfast", "lunch", "dinner", "plan", "itinerary", "booking", "schedule", "hotel",
    "flight", "taxi", "car", "family", "party", "team", "group",
])


def _is_known_destination(name: str) -> bool:
    """Return True if the given name matches a known destination or country.

    Uses `list_available_destinations()` and, if available, `pycountry` to
    validate city/country names. Falls back to a heuristic based on word count
    and blacklist to avoid false positives like 'meal'.
    """
    if not name or not isinstance(name, str):
        return False
    n = name.strip()
    if not n:
        return False

    # exact or substring match against our itinerary templates
    try:
        for d in list_available_destinations():
            if n.lower() in d.lower() or d.lower() in n.lower():
                return True
    except Exception:
        pass

    # Try to use pycountry to detect country names if available
    try:
        import pycountry

        for c in pycountry.countries:
            if n.lower() == c.name.lower() or n.lower() in getattr(c, "official_name", "").lower() or n.lower() in c.alpha_2.lower():
                return True
    except Exception:
        # pycountry not installed; continue with heuristics
        pass

    # Heuristic rules: multi-word names are likely places (e.g., 'New York')
    if len(n.split()) >= 2:
        # but still avoid blacklisted nouns
        if n.lower() in _DEST_BLACKLIST:
            return False
        return True

    # Single-word: must be longer than 3 letters and not a common noun
    if len(n) <= 3:
        return False
    if n.lower() in _DEST_BLACKLIST:
        return False
    return True

# Only these 4 fields are truly required — everything else is inferred or optional
REQUIRED_FIELDS = [
    "destination",
    "duration",
    "pax",
    "event_type",
]

PROMPTS = {
    "destination": "Where are we heading? Let me know the destination — a city, country, or multi-city route like Dubai → Abu Dhabi.",
    "duration":    "How long is the trip? For example: 5 nights, 7 days, or 4N/5D.",
    "pax":         "How many travelers will be joining? Just the number is fine — for example: 20 pax, or 2 adults.",
    "event_type":  "What kind of trip is this? For example: leisure holiday, corporate offsite, incentive trip, MICE conference, honeymoon, or family vacation.",
}

# Maps common phrases → normalised event_type + auto-fills client_type
_EVENT_ALIASES = {
    # corporate / MICE
    "team offsite":       ("team offsite",   "corporate"),
    "offsite":            ("team offsite",   "corporate"),
    "company offsite":    ("team offsite",   "corporate"),
    "team outing":        ("team outing",    "corporate"),
    "team building":      ("team building",  "corporate"),
    "executive retreat":  ("retreat",        "corporate"),
    "corporate retreat":  ("retreat",        "corporate"),
    "retreat":            ("retreat",        "corporate"),
    "incentive trip":     ("incentive",      "corporate"),
    "incentive":          ("incentive",      "corporate"),
    "conference":         ("conference",     "mice"),
    "seminar":            ("conference",     "mice"),
    "summit":             ("conference",     "mice"),
    "annual meet":        ("conference",     "corporate"),
    "annual meeting":     ("conference",     "corporate"),
    "mice":               ("conference",     "mice"),
    "b2b":                ("conference",     "corporate"),
    "corporate event":    ("corporate",      "corporate"),
    "business trip":      ("business",       "corporate"),
    "business travel":    ("business",       "corporate"),
    # leisure
    "leisure":            ("leisure",        "leisure"),
    "family vacation":    ("leisure",        "leisure"),
    "family trip":        ("leisure",        "leisure"),
    "getaway":            ("leisure",        "leisure"),
    "holiday":            ("leisure",        "leisure"),
    "vacation":           ("leisure",        "leisure"),
    "sightseeing":        ("leisure",        "leisure"),
    "backpacking":        ("adventure",      "leisure"),
    "adventure":          ("adventure",      "leisure"),
    "solo trip":          ("leisure",        "leisure"),
    "weekend trip":       ("leisure",        "leisure"),
    "road trip":          ("leisure",        "leisure"),
    # romance
    "honeymoon":          ("honeymoon",      "leisure"),
    "anniversary":        ("anniversary",    "leisure"),
    "romantic":           ("honeymoon",      "leisure"),
    "couples trip":       ("honeymoon",      "leisure"),
    # social
    "wedding":            ("wedding",        "leisure"),
    "destination wedding":("wedding",        "leisure"),
    "birthday":           ("celebration",    "leisure"),
    "celebration":        ("celebration",    "leisure"),
    "reunion":            ("reunion",        "leisure"),
}


class ConversationManager:
    def __init__(self):
        self.required = list(REQUIRED_FIELDS)

    def detect_fields_in_text(self, text: str) -> Dict[str, Any]:
        """Try to extract fields from a free-text message using simple heuristics."""
        text_l = text.lower()
        found = {}
        # destination patterns: 'to Paris', 'in Dubai', 'at Tokyo' (avoid trailing words like 'for')
        m = re.search(r"to\s+([A-Za-z\s]+?)(?:\s+for\b|,|\.|$)", text, re.IGNORECASE)
        if not m:
            m = re.search(r"\b(?:in|at)\s+([A-Za-z\s]+?)(?:\s+for\b|,|\.|$)", text, re.IGNORECASE)
        if m:
            dest = m.group(1).strip().strip(".,")
            if dest and _is_known_destination(dest):
                found["destination"] = dest
            else:
                # ignore likely false positives
                pass

        # Also match standalone capitalized location words (City names), e.g., 'Dubai' or 'Dubai, UAE'
        if "destination" not in found:
            # Find all Capitalized phrases and prefer the last likely one (avoids 'Plan' at sentence start)
            caps = re.findall(r"\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})*)\b", text)
            if caps:
                # Filter out common verbs/nouns that might appear at sentence start
                stopwords = set(["the", "for", "and", "plan", "please", "book", "i", "we", "our"]) 
                # choose last candidate that's not a stopword and length>2
                candidate = None
                for c in reversed(caps):
                    if len(c) > 2 and c.lower() not in stopwords:
                        candidate = c.strip()
                        break
                if candidate and _is_known_destination(candidate):
                    found.setdefault("destination", candidate)
                else:
                    # Ignore capitalized words that aren't valid destinations
                    pass

        # duration (e.g., '3 days' or '3-day' or '3 days 2 nights') -> store days
        m = re.search(r"(\d+)[-\s]*days?", text_l)
        if m:
            found["duration"] = int(m.group(1))
        # nights (optional), accept hyphenated forms like '3-night'
        m2 = re.search(r"(\d+)[-\s]*nights?", text_l)
        if m2:
            found.setdefault("nights", int(m2.group(1)))

        # pax (passengers)
        m = re.search(r"(\d+)\s+(pax|people|persons|guests|passengers)", text_l)
        if m:
            found["pax"] = int(m.group(1))
        # family of N, party of N
        m = re.search(r"(?:family|party)\s+of\s+(\d+)", text_l)
        if m:
            found["pax"] = int(m.group(1))
        # 'couple' => 2
        if re.search(r"\bcouple\b", text_l):
            found.setdefault("pax", 2)
        # word numbers (one,two,three,four,five)
        word_nums = {
            'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
            'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10
        }
        for w, n in word_nums.items():
            if re.search(rf"\b{w}\b\s+(pax|people|persons|guests|passengers|of)", text_l):
                found.setdefault("pax", n)

        # budget per person with optional currency (e.g., INR 50000 or $300)
        m = re.search(r"(?:(INR|USD|AED|EUR|\$)\s*)?(\d{2,7}(?:[\.,]\d{1,2})?)\s*(?:per person|pp|each)?", text, re.IGNORECASE)
        if m:
            curr = m.group(1)
            amt = m.group(2)
            try:
                amt_f = float(amt.replace(",", ""))
                found["budget_per_person"] = amt_f
                if curr:
                    # normalize currency symbols
                    curr_norm = curr.upper().replace("$", "USD")
                    found["budget_currency"] = curr_norm
            except Exception:
                pass

        # explicit currency like '50 thousand INR' or '50k INR'
        m2 = re.search(r"(\d+(?:[\.,]\d+)?)(?:\s*(k|thousand))?\s*(INR|AED|USD|EUR)", text, re.IGNORECASE)
        if m2:
            base = float(m2.group(1).replace(",", ""))
            mult = m2.group(2)
            if mult and mult.lower().startswith("k"):
                base = base * 1000
            found["budget_per_person"] = base
            found["budget_currency"] = m2.group(3).upper()

        # event_type — check alias table first (longest match wins), then simple keywords
        matched_alias = None
        matched_len = 0
        for phrase, (ev, ct) in _EVENT_ALIASES.items():
            if phrase in text_l and len(phrase) > matched_len:
                matched_alias = (ev, ct)
                matched_len = len(phrase)
        if matched_alias:
            found["event_type"] = matched_alias[0]
            found.setdefault("client_type", matched_alias[1])

        # detect 'excluding hotels' or 'exclude hotels'
        if re.search(r"exclude(?:d|)\s+hotels|excluding\s+hotels", text_l):
            found["exclude_hotels"] = True

        # detect transport requirements like 'Lexus taxi for 12hrs' or 'Lexus taxi 12 hours'
        m = re.search(r"(Lexus|taxi|car|minivan|van)\s+(?:taxi|for)?\s*(\d{1,3})\s*(hrs|hours)?", text, re.IGNORECASE)
        if m:
            vehicle = m.group(1)
            hours = int(m.group(2))
            tr = {"vehicle": vehicle, "hours": hours}
            found.setdefault("transport_requirements", []).append(tr)

        # detect mention of Ferrari World or other named activities
        activities = []
        if re.search(r"ferrari\s*world", text, re.IGNORECASE):
            activities.append("Ferrari World")
        if re.search(r"sightseeing|must-visit|must visit|tour", text, re.IGNORECASE):
            activities.append("Sightseeing")
        if activities:
            found.setdefault("activities", []).extend(activities)

        # detect client industry from allowed set
        industries = ["automotive", "technology", "finance", "hospitality", "retail", "manufacturing", "other"]
        for ind in industries:
            if re.search(rf"\b{ind}\b", text, re.IGNORECASE):
                found["client_industry"] = ind.lower()
                break

        # detect client type — explicit mention overrides alias inference
        client_types = ["corporate", "leisure", "mice", "dmc"]
        for ct in client_types:
            if re.search(rf"\b{ct}\b", text, re.IGNORECASE):
                found["client_type"] = ct.lower()
                break

        # hotel_type — explicit keywords, otherwise will be defaulted later
        for k in ["budget", "mid-range", "mid range", "midrange", "mid", "luxury", "lux", "5-star", "5 star", "3-star", "3 star", "4-star", "4 star"]:
            if k in text_l:
                if k in ("luxury", "lux", "5-star", "5 star"):
                    found["hotel_type"] = "luxury"
                elif k in ("budget", "3-star", "3 star"):
                    found["hotel_type"] = "budget"
                else:
                    found["hotel_type"] = "mid-range"
                break

        # meals
        for k in ["vegetarian", "vegan", "kosher", "halal", "no preference"]:
            if k in text_l:
                found["meal_preference"] = k

        # detect relative date phrases for hotel search: 'next month', 'mid next month', 'start next month', 'end next month'
        if re.search(r"next\s+month", text_l):
            # capture modifiers
            if re.search(r"mid\s+next\s+month|middle\s+of\s+next\s+month", text_l):
                found.setdefault("checkin_date", "next month mid")
                found.setdefault("checkout_date", "next month mid")
            elif re.search(r"start\s+of\s+next\s+month|beginning\s+of\s+next\s+month|first\s+week", text_l):
                found.setdefault("checkin_date", "next month start")
                found.setdefault("checkout_date", "next month start")
            elif re.search(r"end\s+of\s+next\s+month|last\s+week|last\s+days", text_l):
                found.setdefault("checkin_date", "next month end")
                found.setdefault("checkout_date", "next month end")
            else:
                found.setdefault("checkin_date", "next month")
                found.setdefault("checkout_date", "next month")

        # explicit ISO date detection for checkin/checkout
        m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
        if m:
            all_dates = re.findall(r"(\d{4}-\d{2}-\d{2})", text)
            if len(all_dates) >= 2:
                found.setdefault("checkin_date", all_dates[0])
                found.setdefault("checkout_date", all_dates[1])
            else:
                found.setdefault("checkin_date", all_dates[0])

        # Natural language date formats: "3 April 2025", "April 3 2025", "3rd April 2025"
        _MONTHS = {
            "january":"01","february":"02","march":"03","april":"04","may":"05","june":"06",
            "july":"07","august":"08","september":"09","october":"10","november":"11","december":"12",
        }
        # "April 3" or "3 April" with optional year, e.g. "3 April 2025" / "April 3, 2025"
        nat_dates = re.findall(
            r"(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s*,?\s*(\d{4})?|"
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(\d{4})?",
            text, re.IGNORECASE
        )
        parsed_nat = []
        from datetime import datetime as _dt
        for grp in nat_dates:
            try:
                if grp[0]:  # "3 April 2025" format
                    day, mon, yr = grp[0], grp[1], grp[2] or str(_dt.now().year)
                else:         # "April 3 2025" format
                    mon, day, yr = grp[3], grp[4], grp[5] or str(_dt.now().year)
                mon_num = _MONTHS.get(mon.lower())
                if mon_num:
                    parsed_nat.append(f"{yr}-{mon_num}-{int(day):02d}")
            except Exception:
                pass
        # Also handle "April 3-6 2025" range
        rng = re.search(
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
            r"(\d{1,2})\s*[-–to]+\s*(\d{1,2})(?:\s*,?\s*(\d{4}))?",
            text, re.IGNORECASE
        )
        if rng:
            try:
                mon = rng.group(1)
                d1, d2 = rng.group(2), rng.group(3)
                yr = rng.group(4) or str(_dt.now().year)
                mon_num = _MONTHS.get(mon.lower())
                if mon_num:
                    parsed_nat = [f"{yr}-{mon_num}-{int(d1):02d}", f"{yr}-{mon_num}-{int(d2):02d}"]
            except Exception:
                pass
        if len(parsed_nat) >= 2:
            found.setdefault("checkin_date", parsed_nat[0])
            found.setdefault("checkout_date", parsed_nat[1])
        elif len(parsed_nat) == 1:
            found.setdefault("checkin_date", parsed_nat[0])

        # detect month name + year like 'March 2026' and set a rough checkin/checkout placeholder
        m_mon = re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b", text, re.IGNORECASE)
        if m_mon:
            mon = m_mon.group(1)
            yr = m_mon.group(2)
            # store as raw phrase; app.py will convert month names to concrete dates using duration
            found.setdefault("checkin_date", f"{mon} {yr}")
            found.setdefault("checkout_date", f"{mon} {yr}")

        return found

    def next_missing_field(self, fields: Dict[str, Any]) -> str | None:
        # Auto-fill smart defaults before checking what's missing
        self._apply_defaults(fields)

        # Only the 4 core fields are blocking
        for f in self.required:
            if f not in fields or fields.get(f) in [None, ""]:
                return f

        return None

    def _apply_defaults(self, fields: Dict[str, Any]) -> None:
        """Fill in optional fields with smart defaults so we never need to ask for them."""
        # If user said "X nights", treat it as duration so we don't re-ask
        if "nights" in fields and "duration" not in fields:
            fields["duration"] = fields["nights"]
        if "total_nights" in fields and "duration" not in fields:
            fields["duration"] = fields["total_nights"]

        # hotel_type default
        if "hotel_type" not in fields or not fields["hotel_type"]:
            fields["hotel_type"] = "mid-range"

        # client_type — infer from event_type if not set
        if "client_type" not in fields or not fields["client_type"]:
            ev = str(fields.get("event_type", "")).lower()
            corporate_signals = {"corporate", "conference", "business", "offsite", "retreat", "incentive", "mice", "seminar", "summit"}
            if any(s in ev for s in corporate_signals):
                fields["client_type"] = "corporate"
            else:
                fields["client_type"] = "leisure"

        # client_industry default
        if "client_industry" not in fields or not fields["client_industry"]:
            fields["client_industry"] = "other"

        # Auto-derive checkout_date from checkin + duration when possible
        if fields.get("checkin_date") and (not fields.get("checkout_date")):
            duration = fields.get("duration") or fields.get("nights")
            if duration:
                try:
                    from datetime import datetime as _dt2, timedelta
                    checkin_dt = _dt2.strptime(str(fields["checkin_date"]), "%Y-%m-%d")
                    fields["checkout_date"] = (checkin_dt + timedelta(days=int(duration))).strftime("%Y-%m-%d")
                except Exception:
                    pass

    def validate_field(self, field: str, value: Any) -> bool:
        # minimal validation
        if field == "duration":
            try:
                return int(value) > 0
            except Exception:
                return False
        if field == "pax":
            try:
                return int(value) > 0
            except Exception:
                return False
        if field == "budget_per_person":
            try:
                return float(value) >= 0
            except Exception:
                return False
        if field == "client_type":
            allowed = {"corporate", "leisure", "mice", "dmc"}
            return str(value).strip().lower() in allowed
        if field == "client_industry":
            allowed_inds = {"automotive", "technology", "finance", "hospitality", "retail", "manufacturing", "other"}
            return str(value).strip().lower() in allowed_inds
        return True

    def update(self, session: Dict[str, Any], message: str) -> Dict[str, Any]:
        """Process incoming user message, update session fields, and return either a prompt for more info or done signal."""
        fields = session.setdefault("fields", {})

        # Accept legacy key `trip_style` (used by formal parser) as `event_type`
        if "trip_style" in fields and "event_type" not in fields:
            try:
                fields["event_type"] = fields.get("trip_style")
            except Exception:
                pass

        # Try to parse explicit 'field: value' style
        pairs = re.findall(r"([A-Za-z_ ]+):\s*([^;\n]+)", message)
        for k, v in pairs:
            key = k.strip().lower().replace(" ", "_")
            if key in self.required:
                val = v.strip()
                if key in ["duration", "pax"]:
                    try:
                        val = int(re.search(r"\d+", val).group(0))
                    except Exception:
                        pass
                if key == "budget_per_person":
                    try:
                        val = float(re.sub(r"[^0-9.]", "", val))
                    except Exception:
                        pass
                if self.validate_field(key, val):
                    fields[key] = val

        # Heuristic detection — accept all parsed fields
        auto = self.detect_fields_in_text(message)
        for k, v in auto.items():
            if k not in fields:
                if k in ("duration", "pax"):
                    if self.validate_field(k, v):
                        fields[k] = v
                else:
                    fields[k] = v

        # Fallback destination extraction
        if "destination" not in fields:
            auto2 = self.detect_fields_in_text(message)
            if auto2.get("destination"):
                fields["destination"] = auto2["destination"]

        # Check what's still missing after extraction + defaults
        missing = self.next_missing_field(fields)
        if not missing:
            return {"need_more": False}

        # Direct answer to the currently missing field
        msg_stripped = message.strip()
        msg_lower = msg_stripped.lower()

        if missing in ("duration", "pax"):
            m = re.search(r"(\d+)", message)
            if m:
                val = int(m.group(1))
                if self.validate_field(missing, val):
                    fields[missing] = val
                    missing = self.next_missing_field(fields)
                    if not missing:
                        return {"need_more": False}

        elif missing == "event_type":
            # Accept any non-empty answer as the event type — check alias table first
            matched = None
            matched_len = 0
            for phrase, (ev, ct) in _EVENT_ALIASES.items():
                if phrase in msg_lower and len(phrase) > matched_len:
                    matched = (ev, ct)
                    matched_len = len(phrase)
            if matched:
                fields["event_type"] = matched[0]
                fields.setdefault("client_type", matched[1])
            elif msg_stripped:
                fields["event_type"] = msg_stripped
            missing = self.next_missing_field(fields)
            if not missing:
                return {"need_more": False}

        elif missing == "destination":
            parsed = self.detect_fields_in_text(message)
            dest = parsed.get("destination") or (msg_stripped if len(msg_stripped) > 2 else None)
            if dest:
                fields["destination"] = dest
                missing = self.next_missing_field(fields)
                if not missing:
                    return {"need_more": False}

        # If required fields are still missing, try one LLM-assisted extraction (best-effort)
        try:
            if missing and not session.get("_llm_tried"):
                session.setdefault("_llm_tried", True)
                # Use conversation history + latest message to give context
                history_texts = []
                for h in session.get("history", []):
                    if isinstance(h, dict):
                        history_texts.append(h.get("content", ""))
                    else:
                        history_texts.append(str(h))
                prompt_text = "\n".join(history_texts[-6:]) + "\nUser: " + message
                llm_parsed = extract_fields_via_llm(prompt_text)
                if isinstance(llm_parsed, dict) and llm_parsed:
                    for k, v in llm_parsed.items():
                        if k in fields:
                            continue
                        # Normalize types for numeric fields
                        try:
                            if k in ["pax", "duration", "nights", "rooms"]:
                                v2 = int(str(v).strip())
                            elif k == "budget_per_person":
                                v2 = float(str(v).replace(",", ""))
                            else:
                                v2 = v
                        except Exception:
                            v2 = v
                        try:
                            if k in self.required:
                                if self.validate_field(k, v2):
                                    fields[k] = v2
                            else:
                                fields[k] = v2
                        except Exception:
                            # ignore any conversion/validation failures
                            continue
                    missing = self.next_missing_field(fields)
                    if not missing:
                        return {"need_more": False}
        except Exception:
            # ensure we don't loop on LLM failures
            session.setdefault("_llm_tried", True)

        # Ask next question — use friendly, brief prompts
        prompt = PROMPTS.get(missing, f"Could you share the {missing.replace('_', ' ')}?")
        return {"need_more": True, "prompt": prompt}
