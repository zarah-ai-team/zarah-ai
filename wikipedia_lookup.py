"""wikipedia_lookup.py
Lightweight helper to search Wikipedia for a destination and return top attractions and short summaries.
Uses the public Wikipedia REST API (no external dependencies required beyond requests).
"""
import requests
from typing import List, Dict, Any

WIKI_SEARCH_URL = "https://en.wikipedia.org/w/api.php"
WIKI_REST_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"


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
        r = requests.get(WIKI_SEARCH_URL, params=params, timeout=8)
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
        r = requests.get(url, timeout=8)
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
