"""MCP gateway: tools go over MCP when a server is up and fall back in-process when it is not."""

import asyncio
import json
from typing import Any

import pytest

from src.core.config import settings
from src.tools import gateway
from src.tools.gateway import MCPToolbox, ServerSpec


class FakeToolbox:
    """Stands in for ``MCPToolbox``: answers, fails or hangs on demand."""

    def __init__(self, tools: tuple[str, ...], result: Any = None, error: Any = None) -> None:
        self.tools = tools
        self.result = result
        self.error = error
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.status = {"hotels": "ready"}

    def has(self, tool_name: str) -> bool:
        return tool_name in self.tools

    async def call(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((tool_name, args))
        if self.error is not None:
            raise self.error
        return dict(self.result)


@pytest.fixture(autouse=True)
def no_toolbox(monkeypatch):
    """Every test starts in the default state: no MCP servers running."""
    monkeypatch.setattr(gateway, "_toolbox", None)


@pytest.fixture
def local(monkeypatch):
    """Replace the in-process tools with recorders that return a marked result."""
    calls: list[tuple[str, dict[str, Any]]] = []

    def make(name: str):
        async def tool(**kwargs: Any) -> dict[str, Any]:
            calls.append((name, kwargs))
            return {"status": "success", "from": "local"}

        return tool

    for name in ("search_hotels", "search_flights", "get_weather"):
        monkeypatch.setattr(gateway.local_tools, name, make(name))
    return calls


# --- _parse_result: MCP returns content blocks, plain text or an already parsed dict ---


def test_parse_result_accepts_a_dict():
    assert gateway._parse_result({"status": "success"}) == {"status": "success"}


def test_parse_result_accepts_json_text():
    assert gateway._parse_result('{"status": "success", "n": 2}') == {"status": "success", "n": 2}


def test_parse_result_joins_text_content_blocks():
    blocks = [
        {"type": "text", "text": '{"status": '},
        {"type": "image", "data": "ignored"},
        {"type": "text", "text": '"success"}'},
    ]
    assert gateway._parse_result(blocks) == {"status": "success"}


@pytest.mark.parametrize("raw", ["[1, 2]", '"just a string"', "42"])
def test_parse_result_rejects_json_that_is_not_an_object(raw):
    with pytest.raises(ValueError, match="JSON object"):
        gateway._parse_result(raw)


@pytest.mark.parametrize("raw", ["not json", [], None])
def test_parse_result_rejects_unreadable_output(raw):
    with pytest.raises(ValueError):
        gateway._parse_result(raw)


# --- launch config ---


def test_connection_uses_this_interpreter_and_the_server_module():
    spec = ServerSpec("weather", "src.mcp_servers.weather", "get_weather")
    conn = gateway._connection(spec)

    assert conn["transport"] == "stdio"
    assert conn["command"] == gateway.sys.executable
    assert conn["args"] == ["-m", "src.mcp_servers.weather"]
    assert conn["cwd"] == str(gateway.PROJECT_ROOT)


def test_connection_hides_secrets_the_server_does_not_need(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@db/yatra")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-secret")
    weather = ServerSpec("weather", "src.mcp_servers.weather", "get_weather")

    env = gateway._connection(weather)["env"]

    assert not {"DATABASE_URL", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "TAVILY_API_KEY"} & set(env)


def test_connection_forwards_only_the_keys_a_server_declares(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@db/yatra")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-secret")
    hotels = next(spec for spec in gateway.SERVERS if spec.name == "hotels")

    env = gateway._connection(hotels)["env"]

    assert env["TAVILY_API_KEY"] == "tvly-secret"
    assert "DATABASE_URL" not in env


def test_hotels_server_needs_a_tavily_key(monkeypatch):
    hotels = next(spec for spec in gateway.SERVERS if spec.name == "hotels")

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    assert gateway._prerequisite_problem(hotels) == "TAVILY_API_KEY is not set"

    monkeypatch.setenv("TAVILY_API_KEY", "tvly-x")
    assert gateway._prerequisite_problem(hotels) is None


def test_servers_without_prerequisites_always_run():
    for spec in gateway.SERVERS:
        if not spec.required_env:
            assert gateway._prerequisite_problem(spec) is None


def test_every_server_module_is_a_real_module_in_this_repo():
    for spec in gateway.SERVERS:
        path = gateway.PROJECT_ROOT.joinpath(*spec.module.split(".")).with_suffix(".py")
        assert path.is_file(), f"{spec.module} does not exist"


# --- the wrappers: MCP first, in-process fallback, "via" always set ---


async def test_without_a_toolbox_the_in_process_tool_answers(local):
    result = await gateway.search_hotels("Rome", 1500.0)

    assert result == {"status": "success", "from": "local", "via": "in-process"}
    assert local == [("search_hotels", {"destination": "Rome", "budget": 1500.0})]


async def test_a_running_server_answers_over_mcp(monkeypatch, local):
    fake = FakeToolbox(("search_hotels",), result={"status": "success", "hotels": []})
    monkeypatch.setattr(gateway, "_toolbox", fake)

    result = await gateway.search_hotels("Rome", 1500.0)

    assert result["via"] == "mcp" and result["hotels"] == []
    assert fake.calls == [("search_hotels", {"destination": "Rome", "budget": 1500.0})]
    assert local == []


async def test_a_tool_the_toolbox_does_not_have_falls_back(monkeypatch, local):
    monkeypatch.setattr(gateway, "_toolbox", FakeToolbox(("get_weather",)))

    result = await gateway.search_hotels("Rome", 1500.0)

    assert result["via"] == "in-process"
    assert len(local) == 1


@pytest.mark.parametrize(
    "error",
    [RuntimeError("pipe closed"), asyncio.TimeoutError(), ValueError("junk")],
    ids=["server-error", "timeout", "bad-payload"],
)
async def test_a_failing_call_falls_back_and_never_raises(monkeypatch, local, error):
    fake = FakeToolbox(("get_weather",), error=error)
    monkeypatch.setattr(gateway, "_toolbox", fake)

    result = await gateway.get_weather("Rome", "2099-05-10", "2099-05-12")

    assert result["via"] == "in-process"
    assert result["from"] == "local"
    assert len(fake.calls) == 1  # MCP was tried once before falling back


async def test_one_broken_server_does_not_affect_the_others(monkeypatch, local):
    class Mixed(FakeToolbox):
        async def call(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
            if tool_name == "search_flights":
                raise RuntimeError("flights server died")
            return {"status": "success", "from": "mcp"}

    monkeypatch.setattr(gateway, "_toolbox", Mixed(("search_flights", "get_weather")))

    flights = await gateway.search_flights("Rome", "2099-05-10", 2, 900.0)
    weather = await gateway.get_weather("Rome", "2099-05-10", "2099-05-12")

    assert flights["via"] == "in-process"
    assert weather["via"] == "mcp"


async def test_flights_and_weather_pass_their_arguments_through(monkeypatch, local):
    await gateway.search_flights("Rome", "2099-05-10", 2, 900.0)
    await gateway.get_weather("Rome", "2099-05-10", "2099-05-12")

    assert local == [
        (
            "search_flights",
            {
                "destination": "Rome",
                "departure_date": "2099-05-10",
                "party_size": 2,
                "budget": 900.0,
            },
        ),
        (
            "get_weather",
            {"destination": "Rome", "start_date": "2099-05-10", "end_date": "2099-05-12"},
        ),
    ]


# --- lifecycle and status ---


def test_status_is_in_process_when_no_server_runs():
    assert gateway.mcp_status() == {"mode": "in-process"}


def test_status_reports_each_server(monkeypatch):
    monkeypatch.setattr(gateway, "_toolbox", FakeToolbox(()))
    assert gateway.mcp_status() == {"hotels": "ready"}


async def test_start_does_nothing_when_mcp_is_disabled(monkeypatch):
    monkeypatch.setattr(settings.mcp, "enabled", False)

    await gateway.start_mcp()

    assert gateway._toolbox is None


async def test_start_and_stop_manage_the_toolbox(monkeypatch):
    started: list[str] = []

    class Stub:
        status = {"weather": "ready"}

        async def start(self) -> None:
            started.append("start")

        async def stop(self) -> None:
            started.append("stop")

    monkeypatch.setattr(settings.mcp, "enabled", True)
    monkeypatch.setattr(gateway, "MCPToolbox", Stub)

    await gateway.start_mcp()
    assert gateway.mcp_status() == {"weather": "ready"}

    await gateway.stop_mcp()
    assert started == ["start", "stop"]
    assert gateway.mcp_status() == {"mode": "in-process"}


async def test_stop_is_safe_when_nothing_was_started():
    await gateway.stop_mcp()
    assert gateway._toolbox is None


async def test_toolbox_skips_a_server_whose_key_is_missing_without_launching_anything(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    spec = ServerSpec(
        "hotels", "src.mcp_servers.hotels", "search_hotels", required_env=("TAVILY_API_KEY",)
    )
    toolbox = MCPToolbox((spec,))

    await toolbox.start()

    assert toolbox.status == {"hotels": "skipped: TAVILY_API_KEY is not set"}
    assert not toolbox.has("search_hotels")
    await toolbox.stop()


async def test_toolbox_times_out_a_call_that_hangs():
    class Slow:
        async def ainvoke(self, args: dict[str, Any]) -> str:
            await asyncio.sleep(5)
            return json.dumps({"status": "success"})

    toolbox = MCPToolbox(())
    toolbox._tools = {"get_weather": Slow()}

    with pytest.raises(TimeoutError):
        await toolbox.call("get_weather", {}, timeout=0.05)


async def test_toolbox_call_parses_the_tool_output():
    class Echo:
        async def ainvoke(self, args: dict[str, Any]) -> list[dict[str, str]]:
            return [{"type": "text", "text": json.dumps({"status": "success", "args": args})}]

    toolbox = MCPToolbox(())
    toolbox._tools = {"get_weather": Echo()}

    result = await toolbox.call("get_weather", {"destination": "Rome"})

    assert result == {"status": "success", "args": {"destination": "Rome"}}
