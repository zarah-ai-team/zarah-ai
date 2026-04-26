"""chat_store.py
Persistent chat session storage with metadata.
Stores chat sessions as JSON files in data/chats/.
Each user gets their own subdirectory.
"""
import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
import uuid

logger = logging.getLogger("chat_store")

CHATS_DIR = os.path.join(os.path.dirname(__file__), "data", "chats")


def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def _user_dir(username: str) -> str:
    d = os.path.join(CHATS_DIR, username)
    _ensure_dir(d)
    return d


def _chat_path(username: str, session_id: str) -> str:
    return os.path.join(_user_dir(username), f"{session_id}.json")


def _load_chat(username: str, session_id: str) -> Optional[Dict[str, Any]]:
    path = _chat_path(username, session_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load chat {session_id}: {e}")
        return None


def _save_chat(username: str, session_id: str, data: Dict[str, Any]):
    path = _chat_path(username, session_id)
    _ensure_dir(os.path.dirname(path))
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to save chat {session_id}: {e}")


# ─── Public API ──────────────────────────────────────────────────────────────

def create_chat(username: str, chat_name: str = "") -> Dict[str, Any]:
    """Create a new chat session and return its metadata."""
    session_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat() + "Z"
    chat = {
        "session_id": session_id,
        "username": username,
        "chat_name": chat_name or f"New Chat {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
        "created_at": now,
        "updated_at": now,
        # Chat metadata (populated as conversation progresses)
        "metadata": {
            "itinerary_name": "",
            "group_client_name": "",
            "travel_dates": "",
            "travelers_max": 0,
            "duration": "",
            "estimated_cost": "",
            "status": "draft",  # draft | in_progress | completed | cancelled
        },
        # Conversation data
        "fields": {},
        "history": [],
        "sanity_checks": [],
        "last_llm_raw": None,
        "last_llm_prompt": None,
    }
    _save_chat(username, session_id, chat)
    return chat


def get_chat(username: str, session_id: str) -> Optional[Dict[str, Any]]:
    """Load a chat session by session_id for a specific user."""
    return _load_chat(username, session_id)


def update_chat(username: str, session_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update chat data (fields, history, metadata, etc.)."""
    chat = _load_chat(username, session_id)
    if not chat:
        return None
    # Merge updates
    for key, value in updates.items():
        if key == "metadata" and isinstance(value, dict):
            chat.setdefault("metadata", {}).update(value)
        else:
            chat[key] = value
    chat["updated_at"] = datetime.utcnow().isoformat() + "Z"
    _save_chat(username, session_id, chat)
    return chat


def update_chat_metadata_from_fields(username: str, session_id: str, fields: Dict[str, Any]):
    """Auto-update chat metadata from conversation fields."""
    chat = _load_chat(username, session_id)
    if not chat:
        return
    meta = chat.get("metadata", {})
    # Map conversation fields to metadata
    if fields.get("destination"):
        meta["itinerary_name"] = f"{fields['destination']} Trip"
    if fields.get("client_name") or fields.get("group_name"):
        meta["group_client_name"] = fields.get("client_name") or fields.get("group_name") or ""
    if fields.get("travel_dates") or fields.get("start_date"):
        meta["travel_dates"] = fields.get("travel_dates") or fields.get("start_date") or ""
    if fields.get("pax") or fields.get("people"):
        try:
            meta["travelers_max"] = int(fields.get("pax") or fields.get("people") or 0)
        except (ValueError, TypeError):
            pass
    if fields.get("duration") or fields.get("nights"):
        meta["duration"] = str(fields.get("duration") or fields.get("nights") or "")
    if fields.get("budget"):
        meta["estimated_cost"] = str(fields.get("budget"))
    # NOTE: do NOT auto-flip status here. The user controls status from the
    # ItineraryManagement dropdown; auto-flipping draft→in_progress on every
    # field update was clobbering their choice (e.g. "Saved" → "In Progress").

    chat["metadata"] = meta
    chat["updated_at"] = datetime.utcnow().isoformat() + "Z"
    _save_chat(username, session_id, chat)


def list_user_chats(username: str) -> List[Dict[str, Any]]:
    """List all chat sessions for a user (metadata only, no full history)."""
    user_dir = _user_dir(username)
    chats = []
    if not os.path.exists(user_dir):
        return chats
    for fname in os.listdir(user_dir):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(user_dir, fname), "r", encoding="utf-8") as f:
                chat = json.load(f)
            chats.append({
                "session_id": chat.get("session_id"),
                "chat_name": chat.get("chat_name", ""),
                "created_at": chat.get("created_at", ""),
                "updated_at": chat.get("updated_at", ""),
                "metadata": chat.get("metadata", {}),
                "has_saved_itinerary": bool(chat.get("saved_itinerary")),
            })
        except Exception as e:
            logger.error(f"Failed to read chat file {fname}: {e}")
    # Sort by updated_at descending
    chats.sort(key=lambda c: c.get("updated_at", ""), reverse=True)
    return chats


def delete_chat(username: str, session_id: str) -> bool:
    """Delete a chat session."""
    path = _chat_path(username, session_id)
    if os.path.exists(path):
        try:
            os.remove(path)
            return True
        except Exception as e:
            logger.error(f"Failed to delete chat {session_id}: {e}")
    return False


def upsert_chat(username: str, session_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Create a chat if it doesn't exist yet, then apply updates (upsert).

    Auto-generated names (name_auto=True) are updated on every sync so the
    title improves as more trip details are collected.  Once a user explicitly
    renames the chat (name_auto=False) the auto-update stops permanently.
    """
    new_chat_name = updates.pop("chat_name", None)
    chat = _load_chat(username, session_id)
    if not chat:
        now = datetime.utcnow().isoformat() + "Z"
        chat = {
            "session_id": session_id,
            "username": username,
            "chat_name": new_chat_name or f"Chat {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
            "name_auto": True,
            "created_at": now,
            "updated_at": now,
            "metadata": {"status": "draft"},
            "fields": {},
            "history": [],
            "sanity_checks": [],
            "last_llm_raw": None,
            "last_llm_prompt": None,
        }
    else:
        # Only refresh the auto-generated name; never touch a user-set name
        if new_chat_name and chat.get("name_auto", True):
            chat["chat_name"] = new_chat_name
    for key, value in updates.items():
        if key == "metadata" and isinstance(value, dict):
            chat.setdefault("metadata", {}).update(value)
        else:
            chat[key] = value
    chat["updated_at"] = datetime.utcnow().isoformat() + "Z"
    _save_chat(username, session_id, chat)
    return chat


def update_chat_status(username: str, session_id: str, new_status: str) -> Optional[Dict[str, Any]]:
    """Update chat status (draft, in_progress, completed, cancelled)."""
    valid_statuses = {"draft", "in_progress", "completed", "cancelled"}
    if new_status not in valid_statuses:
        return None
    chat = _load_chat(username, session_id)
    if not chat:
        return None
    chat.setdefault("metadata", {})["status"] = new_status
    chat["updated_at"] = datetime.utcnow().isoformat() + "Z"
    _save_chat(username, session_id, chat)
    return chat
