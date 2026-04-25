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


def load_clients():
    """Load clients from persistent JSON file."""
    global CLIENTS
    if os.path.exists(CLIENTS_FILE):
        try:
            with open(CLIENTS_FILE, "r") as f:
                CLIENTS = json.load(f)
        except Exception as e:
            print(f"Failed to load clients: {e}")
            CLIENTS = {}
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
    """Update a client's details."""
    if client_id not in CLIENTS:
        return None
    CLIENTS[client_id].update(updates)
    save_clients()
    return CLIENTS[client_id]


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
