"""document_store.py
Document upload and retrieval module.
Stores uploaded documents (PDF, DOCX, images, etc.) in data/documents/<username>/
and maintains a metadata index.
"""
import os
import json
import logging
import uuid
import aiofiles
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger("document_store")

DOCUMENTS_DIR = os.path.join(os.path.dirname(__file__), "data", "documents")
INDEX_FILENAME = "_index.json"


def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def _user_dir(username: str) -> str:
    d = os.path.join(DOCUMENTS_DIR, username)
    _ensure_dir(d)
    return d


def _index_path(username: str) -> str:
    return os.path.join(_user_dir(username), INDEX_FILENAME)


def _load_index(username: str) -> Dict[str, Dict[str, Any]]:
    path = _index_path(username)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load document index for {username}: {e}")
        return {}


def _save_index(username: str, index: Dict[str, Dict[str, Any]]):
    path = _index_path(username)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, default=str, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to save document index for {username}: {e}")


# ─── Public API ──────────────────────────────────────────────────────────────

async def save_document(
    username: str,
    filename: str,
    content: bytes,
    content_type: str = "",
    session_id: str = "",
    description: str = "",
) -> Dict[str, Any]:
    """Save an uploaded document and return its metadata."""
    doc_id = str(uuid.uuid4())
    # Sanitize filename
    safe_name = filename.replace("..", "").replace("/", "_").replace("\\", "_")
    ext = os.path.splitext(safe_name)[1] if "." in safe_name else ""
    stored_name = f"{doc_id}{ext}"

    user_path = _user_dir(username)
    file_path = os.path.join(user_path, stored_name)

    # Write file asynchronously
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    # Update index
    meta = {
        "doc_id": doc_id,
        "original_filename": filename,
        "stored_filename": stored_name,
        "content_type": content_type,
        "size_bytes": len(content),
        "session_id": session_id,
        "description": description,
        "uploaded_at": datetime.utcnow().isoformat() + "Z",
    }
    index = _load_index(username)
    index[doc_id] = meta
    _save_index(username, index)

    return meta


def list_documents(username: str, session_id: str = "") -> List[Dict[str, Any]]:
    """List all documents for a user, optionally filtered by session_id."""
    index = _load_index(username)
    docs = list(index.values())
    if session_id:
        docs = [d for d in docs if d.get("session_id") == session_id]
    docs.sort(key=lambda d: d.get("uploaded_at", ""), reverse=True)
    return docs


def get_document_meta(username: str, doc_id: str) -> Optional[Dict[str, Any]]:
    """Get document metadata by ID."""
    index = _load_index(username)
    return index.get(doc_id)


def get_document_path(username: str, doc_id: str) -> Optional[str]:
    """Get the file system path for a document. Returns None if not found."""
    meta = get_document_meta(username, doc_id)
    if not meta:
        return None
    path = os.path.join(_user_dir(username), meta["stored_filename"])
    if not os.path.exists(path):
        return None
    return path


def delete_document(username: str, doc_id: str) -> bool:
    """Delete a document and its metadata."""
    index = _load_index(username)
    meta = index.get(doc_id)
    if not meta:
        return False
    # Delete file
    file_path = os.path.join(_user_dir(username), meta["stored_filename"])
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        logger.error(f"Failed to delete document file {file_path}: {e}")
    # Remove from index
    del index[doc_id]
    _save_index(username, index)
    return True
