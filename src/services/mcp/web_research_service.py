"""
Web research service — orchestrates focused MCP searches for each destination,
route segment, and optional excursion in the trip.

Gracefully degrades when MCP is unavailable: returns an empty WebResearchResult
so the rest of the pipeline continues with KB-only data.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Dict, List

from src.models.trip_requirements import TripRequirements
from src.services.mcp.mcp_client import MCPError, get_mcp_client

logger = logging.getLogger(__name__)

_RETRY = 2
_RETRY_DELAY = 1.2
_SNIPPET_LEN = 700  # chars to keep per search result


class WebResearchResult:
    def __init__(self):
        self.destination_summaries: Dict[str, str] = {}
        self.route_info: List[Dict[str, str]] = []
        self.senior_attractions: Dict[str, str] = {}
        self.hotel_areas: Dict[str, str] = {}
        self.excursion_notes: List[str] = []
        self.general_notes: List[str] = []
        self.sources: List[str] = []
        self.failed_queries: List[str] = []

    def to_context_string(self) -> str:
        parts: List[str] = []

        if self.destination_summaries:
            parts.append("=== DESTINATION INFO (web) ===")
            for city, txt in self.destination_summaries.items():
                parts.append(f"[{city}]\n{txt}")

        if self.route_info:
            parts.append("\n=== ROUTE INFORMATION (web) ===")
            for item in self.route_info:
                parts.append(f"• {item['route']}: {item['info']}")

        if self.senior_attractions:
            parts.append("\n=== SENIOR-FRIENDLY ATTRACTIONS (web) ===")
            for city, txt in self.senior_attractions.items():
                parts.append(f"[{city}]\n{txt}")

        if self.hotel_areas:
            parts.append("\n=== HOTEL AREA RECOMMENDATIONS (web) ===")
            for city, txt in self.hotel_areas.items():
                parts.append(f"[{city}] {txt}")

        if self.excursion_notes:
            parts.append("\n=== OPTIONAL EXCURSION RESEARCH (web) ===")
            for n in self.excursion_notes:
                parts.append(f"• {n}")

        if self.general_notes:
            parts.append("\n=== GENERAL TRAVEL NOTES (web) ===")
            for n in self.general_notes:
                parts.append(f"• {n}")

        if self.failed_queries:
            parts.append(
                f"\n[NOTE: {len(self.failed_queries)} web queries failed — KB data used as fallback]"
            )

        return "\n".join(parts)


class WebResearchService:
    """Execute focused web searches and aggregate results into a WebResearchResult."""

    def __init__(self):
        self._mcp_disabled = False
        self._mcp_disable_reason = ""
        self._client = None
        self._client_lock = asyncio.Lock()

    async def research_trip(self, req: TripRequirements) -> WebResearchResult:
        result = WebResearchResult()

        if self._mcp_disabled:
            logger.warning("Skipping web research: MCP disabled for this session")
            result.general_notes.append(
                f"Web search unavailable for this session: {self._mcp_disable_reason or 'MCP disabled'}"
            )
            return result

        queries = self._build_query_plan(req)
        tasks = [self._safe_search(q["query"], q["tag"], result) for q in queries]
        await asyncio.gather(*tasks)

        logger.info(
            "Web research done | ok=%s | failed=%s",
            len(result.sources),
            len(result.failed_queries),
        )
        return result

    def _build_query_plan(self, req: TripRequirements) -> List[Dict[str, str]]:
        queries: List[Dict[str, str]] = []

        for city in req.destinations:
            queries.extend(
                [
                    {
                        "query": f"{city} tourist attractions senior friendly minimal walking 2024 2025",
                        "tag": f"senior:{city}",
                    },
                    {
                        "query": f"best hotel area {city} city centre 4 star 5 star location",
                        "tag": f"hotel_area:{city}",
                    },
                    {
                        "query": f"{city} top sightseeing overview travel guide",
                        "tag": f"overview:{city}",
                    },
                ]
            )

        for seg in req.route_segments:
            queries.append(
                {
                    "query": (
                        f"private car transfer {seg.from_city} to {seg.to_city} "
                        f"distance duration road trip scenic stops"
                    ),
                    "tag": f"route:{seg.from_city}:{seg.to_city}",
                }
            )

        for exc in req.optional_excursions[:3]:
            queries.append(
                {
                    "query": f"{exc} senior citizens easy accessible day trip Europe",
                    "tag": f"excursion:{exc[:30]}",
                }
            )

        return queries

    async def _get_client_once(self):
        if self._mcp_disabled:
            raise MCPError(self._mcp_disable_reason or "MCP disabled for session")

        if self._client is not None:
            return self._client

        async with self._client_lock:
            if self._client is not None:
                return self._client

            try:
                self._client = await get_mcp_client()
                return self._client
            except Exception as e:
                self._mcp_disabled = True
                self._mcp_disable_reason = str(e)
                logger.exception(
                    "MCP client could not start; disabling web search for session"
                )
                raise MCPError(self._mcp_disable_reason) from e

    async def _safe_search(
        self, query: str, tag: str, result: WebResearchResult
    ) -> None:
        if self._mcp_disabled:
            result.failed_queries.append(query[:80])
            return

        for attempt in range(_RETRY):
            try:
                client = await self._get_client_once()
                text = await client.search_web(query)
                self._store(text[:_SNIPPET_LEN], tag, result)
                result.sources.append(f"web:{query[:55]}")
                return

            except MCPError as e:
                logger.warning(
                    "MCP search [%s/%s] '%s': %s",
                    attempt + 1,
                    _RETRY,
                    query[:50],
                    e,
                )

                if "NotImplementedError" in str(e) or "permanently unavailable" in str(e):
                    self._mcp_disabled = True
                    self._mcp_disable_reason = str(e)
                    break

                if attempt < _RETRY - 1 and not self._mcp_disabled:
                    await asyncio.sleep(_RETRY_DELAY)

            except Exception as e:
                logger.exception("Web search error for '%s': %s", query[:50], e)
                break

        result.failed_queries.append(query[:80])

    def _store(self, text: str, tag: str, result: WebResearchResult) -> None:
        if not text:
            return

        prefix, _, rest = tag.partition(":")

        if prefix == "senior":
            city = rest.title()
            result.senior_attractions[city] = (
                result.senior_attractions.get(city, "") + "\n" + text
            ).strip()

        elif prefix == "hotel_area":
            city = rest.title()
            result.hotel_areas[city] = text

        elif prefix == "overview":
            city = rest.title()
            result.destination_summaries[city] = (
                result.destination_summaries.get(city, "") + "\n" + text
            ).strip()

        elif prefix == "route":
            parts = rest.split(":")
            from_c = parts[0].title() if parts else "?"
            to_c = parts[1].title() if len(parts) > 1 else "?"
            result.route_info.append({"route": f"{from_c} → {to_c}", "info": text})

        elif prefix == "excursion":
            result.excursion_notes.append(f"{rest}: {text}")

        else:
            result.general_notes.append(text)