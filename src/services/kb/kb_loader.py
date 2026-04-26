"""
Knowledge base loader — ingests Excel dataset, itinerary documents, and hard-coded
pricing rules for European destinations. Exposes a singleton for the rest of the app.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
DATASET_PATH = DATA_DIR / "Comprehensive_Travel_Itinerary_ML_Dataset.xlsx"
ITINERARIES_DIR = DATA_DIR / "itineraries"


class KBLoader:
    def __init__(self):
        self._dataset: Optional[pd.DataFrame] = None
        self._docs: List[Dict[str, Any]] = []
        self._pricing: Dict[str, Any] = {}
        self._loaded = False

    # ------------------------------------------------------------------ #
    # Public API                                                            #
    # ------------------------------------------------------------------ #

    def load(self) -> bool:
        try:
            self._load_excel()
            self._load_docs()
            self._load_pricing()
            self._loaded = True
            row_count = len(self._dataset) if self._dataset is not None else 0
            logger.info(f"KB loaded | excel rows: {row_count} | docs: {len(self._docs)}")
            return True
        except Exception as e:
            logger.error(f"KB load failed: {e}")
            return False

    def reload_docs(self) -> int:
        """
        Re-scan data/itineraries/ (including the saved/ subdir) without
        touching the Excel dataset or pricing rules. Called after a user saves
        a new itinerary so the next request can use it as KB context.
        Returns the new doc count.
        """
        try:
            self._docs = []
            self._load_docs()
            logger.info(f"KB docs reloaded | docs: {len(self._docs)}")
        except Exception as e:
            logger.error(f"KB docs reload failed: {e}")
        return len(self._docs)

    @property
    def dataset(self) -> pd.DataFrame:
        return self._dataset if self._dataset is not None else pd.DataFrame()

    @property
    def itinerary_docs(self) -> List[Dict[str, Any]]:
        return self._docs

    @property
    def pricing_rules(self) -> Dict[str, Any]:
        return self._pricing

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    # ------------------------------------------------------------------ #
    # Loaders                                                               #
    # ------------------------------------------------------------------ #

    def _load_excel(self):
        if DATASET_PATH.exists():
            df = pd.read_excel(DATASET_PATH)
            self._dataset = df if not df.empty else pd.DataFrame()
        else:
            logger.warning(f"Dataset not found: {DATASET_PATH}")
            self._dataset = pd.DataFrame()

    def _load_docs(self):
        try:
            if not ITINERARIES_DIR.exists():
                return
        except Exception:
            return
        # Recursively load every itinerary file (PDFs, XLSX, DOCX) AND every
        # saved itinerary JSON dropped into data/itineraries/saved/ so the KB
        # learns from BOTH historical exports and itineraries the user has
        # generated and saved through the UI.
        for f in ITINERARIES_DIR.rglob("*"):
            try:
                if not f.is_file():
                    continue
                text = _extract_text(f)
                if isinstance(text, str) and text.strip():
                    rel = f.relative_to(ITINERARIES_DIR)
                    self._docs.append({"filename": str(rel), "text": text, "ext": f.suffix.lower()})
            except Exception as e:
                logger.warning(f"Skipping {f.name}: {e}")

    def _load_pricing(self):
        # EUR → USD conversion applied at retrieval time via pricing_engine.py
        self._pricing = {
            "hotels": {
                "4_star_deluxe": {
                    "budapest": {"min": 120, "max": 200, "avg": 155},
                    "prague":   {"min": 130, "max": 220, "avg": 170},
                    "vienna":   {"min": 160, "max": 280, "avg": 210},
                },
                "5_star": {
                    "budapest": {"min": 250, "max": 450, "avg": 320},
                    "prague":   {"min": 280, "max": 500, "avg": 360},
                    "vienna":   {"min": 320, "max": 600, "avg": 420},
                },
                "4_star": {
                    "budapest": {"min": 90, "max": 160, "avg": 120},
                    "prague":   {"min": 100, "max": 180, "avg": 130},
                    "vienna":   {"min": 120, "max": 210, "avg": 155},
                },
            },
            "transport": {
                # EUR per booking
                "inter_city_transfer": {
                    "budapest_prague":  {"cost_eur": 420},
                    "prague_vienna":    {"cost_eur": 360},
                    "budapest_vienna":  {"cost_eur": 300},
                    "vienna_salzburg":  {"cost_eur": 280},
                },
                # EUR per day (includes driver, fuel, tolls)
                "private_van_per_day_eur": 280,
            },
            # EUR per person per attraction
            "sightseeing": {
                "prague": {
                    "prague_castle":        {"cost_pp_eur": 18, "hours": 3.0},
                    "old_town_tour":        {"cost_pp_eur": 25, "hours": 2.5},
                    "vltava_river_cruise":  {"cost_pp_eur": 20, "hours": 1.0},
                    "charles_bridge":       {"cost_pp_eur": 0,  "hours": 1.0, "note": "free"},
                    "petrin_hill_funicular":{"cost_pp_eur": 4,  "hours": 1.5},
                    "mala_strana_walk":     {"cost_pp_eur": 0,  "hours": 1.5, "note": "free, minimal walking route"},
                    "josefov_jewish_quarter":{"cost_pp_eur": 16,"hours": 2.0},
                },
                "vienna": {
                    "schonbrunn_palace":    {"cost_pp_eur": 22, "hours": 2.5},
                    "hofburg_palace":       {"cost_pp_eur": 16, "hours": 2.0},
                    "belvedere_palace":     {"cost_pp_eur": 17, "hours": 2.0},
                    "st_stephens_cathedral":{"cost_pp_eur": 6,  "hours": 1.0},
                    "danube_river_cruise":  {"cost_pp_eur": 28, "hours": 1.5},
                    "vienna_ring_road_tour":{"cost_pp_eur": 35, "hours": 2.0, "note": "private van drive-by tour"},
                    "prater_giant_wheel":   {"cost_pp_eur": 12, "hours": 0.5},
                },
                "budapest": {
                    "parliament_tour":          {"cost_pp_eur": 10, "hours": 1.5},
                    "fishermans_bastion":        {"cost_pp_eur": 3,  "hours": 1.0},
                    "buda_castle":               {"cost_pp_eur": 8,  "hours": 2.0},
                    "buda_castle_funicular":     {"cost_pp_eur": 5,  "hours": 0.25},
                    "danube_cruise_budapest":    {"cost_pp_eur": 20, "hours": 1.0},
                    "heroes_square":             {"cost_pp_eur": 0,  "hours": 0.75, "note": "free"},
                    "great_market_hall":         {"cost_pp_eur": 0,  "hours": 1.0,  "note": "free, light walk"},
                },
            },
            # EUR per guide-day
            "guides": {
                "full_day_eur":  200,
                "half_day_eur":  120,
                "note": "Licensed local guide, 8h full / 4h half day. Indian-origin guide: +15%",
            },
            # EUR per person per day (restaurant, mid-range)
            "meals_per_pax_per_day_eur": {
                "budapest": {"budget": 12, "mid": 28, "high": 55},
                "prague":   {"budget": 15, "mid": 35, "high": 65},
                "vienna":   {"budget": 18, "mid": 45, "high": 85},
                "_default": {"budget": 15, "mid": 35, "high": 65},
            },
            # EUR per person per day (tips, water, city tax, misc)
            "misc_per_pax_per_day_eur": 15,
        }


_MAX_DOC_CHARS = 4000   # cap per document to keep TF-IDF fast


def _extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                pages = []
                for p in pdf.pages[:10]:   # limit to 10 pages
                    t = p.extract_text() or ""
                    pages.append(t)
                    if sum(len(x) for x in pages) > _MAX_DOC_CHARS:
                        break
                return " ".join(pages)[:_MAX_DOC_CHARS]
        except ImportError:
            return ""
    if ext in (".doc", ".docx"):
        try:
            from docx import Document
            paras = [p.text for p in Document(str(path)).paragraphs]
            return " ".join(paras)[:_MAX_DOC_CHARS]
        except Exception:
            return ""
    if ext in (".xlsx", ".xls"):
        try:
            # Read only first 200 rows to avoid huge strings from cost sheets
            df = pd.read_excel(path, nrows=200)
            return df.to_string()[:_MAX_DOC_CHARS]
        except Exception:
            return ""
    if ext == ".txt" or ext == ".md":
        return path.read_text(encoding="utf-8", errors="ignore")[:_MAX_DOC_CHARS]
    if ext == ".json":
        # Saved itinerary JSON dumps — flatten the structure into a readable
        # text block so the KB retriever can match on it.
        try:
            import json as _json
            data = _json.loads(path.read_text(encoding="utf-8", errors="ignore"))
            return _flatten_itinerary_json(data)[:_MAX_DOC_CHARS]
        except Exception:
            return path.read_text(encoding="utf-8", errors="ignore")[:_MAX_DOC_CHARS]
    return ""


def _flatten_itinerary_json(data) -> str:
    """Render a saved-itinerary dict as plain prose for KB indexing."""
    if not isinstance(data, dict):
        return str(data)[:8000]
    parts = []
    for k in ("title", "destination", "duration_days", "pax", "event_type",
              "trip_start_date", "itinerary_summary", "overview"):
        v = data.get(k)
        if v:
            parts.append(f"{k}: {v}")
    cb = data.get("cost_breakdown") or {}
    for k, v in cb.items():
        if v:
            parts.append(f"cost_{k}: {v}")
    for d in (data.get("days") or []):
        if not isinstance(d, dict):
            continue
        parts.append(
            f"Day {d.get('day','')} ({d.get('city','')}, {d.get('date','')}): "
            f"{d.get('summary','')} | morning: {d.get('morning','')[:200]} "
            f"| afternoon: {d.get('afternoon','')[:200]} "
            f"| evening: {d.get('evening','')[:200]} "
            f"| transport: {d.get('transport_note','')[:120]} "
            f"| hotel: {(d.get('hotel') or {}).get('name','')}"
        )
    for h in (data.get("hotels") or []):
        if isinstance(h, dict):
            parts.append(f"Hotel {h.get('city','')}: {h.get('name','')} ({h.get('category','')}) — {h.get('price_per_night_inr','')}")
    for line in (data.get("inclusions") or []):
        parts.append(f"included: {line}")
    return "\n".join(parts)


# Singleton
_instance: Optional[KBLoader] = None


def get_kb_loader() -> KBLoader:
    global _instance
    if _instance is None:
        _instance = KBLoader()
        _instance.load()
    return _instance
