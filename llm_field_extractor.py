"""llm_field_extractor.py
Uses the local LLM to extract structured travel fields from free-form text.
Returns a dict with any of the known fields found or inferred.
"""
from typing import Dict, Any, List
from local_llm_client import LocalLLMClient
import json

_llm = None

def get_llm_client() -> LocalLLMClient:
    global _llm
    if _llm is None:
        _llm = LocalLLMClient()
    return _llm


SYSTEM_PROMPT = (
    "You are an assistant that extracts structured travel request fields from a user's free-form message. "
    "Return only JSON with keys when confident: destination, checkin_date, checkout_date, duration, nights, pax, rooms, "
    "hotel_type, event_type, budget_per_person, budget_currency, meal_preference, transport_private. "
    "If a field cannot be determined, omit it. Use ISO dates if possible."
)


def extract_fields_via_llm(text: str) -> Dict[str, Any]:
    client = get_llm_client()
    # Keep messages short; provide examples
    messages: List[Dict[str, str]] = [
        {"role": "user", "content": text}
    ]
    try:
        resp = client.generate(SYSTEM_PROMPT, messages)
    except Exception:
        return {}

    # Try to find JSON substring in the response
    out = resp.strip()
    # Often LLMs respond with explanation + JSON; attempt to locate the first '{' and parse
    try:
        start = out.index('{')
        end = out.rindex('}')
        candidate = out[start:end+1]
        parsed = json.loads(candidate)
        # Basic sanitization: remove empty keys
        parsed = {k: v for k, v in parsed.items() if v not in [None, "", []]}
        return parsed
    except Exception:
        # If parsing fails, do a best-effort heuristic: look for key: value lines
        result: Dict[str, Any] = {}
        for line in out.splitlines():
            if ':' in line:
                k, v = line.split(':', 1)
                key = k.strip().lower().replace(' ', '_')
                val = v.strip()
                if key in [
                    'destination','checkin_date','checkout_date','duration','nights','pax','rooms',
                    'hotel_type','event_type','budget_per_person','budget_currency','meal_preference','transport_private'
                ]:
                    result[key] = val
        return result


if __name__ == '__main__':
    # quick manual test helper
    s = "I need a leisure trip to Oman from 14th Jan 2026 to 19th Jan 2026 for 4 pax, 2 rooms, 4* hotel."
    print(extract_fields_via_llm(s))
