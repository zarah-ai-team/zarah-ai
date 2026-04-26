"""
Async MCP stdio client — wired for Tavily MCP (tavily-ai/tavily-mcp).

Protocol  : JSON-RPC 2.0 over stdin/stdout
Server    : https://github.com/tavily-ai/tavily-mcp
Launch    : npx -y tavily-mcp@latest   (Node.js >= 18 required)
Auth      : TAVILY_API_KEY env var (get one free at tavily.com)

Notes
-----
- On Windows, asyncio.create_subprocess_* requires ProactorEventLoop which may
  not be the running loop under uvicorn. We use subprocess.Popen + thread
  executors instead on Windows to avoid NotImplementedError entirely.
- This client degrades gracefully: once startup is determined to be unrecoverable
  for the session, it marks itself unavailable and future calls fail fast.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import shlex
import subprocess as _subprocess
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_IS_WINDOWS: bool = platform.system() == "Windows"

MCP_SERVER_CMD: str = os.getenv("MCP_SERVER_CMD", "npx -y ollama-web-search-mcp")
MCP_TIMEOUT: int = int(os.getenv("MCP_TIMEOUT", "200"))

def _make_env() -> Dict[str, str]:
    """Build env for MCP subprocess — injects TAVILY_API_KEY for Tavily MCP."""
    env = dict(os.environ)
    tavily_key = os.getenv("TAVILY_API_KEY", "")
    if tavily_key and not tavily_key.startswith("tvly-YOUR"):
        env["TAVILY_API_KEY"] = tavily_key
    return env


class MCPError(Exception):
    pass


class MCPClient:
    def __init__(self):
        self._proc: Optional[asyncio.subprocess.Process] = None   # non-Windows
        self._popen: Optional[_subprocess.Popen] = None           # Windows
        self._req_id = 0
        self._initialized = False
        self._unavailable = False
        self._rpc_lock = asyncio.Lock()
        self._start_lock = asyncio.Lock()
        # Cached, dynamically-resolved tool names. tavily-mcp v1 used "tavily-search"
        # / "tavily-extract"; v2 renamed them to "tavily_search" / "tavily_extract".
        # We discover the actual name on first use via tools/list to support both.
        self._search_tool_name: Optional[str] = None
        self._extract_tool_name: Optional[str] = None

    async def start(self) -> None:
        async with self._start_lock:
            if self._initialized or self._unavailable:
                return
            if self._proc and self._proc.returncode is None:
                return
            if self._popen and self._popen.poll() is None:
                return
            await self._launch()

    async def _launch(self) -> None:
        cmd = MCP_SERVER_CMD
        logger.info("Starting MCP server: %s", cmd)
        env = _make_env()

        if _IS_WINDOWS:
            await self._launch_popen(cmd, env)
        else:
            await self._launch_asyncio(cmd, env)

    async def _launch_popen(self, cmd: str, env: Dict[str, str]) -> None:
        """Windows path: subprocess.Popen + thread executors (no ProactorLoop needed)."""
        loop = asyncio.get_event_loop()
        try:
            self._popen = await loop.run_in_executor(
                None,
                lambda: _subprocess.Popen(
                    cmd, shell=True,
                    stdin=_subprocess.PIPE,
                    stdout=_subprocess.PIPE,
                    stderr=_subprocess.PIPE,
                    env=env,
                ),
            )
        except FileNotFoundError:
            self._unavailable = True
            raise MCPError(
                "npx not found. Install Node.js >= 18 and ensure it is in PATH. "
                "Or set MCP_SERVER_CMD env var to an alternative command."
            )
        except Exception as e:
            self._unavailable = True
            raise MCPError(f"Failed to launch MCP server: {type(e).__name__}: {e}")

        await asyncio.sleep(0.4)

        if self._popen.poll() is not None:
            stderr_hint = await self._read_stderr()
            self._unavailable = True
            raise MCPError(
                f"MCP process exited immediately (code {self._popen.returncode})"
                + (f" | stderr: {stderr_hint}" if stderr_hint else "")
            )

        logger.info("MCP server process started (pid=%s)", self._popen.pid)
        await self._initialize()

    async def _launch_asyncio(self, cmd: str, env: Dict[str, str]) -> None:
        """Non-Windows path: native asyncio subprocess."""
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *shlex.split(cmd),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except FileNotFoundError:
            self._unavailable = True
            raise MCPError(
                "npx not found. Install Node.js >= 18 and ensure it is in PATH."
            )
        except Exception as e:
            self._unavailable = True
            raise MCPError(f"Failed to launch MCP server: {type(e).__name__}: {e}")

        if not self._proc:
            self._unavailable = True
            raise MCPError("MCP process did not start.")

        await asyncio.sleep(0.4)

        if self._proc.returncode is not None:
            stderr_hint = await self._read_stderr()
            self._unavailable = True
            raise MCPError(
                f"MCP process exited immediately with code {self._proc.returncode}"
                + (f" | stderr: {stderr_hint}" if stderr_hint else "")
            )

        logger.info("MCP server process started (pid=%s)", self._proc.pid)
        await self._initialize()

    async def _initialize(self) -> None:
        try:
            resp = await self._rpc(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "tmc-itinerary-pipeline",
                        "version": "2.0",
                    },
                },
            )
        except MCPError as e:
            stderr_hint = await self._read_stderr()
            self._unavailable = True
            raise MCPError(
                f"MCP init failed: {e}"
                + (f" | stderr: {stderr_hint}" if stderr_hint else "")
            )

        if resp.get("result"):
            self._initialized = True
            logger.info("MCP protocol initialized successfully")
        else:
            stderr_hint = await self._read_stderr()
            self._unavailable = True
            raise MCPError(
                f"Unexpected init response: {resp}"
                + (f" | stderr: {stderr_hint}" if stderr_hint else "")
            )

    async def _read_stderr(self, max_bytes: int = 1000) -> str:
        loop = asyncio.get_event_loop()
        if self._popen and self._popen.stderr:
            try:
                data = await asyncio.wait_for(
                    loop.run_in_executor(
                        None, lambda: self._popen.stderr.read(max_bytes)
                    ),
                    timeout=1.5,
                )
                return data.decode(errors="replace").strip()
            except Exception:
                return ""
        if self._proc and self._proc.stderr:
            try:
                data = await asyncio.wait_for(
                    self._proc.stderr.read(max_bytes), timeout=1.5
                )
                return data.decode(errors="replace").strip()
            except Exception:
                return ""
        return ""

    async def stop(self) -> None:
        if self._popen and self._popen.poll() is None:
            self._popen.terminate()
            loop = asyncio.get_event_loop()
            try:
                await asyncio.wait_for(
                    loop.run_in_executor(None, self._popen.wait), timeout=5
                )
            except asyncio.TimeoutError:
                self._popen.kill()
            logger.info("MCP server stopped (popen)")

        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._proc.kill()
                await self._proc.wait()
            logger.info("MCP server stopped")

        self._initialized = False
        self._proc = None
        self._popen = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *_):
        await self.stop()

    async def search_web(self, query: str, depth: str = "basic") -> str:
        """Search via Tavily MCP. Resolves the tool name dynamically (v1 vs v2)."""
        name = await self._resolve_tool("search")
        return await self.call_tool(
            name,
            {"query": query, "search_depth": depth, "max_results": 3},
        )

    async def fetch_page(self, url: str) -> str:
        name = await self._resolve_tool("extract")
        return await self.call_tool(name, {"urls": [url]})

    async def _resolve_tool(self, kind: str) -> str:
        """
        Resolve the actual MCP tool name for 'search' or 'extract' by listing
        the server's tools. tavily-mcp v1 uses hyphens ('tavily-search'),
        v2 uses underscores ('tavily_search'). Cached after first lookup.
        """
        cached = self._search_tool_name if kind == "search" else self._extract_tool_name
        if cached:
            return cached

        # Preferred names in order: v2 (underscore), v1 (hyphen), bare verb.
        if kind == "search":
            preferred = ("tavily_search", "tavily-search", "search")
        else:
            preferred = ("tavily_extract", "tavily-extract", "extract")

        try:
            tools = await self.list_tools()
            names = [t.get("name", "") for t in tools if isinstance(t, dict)]
            chosen: Optional[str] = None
            for cand in preferred:
                if cand in names:
                    chosen = cand
                    break
            if not chosen:
                # Fall back to any tool name containing the verb.
                for n in names:
                    if kind in n.lower():
                        chosen = n
                        break
            if chosen:
                if kind == "search":
                    self._search_tool_name = chosen
                else:
                    self._extract_tool_name = chosen
                logger.info("Resolved Tavily %s tool: %s", kind, chosen)
                return chosen
        except Exception as e:
            logger.warning("Tool discovery failed (%s); falling back to legacy name", e)

        # Last-resort legacy name (will produce a clear -32601 error if wrong).
        return preferred[0]

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        if not self._initialized:
            await self.start()

        resp = await self._rpc("tools/call", {"name": name, "arguments": arguments})
        if "error" in resp:
            raise MCPError(f"Tool '{name}' error: {resp['error']}")

        content = resp.get("result", {}).get("content", [])
        if isinstance(content, list):
            return "\n".join(
                item["text"]
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            )
        return str(resp.get("result", ""))

    async def list_tools(self) -> list:
        resp = await self._rpc("tools/list", {})
        return resp.get("result", {}).get("tools", [])

    async def _rpc(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        async with self._rpc_lock:
            if self._popen is not None:
                return await self._rpc_popen(method, params)
            return await self._rpc_asyncio(method, params)

    async def _rpc_popen(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Thread-executor based RPC for Windows Popen subprocess."""
        if not self._popen or self._popen.poll() is not None:
            raise MCPError("MCP process is not running.")

        self._req_id += 1
        msg = json.dumps({
            "jsonrpc": "2.0",
            "id": self._req_id,
            "method": method,
            "params": params,
        }) + "\n"

        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None, lambda: self._popen.stdin.write(msg.encode("utf-8"))
            )
            await loop.run_in_executor(None, self._popen.stdin.flush)
        except Exception as e:
            raise MCPError(f"Failed writing to MCP stdin: {type(e).__name__}: {e}")

        try:
            raw = await asyncio.wait_for(
                loop.run_in_executor(None, self._popen.stdout.readline),
                timeout=MCP_TIMEOUT,
            )
        except asyncio.TimeoutError:
            raise MCPError(
                f"MCP response timeout ({MCP_TIMEOUT}s) for method='{method}'. "
                "First run may take longer if npm is downloading the package."
            )

        if not raw:
            stderr_hint = await self._read_stderr()
            raise MCPError(
                "MCP process closed stdout unexpectedly"
                + (f" | stderr: {stderr_hint}" if stderr_hint else "")
            )

        try:
            return json.loads(raw.decode("utf-8").strip())
        except json.JSONDecodeError as e:
            raise MCPError(f"Invalid JSON from MCP server: {e}")

    async def _rpc_asyncio(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Asyncio-native RPC for non-Windows asyncio subprocess."""
        if not self._proc or self._proc.returncode is not None:
            raise MCPError("MCP process is not running.")
        if not self._proc.stdin or not self._proc.stdout:
            raise MCPError("MCP stdio pipes are not available.")

        self._req_id += 1
        msg = json.dumps({
            "jsonrpc": "2.0",
            "id": self._req_id,
            "method": method,
            "params": params,
        }) + "\n"

        try:
            self._proc.stdin.write(msg.encode("utf-8"))
            await self._proc.stdin.drain()
        except Exception as e:
            raise MCPError(f"Failed writing to MCP stdin: {type(e).__name__}: {e}")

        try:
            raw = await asyncio.wait_for(
                self._proc.stdout.readline(),
                timeout=MCP_TIMEOUT,
            )
        except asyncio.TimeoutError:
            raise MCPError(
                f"MCP response timeout ({MCP_TIMEOUT}s) for method='{method}'. "
                "First run may take longer if npm is downloading the package."
            )

        if not raw:
            stderr_hint = await self._read_stderr()
            raise MCPError(
                "MCP process closed stdout unexpectedly"
                + (f" | stderr: {stderr_hint}" if stderr_hint else "")
            )

        try:
            return json.loads(raw.decode("utf-8").strip())
        except json.JSONDecodeError as e:
            raise MCPError(f"Invalid JSON from MCP server: {e}")


_client: Optional[MCPClient] = None
_singleton_lock: Optional[asyncio.Lock] = None


def _get_lock() -> asyncio.Lock:
    global _singleton_lock
    if _singleton_lock is None:
        _singleton_lock = asyncio.Lock()
    return _singleton_lock


async def get_mcp_client() -> MCPClient:
    global _client

    async with _get_lock():
        if _client is None:
            _client = MCPClient()

        if _client._unavailable:
            raise MCPError("MCP is permanently unavailable for this session")

        if not _client._initialized:
            try:
                await _client.start()
            except MCPError as e:
                logger.warning(
                    "MCP client could not start: %s — web search will be degraded", e
                )
                raise
            except Exception as e:
                msg = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
                logger.warning(
                    "MCP client could not start: %s — web search will be degraded", msg
                )
                _client._unavailable = True
                raise MCPError(msg)

    return _client


async def shutdown_mcp_client() -> None:
    global _client
    if _client:
        await _client.stop()
        _client = None
