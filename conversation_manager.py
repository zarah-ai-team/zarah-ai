"""conversation_manager.py
Handles multi-turn conversation and collecting required fields.

Field extraction strategy (tried in order, first that returns a non-empty
dict wins for the corresponding key):
  1. LangChain + Ollama structured output  (intelligent — handles nuance)
  2. country-state-city DB destination scan (definitive for place names)
  3. Regex heuristics                       (fast fallback for numbers / words)
"""
import os
import re
from typing import Dict, Any
from llm_field_extractor import extract_fields_via_llm
from itinerary_database import list_available_destinations
try:
    from destination_resolver import detect_route as _resolver_detect_route, is_known_destination as _resolver_is_known
except Exception:
    _resolver_detect_route = None
    _resolver_is_known = None

try:
    from langchain_field_extractor import extract_fields as _langchain_extract
except Exception:
    _langchain_extract = None

# Whether LangChain extraction runs by default. Disabled when set to "0"/"false"
# (useful for tests, or if the local LLM is too slow for per-message extraction).
_USE_LANGCHAIN = os.getenv("USE_LANGCHAIN_EXTRACTOR", "1").lower() not in ("0", "false", "no")


# Heuristic blacklist of common non-location nouns/verbs/adjectives that may
# appear capitalized at the start of a travel query but are NOT destinations.
# Without this list a sentence like "Estimate the total trip cost..." extracts
# "Estimate" as the destination.
_DEST_BLACKLIST = set([
    # meal / lodging / transport nouns
    "meal", "breakfast", "lunch", "dinner", "snack",
    "plan", "itinerary", "booking", "schedule", "hotel", "flight",
    "taxi", "cab", "car", "vehicle", "bus", "train",
    # group nouns
    "family", "party", "team", "group", "couple", "client", "customer",
    "guest", "traveler", "traveller", "person", "people", "adult", "adults",
    # verbs commonly used at sentence start
    "estimate", "calculate", "compute", "summarize", "summarise",
    "analyze", "analyse", "review", "optimize", "optimise",
    "build", "generate", "create", "make", "prepare", "draft", "design",
    "suggest", "recommend", "propose", "show", "tell", "give", "provide",
    "explain", "describe", "list", "share", "draft", "find",
    "include", "exclude", "skip", "remove", "add",
    # common adjectives/adverbs
    "total", "rough", "approximate", "average", "minimum", "maximum",
    "luxury", "budget", "midrange", "premium", "deluxe",
    "corporate", "leisure", "holiday", "vacation", "honeymoon",
    "domestic", "international", "private", "shared",
    # generic travel nouns
    "trip", "travel", "journey", "tour", "destination", "route",
    "cost", "price", "budget", "expense", "fee",
    "sightseeing", "activity", "activities", "experience",
    # time / date words
    "morning", "afternoon", "evening", "night", "midnight", "noon",
    "today", "tomorrow", "yesterday", "tonight",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
    # filler / pronouns
    "this", "that", "these", "those", "here", "there",
    "please", "kindly", "thanks", "thank",
])

# Curated set of common travel destinations (cities) we accept as single-word
# answers when neither pycountry nor the template DB has them. Lowercase keys.
_KNOWN_CITIES = set([
    # Middle East
    "dubai", "abu dhabi", "sharjah", "ajman", "doha", "muscat", "manama",
    "riyadh", "jeddah", "mecca", "medina", "amman", "petra", "beirut",
    "cairo", "luxor", "alexandria", "istanbul", "ankara", "cappadocia",
    # Asia
    "tokyo", "kyoto", "osaka", "hiroshima", "sapporo",
    "seoul", "busan", "jeju", "beijing", "shanghai", "guangzhou", "hong kong",
    "taipei", "bangkok", "phuket", "chiang mai", "krabi", "pattaya",
    "singapore", "kuala lumpur", "penang", "langkawi",
    "bali", "jakarta", "yogyakarta", "lombok",
    "hanoi", "ho chi minh", "halong bay", "danang",
    "manila", "cebu", "boracay", "palawan",
    "siem reap", "phnom penh", "luang prabang", "vientiane",
    "kathmandu", "pokhara", "thimphu", "paro",
    "colombo", "kandy", "galle", "male", "maldives",
    # India
    "mumbai", "delhi", "bangalore", "chennai", "kolkata", "hyderabad",
    "pune", "ahmedabad", "jaipur", "udaipur", "jodhpur", "agra",
    "varanasi", "rishikesh", "haridwar", "amritsar", "shimla", "manali",
    "leh", "ladakh", "srinagar", "darjeeling", "gangtok",
    "goa", "kerala", "kochi", "munnar", "thekkady", "alleppey",
    "mahabalipuram", "pondicherry", "ooty", "coorg",
    # Europe
    "london", "paris", "rome", "venice", "florence", "milan", "naples",
    "madrid", "barcelona", "seville", "lisbon", "porto",
    "amsterdam", "rotterdam", "brussels", "bruges",
    "berlin", "munich", "hamburg", "frankfurt",
    "vienna", "salzburg", "zurich", "geneva", "bern", "interlaken",
    "prague", "budapest", "warsaw", "krakow",
    "athens", "santorini", "mykonos", "crete",
    "stockholm", "copenhagen", "oslo", "helsinki", "reykjavik",
    "moscow", "saint petersburg",
    "edinburgh", "dublin",
    # Americas
    "new york", "los angeles", "san francisco", "chicago", "miami", "boston",
    "seattle", "washington", "las vegas",
    "toronto", "vancouver", "montreal",
    "mexico city", "cancun", "tulum", "havana",
    "rio", "rio de janeiro", "sao paulo", "buenos aires", "santiago", "lima",
    "machu picchu", "cusco", "quito",
    # Africa
    "cape town", "johannesburg", "nairobi", "zanzibar", "marrakech",
    "casablanca", "fes", "luxor", "victoria falls",
    # Oceania
    "sydney", "melbourne", "brisbane", "perth", "auckland", "queenstown",
    # Country-shorthand often used as destination
    "uae", "oman", "bahrain", "qatar", "saudi arabia", "kuwait", "jordan",
    "lebanon", "egypt", "japan", "thailand", "vietnam", "malaysia", "indonesia",
    "korea", "china", "india", "nepal", "bhutan", "sri lanka",
    "italy", "france", "spain", "portugal", "germany", "switzerland",
    "austria", "greece", "turkey", "egypt", "morocco", "kenya",
    "australia", "new zealand", "usa", "canada", "mexico", "brazil",
    "argentina", "chile", "peru",
])


def _is_known_destination(name: str) -> bool:
    """Return True if the given name matches a known destination or country.

    Uses the country-state-city DB via destination_resolver when available;
    otherwise falls back to pycountry / template DB / curated city list.
    """
    if not name or not isinstance(name, str):
        return False
    n = name.strip()
    if not n:
        return False
    # Authoritative source first: country-state-city DB (~250 countries + ~5k
    # states/regions + ~147k cities).
    if _resolver_is_known is not None:
        try:
            if _resolver_is_known(n):
                return True
        except Exception:
            pass

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

    # Curated city/country list — accepts well-known destinations even when
    # the template DB / pycountry don't have them.
    if n.lower() in _KNOWN_CITIES:
        return True

    # Multi-word: more likely a place (e.g., "New York", "Abu Dhabi"), but
    # still reject if every word is a blacklisted noun/verb.
    if len(n.split()) >= 2:
        words = [w.lower() for w in n.split()]
        if all(w in _DEST_BLACKLIST for w in words):
            return False
        if any(w in _DEST_BLACKLIST for w in words):
            # Mixed bag like "Estimate Total" — reject; valid multi-word
            # destinations rarely contain blacklisted verbs/adjectives.
            return False
        return True

    # Single-word: be CONSERVATIVE. Without a hit from pycountry, the template
    # DB, or the curated _KNOWN_CITIES list, we don't accept random capitalised
    # words. This prevents "Estimate", "Calculate", "Suggest", etc. from being
    # treated as destinations.
    return False

# Only these 4 fields are truly required — everything else is inferred or optional
REQUIRED_FIELDS = [
    "destination",
    "duration",
    "pax",
    "event_type",
]

PROMPTS = {
    "destination": "Where are we heading? A country (e.g. 'Japan'), a city (e.g. 'Tokyo'), or a multi-city route ('Dubai → Abu Dhabi') all work — I'll plan a smart multi-city itinerary if you only give a country.",
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
        """Extract fields using LangChain LLM (if available) + DB resolver + regex."""
        text_l = text.lower()
        found: Dict[str, Any] = {}

        # ── 1. LangChain LLM extraction (intelligent, schema-validated) ──
        # Skip on very short messages (single words, "yes", numeric replies)
        # — regex/db are faster and just as good for those.
        if _USE_LANGCHAIN and _langchain_extract is not None and len(text.split()) >= 3:
            try:
                lc = _langchain_extract(text) or {}
                for k, v in lc.items():
                    if v in (None, "", []):
                        continue
                    found[k] = v
            except Exception:
                pass

        # ── 2. Database-backed destination + route detection (preferred) ──
        # Uses country-state-city to find ALL destinations mentioned anywhere
        # in the query. Sets `destination` to the first one and `destinations`
        # to the full ordered list when multiple cities/countries are detected.
        if _resolver_detect_route is not None:
            try:
                _route = _resolver_detect_route(text)
                if _route.get("primary"):
                    found["destination"] = _route["primary"]
                if _route.get("is_multi"):
                    found["destinations"] = _route["destinations"]
                    found["route"] = _route["route_str"]
                if _route.get("kind") in ("country", "city", "mixed"):
                    found["destination_kind"] = _route["kind"]
            except Exception:
                pass
        # Skip the legacy regex destination detectors entirely when the DB-backed
        # resolver above already produced a result — its output is authoritative
        # and order-correct.
        _skip_legacy_dest = "destination" in found

        # Destination patterns: prefer "to <CapitalizedCity>" / "in <City>" / "at <City>".
        # Stop at any non-letter (digit, punctuation, "for", "in", "during", "from", "next").
        # The previous regex used [A-Za-z\s]+? which choked on "to Singapore in March 2026"
        # because 2026 breaks the char class — the engine then failed to capture anything
        # OR captured way too much.
        _STOP_WORDS = r"for|in|on|during|from|with|including|next|this|that|by|over|across"
        if not _skip_legacy_dest:
            for pat in (
                rf"\bto\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){{0,2}})\b(?:\s+(?:{_STOP_WORDS})\b|[,\.\d]|$)",
                rf"\b(?:in|at|visit|visiting)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){{0,2}})\b(?:\s+(?:{_STOP_WORDS})\b|[,\.\d]|$)",
                # Acronyms (UAE, USA, UK) after to/in/at/for/visit
                r"\b(?:to|in|at|for|visit|visiting)\s+([A-Z]{2,5})\b",
                # Lowercase fallback (e.g. user types "to japan")
                r"\bto\s+([a-z][a-z]{2,}(?:\s+[a-z][a-z]{2,}){0,2})\b(?:\s+for\b|[,\.\d]|$)",
            ):
                m = re.search(pat, text)
                if m:
                    raw = m.group(1).strip().strip(".,")
                    # Preserve all-caps acronyms (UAE, USA, UK) — don't title-case them
                    dest = raw if raw.isupper() else raw.title()
                    if dest and _is_known_destination(dest):
                        found["destination"] = dest
                        break

        # Standalone Capitalized fallback — pick the FIRST capitalized phrase that looks
        # like a known destination (cities tend to appear early in a request).
        if "destination" not in found:
            caps = re.findall(r"\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){0,2})\b", text)
            stopwords = {
                "the", "for", "and", "plan", "please", "book", "i", "we", "our",
                "prepare", "include", "budget", "meal", "marina", "universal",
                "skypark", "studios", "sands", "bay", "march", "april", "may",
                "june", "july", "august", "september", "october", "november",
                "december", "january", "february",
            }
            if caps:
                for c in caps:
                    parts = [p.lower() for p in c.split()]
                    # Skip if every word is a stopword
                    if all(p in stopwords for p in parts):
                        continue
                    if len(c) > 2 and _is_known_destination(c):
                        found["destination"] = c.strip()
                        break

        # ── Duration / nights ──────────────────────────────────────────────
        # Combined "4N/5D", "5D/4N", "4D 3N", "3N4D" formats (DMC shorthand)
        combo = re.search(
            r"(\d+)\s*[Nn]\s*[/\\\-\s]*\s*(\d+)\s*[Dd]\b|(\d+)\s*[Dd]\s*[/\\\-\s]*\s*(\d+)\s*[Nn]\b",
            text,
        )
        if combo:
            if combo.group(1) and combo.group(2):
                found["nights"]   = int(combo.group(1))
                found["duration"] = int(combo.group(2))
            elif combo.group(3) and combo.group(4):
                found["duration"] = int(combo.group(3))
                found["nights"]   = int(combo.group(4))
        # Plain '5 nights' / '5-night' / 'five nights'
        m = re.search(r"(\d+)\s*[-]?\s*nights?\b", text_l)
        if m:
            found.setdefault("nights", int(m.group(1)))
        m = re.search(r"(\d+)\s*[-]?\s*days?\b", text_l)
        if m:
            found.setdefault("duration", int(m.group(1)))
        # Word-number variants ("five nights", "ten days")
        _word_nums = {
            "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
            "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
        }
        for w, n in _word_nums.items():
            if re.search(rf"\b{w}\s+nights?\b", text_l):
                found.setdefault("nights", n)
            if re.search(rf"\b{w}\s+days?\b", text_l):
                found.setdefault("duration", n)
        # 'a week' / 'one week' / '2 weeks' → 7-day multiples
        wk = re.search(r"\b(\d+|a|one|two|three|four)\s*[-]?\s*weeks?\b", text_l)
        if wk:
            wmap = {"a": 1, "one": 1, "two": 2, "three": 3, "four": 4}
            n = wmap.get(wk.group(1), None)
            if n is None:
                try: n = int(wk.group(1))
                except Exception: n = None
            if n:
                found.setdefault("nights", n * 7)
                found.setdefault("duration", n * 7 + 1)
        # 'long weekend' → 3 nights
        if re.search(r"\blong\s+weekend\b", text_l):
            found.setdefault("nights", 3)
            found.setdefault("duration", 4)

        # ── Pax / travellers ───────────────────────────────────────────────
        # Standard "N pax / people / persons / guests / passengers / travellers / travelers / adults / members"
        m = re.search(r"\b(\d+)\s+(?:pax|people|persons|guests|passengers|travell?ers|adults|members|seats)\b", text_l)
        if m:
            found["pax"] = int(m.group(1))
        # "for N" / "for a group of N" / "group of N" / "party of N" / "family of N"
        if "pax" not in found:
            m = re.search(r"(?:group|party|family|team|batch)\s+of\s+(\d+)", text_l)
            if m:
                found["pax"] = int(m.group(1))
        if "pax" not in found:
            m = re.search(r"\bfor\s+a?\s*group\s+of\s+(\d+)", text_l)
            if m:
                found["pax"] = int(m.group(1))
        # "we are N" / "we're N" / "N of us" / "N of them"
        if "pax" not in found:
            m = re.search(r"(?:we(?:'re|\s+are)|us(?:\s+being)?|there\s+are)\s+(\d+)", text_l)
            if m:
                found["pax"] = int(m.group(1))
        if "pax" not in found:
            m = re.search(r"\b(\d+)\s+of\s+(?:us|them|our|my)\b", text_l)
            if m:
                found["pax"] = int(m.group(1))
        # "couple" or "honeymoon couple" → 2
        if "pax" not in found and re.search(r"\bcouple\b", text_l):
            found["pax"] = 2
        # "solo" → 1
        if "pax" not in found and re.search(r"\bsolo\s+(?:trip|travel|traveller|traveler)?\b", text_l):
            found["pax"] = 1
        # Word numbers + travel noun
        if "pax" not in found:
            for w, n in _word_nums.items():
                if re.search(rf"\b{w}\b\s+(pax|people|persons|guests|passengers|travell?ers|adults|members|of\s+us)", text_l):
                    found["pax"] = n
                    break

        # budget per person — must include either a currency prefix (INR/USD/AED/EUR/$)
        # OR a per-person suffix (per person / pp / each / /person). Otherwise we'd
        # false-positive on bare numbers like "10 days" or "5 nights".
        m = re.search(
            r"(INR|USD|AED|EUR|\$)\s*(\d{2,7}(?:[\.,]\d{1,3})?)(?:\s*(k|thousand))?",
            text, re.IGNORECASE,
        )
        if m:
            curr, amt, mult = m.group(1), m.group(2), m.group(3)
            try:
                amt_f = float(amt.replace(",", ""))
                if mult and mult.lower().startswith("k"):
                    amt_f *= 1000
                found["budget_per_person"] = amt_f
                curr_norm = curr.upper().replace("$", "USD")
                found["budget_currency"] = curr_norm
            except Exception:
                pass
        else:
            m_pp = re.search(
                r"(\d{3,7}(?:[\.,]\d{1,3})?)\s*(?:per\s+person|pp|each|/person)",
                text, re.IGNORECASE,
            )
            if m_pp:
                try:
                    found["budget_per_person"] = float(m_pp.group(1).replace(",", ""))
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
            dest = parsed.get("destination")
            # If the parser couldn't find a destination, only accept the raw message
            # as the destination if it LOOKS LIKE a single short answer (1-4 words,
            # no punctuation, no digits). Long pasted requests get rejected here so
            # they fall through to the LLM-assisted extraction below — preventing the
            # whole paragraph from being mistakenly stored as the destination.
            if not dest:
                words = msg_stripped.split()
                looks_like_short_answer = (
                    1 <= len(words) <= 4
                    and len(msg_stripped) <= 40
                    and not re.search(r"[\.\d!?]", msg_stripped)
                )
                if looks_like_short_answer:
                    dest = msg_stripped.strip(",.!?")
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
