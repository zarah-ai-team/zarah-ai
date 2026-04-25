"""
Ollama itinerary generation layer.

Uses aiohttp if available, falls back to requests (sync in executor) otherwise.
Tries both /api/chat (Ollama native) and /v1/chat/completions (OpenAI-compat).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import traceback
from typing import Any, Dict, Optional, Tuple

from dotenv import load_dotenv
load_dotenv()

from src.services.itinerary.schema import ITINERARY_GENERATION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

_APP_ENV = os.getenv("APP_ENV", "dev").strip().lower()
if _APP_ENV == "dev":
    OLLAMA_URL = os.getenv("OLLAMA_BASE_URL_DEV", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    OLLAMA_API_KEY = ""
else:
    OLLAMA_URL = os.getenv("OLLAMA_BASE_URL_PROD", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")
if _APP_ENV == "dev":
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL_DEV", os.getenv("OLLAMA_MODEL", "llama3:8b"))
else:
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL_PROD", os.getenv("OLLAMA_MODEL", "llama3"))
LLM_TIMEOUT   = int(os.getenv("LOCAL_LLM_TIMEOUT", "300"))
MAX_RETRIES   = 2


def _ollama_headers() -> Dict[str, str]:
    h = {"Content-Type": "application/json"}
    if OLLAMA_API_KEY:
        h["Authorization"] = f"Bearer {OLLAMA_API_KEY}"
    return h


class ItineraryGenerator:
    def __init__(self, base_url: str = OLLAMA_URL, model: str = OLLAMA_MODEL):
        self.base_url = base_url.rstrip("/")
        self.model    = model

    async def generate(
        self,
        context: str,
        schema: Dict,
        pax: int,
        total_cost: float,
    ) -> Dict[str, Any]:
        user_prompt = self._build_user_prompt(context, schema, pax, total_cost)

        # Try Ollama native /api/chat (streaming) first, then OpenAI-compat
        native_url = f"{self.base_url}/api/chat"
        compat_url = f"{self.base_url}/v1/chat/completions"

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                text = await self._post_stream_native(native_url, user_prompt)
                logger.debug(f"Ollama stream response first 400: {text[:400]}")
                parsed = self._normalize_days(self._extract_json(text))
                if parsed and parsed.get("days"):
                    logger.info(f"Itinerary generated via streaming ({len(parsed['days'])} days)")
                    return parsed
                if parsed:
                    logger.warning("Streaming: JSON parsed but no 'days' key")
                    return parsed
                logger.warning(f"Streaming attempt {attempt}: JSON not found in response")
            except Exception as e:
                logger.warning(f"Streaming attempt {attempt}/{MAX_RETRIES} failed: {type(e).__name__}: {e}")
                logger.debug(traceback.format_exc())

        # Fallback: OpenAI-compat non-streaming (one attempt)
        try:
            payload = self._build_payload(user_prompt, "openai-compat")
            raw = await self._post(compat_url, payload)
            text = self._extract_text(raw, "openai-compat")
            parsed = self._normalize_days(self._extract_json(text))
            if parsed:
                logger.info(f"Itinerary generated via openai-compat fallback")
                return parsed
        except Exception as e:
            logger.warning(f"OpenAI-compat fallback failed: {type(e).__name__}: {e}")

        logger.error("All Ollama generation attempts failed")
        return {}

    # ------------------------------------------------------------------ #

    def _build_payload(self, user_prompt: str, mode: str) -> Dict:
        messages = [
            {"role": "system", "content": ITINERARY_GENERATION_SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ]
        num_predict = int(os.getenv("OLLAMA_NUM_PREDICT", "4096"))
        num_ctx     = int(os.getenv("OLLAMA_NUM_CTX",     "8192"))
        if mode == "native":
            return {
                "model":   self.model,
                "messages": messages,
                "stream":  False,
                "options": {
                    "temperature": 0.15,
                    "num_predict": num_predict,
                    "num_ctx":     num_ctx,
                },
            }
        else:  # openai-compat
            return {
                "model":       self.model,
                "messages":    messages,
                "temperature": 0.15,
                "max_tokens":  num_predict,
            }

    async def _post_stream_native(self, url: str, user_prompt: str) -> str:
        """
        Stream the native Ollama /api/chat response line by line.
        Uses sock_read timeout per chunk (not total), so slow CPU models
        never trigger an overall timeout as long as tokens keep arriving.
        """
        num_predict = int(os.getenv("OLLAMA_NUM_PREDICT", "4096"))
        num_ctx     = int(os.getenv("OLLAMA_NUM_CTX",     "8192"))
        per_chunk_timeout = int(os.getenv("OLLAMA_CHUNK_TIMEOUT", "120"))  # sec between tokens

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": ITINERARY_GENERATION_SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            "stream": True,
            "options": {
                "temperature": 0.15,
                "num_predict": num_predict,
                "num_ctx":     num_ctx,
            },
        }
        headers = _ollama_headers()

        try:
            import aiohttp
            timeout = aiohttp.ClientTimeout(
                total=None,                 # no wall-clock timeout
                connect=15,                 # connection must establish in 15s
                sock_read=per_chunk_timeout,
            )
            accumulated = []
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        raise RuntimeError(f"HTTP {resp.status}: {body[:300]}")
                    async for raw_line in resp.content:
                        line = raw_line.decode("utf-8", errors="replace").strip()
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            accumulated.append(token)
                        if chunk.get("done"):
                            break
            return "".join(accumulated)
        except ImportError:
            # Fallback: sync streaming via requests
            return await asyncio.get_event_loop().run_in_executor(
                None, self._post_stream_sync, url, payload
            )

    def _post_stream_sync(self, url: str, payload: Dict) -> str:
        """Sync streaming fallback using requests."""
        import requests as _req
        headers = _ollama_headers()
        accumulated = []
        with _req.post(url, json=payload, headers=headers, stream=True, timeout=(15, 120)) as resp:
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue
                try:
                    chunk = json.loads(raw_line.decode("utf-8", errors="replace"))
                except Exception:
                    continue
                token = chunk.get("message", {}).get("content", "")
                if token:
                    accumulated.append(token)
                if chunk.get("done"):
                    break
        return "".join(accumulated)

    async def _post(self, url: str, payload: Dict) -> Dict:
        """POST with aiohttp if available, otherwise sync requests via executor."""
        headers = _ollama_headers()
        try:
            import aiohttp
            timeout = aiohttp.ClientTimeout(total=LLM_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        raise RuntimeError(f"HTTP {resp.status}: {body[:300]}")
                    return await resp.json(content_type=None)
        except ImportError:
            return await asyncio.get_event_loop().run_in_executor(
                None, self._post_sync, url, payload
            )

    def _post_sync(self, url: str, payload: Dict) -> Dict:
        import requests
        headers = _ollama_headers()
        resp = requests.post(url, json=payload, headers=headers, timeout=LLM_TIMEOUT)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    @staticmethod
    def _extract_text(data: Dict, mode: str) -> str:
        """Pull the assistant text from either Ollama native or OpenAI-compat response."""
        if mode == "native":
            return data.get("message", {}).get("content", "")
        else:
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
        return str(data)

    @staticmethod
    def _build_user_prompt(context: str, schema: Dict, pax: int, total_cost: float) -> str:
        import re as _re
        day_match = _re.search(r"Total nights[:\s]+(\d+)", context)
        n_nights = int(day_match.group(1)) if day_match else None
        n_days   = (n_nights + 1) if n_nights else None
        day_line = (
            f'days array must have EXACTLY {n_days} elements (nights={n_nights}, +1 for departure day).\n'
            if n_days else
            'days array must have one element per travel day.\n'
        )

        return (
            f"KB CONTEXT:\n{context}\n\n"
            "Generate a complete day-by-day itinerary JSON using ONLY the context above.\n"
            f"- {day_line}"
            f"- total_estimated_cost = {total_cost:.0f}, cost_per_person = {total_cost / max(pax, 1):.0f}, currency = USD\n"
            "- days[] MUST be an array. Each element: day_number, city, title, morning, afternoon, evening, walking_level, hotel, transport, meals, inclusions, exclusions, estimated_day_cost\n"
            "- Keep each description 1-2 sentences. Be specific but brief.\n"
            "- Output raw JSON only. No markdown, no preamble. Start with { end with }."
        )

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        stripped = text.strip()

        # Direct parse
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass

        # Strip markdown fences
        fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", stripped)
        if fenced:
            try:
                return json.loads(fenced.group(1))
            except json.JSONDecodeError:
                pass

        # Outermost { ... } block
        start = stripped.find("{")
        if start == -1:
            return {}
        depth = 0
        for i, ch in enumerate(stripped[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(stripped[start : i + 1])
                    except json.JSONDecodeError:
                        break

        logger.error(f"JSON extraction failed. Response starts with: {stripped[:200]}")
        return {}

    @staticmethod
    def _normalize_days(parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Convert day1/day2/Day 1 key pattern to proper days[] array if needed."""
        if parsed.get("days") and isinstance(parsed["days"], list):
            return parsed

        import re as _re
        day_entries = []
        other_keys = {}
        for k, v in parsed.items():
            if _re.match(r"(?i)^day[\s_-]?\d+$", k) and isinstance(v, dict):
                num = int(_re.search(r"\d+", k).group())
                v.setdefault("day_number", num)
                day_entries.append(v)
            else:
                other_keys[k] = v

        if day_entries:
            day_entries.sort(key=lambda d: d.get("day_number", 0))
            other_keys["days"] = day_entries
            logger.warning(f"Converted {len(day_entries)} day keys → days[] array")
            return other_keys

        return parsed
