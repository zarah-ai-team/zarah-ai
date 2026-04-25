"""feature_extractor.py
Extracts structured features and produces a small text summary for matching and ML.
"""
from typing import Dict, Any
import numpy as np


class FeatureExtractor:
    def __init__(self):
        pass

    def extract(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        """Return a dict with numeric feature vector and a text summary."""
        # Normalize / coerce
        dest = fields.get("destination", "unknown")
        try:
            duration = int(fields.get("duration", 1))
        except Exception:
            duration = 1
        try:
            pax = int(fields.get("pax", 1))
        except Exception:
            pax = 1
        try:
            budget = float(fields.get("budget_per_person", 0))
        except Exception:
            budget = 0.0

        # Simple encoding for event_type and hotel_type
        event = fields.get("event_type", "leisure").lower()
        hotel = fields.get("hotel_type", "mid-range").lower()

        event_map = {"leisure": 0, "honeymoon": 1, "conference": 2, "adventure": 3, "business": 4}
        hotel_map = {"budget": 0, "mid-range": 1, "luxury": 2}

        ev = event_map.get(event, 0)
        hv = hotel_map.get(hotel, 1)

        vector = np.array([duration, pax, budget, ev, hv], dtype=float)

        text_summary = (
            f"Destination: {dest}. Duration: {duration} days for {pax} pax. "
            f"Event: {event}. Hotel: {hotel}. Budget per pax: ${budget:.2f}. Meals: {fields.get('meal_preference', 'no preference')}."
        )

        return {"vector": vector, "text_summary": text_summary, "fields": fields}
