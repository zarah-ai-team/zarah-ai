"""price_engine.py
Simple dynamic price estimator for transport, activities and tickets.
This is NOT a real-time API but uses configurable exchange rates and simple heuristics
to compute realistic per-person and line-item costs. Make it pluggable to call real APIs later.
"""
from typing import Dict, Any, List
import os

# Default exchange rates (can be overridden with env vars)
EXCHANGE_RATES = {
    "INR_USD": float(os.getenv("INR_USD", "0.012")),  # 1 INR = 0.012 USD
    "INR_AED": float(os.getenv("INR_AED", "0.044")),
    # Common direct conversions (can be overridden with env vars)
    "AED_USD": float(os.getenv("AED_USD", "0.272")),  # 1 AED ~= 0.272 USD
    "USD_USD": 1.0,
}


class PriceEngine:
    def __init__(self, base_currency: str = "USD"):
        self.base_currency = base_currency

    def convert_inr_to_usd(self, inr: float) -> float:
        return round(inr * EXCHANGE_RATES["INR_USD"], 2)

    def convert_to_usd(self, amount: float, currency: str | None) -> float:
        """Convert an amount in given currency to USD using available exchange rates.

        Supports INR and AED by default; if currency is missing or unknown it assumes USD.
        """
        if amount is None:
            return 0.0
        if not currency:
            return round(float(amount), 2)
        cur = currency.upper()
        try:
            if cur == "INR":
                return round(float(amount) * EXCHANGE_RATES["INR_USD"], 2)
            if cur == "AED":
                return round(float(amount) * EXCHANGE_RATES["AED_USD"], 2)
            if cur == "USD":
                return round(float(amount), 2)
            # Fallback: try direct env var like EUR_USD, GBP_USD etc.
            key = f"{cur}_USD"
            if key in EXCHANGE_RATES:
                return round(float(amount) * EXCHANGE_RATES[key], 2)
        except Exception:
            pass
        # If we don't know the currency treat the amount as USD (best-effort)
        try:
            return round(float(amount), 2)
        except Exception:
            return 0.0

    def taxi_estimate(self, vehicle: str, hours: int, location: str = "UAE") -> Dict[str, Any]:
        # heuristic rates per hour by vehicle type (USD)
        rates = {
            "lexus": 40.0,  # premium
            "taxi": 15.0,
            "minivan": 35.0,
            "van": 30.0,
            "car": 20.0,
        }
        key = vehicle.lower() if vehicle else "car"
        r = rates.get(key, 25.0)
        total = round(r * hours, 2)
        return {"vehicle": vehicle, "hours": hours, "rate_per_hour_usd": r, "total_usd": total}

    def ferrari_world_ticket(self, pax: int, location: str = "UAE") -> Dict[str, Any]:
        # approximate ticket price range per pax (USD) — varies by season
        # Use AED approx 295 => ~80 USD (mid-range)
        range_low = 70.0
        range_high = 95.0
        total_low = round(range_low * pax, 2)
        total_high = round(range_high * pax, 2)
        return {"activity": "Ferrari World ticket", "per_pax_range_usd": f"${range_low:.0f}-${range_high:.0f}", "total_range_usd": f"${total_low:.0f}-${total_high:.0f}", "pax": pax}

    def sightseeing_estimate(self, pax: int) -> Dict[str, Any]:
        # approximate sightseeing/day per pax range
        range_low = 30.0
        range_high = 60.0
        total_low = round(range_low * pax, 2)
        total_high = round(range_high * pax, 2)
        return {"activity": "Sightseeing & attractions", "per_pax_range_usd": f"${range_low:.0f}-${range_high:.0f}", "total_range_usd": f"${total_low:.0f}-${total_high:.0f}", "pax": pax}

    def activity_estimates(self, activities: List[str], pax: int) -> List[Dict[str, Any]]:
        estimates = []
        for a in activities:
            if "ferrari" in a.lower():
                estimates.append(self.ferrari_world_ticket(pax))
            elif "sight" in a.lower() or "tour" in a.lower():
                estimates.append(self.sightseeing_estimate(pax))
            else:
                # default activity cost range
                range_low = 20.0
                range_high = 50.0
                total_low = round(range_low * pax, 2)
                total_high = round(range_high * pax, 2)
                estimates.append({"activity": a, "per_pax_range_usd": f"${range_low:.0f}-${range_high:.0f}", "total_range_usd": f"${total_low:.0f}-${total_high:.0f}", "pax": pax})
        return estimates

    def estimate_total(self, fields: Dict[str, Any], pax: int) -> Dict[str, Any]:
        # Build a dynamic estimate using parsed fields, focused on ranges and hotel suggestions
        activities = fields.get("activities", [])
        transports = fields.get("transport_requirements", [])

        activity_lines = self.activity_estimates(activities, pax)
        transport_lines = []
        for t in transports:
            vehicle = t.get("vehicle", "taxi")
            hours = int(t.get("hours", 1))
            transport_lines.append(self.taxi_estimate(vehicle, hours))

        # For hotel suggestions, provide range instead of fixed estimate
        include_hotels = not fields.get("exclude_hotels", False)
        hotel_suggestions = []
        accommodation_range = {"low_usd": 0, "high_usd": 0, "suggestions": []}

        if include_hotels:
            nights = fields.get("nights") or max(int(fields.get("duration", 1)) - 1, 1)
            hotel_type = fields.get("hotel_type", "mid-range").lower()
            
            # Hotel price ranges by type (per night per room)
            hotel_ranges = {
                "budget": {"low": 40, "high": 80},
                "mid": {"low": 100, "high": 200},
                "mid-range": {"low": 100, "high": 200},
                "luxury": {"low": 250, "high": 500},
            }
            
            range_info = hotel_ranges.get(hotel_type, hotel_ranges["mid"])
            rooms = max(1, (pax + 1) // 2)  # Estimate rooms needed
            
            low = round(range_info["low"] * rooms * nights, 2)
            high = round(range_info["high"] * rooms * nights, 2)
            
            accommodation_range = {
                "low_usd": low,
                "high_usd": high,
                "range_str": f"${low:.0f} - ${high:.0f} (estimated for {rooms} room(s), {nights} night(s))",
                "suggestions": [
                    f"{hotel_type.title()} hotels: {range_info['low']}-{range_info['high']} USD per night (per room)",
                    f"Estimated {rooms} room(s) needed for {pax} pax",
                    f"Total stay: {nights} night(s)"
                ]
            }

        # Budget per pax input may be in INR; try to convert to USD
        budget_pp = fields.get("budget_per_person", 0)
        budget_currency = fields.get("budget_currency", "USD")
        if budget_currency and budget_currency.upper() in ["INR"]:
            budget_pp_usd = self.convert_inr_to_usd(float(budget_pp))
        else:
            budget_pp_usd = float(budget_pp)

        total_budget_usd = round(budget_pp_usd * pax, 2)

        return {
            "activity_lines": activity_lines,
            "transport_lines": transport_lines,
            "accommodation_range": accommodation_range,
            "budget_total_usd": total_budget_usd,
            "budget_per_pax_usd": round(budget_pp_usd, 2),
            "pax": pax,
        }
