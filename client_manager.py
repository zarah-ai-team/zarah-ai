"""client_manager.py
Optional client management system for tracking clients, their details, and associated itineraries.
Clients can be created and managed via a dashboard endpoint.
"""
import json
import os
from typing import Dict, Any, List, Optional
from datetime import datetime

# In-memory client store (in production, use database)
CLIENTS = {}
CLIENTS_FILE = os.path.join(os.path.dirname(__file__), "data", "clients.json")

# Default empty preferences shape — used to backfill clients created before
# preferences existed and to validate incoming payloads. All fields optional
# so the planner only steers on what's actually set.
EMPTY_PREFERENCES: Dict[str, Any] = {
    "travel_style":          "",   # luxury | premium | mid-range | budget
    "budget_level":          "",   # low | medium | high | luxury
    "pace":                  "",   # relaxed | balanced | packed
    "hotel_categories":      [],   # ["3-Star", "4-Star", "5-Star", "5-Star Luxury"]
    "cuisine":               [],   # ["Vegetarian","Vegan","Halal","Kosher","Gluten-free","Local food"]
    "activities":            [],   # ["Adventure","Cultural","Beach","Wildlife","Shopping","Nightlife","Wellness","Sightseeing"]
    "special_requirements":  "",   # free text — accessibility, allergies, etc.
    "preferred_destinations": [],  # cities/countries the client tends to favour
    "avoid":                 [],   # things the client wants to avoid
    "notes":                 "",   # free text
}


def _normalize_preferences(prefs: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Coerce incoming preferences into the canonical shape, dropping unknown keys
    and filling missing ones with empty defaults. Lists/strings are sanitised."""
    if not isinstance(prefs, dict):
        return dict(EMPTY_PREFERENCES)
    out: Dict[str, Any] = {}
    for key, default in EMPTY_PREFERENCES.items():
        val = prefs.get(key, default)
        if isinstance(default, list):
            out[key] = [str(x).strip() for x in val if str(x).strip()] if isinstance(val, list) else []
        else:
            out[key] = str(val).strip() if val is not None else ""
    return out


def has_meaningful_preferences(prefs: Optional[Dict[str, Any]]) -> bool:
    """True when the client has at least one preference filled in."""
    if not isinstance(prefs, dict):
        return False
    return any(bool(v) for v in prefs.values())


def load_clients():
    """Load clients from persistent JSON file. Backfills `preferences` for any
    legacy client records that were saved before that field existed."""
    global CLIENTS
    if os.path.exists(CLIENTS_FILE):
        try:
            with open(CLIENTS_FILE, "r") as f:
                CLIENTS = json.load(f)
        except Exception as e:
            print(f"Failed to load clients: {e}")
            CLIENTS = {}
    # Backward compatibility — older client rows have no `preferences` key
    for c in CLIENTS.values():
        if not isinstance(c.get("preferences"), dict):
            c["preferences"] = dict(EMPTY_PREFERENCES)
        else:
            c["preferences"] = _normalize_preferences(c["preferences"])
    return CLIENTS


def save_clients():
    """Save clients to persistent JSON file."""
    os.makedirs(os.path.dirname(CLIENTS_FILE), exist_ok=True)
    try:
        with open(CLIENTS_FILE, "w") as f:
            json.dump(CLIENTS, f, indent=2, default=str)
    except Exception as e:
        print(f"Failed to save clients: {e}")


def create_client(
    company_name: str,
    client_type: str,
    status: str = "",
    primary_contact: Dict[str, str] | None = None,
    country: str = "",
    city: str = "",
    address: str = "",
    industry: str = "Other",
    lead_source: str = "",
    notes: str = "",
    secondary_contact: Dict[str, str] | None = None,
    preferences: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a new client with validation against allowed enums."""
    allowed_types = {"corporate", "leisure", "mice", "dmc"}
    allowed_inds = {"automotive", "technology", "finance", "hospitality", "retail", "manufacturing", "other"}
    if client_type.strip().lower() not in allowed_types:
        raise ValueError(f"client_type must be one of {sorted(allowed_types)}")
    if industry.strip().lower() not in allowed_inds:
        raise ValueError(f"industry must be one of {sorted(allowed_inds)}")
    # primary_contact must include full_name, email, phone
    # primary_contact is optional; if provided it must include required fields
    if primary_contact is not None:
        if not isinstance(primary_contact, dict) or not primary_contact.get("full_name") or not primary_contact.get("email"):
            raise ValueError("primary_contact must include at least 'full_name' and 'email'")

    client_id = f"client_{len(CLIENTS) + 1}_{int(datetime.now().timestamp())}"
    client = {
        "id": client_id,
        "company_name": company_name,
        "client_type": client_type.strip().title(),
        "status": status,
        "primary_contact": primary_contact,
        "secondary_contact": secondary_contact or {},
        "country": country,
        "city": city,
        "address": address,
        "industry": industry.strip().title(),
        "lead_source": lead_source,
        "notes": notes,
        "preferences": _normalize_preferences(preferences),
        "created_at": datetime.utcnow().isoformat() + "Z",
        "itineraries": [],
    }
    CLIENTS[client_id] = client
    save_clients()
    return client


def get_client(client_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a client by ID."""
    return CLIENTS.get(client_id)


def list_clients() -> List[Dict[str, Any]]:
    """List all clients."""
    return list(CLIENTS.values())


def update_client(
    client_id: str, updates: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Update a client's details. Preferences are merged onto the existing
    record (partial updates are supported), then re-normalised."""
    if client_id not in CLIENTS:
        return None
    if "preferences" in updates:
        merged_prefs = {
            **CLIENTS[client_id].get("preferences", EMPTY_PREFERENCES),
            **(updates["preferences"] or {}),
        }
        updates["preferences"] = _normalize_preferences(merged_prefs)
    CLIENTS[client_id].update(updates)
    save_clients()
    return CLIENTS[client_id]


def get_client_preferences(client_id: str) -> Dict[str, Any]:
    """Return the client's preferences (or empty defaults if not set / not found)."""
    client = CLIENTS.get(client_id)
    if not client:
        return dict(EMPTY_PREFERENCES)
    return _normalize_preferences(client.get("preferences"))


def delete_client(client_id: str) -> bool:
    """Delete a client (and optionally its itineraries)."""
    if client_id in CLIENTS:
        del CLIENTS[client_id]
        save_clients()
        return True
    return False


def add_itinerary_to_client(client_id: str, itinerary_id: str) -> Optional[Dict[str, Any]]:
    """Link an itinerary to a client."""
    if client_id not in CLIENTS:
        return None
    if itinerary_id not in CLIENTS[client_id]["itineraries"]:
        CLIENTS[client_id]["itineraries"].append(itinerary_id)
        save_clients()
    return CLIENTS[client_id]


def get_client_itineraries(client_id: str) -> List[str]:
    """Get all itinerary IDs for a client."""
    if client_id not in CLIENTS:
        return []
    return CLIENTS[client_id].get("itineraries", [])


def search_clients(query: str) -> List[Dict[str, Any]]:
    """Search clients by name, email, or industry (case-insensitive)."""
    query_lower = query.lower()
    results = []
    for client in CLIENTS.values():
        if (
            query_lower in client.get("name", "").lower()
            or query_lower in client.get("email", "").lower()
            or query_lower in client.get("industry", "").lower()
        ):
            results.append(client)
    return results


# Load clients on module import
load_clients()
