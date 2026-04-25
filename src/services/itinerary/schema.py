"""
JSON schema for Ollama structured output + all prompt templates.
"""

# ── Output schema ─────────────────────────────────────────────────────────────
ITINERARY_JSON_SCHEMA: dict = {
    "type": "object",
    "required": [
        "title", "trip_overview", "assumptions",
        "total_estimated_cost", "cost_per_person", "currency",
        "cost_breakdown_summary", "days",
    ],
    "properties": {
        "title":                {"type": "string"},
        "trip_overview":        {"type": "string"},
        "assumptions":          {"type": "array", "items": {"type": "string"}},
        "total_estimated_cost": {"type": "number"},
        "cost_per_person":      {"type": "number"},
        "currency":             {"type": "string"},
        "cost_breakdown_summary": {
            "type": "object",
            "properties": {
                "accommodation": {"type": "number"},
                "transport":     {"type": "number"},
                "sightseeing":   {"type": "number"},
                "guide_fees":    {"type": "number"},
                "meals":         {"type": "number"},
                "miscellaneous": {"type": "number"},
                "total":         {"type": "number"},
            },
        },
        "days": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["day_number", "city", "title", "morning", "afternoon", "evening", "walking_level"],
                "properties": {
                    "day_number":   {"type": "integer"},
                    "date":         {"type": "string"},
                    "city":         {"type": "string"},
                    "title":        {"type": "string"},
                    "morning":      {"type": "string"},
                    "afternoon":    {"type": "string"},
                    "evening":      {"type": "string"},
                    "meals": {
                        "type": "object",
                        "properties": {
                            "breakfast": {"type": "string"},
                            "lunch":     {"type": "string"},
                            "dinner":    {"type": "string"},
                        },
                    },
                    "transport": {
                        "type": "object",
                        "properties": {
                            "type":        {"type": "string"},
                            "description": {"type": "string"},
                            "duration":    {"type": "string"},
                            "notes":       {"type": "string"},
                        },
                    },
                    "walking_level":        {"type": "string", "enum": ["minimal", "moderate", "high"]},
                    "senior_friendly_notes":{"type": "string"},
                    "hotel": {
                        "type": "object",
                        "properties": {
                            "name":     {"type": "string"},
                            "area":     {"type": "string"},
                            "category": {"type": "string"},
                            "notes":    {"type": "string"},
                        },
                    },
                    "estimated_day_cost": {"type": "number"},
                    "inclusions":  {"type": "array", "items": {"type": "string"}},
                    "exclusions":  {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "optional_experiences": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name":                 {"type": "string"},
                    "city":                 {"type": "string"},
                    "description":          {"type": "string"},
                    "duration":             {"type": "string"},
                    "estimated_cost":       {"type": "number"},
                    "suitable_for_seniors": {"type": "boolean"},
                    "walking_level":        {"type": "string"},
                    "booking_notes":        {"type": "string"},
                },
            },
        },
        "important_notes":   {"type": "array", "items": {"type": "string"}},
        "missing_information": {"type": "array", "items": {"type": "string"}},
        "confidence_summary": {
            "type": "object",
            "properties": {
                "overall":           {"type": "number"},
                "costing":           {"type": "number"},
                "routing":           {"type": "number"},
                "hotel_suggestions": {"type": "number"},
                "sightseeing":       {"type": "number"},
                "notes":             {"type": "array", "items": {"type": "string"}},
            },
        },
        "sources_summary": {"type": "array", "items": {"type": "string"}},
    },
}

# ── Prompts ───────────────────────────────────────────────────────────────────

NORMALIZATION_PROMPT = """\
You are a travel request parser. Extract structured trip requirements from the client message below.

Return a single JSON object — no markdown, no explanation. Use null for missing values.

Schema:
{
  "client_name": string|null,
  "origin": string,
  "destinations": [string],
  "route": string,
  "trip_start_date": "YYYY-MM-DD"|null,
  "total_nights": number,
  "adults": number,
  "seniors": number,
  "children": number,
  "room_config": {"double": number, "twin": number},
  "hotel_category": "3_star"|"4_star"|"4_star_deluxe"|"5_star",
  "transport_preference": "private_van"|"private_car"|"shared_transfer",
  "vehicle_type": string,
  "driver_preference": string|null,
  "pace": "relaxed"|"moderate"|"active",
  "walking_tolerance": "minimal"|"moderate"|"high",
  "guide_required": boolean,
  "meal_preferences": [string],
  "mandatory_sightseeing": [string],
  "optional_excursions": [string],
  "departure_details": string|null,
  "nights_per_city": {"city_name": number},
  "budget_preference": string|null
}

Rules:
- "4★ Deluxe" or "4* Deluxe" → "4_star_deluxe"
- "5★" or "luxury" → "5_star"
- If pace not mentioned and seniors present → "relaxed"
- If walking not mentioned and seniors present → "minimal"
- Extract every city mentioned in the route even if implicit
- Parse nights per city if stated (e.g. "Prague: 4 Nights")
- Senior = "60+", "senior citizen", "elderly"

Client message:
"""

ITINERARY_GENERATION_SYSTEM_PROMPT = """\
You are a professional tour designer. Output ONLY a single compact JSON object — no markdown, no explanation.

REQUIRED ROOT KEYS: title, trip_overview, total_estimated_cost, cost_per_person, currency, cost_breakdown_summary, days, assumptions, important_notes, optional_experiences, missing_information

DAYS ARRAY FORMAT (one object per day — use ARRAY not day1/day2 keys):
{"day_number":1,"city":"Prague","title":"Arrival","morning":"...","afternoon":"...","evening":"...","walking_level":"minimal","hotel":{"name":"TBC","area":"Old Town","category":"4-star deluxe","notes":""},"transport":{"type":"Private van","description":"Airport pickup","duration":"45 min","notes":""},"meals":{"breakfast":"Included","lunch":"Own account","dinner":"Included"},"inclusions":["Transfer","Hotel"],"exclusions":["Flights"],"estimated_day_cost":420}

RULES:
1. Hotel name = "To be confirmed – [area]" if unknown.
2. Prices = ONLY from cost_basis in context. Do NOT invent costs.
3. Keep descriptions concise (1-2 sentences per time slot).
4. walking_level: "minimal" | "moderate" | "high".
5. Senior pacing: max 4h activity/day, rest breaks, no long walks.
6. First char of output: {   Last char: }
"""
