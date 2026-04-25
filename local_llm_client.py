"""local_llm_client.py
Simple client for a local LLM that exposes an HTTP chat/completions endpoint (e.g., Ollama).
Integrated with real-time search (Wikipedia, Attractions, News - all FREE, no API keys).
"""
import requests
import logging
import os
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import List, Dict, Any

from dotenv import load_dotenv
load_dotenv()

from real_time_search import enrich_destination

_APP_ENV = os.getenv("APP_ENV", "dev").strip().lower()

if _APP_ENV == "dev":
    _OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL_DEV", "http://localhost:11434")
    _OLLAMA_API_KEY = ""
else:
    _OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL_PROD", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    _OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")


class LocalLLMClient:
    def __init__(self, base_url: str = ""):
        self.base_url = (base_url or _OLLAMA_BASE_URL).rstrip("/")
        self.logger = logging.getLogger("local_llm_client")
        # default read timeout for LLM responses (seconds); can be overridden via env var
        try:
            self.read_timeout = int(os.getenv("LOCAL_LLM_TIMEOUT", "300"))
        except Exception:
            self.read_timeout = 300

    def generate(self, system_prompt: str, messages: List[Dict[str, Any]], model: str = "") -> str:
        """Call Ollama and return assistant text.

        Dev mode  → native /api/chat  (stream=false, supports all options)
        Prod mode → OpenAI-compatible /v1/chat/completions
        """
        if not model:
            if _APP_ENV == "dev":
                model = os.getenv("OLLAMA_MODEL_DEV", os.getenv("OLLAMA_MODEL", "llama3:8b"))
            else:
                model = os.getenv("OLLAMA_MODEL_PROD", os.getenv("OLLAMA_MODEL", "llama3"))
        try:
            num_predict = int(os.getenv("OLLAMA_NUM_PREDICT", "16000"))
        except (ValueError, TypeError):
            num_predict = 16000
        try:
            num_ctx = int(os.getenv("OLLAMA_NUM_CTX", "32768"))
        except (ValueError, TypeError):
            num_ctx = 32768

        if _APP_ENV == "dev":
            return self._generate_native(system_prompt, messages, model, num_ctx, num_predict)
        return self._generate_openai(system_prompt, messages, model, num_ctx, num_predict)

    def _generate_native(self, system_prompt: str, messages: List[Dict], model: str,
                         num_ctx: int, num_predict: int) -> str:
        """Ollama native /api/chat — most reliable for local instances."""
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system_prompt}] + messages,
            "stream": False,
            "options": {
                "num_ctx": num_ctx,
                "num_predict": num_predict,
                "temperature": 0.7,
            },
        }
        self.logger.info("Calling Ollama native API: %s  model=%s", url, model)
        try:
            resp = requests.post(url, json=payload, timeout=(15, self.read_timeout))
            self.logger.info("Ollama response status: %s", resp.status_code)
            if resp.status_code != 200:
                self.logger.error("Ollama error body: %s", resp.text[:1000])
            resp.raise_for_status()
        except Exception as e:
            self.logger.error("Ollama native request failed: %s", e)
            raise RuntimeError(f"Ollama unreachable at {self.base_url}: {e}")

        try:
            data = resp.json()
        except Exception:
            return resp.text

        # Native response: {"message": {"role": "assistant", "content": "..."}}
        if isinstance(data, dict):
            msg = data.get("message")
            if isinstance(msg, dict):
                return msg.get("content", "")
        return str(data)

    def _generate_openai(self, system_prompt: str, messages: List[Dict], model: str,
                         num_ctx: int, num_predict: int) -> str:
        """OpenAI-compatible /v1/chat/completions — used for remote/prod Ollama."""
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system_prompt}] + messages,
            "temperature": 0.7,
            "max_tokens": num_predict,
            # Ollama-specific: extend context window so long itineraries aren't truncated
            "options": {"num_ctx": num_ctx, "num_predict": num_predict},
        }
        session = requests.Session()
        retries = Retry(total=2, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        headers = {"Content-Type": "application/json"}
        if _OLLAMA_API_KEY:
            headers["Authorization"] = f"Bearer {_OLLAMA_API_KEY}"

        self.logger.info("Calling OpenAI-compat API: %s  model=%s", url, model)
        try:
            resp = session.post(url, json=payload, headers=headers, timeout=(15, self.read_timeout))
            self.logger.info("LLM response status: %s", resp.status_code)
            if resp.status_code != 200:
                self.logger.error("LLM error body: %s", resp.text[:1000])
            resp.raise_for_status()
        except Exception as e:
            self.logger.error("LLM request failed: %s", e)
            raise RuntimeError(f"LLM unreachable at {self.base_url}: {e}")

        try:
            data = resp.json()
        except Exception:
            return resp.text

        if isinstance(data, dict):
            choices = data.get("choices") or data.get("results")
            if choices:
                first = choices[0]
                if isinstance(first, dict) and "message" in first:
                    return first["message"].get("content", "")
                if isinstance(first, dict) and "text" in first:
                    return first.get("text", "")
        return str(data)

    def ping(self, model: str = "", timeout: float = 5.0) -> Dict[str, Any]:
        """Quick health check — tries /api/tags then /v1/models (remote-hosted Ollama)."""
        headers = {}
        if _OLLAMA_API_KEY:
            headers["Authorization"] = f"Bearer {_OLLAMA_API_KEY}"
        for path in ["/api/tags", "/v1/models"]:
            try:
                resp = requests.get(f"{self.base_url}{path}", headers=headers, timeout=timeout)
                if resp.status_code < 500:
                    return {"ok": resp.status_code < 400, "status_code": resp.status_code, "endpoint": path}
            except Exception:
                continue
        return {"ok": False, "error": f"No reachable endpoint at {self.base_url}"}

    def enrich_with_realtime_data(self, destination: str) -> Dict[str, Any]:
        """
        Enrich the LLM context with real-time data from free sources.
        NO API KEYS REQUIRED - Uses:
        - Wikipedia API (free public endpoint)
        - Overpass/OpenStreetMap (free attractions database)
        - DuckDuckGo/RSS feeds (free news)
        
        Returns: {wikipedia, attractions, news} for destination
        """
        try:
            self.logger.info(f"Fetching real-time data for: {destination}")
            enrichment = enrich_destination(destination)
            self.logger.info(f"Real-time enrichment complete: {len(enrichment.get('attractions', []))} attractions, {len(enrichment.get('news', []))} news items")
            return enrichment
        except Exception as e:
            self.logger.error(f"Real-time enrichment failed: {e}")
            return {
                'destination': destination,
                'wikipedia': {},
                'attractions': [],
                'news': []
            }
