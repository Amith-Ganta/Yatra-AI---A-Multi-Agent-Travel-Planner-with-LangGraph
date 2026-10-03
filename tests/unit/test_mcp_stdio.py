"""The MCP path end to end: a real server subprocess, the real protocol, no fakes.

Everything else in ``test_gateway.py`` fakes the toolbox. These tests start the flights server
(it needs no key and no network), call it through ``langchain-mcp-adapters`` and check the answer
that comes back over the pipe. They also prove that a server that cannot start is skipped and
that a call to a dead server still returns an answer through the in-process fallback.
"""

import pytest

from src.tools import gateway
from src.tools.gateway import MCPToolbox, ServerSpec

FLIGHTS = ServerSpec("flights", "src.mcp_servers.flights", "search_flights")

ARGS = {"destination": "Rome", "departure_date": "2099-05-10", "party_size": 2, "budget": 900.0}


@pytest.fixture(autouse=True)
def no_toolbox(monkeypatch):
    monkeypatch.setattr(gateway, "_toolbox", None)


async def test_a_real_server_answers_over_stdio():
    toolbox = MCPToolbox((FLIGHTS,))
    try:
        await toolbox.start(startup_timeout=60)

        assert toolbox.status == {"flights": "ready"}
        assert toolbox.has("search_flights")

        result = await toolbox.call("search_flights", ARGS, timeout=60)
    finally:
        await toolbox.stop()

    assert result["destination"] == "Rome"
    assert result["source"] == "mock"
    assert len(result["flights"]) == 3


async def test_the_wrapper_reports_that_mcp_answered(monkeypatch):
    toolbox = MCPToolbox((FLIGHTS,))
    try:
        await toolbox.start(startup_timeout=60)
        monkeypatch.setattr(gateway, "_toolbox", toolbox)

        result = await gateway.search_flights(**ARGS)
    finally:
        monkeypatch.setattr(gateway, "_toolbox", None)
        await toolbox.stop()

    assert result["via"] == "mcp"
    assert result["source"] == "mock"


async def test_a_server_that_cannot_start_is_skipped_not_fatal():
    broken = ServerSpec("broken", "src.mcp_servers.does_not_exist", "search_flights")
    toolbox = MCPToolbox((broken, FLIGHTS))
    try:
        await toolbox.start(startup_timeout=60)

        assert toolbox.status["broken"].startswith("failed")
        assert toolbox.status["flights"] == "ready"
        assert toolbox.has("search_flights")
    finally:
        await toolbox.stop()


async def test_a_dead_server_falls_back_to_the_in_process_tool(monkeypatch):
    toolbox = MCPToolbox((FLIGHTS,))
    await toolbox.start(startup_timeout=60)
    assert toolbox.has("search_flights")
    # Close the pipes under the toolbox while it still lists the tool: the next call must fail
    # over MCP and be answered in-process, not raise.
    await toolbox.stop()
    toolbox._tools = {"search_flights": _Dead()}
    monkeypatch.setattr(gateway, "_toolbox", toolbox)

    result = await gateway.search_flights(**ARGS)

    assert result["via"] == "in-process"
    assert result["source"] == "mock"


class _Dead:
    async def ainvoke(self, args: dict) -> dict:
        raise ConnectionError("server process is gone")
