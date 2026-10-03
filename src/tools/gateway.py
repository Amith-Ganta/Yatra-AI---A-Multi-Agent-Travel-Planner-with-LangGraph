"""MCP gateway: the agents call tools over MCP, with an in-process fallback.

``src/mcp_servers/`` holds three FastMCP servers (hotels, flights, weather). At startup this
module launches each one as a stdio subprocess through ``langchain-mcp-adapters`` and keeps the
sessions open for the life of the app, so a tool call is a message on an open pipe and not a
process spawn.

Failure handling is per server:

* A server whose prerequisite is missing (for example no ``TAVILY_API_KEY``) is not started at all.
* A server that fails to start or list its tools is skipped; the other servers still work.
* A call that fails or times out falls back to the same function running in-process, so one
  broken subprocess degrades a single call and never the whole plan.

Every result carries ``"via"`` ("mcp" or "in-process") so you can see which path answered.

The module exports ``search_hotels``, ``search_flights`` and ``get_weather`` with the same
signatures as ``src.tools``, so the agents import them without knowing which path is in use.
"""

import asyncio
import json
import logging
import os
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, cast

from langchain_mcp_adapters.client import MultiServerMCPClient  # pyright: ignore
from langchain_mcp_adapters.tools import load_mcp_tools  # pyright: ignore
from mcp.client.stdio import get_default_environment

from src import tools as local_tools
from src.core.config import settings

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ServerSpec:
    """How to launch one MCP server and which secrets it may see."""

    name: str
    module: str
    tool: str
    # Forwarded to this server only; the subprocess never sees DATABASE_URL or LLM keys.
    env_keys: tuple[str, ...] = ()
    # The server is not started when one of these is unset.
    required_env: tuple[str, ...] = ()


SERVERS: tuple[ServerSpec, ...] = (
    ServerSpec(
        "hotels",
        "src.mcp_servers.hotels",
        "search_hotels",
        env_keys=("TAVILY_API_KEY",),
        required_env=("TAVILY_API_KEY",),
    ),
    ServerSpec("flights", "src.mcp_servers.flights", "search_flights"),
    ServerSpec("weather", "src.mcp_servers.weather", "get_weather"),
)


def _prerequisite_problem(spec: ServerSpec) -> Optional[str]:
    """Why this server cannot start, or None when it can."""
    missing = [key for key in spec.required_env if not os.getenv(key)]
    if missing:
        return f"{', '.join(missing)} is not set"
    return None


def _connection(spec: ServerSpec) -> dict[str, Any]:
    """The stdio launch config for one server, using this interpreter and a minimal env."""
    env = dict(get_default_environment())
    for key in spec.env_keys:
        value = os.getenv(key)
        if value:
            env[key] = value
    return {
        "transport": "stdio",
        "command": sys.executable,
        "args": ["-m", spec.module],
        "cwd": str(PROJECT_ROOT),
        "env": env,
    }


def _describe(exc: BaseException) -> str:
    """Name the real cause: the MCP SDK wraps startup failures in an ExceptionGroup."""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:  # pyright: ignore
        exc = cast(BaseException, exc.exceptions[0])  # pyright: ignore
    return type(exc).__name__  # pyright: ignore


def _parse_result(raw: Any) -> dict[str, Any]:
    """Turn an MCP tool result (content blocks or text) back into the tool's dict."""
    if isinstance(raw, dict):
        return dict(raw)  # pyright: ignore[reportUnknownArgumentType]
    if isinstance(raw, str):
        text = raw
    else:
        parts: list[str] = []
        blocks: list[Any] = raw if isinstance(raw, list) else []  # pyright: ignore
        for block in blocks:
            if isinstance(block, dict) and block.get("type") == "text":  # pyright: ignore
                parts.append(str(block.get("text", "")))  # pyright: ignore
        text = "".join(parts)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("MCP tool did not return a JSON object")
    return dict(data)  # pyright: ignore[reportUnknownArgumentType]


class MCPToolbox:
    """Owns the MCP client sessions and the tools loaded from them."""

    def __init__(self, specs: tuple[ServerSpec, ...] = SERVERS) -> None:
        self._specs = specs
        self._stack: Optional[AsyncExitStack] = None
        self._tools: dict[str, Any] = {}
        # server name -> "ready" or the reason it is not running
        self.status: dict[str, str] = {}

    async def start(self, startup_timeout: Optional[float] = None) -> None:
        """Launch every server that can run. Never raises: failures become ``status`` entries."""
        timeout = startup_timeout if startup_timeout is not None else settings.mcp.startup_timeout
        runnable = [spec for spec in self._specs if _prerequisite_problem(spec) is None]
        for spec in self._specs:
            problem = _prerequisite_problem(spec)
            if problem:
                self.status[spec.name] = f"skipped: {problem}"
                logger.warning("MCP server %s skipped: %s", spec.name, problem)

        stack = AsyncExitStack()
        self._stack = stack
        connections: Any = {spec.name: _connection(spec) for spec in runnable}
        client = MultiServerMCPClient(connections)

        for spec in runnable:
            try:
                # asyncio.timeout (not wait_for) keeps start and stop in one task, which the
                # MCP SDK's task groups require.
                async with asyncio.timeout(timeout):
                    opened = client.session(spec.name)  # pyright: ignore
                    session = await stack.enter_async_context(opened)  # pyright: ignore
                    loaded = await load_mcp_tools(session)  # pyright: ignore
            except Exception as exc:
                self.status[spec.name] = f"failed: {_describe(exc)}"
                logger.warning("MCP server %s failed to start: %s", spec.name, exc)
                continue

            names = [tool.name for tool in loaded]  # pyright: ignore
            if spec.tool not in names:
                self.status[spec.name] = f"failed: tool {spec.tool} missing (has {names})"
                logger.warning("MCP server %s does not expose %s", spec.name, spec.tool)
                continue
            self._tools[spec.tool] = next(
                t for t in loaded if t.name == spec.tool
            )  # pyright: ignore
            self.status[spec.name] = "ready"
            logger.info("MCP server %s ready", spec.name)

    async def stop(self) -> None:
        """Close every session and stop the subprocesses."""
        stack, self._stack = self._stack, None
        self._tools = {}
        if stack is None:
            return
        try:
            await stack.aclose()
        except Exception as exc:
            logger.warning("MCP shutdown was not clean: %s", exc)

    def has(self, tool_name: str) -> bool:
        return tool_name in self._tools

    async def call(
        self, tool_name: str, args: dict[str, Any], timeout: Optional[float] = None
    ) -> dict[str, Any]:
        """Call a tool over MCP. Raises when the server is down, slow or returns junk."""
        tool = self._tools[tool_name]
        limit = timeout if timeout is not None else settings.mcp.call_timeout
        async with asyncio.timeout(limit):
            raw = await tool.ainvoke(args)
        return _parse_result(raw)


_toolbox: Optional[MCPToolbox] = None


async def start_mcp() -> None:
    """Start the MCP servers (called once from app startup)."""
    global _toolbox
    if not settings.mcp.enabled:
        logger.info("MCP disabled; tools run in-process")
        return
    toolbox = MCPToolbox()
    await toolbox.start()
    _toolbox = toolbox


async def stop_mcp() -> None:
    """Stop the MCP servers (called once from app shutdown)."""
    global _toolbox
    toolbox, _toolbox = _toolbox, None
    if toolbox is not None:
        await toolbox.stop()


def mcp_status() -> dict[str, str]:
    """Per-server state, for the readiness endpoint and logs."""
    if _toolbox is None:
        return {"mode": "in-process"}
    return dict(_toolbox.status)


async def _call(
    tool_name: str,
    args: dict[str, Any],
    fallback: Callable[..., Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    toolbox = _toolbox
    if toolbox is not None and toolbox.has(tool_name):
        try:
            result = await toolbox.call(tool_name, args)
            result["via"] = "mcp"
            return result
        except Exception as exc:
            logger.warning("MCP call %s failed (%s); using the in-process tool", tool_name, exc)
    result = await fallback(**args)
    result["via"] = "in-process"
    return result


async def search_hotels(destination: str, budget: float) -> dict[str, Any]:
    """Hotel search over MCP (Tavily), in-process when MCP is unavailable."""
    args = {"destination": destination, "budget": budget}
    return await _call("search_hotels", args, local_tools.search_hotels)


async def search_flights(
    destination: str, departure_date: str, party_size: int, budget: float
) -> dict[str, Any]:
    """Flight options over MCP, in-process when MCP is unavailable."""
    args = {
        "destination": destination,
        "departure_date": departure_date,
        "party_size": party_size,
        "budget": budget,
    }
    return await _call("search_flights", args, local_tools.search_flights)


async def get_weather(destination: str, start_date: str, end_date: str) -> dict[str, Any]:
    """Weather over MCP (Open-Meteo), in-process when MCP is unavailable."""
    args = {"destination": destination, "start_date": start_date, "end_date": end_date}
    return await _call("get_weather", args, local_tools.get_weather)
