"""wikipedia_lookup.py
Lightweight helper to search Wikipedia for a destination and return top attractions
and short summaries. Uses the public Wikipedia API.

Wikimedia Foundation User-Agent Policy (must comply or requests are 403'd):
  https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy

Required format:
  <client>/<version> (<contact URL or email>) <library>/<version>

The contact MUST be reachable — fake placeholder emails (anything @example.com,
@example.org, or a .example TLD) get flagged and rejected by some edge nodes.
"""
import os
import requests
from typing import List, Dict, Any

WIKI_SEARCH_URL = "https://en.wikipedia.org/w/api.php"
WIKI_REST_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"

# Build a policy-compliant User-Agent. Project URL acts as the verifiable contact.
# Both pieces are env-overridable for production deployments.
_REQUESTS_VER = getattr(requests, "__version__", "2")
_PROJECT_URL = os.getenv("WIKI_CONTACT_URL", "https://github.com/zarah-ai-team/zarah-ai")
_CONTACT_EMAIL = os.getenv("WIKI_CONTACT_EMAIL", "")
_CONTACT_BLOCK = (
    f"{_PROJECT_URL}; {_CONTACT_EMAIL}" if _CONTACT_EMAIL else _PROJECT_URL
)
_DEFAULT_UA = (
    f"ZarahAI-TravelChatbot/1.0 ({_CONTACT_BLOCK}) "
    f"python-requests/{_REQUESTS_VER}"
)
_WIKI_HEADERS = {
    "User-Agent": os.getenv("WIKI_USER_AGENT", _DEFAULT_UA),
    "Accept": "application/json",
    # Api-User-Agent is honored by some Wikimedia services in addition to UA.
    "Api-User-Agent": os.getenv("WIKI_USER_AGENT", _DEFAULT_UA),
}


def search_wikipedia(title: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Search for pages matching title and return a list of page titles."""
    params = {
        'action': 'query',
        'list': 'search',
        'srsearch': title,
        'format': 'json',
        'srlimit': limit
    }
    try:
        r = requests.get(WIKI_SEARCH_URL, params=params, headers=_WIKI_HEADERS, timeout=8)
        r.raise_for_status()
        data = r.json()
        results = data.get('query', {}).get('search', [])
        return [{'title': r.get('title'), 'snippet': r.get('snippet')} for r in results]
    except Exception:
        return []


def get_summary_for_title(title: str) -> Dict[str, Any]:
    """Return summary for a given page title using REST summary endpoint."""
    try:
        # encode title for URL
        url = WIKI_REST_SUMMARY + requests.utils.quote(title)
        r = requests.get(url, headers=_WIKI_HEADERS, timeout=8)
        r.raise_for_status()
        data = r.json()
        return {
            'title': data.get('title'),
            'description': data.get('description'),
            'extract': data.get('extract'),
            'url': data.get('content_urls', {}).get('desktop', {}).get('page')
        }
    except Exception:
        return {}


def get_top_attractions(destination: str, max_items: int = 5) -> List[Dict[str, Any]]:
    """Search Wikipedia for the destination and return summaries for top likely attractions."""
    out = []
    search_candidates = search_wikipedia(destination, limit=max_items*2)
    titles = [c['title'] for c in search_candidates]
    # prioritize pages that include words like 'tourism', 'attractions', 'museum', 'fort', 'park'
    prioritized = []
    for t in titles:
        low = t.lower()
        score = 0
        for kw in ['museum', 'fort', 'park', 'beach', 'island', 'palace', 'national', 'zoo', 'aquarium', 'louvre', 'burj', 'souk']:
            if kw in low:
                score += 2
        if destination.lower() in low:
            score += 1
        prioritized.append((score, t))
    prioritized.sort(reverse=True)
    chosen = [t for s, t in prioritized][:max_items]
    for t in chosen:
        s = get_summary_for_title(t)
        if s:
            out.append(s)
    # Fallback: if none found, return the page for the destination itself
    if not out:
        s = get_summary_for_title(destination)
        if s:
            out.append(s)
    return out


if __name__ == '__main__':
    print(get_top_attractions('Muscat'))
