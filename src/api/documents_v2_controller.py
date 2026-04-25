"""
Document management v2 — upload to S3 (or local fallback), process for KB,
and expose CRUD endpoints.

No authentication required on these endpoints so the frontend can call them
without a JWT during development.  Add Depends(get_current_user) to each
route when you are ready to lock things down.

Endpoints
---------
POST   /api/v2/documents/upload         Upload a file + optionally add to KB
GET    /api/v2/documents                List all uploaded documents
GET    /api/v2/documents/{doc_id}       Download a document (presigned URL or redirect)
GET    /api/v2/documents/{doc_id}/status  Processing / KB status
DELETE /api/v2/documents/{doc_id}       Delete from storage + KB index
POST   /api/v2/documents/{doc_id}/reprocess  Re-run KB extraction on existing doc
GET    /api/v2/documents/health         Storage + KB health check
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse

from src.services.kb.document_processor import (
    get_user_kb_docs,
    process_and_index,
    remove_from_kb,
)
from src.services.storage.s3_client import get_storage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v2/documents", tags=["documents-v2"])

# Persistent document metadata index (separate from KB text index)
_META_DIR  = Path(os.getenv("USER_KB_DOCS_DIR", "data/user_kb_docs"))
_META_FILE = _META_DIR / "documents.json"

_ALLOWED_TYPES = {
    "application/pdf", "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain", "text/csv",
    "application/json",
}
_MAX_SIZE_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))


# ─────────────────────────────────────────────────────────────────────────────
# Metadata helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_meta() -> List[Dict]:
    if _META_FILE.exists():
        try:
            return json.loads(_META_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_meta(docs: List[Dict]) -> None:
    _META_DIR.mkdir(parents=True, exist_ok=True)
    _META_FILE.write_text(json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_doc(doc_id: str) -> Optional[Dict]:
    return next((d for d in _load_meta() if d["doc_id"] == doc_id), None)


def _update_doc(doc_id: str, updates: Dict) -> None:
    docs = _load_meta()
    for d in docs:
        if d["doc_id"] == doc_id:
            d.update(updates)
    _save_meta(docs)


# ─────────────────────────────────────────────────────────────────────────────
# Background KB processing
# ─────────────────────────────────────────────────────────────────────────────

def _process_bg(doc_id: str, filename: str, content: bytes,
                content_type: str, s3_key: str, storage_uri: str) -> None:
    try:
        result = process_and_index(doc_id, filename, content, content_type, s3_key, storage_uri)
        _update_doc(doc_id, {
            "kb_status":      result["status"],
            "kb_char_count":  result["char_count"],
            "kb_cities":      result["cities_found"],
            "kb_has_pricing": result["has_pricing"],
            "kb_has_hotels":  result["has_hotels"],
            "kb_processed_at": datetime.utcnow().isoformat() + "Z",
        })
        logger.info("KB processing done for %s: %s", doc_id, result["status"])
    except Exception as e:
        logger.error("KB processing failed for %s: %s", doc_id, e)
        _update_doc(doc_id, {"kb_status": "error", "kb_error": str(e)})


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/upload", summary="Upload a document and optionally index it for KB")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    description: str = Form(""),
    process_for_kb: bool = Form(True),
):
    content_type = file.content_type or "application/octet-stream"
    content = await file.read()

    # Validations
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    max_bytes = _MAX_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"File exceeds {_MAX_SIZE_MB} MB limit")

    doc_id    = str(uuid.uuid4())[:12]
    filename  = file.filename or "unnamed"
    s3_key    = f"documents/{doc_id}/{filename}"

    # Upload to S3 / local
    storage = get_storage()
    try:
        storage_uri = storage.upload(content, s3_key, content_type)
        download_url = storage.get_url(s3_key)
    except Exception as e:
        logger.error("Storage upload failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Storage upload failed: {e}")

    meta: Dict[str, Any] = {
        "doc_id":       doc_id,
        "filename":     filename,
        "content_type": content_type,
        "size_bytes":   len(content),
        "description":  description,
        "s3_key":       s3_key,
        "storage_uri":  storage_uri,
        "download_url": download_url,
        "uploaded_at":  datetime.utcnow().isoformat() + "Z",
        "kb_status":    "queued" if process_for_kb else "skipped",
    }

    docs = _load_meta()
    docs.append(meta)
    _save_meta(docs)

    if process_for_kb:
        background_tasks.add_task(
            _process_bg, doc_id, filename, content, content_type, s3_key, storage_uri
        )

    return {"success": True, "document": meta}


@router.get("", summary="List all uploaded documents")
async def list_documents(
    page: int = 1,
    page_size: int = 20,
    kb_only: bool = False,
):
    docs = _load_meta()
    if kb_only:
        docs = [d for d in docs if d.get("kb_status") == "indexed"]
    total = len(docs)
    start = (page - 1) * page_size
    return {
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "documents": docs[start: start + page_size],
    }


@router.get("/health", summary="Storage and KB health")
async def documents_health():
    storage = get_storage()
    ping   = storage.ping()
    docs   = _load_meta()
    indexed = sum(1 for d in docs if d.get("kb_status") == "indexed")
    return {
        "storage": ping,
        "documents_total":   len(docs),
        "documents_indexed": indexed,
        "documents_queued":  sum(1 for d in docs if d.get("kb_status") == "queued"),
        "documents_error":   sum(1 for d in docs if d.get("kb_status") == "error"),
    }


@router.get("/{doc_id}/status", summary="KB processing status for a document")
async def document_status(doc_id: str):
    doc = _get_doc(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {
        "doc_id":           doc["doc_id"],
        "filename":         doc["filename"],
        "kb_status":        doc.get("kb_status"),
        "kb_char_count":    doc.get("kb_char_count"),
        "kb_cities":        doc.get("kb_cities", []),
        "kb_has_pricing":   doc.get("kb_has_pricing"),
        "kb_has_hotels":    doc.get("kb_has_hotels"),
        "kb_processed_at":  doc.get("kb_processed_at"),
        "kb_error":         doc.get("kb_error"),
    }


@router.get("/{doc_id}", summary="Get download URL for a document")
async def get_document(doc_id: str, redirect: bool = False):
    doc = _get_doc(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    storage = get_storage()
    try:
        url = storage.get_url(doc["s3_key"])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not generate URL: {e}")

    if redirect:
        return RedirectResponse(url)
    return {"doc_id": doc_id, "filename": doc["filename"], "download_url": url}


@router.post("/{doc_id}/reprocess", summary="Re-run KB extraction on a stored document")
async def reprocess_document(doc_id: str, background_tasks: BackgroundTasks):
    doc = _get_doc(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    storage = get_storage()
    # Try to fetch content from storage for re-processing
    s3_key = doc.get("s3_key", "")
    local_path = Path(os.getenv("LOCAL_UPLOAD_DIR", "data/uploads")) / s3_key
    content = b""
    if local_path.exists():
        content = local_path.read_bytes()
    else:
        raise HTTPException(
            status_code=422,
            detail="Original file content not available for reprocessing (S3-only or deleted)"
        )

    _update_doc(doc_id, {"kb_status": "queued"})
    background_tasks.add_task(
        _process_bg, doc_id, doc["filename"], content,
        doc.get("content_type", ""), s3_key, doc.get("storage_uri", "")
    )
    return {"success": True, "doc_id": doc_id, "kb_status": "queued"}


@router.delete("/{doc_id}", summary="Delete a document from storage and KB")
async def delete_document(doc_id: str):
    doc = _get_doc(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    storage = get_storage()
    try:
        storage.delete(doc["s3_key"])
    except Exception as e:
        logger.warning("Storage delete failed for %s: %s", doc_id, e)

    remove_from_kb(doc_id)

    docs = [d for d in _load_meta() if d["doc_id"] != doc_id]
    _save_meta(docs)

    return {"success": True, "message": f"Document {doc_id} deleted"}
