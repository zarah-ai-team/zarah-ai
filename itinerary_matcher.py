"""itinerary_matcher.py
Loads historical itineraries from an Excel dataset and from files in data/itineraries.
Provides a find_similar method returning top matches.
"""
import os
import pandas as pd
import glob
from typing import List, Dict, Any
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import pdfplumber
import logging

logger = logging.getLogger("itinerary_matcher")


class ItineraryMatcher:
    def __init__(self, dataset_path: str = "data/Comprehensive_Travel_Itinerary_ML_Dataset.xlsx", folder_path: str = "data/itineraries"):
        self.dataset_path = dataset_path
        self.folder_path = folder_path
        self.past_texts = []
        self.past_meta = []
        self._load()

    def _load(self):
        # Load Excel dataset if exists
        if os.path.exists(self.dataset_path):
            try:
                df = pd.read_excel(self.dataset_path)
                # Attempt to consolidate a 'description' column
                if "description" in df.columns:
                    for _, row in df.iterrows():
                        self.past_texts.append(str(row.get("description", "")))
                        self.past_meta.append(row.to_dict())
            except Exception:
                pass

        # Load files from folder
        if os.path.isdir(self.folder_path):
            patterns = ["**/*.pdf", "**/*.docx", "**/*.xlsx"]
            for pat in patterns:
                for path in glob.glob(os.path.join(self.folder_path, pat), recursive=True):
                    try:
                        text = self._extract_text(path)
                        if text:
                            self.past_texts.append(text)
                            self.past_meta.append({"source": path})
                    except Exception:
                        continue

        # Build TF-IDF vectorizer
        if self.past_texts:
            try:
                self.vectorizer = TfidfVectorizer(max_features=2000, stop_words="english")
                self.tfidf = self.vectorizer.fit_transform(self.past_texts)
            except Exception:
                self.vectorizer = None
                self.tfidf = None
        else:
            self.vectorizer = None
            self.tfidf = None

    def _extract_text(self, path: str) -> str:
        lpath = path.lower()
        if lpath.endswith(".pdf"):
            return self._extract_pdf(path)
        if lpath.endswith(".docx"):
            return self._extract_docx(path)
        if lpath.endswith(".xlsx"):
            return self._extract_xlsx(path)
        return ""

    def _extract_pdf(self, path: str) -> str:
        texts = []
        try:
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    texts.append(page.extract_text() or "")
        except Exception:
            return ""
        return "\n".join(texts)

    def _extract_docx(self, path: str) -> str:
        # Import python-docx lazily and handle broken/missing installations gracefully.
        try:
            import docx as docx_module
        except ModuleNotFoundError as e:
            logger.warning("python-docx is not installed (or a conflicting 'docx' package exists): %s", e)
            logger.warning("If you have 'docx' installed, please uninstall it and install 'python-docx' instead: pip uninstall docx; pip install python-docx")
            return ""
        except Exception as e:
            logger.warning("Failed to import python-docx: %s", e)
            return ""

        try:
            doc = docx_module.Document(path)
            return "\n".join([p.text for p in doc.paragraphs])
        except Exception as e:
            logger.debug("Failed to read docx %s: %s", path, e)
            return ""

    def _extract_xlsx(self, path: str) -> str:
        try:
            df = pd.read_excel(path, sheet_name=0)
            return df.astype(str).fillna("").agg(" ".join, axis=1).str.cat(sep="\n")
        except Exception:
            return ""

    def find_similar(self, fields: Dict[str, Any], text_summary: str | None = None, top_k: int = 3) -> List[Dict[str, Any]]:
        """Return a list of top_k similar itineraries (meta and score)."""
        results = []
        if not text_summary or self.vectorizer is None or self.tfidf is None:
            # fallback: match by destination and pax in meta from dataset
            for meta in self.past_meta[:top_k]:
                results.append({"meta": meta, "score": 0.0})
            return results

        try:
            qtf = self.vectorizer.transform([text_summary])
            sims = cosine_similarity(qtf, self.tfidf)[0]
            idx = sims.argsort()[::-1][:top_k]
            for i in idx:
                results.append({"meta": self.past_meta[i], "score": float(sims[i])})
        except Exception:
            pass

        return results

    def summarize_matches(self, matches: List[Dict[str, Any]]) -> str:
        """Create an anonymized, short summary of matches for the LLM to use.

        This avoids returning file names or raw metadata but signals that historical
        examples exist and provides lightweight hints (count, sample destinations).
        """
        if not matches:
            return "No historical itineraries available."

        count = len(matches)
        samples = []
        for m in matches[:5]:
            meta = m.get("meta", {}) if isinstance(m, dict) else {}
            # try common fields from dataset rows
            found_sample = None
            for key in ("trip_name", "destination_city", "destination_country", "hotel_name"):
                if key in meta and meta.get(key):
                    found_sample = str(meta.get(key))
                    break
            if not found_sample and "source" in meta and meta.get("source"):
                # avoid exposing file paths; replace with generic label
                found_sample = "past itinerary"

            if found_sample:
                samples.append(found_sample)
            else:
                # fallback to score if no descriptive field
                samples.append(f"score:{m.get('score', 0):.2f}")

        # make a compact summary
        unique_samples = []
        for s in samples:
            if s not in unique_samples:
                unique_samples.append(s)
        sample_list = unique_samples[:3]
        sample_text = ", ".join(sample_list) if sample_list else "(examples not available)"
        return f"{count} historical itineraries available; sample entries: {sample_text}. Use them to inform itinerary planning but do not quote filenames or raw past documents."
