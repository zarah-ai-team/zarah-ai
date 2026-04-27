"""real_time_search.py
Real-time search integration for Wikipedia, attractions, news, Google Search, and travel pricing.
All APIs are completely free and require NO API keys.
"""
import os
import re
import requests
from functools import lru_cache
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger("real_time_search")

# Wikipedia silently returns 403 to clients with the default `python-requests/X.Y.Z`
# UA. Send a descriptive UA per their robot policy.
_WIKI_HEADERS = {
    "User-Agent": os.getenv(
        "WIKI_USER_AGENT",
        f"ZarahAI-TravelAssistant/1.0 (+https://github.com/anthropic-quickstarts; contact: {os.getenv('WIKI_CONTACT_EMAIL', 'support@zarah-ai.example')})",
    ),
    "Accept": "application/json",
}

# Overpass API rejects requests without a descriptive UA (returns 406 Not Acceptable).
# It also wants a JSON-friendly Accept and POSTs for large queries.
_OVERPASS_HEADERS = {
    "User-Agent": os.getenv(
        "OVERPASS_USER_AGENT",
        f"ZarahAI-TravelAssistant/1.0 ({os.getenv('WIKI_CONTACT_EMAIL', 'support@zarah-ai.example')})",
    ),
    "Accept": "application/json",
}

# Resolve the optional googlesearch module ONCE at import time. The pip package
# `googlesearch-python` may or may not be installed; either way we just record it
# and never spam the log on every call.
try:
    from googlesearch import search as _gsearch  # type: ignore
    _GOOGLESEARCH_AVAILABLE = True
except Exception:
    _gsearch = None
    _GOOGLESEARCH_AVAILABLE = False
    logger.info("googlesearch-python not available — relying on Tavily REST for web search.")

# Tokens that look like fields/labels/categories rather than real place names.
# We strip these from a destinations list before sending it off to enrichment so
# we don't end up Wikipedia-searching for "Date" or "Star".
_NON_PLACE_TOKENS = frozenset({
    "date", "dates", "start", "end", "from", "to", "checkin", "checkout",
    "star", "stars", "5-star", "4-star", "3-star",
    "hotel", "hotels", "resort", "resorts", "villa", "villas",
    "trip", "tour", "vacation", "holiday", "itinerary", "package",
    "lunch", "dinner", "breakfast", "meal", "meals",
    "pax", "person", "persons", "people", "traveler", "travelers",
    "duration", "nights", "days", "morning", "afternoon", "evening",
    "transport", "vehicle", "guide", "driver",
    "leisure", "corporate", "mice", "incentive", "honeymoon", "family",
})


def sanitize_place_list(places: List[str]) -> List[str]:
    """Drop obvious non-place tokens and dedupe (case-insensitive).
    Caller should treat the result as ground truth for enrichment queries.
    """
    if not places:
        return []
    out: List[str] = []
    seen = set()
    for raw in places:
        if not isinstance(raw, str):
            continue
        cand = raw.strip().strip(",.;:")
        if not cand:
            continue
        low = cand.lower()
        if low in _NON_PLACE_TOKENS:
            continue
        # Drop anything that's clearly not a place: digits, very short tokens
        if any(ch.isdigit() for ch in cand):
            continue
        if len(cand) < 2:
            continue
        key = low
        if key in seen:
            continue
        seen.add(key)
        out.append(cand)
    return out

# ============ WEB SEARCH (Tavily REST → googlesearch-python fallback) ============
# `googlesearch-python` scrapes Google's HTML and is routinely blocked by their bot
# detection — it silently returns 0 results. We route through Tavily's REST endpoint
# (the same provider used by the MCP web-search stage) when TAVILY_API_KEY is set,
# and only fall back to the scraper when it isn't.
def _tavily_rest_search(query: str, num_results: int = 5) -> List[Dict[str, str]]:
    key = os.getenv("TAVILY_API_KEY", "")
    if not key or key.startswith("tvly-YOUR"):
        return []
    try:
        r = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": key,
                "query": query,
                "max_results": max(1, min(num_results, 10)),
                "search_depth": "basic",
            },
            timeout=8,
        )
        r.raise_for_status()
        data = r.json() or {}
        out: List[Dict[str, str]] = []
        for item in (data.get("results") or [])[:num_results]:
            out.append({
                "url": item.get("url") or "",
                "title": (item.get("title") or item.get("url") or "")[:160],
                "snippet": (item.get("content") or "")[:300],
            })
        return out
    except Exception as e:
        logger.warning(f"Tavily REST search failed: {e}")
        return []


def google_search(query: str, num_results: int = 5) -> List[Dict[str, str]]:
    """
    Search the web for real-time information about a destination.
    Prefers Tavily REST (reliable, returns title/url/snippet); falls back to
    googlesearch-python only when Tavily isn't configured AND the optional
    package is installed (we silently skip when it's missing).
    """
    results = _tavily_rest_search(query, num_results=num_results)
    if results:
        return results
    if not _GOOGLESEARCH_AVAILABLE or _gsearch is None:
        # No Tavily results and no scraper installed — return empty quietly.
        return []
    try:
        scraped: List[Dict[str, str]] = []
        for url in _gsearch(query, num_results=num_results, lang="en", sleep_interval=1):
            scraped.append({"url": url, "title": url.split("/")[-1].replace("-", " ").replace("_", " ")[:80], "snippet": ""})
        return scraped
    except Exception as e:
        logger.warning(f"Web search scraper failed: {e}")
        return []


def google_destination_info(destination: str) -> Dict[str, Any]:
    """
    Get real-time Google search results for a travel destination.
    Searches for travel tips, things to do, and current info.
    """
    info = {"destination": destination, "travel_tips": [], "things_to_do": [], "general": []}
    try:
        info["travel_tips"] = google_search(f"{destination} travel tips best time to visit", num_results=3)
    except Exception as e:
        logger.debug(f"Google travel tips search failed: {e}")
    try:
        info["things_to_do"] = google_search(f"{destination} top things to do attractions", num_results=3)
    except Exception as e:
        logger.debug(f"Google things to do search failed: {e}")
    try:
        info["general"] = google_search(f"{destination} travel guide", num_results=3)
    except Exception as e:
        logger.debug(f"Google general search failed: {e}")
    return info

# ============ WIKIPEDIA SEARCH (Free) ============
def search_wikipedia(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Search Wikipedia for articles related to query.
    No API key required - uses public Wikipedia API.
    """
    try:
        url = "https://en.wikipedia.org/w/api.php"
        params = {
            'action': 'query',
            'list': 'search',
            'srsearch': query,
            'format': 'json',
            'srlimit': limit
        }
        r = requests.get(url, params=params, headers=_WIKI_HEADERS, timeout=5)
        r.raise_for_status()
        results = r.json().get('query', {}).get('search', [])
        return [{'title': r['title'], 'snippet': r['snippet']} for r in results]
    except Exception as e:
        logger.warning(f"Wikipedia search failed: {e}")
        return []


def get_wikipedia_summary(title: str) -> Dict[str, Any]:
    """
    Get detailed summary of a Wikipedia article.
    No API key required - uses public REST API.
    """
    try:
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(title)}"
        r = requests.get(url, headers=_WIKI_HEADERS, timeout=5)
        r.raise_for_status()
        data = r.json()
        return {
            'title': data.get('title'),
            'description': data.get('description'),
            'extract': data.get('extract'),
            'image': data.get('thumbnail', {}).get('source'),
            'url': data.get('content_urls', {}).get('desktop', {}).get('page')
        }
    except Exception as e:
        logger.warning(f"Wikipedia summary failed: {e}")
        return {}


# ============ NEARBY ATTRACTIONS SEARCH (Overpass API - Free) ============
def search_nearby_attractions(latitude: float, longitude: float, radius: int = 5000, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Search for nearby attractions, restaurants, museums using Overpass API (Free - no key).
    Uses OpenStreetMap data.
    
    Args:
        latitude: Location latitude
        longitude: Location longitude
        radius: Search radius in meters (default 5km)
        limit: Maximum results
    """
    try:
        # Query Overpass API for amenities and attractions
        overpass_url = "https://overpass-api.de/api/interpreter"
        
        # Build Overpass query for restaurants, museums, hotels, attractions
        query = f"""
        [bbox:{latitude-0.05},{longitude-0.05},{latitude+0.05},{longitude+0.05}];
        (
          node["tourism"="attraction"];
          node["tourism"="museum"];
          node["amenity"="restaurant"];
          node["amenity"="cafe"];
          node["amenity"="hotel"];
          node["shop"="mall"];
          way["tourism"="attraction"];
          way["tourism"="museum"];
          way["amenity"="restaurant"];
        );
        out center {limit};
        """
        
        r = requests.post(overpass_url, data={'data': query}, headers=_OVERPASS_HEADERS, timeout=8)
        r.raise_for_status()
        data = r.json()
        
        attractions = []
        for element in data.get('elements', [])[:limit]:
            tags = element.get('tags', {})
            name = tags.get('name', 'Unknown')
            category = tags.get('tourism') or tags.get('amenity') or tags.get('shop') or 'Attraction'
            lat = element.get('lat') or element.get('center', {}).get('lat')
            lon = element.get('lon') or element.get('center', {}).get('lon')
            
            if lat and lon:
                attractions.append({
                    'name': name,
                    'category': category,
                    'latitude': lat,
                    'longitude': lon,
                    'description': tags.get('description', ''),
                    'website': tags.get('website', '')
                })
        
        return attractions[:limit]
    except Exception as e:
        logger.warning(f"Nearby attractions search failed: {e}")
        return []


def search_attractions_by_name(city: str, category: str = None, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Search for attractions in a city by name using Overpass API.
    Categories: museum, restaurant, hotel, attraction, cafe, mall, park, beach, etc.
    No API key required.
    """
    try:
        overpass_url = "https://overpass-api.de/api/interpreter"
        
        # Build query based on category
        if category and category.lower() in ['museum', 'restaurant', 'hotel', 'attraction', 'cafe', 'mall', 'park', 'beach']:
            if category.lower() in ['museum', 'attraction']:
                query = f'[bbox:-90,-180,90,180];(node["tourism"="{category}"]["name"~"{city}"];way["tourism"="{category}"]["name"~"{city}"];);out center {limit};'
            else:
                query = f'[bbox:-90,-180,90,180];(node["amenity"="{category}"]["name"~"{city}"];way["amenity"="{category}"]["name"~"{city}"];);out center {limit};'
        else:
            query = f'[bbox:-90,-180,90,180];(node["name"~"{city}"];way["name"~"{city}"];node["tourism"]["name"~"{city}"];way["tourism"]["name"~"{city}"];);out center {limit};'
        
        r = requests.post(overpass_url, data={'data': query}, headers=_OVERPASS_HEADERS, timeout=8)
        r.raise_for_status()
        data = r.json()
        
        attractions = []
        for element in data.get('elements', [])[:limit]:
            tags = element.get('tags', {})
            name = tags.get('name', '')
            if city.lower() not in name.lower():
                continue
                
            attractions.append({
                'name': name,
                'category': tags.get('tourism') or tags.get('amenity') or 'Attraction',
                'latitude': element.get('lat') or element.get('center', {}).get('lat'),
                'longitude': element.get('lon') or element.get('center', {}).get('lon'),
                'description': tags.get('description', ''),
                'phone': tags.get('phone', ''),
                'website': tags.get('website', '')
            })
        
        return attractions[:limit]
    except Exception as e:
        logger.warning(f"Attractions by name search failed: {e}")
        return []


# ============ NEWS SEARCH (NewsAPI Alternative - Using RSS feeds - Free) ============
def search_news(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Search for recent news using free RSS feeds and public news sources.
    No API key required.
    """
    try:
        # Use DuckDuckGo which provides free news search
        url = "https://api.duckduckgo.com/"
        params = {
            'q': f'{query} news',
            'format': 'json',
            'no_redirect': 1,
            'skip_disambig': 1
        }
        r = requests.get(url, params=params, timeout=5)
        r.raise_for_status()
        data = r.json()
        
        news_items = []
        
        # Extract from DuckDuckGo results
        for result in data.get('Results', [])[:limit]:
            if result.get('Text'):
                news_items.append({
                    'title': result.get('FirstURL', '').split('/')[-1][:50],
                    'description': result.get('Text'),
                    'url': result.get('FirstURL'),
                    'source': result.get('FirstURL').split('/')[2] if result.get('FirstURL') else 'Unknown'
                })
        
        return news_items[:limit]
    except Exception as e:
        logger.error(f"News search failed: {e}")
        return []


def search_local_news(city: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Search for news specific to a city/location.
    No API key required.
    """
    return search_news(f"{city} local news events", limit)


# ============ INTEGRATED ENRICHMENT FUNCTION ============
def enrich_destination(destination: str) -> Dict[str, Any]:
    """
    Get comprehensive real-time data for a destination:
    - Wikipedia summary and articles
    - Top attractions nearby
    - Recent news and events
    - Google Search results (travel tips, things to do)
    
    This is the main function to call from the LLM context.
    No API keys required - everything is FREE.
    """
    enrichment = {
        'destination': destination,
        'wikipedia': {},
        'attractions': [],
        'news': [],
        'google': {},
    }
    
    try:
        # 1. Wikipedia search and summary
        wiki_results = search_wikipedia(destination, limit=3)
        if wiki_results:
            wiki_summary = get_wikipedia_summary(wiki_results[0]['title'])
            enrichment['wikipedia'] = wiki_summary
    except Exception as e:
        logger.error(f"Wikipedia enrichment failed: {e}")
    
    try:
        # 2. Attractions search
        attractions = search_attractions_by_name(destination, limit=10)
        enrichment['attractions'] = attractions
    except Exception as e:
        logger.error(f"Attractions enrichment failed: {e}")
    
    try:
        # 3. Local news
        news = search_local_news(destination, limit=5)
        enrichment['news'] = news
    except Exception as e:
        logger.error(f"News enrichment failed: {e}")

    try:
        # 4. Google Search real-time info
        google_info = google_destination_info(destination)
        enrichment['google'] = google_info
    except Exception as e:
        logger.error(f"Google search enrichment failed: {e}")
    
    return enrichment


# ============ REAL-TIME PRICING (Free APIs — No Key Required) ============

# ── Categorical price mining (date-anchored, from Tavily/Wikipedia prose) ─────
# Tavily returns prose like "5-star hotels in Phuket cost $150-250/night in April 2026,
# private taxi hire averages $80/day, meals at local restaurants $15-30 per person".
# We mine each price, look at nearby keywords (within ±60 chars), and bucket it into
# hotel/transport/meal categories. Then convert to the user's chosen currency.

# Currency-aware extraction: returns (amount, currency_code) tuples.
_AMOUNT_REGEX = re.compile(
    r"""
    (?P<curr_pre>USD|EUR|GBP|INR|AED|SGD|JPY|AUD|CAD|THB|\$|€|£|₹)?
    \s*
    (?P<amount>\d{1,3}(?:[,\s]\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)
    \s*
    (?P<curr_post>USD|EUR|GBP|INR|AED|SGD|JPY|AUD|CAD|THB|\$|€|£|₹|dollars?|euros?|pounds?|rupees?|dirhams?|baht)?
    """,
    re.IGNORECASE | re.VERBOSE,
)
_SYMBOL_TO_CODE = {"$": "USD", "€": "EUR", "£": "GBP", "₹": "INR"}
_WORD_TO_CODE = {
    "DOLLAR":"USD","DOLLARS":"USD","EURO":"EUR","EUROS":"EUR","POUND":"GBP","POUNDS":"GBP",
    "RUPEE":"INR","RUPEES":"INR","DIRHAM":"AED","DIRHAMS":"AED","BAHT":"THB",
}
_KNOWN_CODES = {"USD","EUR","GBP","INR","AED","SGD","JPY","AUD","CAD","THB"}

# Approximate USD conversion table for filtering plausibility ranges only —
# the *real* conversion uses live Frankfurter rates (see _convert_via_fx below).
_APPROX_TO_USD = {
    "USD": 1.0, "EUR": 1.09, "GBP": 1.27, "INR": 0.012, "AED": 0.272,
    "SGD": 0.74, "JPY": 0.0066, "AUD": 0.66, "CAD": 0.73, "THB": 0.028,
}

# Keyword sets for bucketing prices by surrounding context
_HOTEL_KEYWORDS    = ("hotel", "room", "night", "/night", "per night", "stay", "accommodation", "resort", "villa", "lodging")
_TRANSPORT_KEYS    = ("taxi", "car hire", "vehicle hire", "private car", "minivan", "coach", "transfer", "transport", "rental", "/day", "per day", "daily rate", "chauffeur", "driver", "tuk-tuk", "uber", "grab")
_MEAL_KEYS         = ("meal", "lunch", "dinner", "breakfast", "restaurant", "food", "cuisine", "dining", "per person", "/person", "per pax", "/pax")
_ACTIVITY_KEYS     = ("entry", "ticket", "tour", "attraction", "admission", "guided", "experience", "activity")


def _normalise_currency(curr: str) -> Optional[str]:
    if not curr:
        return None
    curr = curr.upper().strip()
    if curr in _SYMBOL_TO_CODE:
        return _SYMBOL_TO_CODE[curr]
    if curr in _WORD_TO_CODE:
        return _WORD_TO_CODE[curr]
    if curr in _KNOWN_CODES:
        return curr
    return None


def _categorise_price(text: str, start: int, end: int) -> Optional[str]:
    """Bucket a price into 'hotel' / 'transport' / 'meal' / 'activity' using
    the strongest available signal:

    1. Suffix unit attached to the number — '/night' = hotel, '/day' = transport,
       '/person' = meal-or-activity (disambiguated by tight context).
    2. Keywords in the 40 chars BEFORE the price (closest signal wins).

    Returns None when the price is genuinely ambiguous (we'd rather drop it than
    pollute the average).
    """
    after_lo = text[end:end + 22].lower()
    before_lo = text[max(0, start - 40):start].lower()

    # 1) Suffix unit — strongest signal because it's directly attached
    if any(s in after_lo for s in ("/night", "/ night", " per night", " a night", "/room", " per room")):
        return "hotel"
    if any(s in after_lo for s in ("/day", "/ day", " per day", " a day", "/daily", " daily rate")):
        return "transport"
    if any(s in after_lo for s in ("/person", "/pax", " per person", " per pax", "/head", " per head")):
        # /person is shared by meals, activities, and pax-priced transport.
        # Disambiguate via the immediately-preceding noun.
        if any(k in before_lo for k in ("meal", "lunch", "dinner", "breakfast", "restaurant", "food", "dining", "cuisine")):
            return "meal"
        if any(k in before_lo for k in ("entry", "ticket", "tour", "attraction", "admission", "sightseeing", "guide", "experience", "activity")):
            return "activity"
        if any(k in before_lo for k in ("transport", "transfer", "taxi", "shuttle", "ride")):
            return "transport"
        return "meal"  # bias to meal for /person when context is silent

    # 2) Tight pre-price window — only the words nearest the price matter
    if any(k in before_lo for k in ("hotel", "room", "resort", "villa", "accommodation", "stay", "lodging", "suite", "guesthouse")):
        return "hotel"
    if any(k in before_lo for k in ("taxi", "transfer", "transport", "minivan", "coach", "driver", "vehicle", "chauffeur", "rental", "tuk-tuk", "grab", "uber", "car hire", "limousine", "shuttle")):
        return "transport"
    if any(k in before_lo for k in ("meal", "lunch", "dinner", "breakfast", "restaurant", "food", "dining", "cuisine")):
        return "meal"
    if any(k in before_lo for k in ("entry", "ticket", "tour", "attraction", "admission", "sightseeing", "guide", "experience")):
        return "activity"
    return None


def _is_plausible(category: str, usd_value: float) -> bool:
    """Reject prices that are clearly not in this category's typical range
    (e.g. a $5 'hotel' is a typo; a $5000 'meal' is a banquet, not per-person)."""
    if category == "hotel":     return 25   <= usd_value <= 1500
    if category == "transport": return 15   <= usd_value <= 800
    if category == "meal":      return 3    <= usd_value <= 200
    if category == "activity":  return 2    <= usd_value <= 500
    return False


@lru_cache(maxsize=64)
def _fx_rate_cached(from_curr: str, to_curr: str) -> Optional[float]:
    """Cached wrapper around get_exchange_rate so we don't hit Frankfurter
    repeatedly for the same currency pair within a session."""
    if from_curr == to_curr:
        return 1.0
    return get_exchange_rate(from_curr, to_curr)


def _convert_via_fx(amount: float, from_curr: str, to_curr: str) -> Optional[float]:
    rate = _fx_rate_cached(from_curr, to_curr)
    if rate is None:
        # Fall back to approx table — better than dropping the data point
        try:
            usd = amount * _APPROX_TO_USD.get(from_curr, 1.0)
            inv = _APPROX_TO_USD.get(to_curr)
            if not inv:
                return None
            return round(usd / inv, 2)
        except Exception:
            return None
    return round(amount * rate, 2)


def mine_categorical_prices(text: str, target_currency: str = "USD") -> Dict[str, Any]:
    """Mine prices from prose, bucket by surrounding context, convert to target currency.

    Returns:
        {
          "hotel_per_night":    {"avg": 145.0, "min": 90, "max": 220, "n": 6, "samples": [...]},
          "transport_per_day":  {"avg": 78.0, ...},
          "meal_per_person":    {"avg": 22.0, ...},
          "activity_per_person":{"avg": 35.0, ...},
          "currency": "USD",
        }

    Ranges are filtered to plausibility windows so a $5 hotel or $5000 meal don't
    pollute the average.
    """
    target_currency = (target_currency or "USD").upper()
    out = {
        "hotel_per_night":     {"avg": None, "min": None, "max": None, "n": 0, "samples": []},
        "transport_per_day":   {"avg": None, "min": None, "max": None, "n": 0, "samples": []},
        "meal_per_person":     {"avg": None, "min": None, "max": None, "n": 0, "samples": []},
        "activity_per_person": {"avg": None, "min": None, "max": None, "n": 0, "samples": []},
        "currency":            target_currency,
    }
    if not isinstance(text, str) or not text:
        return out

    buckets: Dict[str, List[float]] = {"hotel": [], "transport": [], "meal": [], "activity": []}
    for m in _AMOUNT_REGEX.finditer(text):
        curr_raw = m.group("curr_pre") or m.group("curr_post")
        curr = _normalise_currency(curr_raw)
        if not curr:
            continue
        try:
            amount = float(m.group("amount").replace(",", "").replace(" ", ""))
        except ValueError:
            continue
        # Reject obvious non-prices: years, IDs
        if 1900 <= amount <= 2100 and curr == "USD":
            continue
        if amount <= 0:
            continue

        # Approx-USD plausibility check (cheaper than FX call for noise filter)
        usd_approx = amount * _APPROX_TO_USD.get(curr, 1.0)
        category = _categorise_price(text, m.start(), m.end())
        if not category or not _is_plausible(category, usd_approx):
            continue

        # Real FX conversion to the target currency
        converted = _convert_via_fx(amount, curr, target_currency)
        if converted is None or converted <= 0:
            continue
        buckets[category].append(converted)

    _bucket_keys = {
        "hotel":     "hotel_per_night",
        "transport": "transport_per_day",
        "meal":      "meal_per_person",
        "activity":  "activity_per_person",
    }
    for src, dst in _bucket_keys.items():
        vals = sorted(buckets[src])
        if not vals:
            continue
        # Trimmed mean if we have enough samples; plain mean otherwise
        if len(vals) >= 4:
            k = max(1, len(vals) // 5)
            trimmed = vals[k:-k] or vals
        else:
            trimmed = vals
        avg = round(sum(trimmed) / len(trimmed), 2)
        out[dst] = {
            "avg":     avg,
            "min":     vals[0],
            "max":     vals[-1],
            "n":       len(vals),
            "samples": vals[:8],
        }
    return out


def get_exchange_rate(from_currency: str = "EUR", to_currency: str = "INR") -> Optional[float]:
    """
    Fetch live exchange rate using Frankfurter API (ECB data, free, no key).
    Returns rate as float or None on failure.
    """
    try:
        url = f"https://api.frankfurter.app/latest?from={from_currency}&to={to_currency}"
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        data = r.json()
        rate = data.get("rates", {}).get(to_currency)
        if rate:
            logger.info("Exchange rate %s→%s: %.2f", from_currency, to_currency, rate)
            return float(rate)
    except Exception as e:
        logger.warning("Exchange rate fetch failed: %s", e)
    return None


def search_hotel_prices_ddg(city: str, hotel_category: str, month: str = "") -> Dict[str, Any]:
    """
    Search DuckDuckGo instant answers for hotel price estimates in a city.
    Returns a dict with raw_text and any extracted price ranges.
    """
    query = f"average {hotel_category} hotel price per night {city} {month}".strip()
    result = {"city": city, "query": query, "raw": "", "prices_eur": []}
    try:
        url = "https://api.duckduckgo.com/"
        params = {"q": query, "format": "json", "no_redirect": 1, "skip_disambig": 1}
        r = requests.get(url, params=params, timeout=6)
        r.raise_for_status()
        data = r.json()
        text = (data.get("AbstractText") or "") + " " + (data.get("Answer") or "")
        result["raw"] = text[:400]
        # Extract EUR price patterns: €120, EUR 150, 100 EUR, €80-120
        for m in re.finditer(r"[€](\d{2,4})(?:\s*[-–]\s*(\d{2,4}))?|(\d{2,4})\s*EUR|EUR\s*(\d{2,4})", text, re.IGNORECASE):
            nums = [int(g) for g in m.groups() if g]
            result["prices_eur"].extend(nums)
    except Exception as e:
        logger.warning("DDG hotel price search failed for %s: %s", city, e)
    return result


def get_numbeo_cost_of_living(city: str) -> Dict[str, Any]:
    """
    Fetch cost of living / hotel price data from Numbeo's free API.
    Returns dict with hotel_eur_per_night estimate or empty dict on failure.
    """
    try:
        url = f"https://www.numbeo.com/api/indices?api_key=free&query={requests.utils.quote(city)}"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            data = r.json()
            return data
    except Exception:
        pass
    return {}


# Known approximate nightly hotel rates by city (EUR) — fallback baseline, updated periodically
_HOTEL_BASELINES_EUR: Dict[str, Dict[str, int]] = {
    "prague":    {"3-star": 60,  "4-star": 110, "4-star deluxe": 150, "5-star": 220},
    "vienna":    {"3-star": 80,  "4-star": 140, "4-star deluxe": 190, "5-star": 280},
    "budapest":  {"3-star": 55,  "4-star": 95,  "4-star deluxe": 130, "5-star": 200},
    "paris":     {"3-star": 110, "4-star": 200, "4-star deluxe": 280, "5-star": 500},
    "rome":      {"3-star": 90,  "4-star": 160, "4-star deluxe": 230, "5-star": 400},
    "amsterdam": {"3-star": 100, "4-star": 180, "4-star deluxe": 250, "5-star": 420},
    "london":    {"3-star": 120, "4-star": 220, "4-star deluxe": 320, "5-star": 600},
    "dubai":     {"3-star": 60,  "4-star": 120, "4-star deluxe": 180, "5-star": 320},
    "singapore": {"3-star": 90,  "4-star": 180, "4-star deluxe": 250, "5-star": 450},
    "bali":      {"3-star": 40,  "4-star": 90,  "4-star deluxe": 130, "5-star": 250},
    "maldives":  {"3-star": 200, "4-star": 350, "4-star deluxe": 500, "5-star": 900},
}

# Peak-season month multipliers (June–August = 1.25 for European cities)
_SEASON_MULTIPLIERS: Dict[int, float] = {
    6: 1.25, 7: 1.30, 8: 1.25,   # Summer peak
    12: 1.15, 1: 1.05,            # Winter/Christmas
}


def get_travel_price_context(
    destinations: List[str],
    hotel_category: str,
    start_date: str = "",
    pax: int = 2,
    nights_per_city: Dict[str, int] = None,
) -> Dict[str, Any]:
    """
    Build a price context object with real/estimated costs for each destination.
    Returns dict with:
      - eur_to_inr: current exchange rate
      - per_city: {city: {hotel_per_night_inr, hotel_total_inr, ...}}
      - notes: list of data source notes
    """
    ctx: Dict[str, Any] = {"per_city": {}, "notes": []}
    nights_per_city = nights_per_city or {}

    # 1. Fetch live EUR→INR rate
    eur_to_inr = get_exchange_rate("EUR", "INR")
    if not eur_to_inr:
        eur_to_inr = 90.0  # fallback
        ctx["notes"].append("EUR→INR rate: estimated 90 (live fetch failed)")
    else:
        ctx["notes"].append(f"EUR→INR rate: {eur_to_inr:.1f} (live from ECB)")
    ctx["eur_to_inr"] = eur_to_inr

    # 2. Parse month from start_date for seasonality
    peak_multiplier = 1.0
    start_month = 0
    if start_date:
        try:
            from datetime import datetime as _dt
            _d = _dt.strptime(start_date, "%Y-%m-%d")
            start_month = _d.month
            peak_multiplier = _SEASON_MULTIPLIERS.get(start_month, 1.0)
        except Exception:
            pass

    cat_key = hotel_category.lower().replace(" ", " ")

    # 3. Per destination prices
    for city in destinations:
        city_key = city.lower().strip()
        nights = nights_per_city.get(city, 0)

        # Base rate from baselines (fallback)
        baseline = _HOTEL_BASELINES_EUR.get(city_key, {})
        if not baseline:
            # Try partial match
            for k in _HOTEL_BASELINES_EUR:
                if k in city_key or city_key in k:
                    baseline = _HOTEL_BASELINES_EUR[k]
                    break

        base_eur = baseline.get(cat_key) or baseline.get("4-star") or 120

        # Try DuckDuckGo live search for better estimate
        month_name = ""
        if start_month:
            month_name = ["", "January","February","March","April","May","June","July","August","September","October","November","December"][start_month]
        ddg = search_hotel_prices_ddg(city, hotel_category, month_name)
        if ddg["prices_eur"]:
            ddg_avg = sum(ddg["prices_eur"]) / len(ddg["prices_eur"])
            # Blend baseline with live estimate (60% live, 40% baseline)
            base_eur = round(ddg_avg * 0.6 + base_eur * 0.4)
            ctx["notes"].append(f"{city} hotel rate: live search ≈ €{int(ddg_avg)}/night (blended)")
        else:
            ctx["notes"].append(f"{city} hotel rate: baseline ≈ €{base_eur}/night")

        # Apply peak-season multiplier
        seasonal_eur = round(base_eur * peak_multiplier)
        per_night_inr = round(seasonal_eur * eur_to_inr / 500) * 500  # round to nearest 500

        city_data: Dict[str, Any] = {
            "hotel_per_night_eur": seasonal_eur,
            "hotel_per_night_inr": per_night_inr,
        }
        if nights:
            rooms = max(1, (pax + 1) // 2)  # rough room count
            city_data["hotel_total_inr"] = per_night_inr * nights * rooms
            city_data["nights"] = nights
            city_data["rooms_estimated"] = rooms

        ctx["per_city"][city] = city_data

    # 4. Ground transport estimate (private van Europe: ~€150-200/day)
    van_daily_eur = 175
    if peak_multiplier > 1.1:
        van_daily_eur = 200
    ctx["transport_per_day_eur"] = van_daily_eur
    ctx["transport_per_day_inr"] = round(van_daily_eur * eur_to_inr / 500) * 500

    # 5. Meal estimates per person per day (Europe mid-range)
    meal_pp_day_eur = 60  # breakfast + lunch + dinner
    ctx["meals_per_person_per_day_eur"] = meal_pp_day_eur
    ctx["meals_per_person_per_day_inr"] = round(meal_pp_day_eur * eur_to_inr / 100) * 100

    # 6. Sightseeing/entry fees estimate per person per day
    sight_pp_day_eur = 40
    ctx["sightseeing_per_person_per_day_eur"] = sight_pp_day_eur
    ctx["sightseeing_per_person_per_day_inr"] = round(sight_pp_day_eur * eur_to_inr / 100) * 100

    return ctx


if __name__ == '__main__':
    # Test the integration
    print("Testing Real-Time Search Integration (No API Keys Required)\n")
    
    result = enrich_destination("Muscat, Oman")
    print(f"Destination: {result['destination']}")
    print(f"\nWikipedia: {result['wikipedia'].get('title')}")
    print(f"Attractions found: {len(result['attractions'])}")
    print(f"News items: {len(result['news'])}")
    
    if result['attractions']:
        print(f"\nFirst attraction: {result['attractions'][0]['name']}")
    
    if result['news']:
        print(f"\nFirst news: {result['news'][0]['title']}")
