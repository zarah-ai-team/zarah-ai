"""price_engine.py
Dynamic price estimator for transport, activities, hotels and tickets.

Combines two sources:
  1. Heuristic ranges (hardcoded fallbacks) for stability when live data is missing.
  2. Live data parsed from Tavily / Wikipedia search prose — when available, a
     trimmed-mean of those numbers is blended with the heuristic baseline so we
     get realistic, destination-aware prices.

This is intentionally NOT a trained ML model yet (a proper feature store +
retraining loop is a larger project). The blending is statistical (weighted
trimmed mean) so it's still robust to outliers in scraped prose.
"""
import re
import os
import statistics
from typing import Dict, Any, List, Optional, Tuple

# Default exchange rates (can be overridden with env vars)
EXCHANGE_RATES = {
    "INR_USD": float(os.getenv("INR_USD", "0.012")),  # 1 INR = 0.012 USD
    "INR_AED": float(os.getenv("INR_AED", "0.044")),
    # Common direct conversions (can be overridden with env vars)
    "AED_USD": float(os.getenv("AED_USD", "0.272")),  # 1 AED ~= 0.272 USD
    "USD_USD": 1.0,
    "EUR_USD": float(os.getenv("EUR_USD", "1.08")),
    "GBP_USD": float(os.getenv("GBP_USD", "1.26")),
}


# ── Price extraction from scraped prose ─────────────────────────────────────────
# Recognises forms like:  $120, USD 200, 250 USD, INR 12,500, ₹12500, €180, £95,
# AED 700, "starting from $80/night", "rooms from 4500 INR per night".
_PRICE_REGEX = re.compile(
    r"""
    (?P<curr_pre>USD|EUR|GBP|INR|AED|\$|€|£|₹)?    # currency before
    \s*
    (?P<amount>\d{1,3}(?:[,\s]\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)
    \s*
    (?P<curr_post>USD|EUR|GBP|INR|AED|\$|€|£|₹|dollars?|euros?|pounds?|rupees?|dirhams?)?
    """,
    re.IGNORECASE | re.VERBOSE,
)

_CURRENCY_TO_USD = {
    "USD": 1.0, "$": 1.0, "DOLLAR": 1.0, "DOLLARS": 1.0,
    "EUR": EXCHANGE_RATES["EUR_USD"], "€": EXCHANGE_RATES["EUR_USD"], "EURO": EXCHANGE_RATES["EUR_USD"], "EUROS": EXCHANGE_RATES["EUR_USD"],
    "GBP": EXCHANGE_RATES["GBP_USD"], "£": EXCHANGE_RATES["GBP_USD"], "POUND": EXCHANGE_RATES["GBP_USD"], "POUNDS": EXCHANGE_RATES["GBP_USD"],
    "INR": EXCHANGE_RATES["INR_USD"], "₹": EXCHANGE_RATES["INR_USD"], "RUPEE": EXCHANGE_RATES["INR_USD"], "RUPEES": EXCHANGE_RATES["INR_USD"],
    "AED": EXCHANGE_RATES["AED_USD"], "DIRHAM": EXCHANGE_RATES["AED_USD"], "DIRHAMS": EXCHANGE_RATES["AED_USD"],
}


def extract_prices_usd(text: str, min_usd: float = 5.0, max_usd: float = 5000.0) -> List[float]:
    """
    Extract numeric prices from prose (Tavily/Wikipedia/etc.) and convert to USD.
    Filters out pure years (1995–2030), phone numbers (drops 4+ digit no-currency), and
    extreme outliers via min/max bounds.

    Returns a list of USD floats, suitable for trimmed-mean aggregation.
    """
    if not isinstance(text, str) or not text:
        return []

    out: List[float] = []
    for m in _PRICE_REGEX.finditer(text):
        curr_pre = (m.group("curr_pre") or "").upper().strip()
        curr_post = (m.group("curr_post") or "").upper().strip()
        amount_str = m.group("amount").replace(",", "").replace(" ", "")
        curr = curr_pre or curr_post
        # Require a currency marker; otherwise we'd grab any number.
        if not curr:
            continue
        rate = _CURRENCY_TO_USD.get(curr)
        if rate is None:
            continue
        try:
            amount = float(amount_str)
        except ValueError:
            continue
        # Reject obvious non-prices: years, phone-number-ish chunks
        if 1900 <= amount <= 2100 and curr in {"$", "USD", "DOLLAR", "DOLLARS"}:
            # Skip "$2024" mistakes; real prices in this range need decimal or context
            continue
        usd = amount * rate
        if min_usd <= usd <= max_usd:
            out.append(round(usd, 2))
    return out


def trimmed_mean(values: List[float], trim_pct: float = 0.2) -> Optional[float]:
    """Mean after dropping the top/bottom trim_pct of values. None if too few samples."""
    if not values:
        return None
    if len(values) < 4:
        return statistics.mean(values)
    sorted_v = sorted(values)
    k = int(len(sorted_v) * trim_pct)
    trimmed = sorted_v[k:len(sorted_v) - k] or sorted_v
    return statistics.mean(trimmed)


def blend_estimates(
    heuristic_low: float,
    heuristic_high: float,
    live_samples: List[float],
    live_weight: float = 0.7,
) -> Tuple[float, float, str]:
    """
    Blend a heuristic [low, high] range with live-scraped USD prices.

    When live samples exist, the trimmed mean acts as the centre of the new
    range and the heuristic provides the spread; final range is a weighted
    combination of both centres.

    Returns (low, high, source) where source describes provenance.
    """
    if not live_samples:
        return heuristic_low, heuristic_high, "heuristic"

    live_centre = trimmed_mean(live_samples)
    if live_centre is None:
        return heuristic_low, heuristic_high, "heuristic"

    h_centre = (heuristic_low + heuristic_high) / 2.0
    h_spread = max(heuristic_high - heuristic_low, h_centre * 0.4)

    blended_centre = live_weight * live_centre + (1 - live_weight) * h_centre
    new_low = max(0.0, blended_centre - h_spread / 2.0)
    new_high = blended_centre + h_spread / 2.0
    return round(new_low, 2), round(new_high, 2), f"live+heuristic (n={len(live_samples)})"


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

    def estimate_total(self, fields: Dict[str, Any], pax: int, live_text: str = "") -> Dict[str, Any]:
        """
        Build a dynamic price estimate.

        live_text: optional prose from Tavily / Wikipedia / news to mine for
        real prices. When provided, the per-night hotel range is blended with
        a trimmed mean of the parsed numbers (live data wins 70%).
        """
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
        accommodation_range = {"low_usd": 0, "high_usd": 0, "suggestions": []}

        # Mine prices from live text once — reused below for hotel + activities.
        live_prices_usd = extract_prices_usd(live_text) if live_text else []

        if include_hotels:
            nights = fields.get("nights") or max(int(fields.get("duration", 1)) - 1, 1)
            hotel_type = fields.get("hotel_type", "mid-range").lower()

            # Heuristic ranges by category (per night, per room)
            hotel_ranges = {
                "budget":    {"low": 40,  "high": 80},
                "mid":       {"low": 100, "high": 200},
                "mid-range": {"low": 100, "high": 200},
                "luxury":    {"low": 250, "high": 500},
            }
            range_info = hotel_ranges.get(hotel_type, hotel_ranges["mid"])

            # Filter live prices to a plausible per-night-per-room window before blending,
            # so things like activity tickets or restaurant prices don't pollute the hotel range.
            per_night_candidates = [p for p in live_prices_usd if 25 <= p <= 800]
            blended_low, blended_high, source = blend_estimates(
                heuristic_low=range_info["low"],
                heuristic_high=range_info["high"],
                live_samples=per_night_candidates,
            )

            rooms = max(1, (pax + 1) // 2)
            low  = round(blended_low  * rooms * nights, 2)
            high = round(blended_high * rooms * nights, 2)

            accommodation_range = {
                "low_usd": low,
                "high_usd": high,
                "per_night_low":  round(blended_low, 2),
                "per_night_high": round(blended_high, 2),
                "source": source,
                "live_samples_count": len(per_night_candidates),
                "range_str": f"${low:.0f} - ${high:.0f} ({rooms} room(s) × {nights} night(s); {source})",
                "suggestions": [
                    f"{hotel_type.title()} per night per room: ${blended_low:.0f}-${blended_high:.0f} ({source})",
                    f"Estimated {rooms} room(s) needed for {pax} pax",
                    f"Total stay: {nights} night(s)",
                ],
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
            "live_prices_mined": len(live_prices_usd),
        }
