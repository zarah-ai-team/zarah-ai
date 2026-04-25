"""real_time_search.py
Real-time search integration for Wikipedia, attractions, news, and Google Search.
All APIs are completely free and require NO API keys.
"""
import requests
from typing import List, Dict, Any
import logging

logger = logging.getLogger("real_time_search")

# ============ GOOGLE SEARCH (Free via googlesearch-python) ============
def google_search(query: str, num_results: int = 5) -> List[Dict[str, str]]:
    """
    Search Google for real-time information about a destination.
    Uses googlesearch-python package (no API key required).
    """
    try:
        from googlesearch import search as gsearch
        results = []
        for url in gsearch(query, num_results=num_results, lang="en", sleep_interval=1):
            results.append({"url": url, "title": url.split("/")[-1].replace("-", " ").replace("_", " ")[:80]})
        return results
    except Exception as e:
        logger.error(f"Google search failed: {e}")
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
        r = requests.get(url, params=params, timeout=5)
        r.raise_for_status()
        results = r.json().get('query', {}).get('search', [])
        return [{'title': r['title'], 'snippet': r['snippet']} for r in results]
    except Exception as e:
        logger.error(f"Wikipedia search failed: {e}")
        return []


def get_wikipedia_summary(title: str) -> Dict[str, Any]:
    """
    Get detailed summary of a Wikipedia article.
    No API key required - uses public REST API.
    """
    try:
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(title)}"
        r = requests.get(url, timeout=5)
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
        logger.error(f"Wikipedia summary failed: {e}")
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
        
        r = requests.get(overpass_url, params={'data': query}, timeout=10)
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
        logger.error(f"Nearby attractions search failed: {e}")
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
        
        r = requests.get(overpass_url, params={'data': query}, timeout=10)
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
        logger.error(f"Attractions by name search failed: {e}")
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
