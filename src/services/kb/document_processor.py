"""
Document processor — extracts text from uploaded files and adds them to the
user knowledge base so the itinerary pipeline can reference them.

Supported formats: PDF (pdfplumber), DOCX (python-docx), XLSX/CSV (openpyxl),
                   plain TXT.

Processed documents are stored as JSON entries in data/user_kb_docs/index.json.
The KB retriever picks them up via get_user_kb_docs().
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_KB_DOCS_DIR = Path(os.getenv("USER_KB_DOCS_DIR", "data/user_kb_docs"))
_KB_INDEX    = _KB_DOCS_DIR / "index.json"


# ─────────────────────────────────────────────────────────────────────────────
# Text extraction
# ─────────────────────────────────────────────────────────────────────────────

def extract_text(content: bytes, content_type: str, filename: str) -> str:
    """Extract plain text from a file.  Returns empty string on failure."""
    fname = filename.lower()
    try:
        if fname.endswith(".pdf") or "pdf" in content_type:
            return _from_pdf(content)
        if fname.endswith(".docx") or "word" in content_type:
            return _from_docx(content)
        if fname.endswith(".xlsx") or "spreadsheet" in content_type or "excel" in content_type:
            return _from_xlsx(content)
        if fname.endswith(".csv") or "csv" in content_type:
            return content.decode("utf-8", errors="replace")
        # Plain text / JSON / markdown
        return content.decode("utf-8", errors="replace")
    except Exception as e:
        logger.warning("Text extraction failed for %s: %s", filename, e)
        return ""


def _from_pdf(content: bytes) -> str:
    import pdfplumber
    pages: List[str] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n".join(pages)


def _from_docx(content: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(content))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _from_xlsx(content: bytes) -> str:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    rows: List[str] = []
    for sheet in wb.worksheets:
        rows.append(f"[Sheet: {sheet.title}]")
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c) if c is not None else "" for c in row]
            rows.append("\t".join(cells))
    return "\n".join(rows)


# ─────────────────────────────────────────────────────────────────────────────
# KB data extraction (hotels, pricing, sightseeing from text)
# ─────────────────────────────────────────────────────────────────────────────

def extract_kb_hints(text: str) -> Dict[str, Any]:
    """
    Best-effort extraction of structured KB hints from document text.
    Returns a dict with optional keys: hotels, pricing_lines, cities_mentioned.
    """
    hints: Dict[str, Any] = {}

    # Cities mentioned
    from src.services.kb.matchers import KNOWN_CITIES
    text_lower = text.lower()
    cities = sorted({KNOWN_CITIES[k] for k in KNOWN_CITIES if re.search(r"\b" + re.escape(k) + r"\b", text_lower)})
    if cities:
        hints["cities_mentioned"] = cities

    # Price lines — look for patterns like "$120", "€95/night", "INR 8500"
    price_pattern = re.findall(
        r"(?:USD|EUR|INR|GBP|AED|₹|\$|€)?\s*[\d,]+(?:\.\d+)?\s*(?:per\s+night|/night|\/nn?|per\s+person|/pp)?",
        text,
        re.IGNORECASE,
    )
    if price_pattern:
        hints["pricing_lines"] = price_pattern[:20]

    # Hotel name hints
    hotel_lines = re.findall(
        r"(?:hotel|resort|inn|lodge|palace|suites?|grand|hyatt|marriott|hilton|ibis|sheraton)[^\n]{0,80}",
        text,
        re.IGNORECASE,
    )
    if hotel_lines:
        hints["hotel_mentions"] = [h.strip() for h in hotel_lines[:10]]

    return hints


# ─────────────────────────────────────────────────────────────────────────────
# KB index management
# ─────────────────────────────────────────────────────────────────────────────

def _load_index() -> List[Dict]:
    if _KB_INDEX.exists():
        try:
            return json.loads(_KB_INDEX.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_index(entries: List[Dict]) -> None:
    _KB_DOCS_DIR.mkdir(parents=True, exist_ok=True)
    _KB_INDEX.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def add_to_kb(
    doc_id: str,
    filename: str,
    text: str,
    hints: Dict[str, Any],
    s3_key: str,
    storage_uri: str,
) -> None:
    """Append a processed document to the KB index."""
    entries = _load_index()
    # Remove any previous entry with the same doc_id
    entries = [e for e in entries if e.get("doc_id") != doc_id]
    entries.append({
        "doc_id":       doc_id,
        "filename":     filename,
        "s3_key":       s3_key,
        "storage_uri":  storage_uri,
        "processed_at": datetime.utcnow().isoformat() + "Z",
        "text_preview": text[:400],
        "char_count":   len(text),
        "hints":        hints,
        "full_text_path": str(_KB_DOCS_DIR / f"{doc_id}.txt"),
    })
    # Save full text separately for retrieval
    full_path = _KB_DOCS_DIR / f"{doc_id}.txt"
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(text, encoding="utf-8")
    _save_index(entries)
    logger.info("Added doc %s (%s chars) to KB index", doc_id, len(text))


def remove_from_kb(doc_id: str) -> None:
    entries = _load_index()
    entries = [e for e in entries if e.get("doc_id") != doc_id]
    _save_index(entries)
    # Remove full text
    txt_path = _KB_DOCS_DIR / f"{doc_id}.txt"
    if txt_path.exists():
        txt_path.unlink()


def get_user_kb_docs(query: Optional[str] = None, top_k: int = 3) -> List[Dict]:
    """
    Return the most relevant user-uploaded KB documents for a query.
    Falls back to most-recent documents when no query is given.
    """
    entries = _load_index()
    if not entries:
        return []

    if not query:
        return entries[-top_k:]

    # Simple TF-IDF-style scoring: count query word hits in text_preview + hints
    query_words = set(re.findall(r"\w+", query.lower()))
    scored = []
    for entry in entries:
        haystack = (
            entry.get("text_preview", "").lower()
            + " ".join(str(v) for v in entry.get("hints", {}).values()).lower()
        )
        score = sum(1 for w in query_words if w in haystack)
        scored.append((score, entry))

    scored.sort(key=lambda x: -x[0])
    return [e for _, e in scored[:top_k] if _ > 0] or entries[-top_k:]


# ─────────────────────────────────────────────────────────────────────────────
# Full pipeline: content → KB
# ─────────────────────────────────────────────────────────────────────────────

def process_and_index(
    doc_id: str,
    filename: str,
    content: bytes,
    content_type: str,
    s3_key: str,
    storage_uri: str,
) -> Dict[str, Any]:
    """
    Extract text, compute KB hints, persist to index.
    Returns a status dict suitable for the API response.
    """
    text = extract_text(content, content_type, filename)
    hints = extract_kb_hints(text) if text else {}

    if text:
        add_to_kb(doc_id, filename, text, hints, s3_key, storage_uri)
        status = "indexed"
    else:
        status = "no_text_extracted"

    return {
        "doc_id":        doc_id,
        "status":        status,
        "char_count":    len(text),
        "cities_found":  hints.get("cities_mentioned", []),
        "has_pricing":   bool(hints.get("pricing_lines")),
        "has_hotels":    bool(hints.get("hotel_mentions")),
    }
