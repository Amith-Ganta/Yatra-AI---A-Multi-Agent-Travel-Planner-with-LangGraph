"""The Streamlit runtime: a real graph on a real background loop, with the LLM and tools faked.

Supervisor, routing, the approval interrupt, the revision loop and ``build_plan`` are production
code. The planner runs on its own event loop in a thread, exactly as it does inside the app.
"""

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest
from langgraph.types import Command

import src.agents.graph as graph_module
import src.ui.runtime as runtime_module
from src.agents.state import new_request_state
from src.core.config import ModelEnum, settings
from src.ui.runtime import (
    PLANNING_FAILED,
    PlannerRuntime,
    PlanningError,
    TurnHandle,
    missing_llm_key,
)

CONSTRAINTS = {
    "destination": "Rome",
    "start_date": "2099-05-10",
    "end_date": "2099-05-13",
    "budget_usd": 2000,
    "party_size": 2,
    "trip_type": "leisure",
}

TURN_WAIT = 60.0


class FakeLLM:
    """Stands in for the chat model that rewrites the itinerary after a rejection."""

    def __init__(self, reply: str) -> None:
        self.reply = reply

    async def ainvoke(self, prompt: str) -> Any:
        return SimpleNamespace(content=self.reply)


def _revised(activity: str) -> str:
    entries = [{"day": n, "activities": [activity]} for n in range(1, 5)]
    return json.dumps({"itinerary": entries, "summary": f"Added {activity}."})


def _supervisor(allowed: bool = True, reason: str = "test"):
    async def fake_supervisor(state: Any) -> dict[str, Any]:
        return {
            "allowed": allowed,
            "reason": reason,
            "selected_agents": ["flight"] if allowed else [],
            "trip_constraints": dict(CONSTRAINTS) if allowed else {},
        }

    return fake_supervisor


@pytest.fixture
def behaviour():
    """The graph keeps the node functions it was built with, so tests swap behaviour here."""
    return SimpleNamespace(supervisor=_supervisor())


@pytest.fixture
def fake_tools(monkeypatch, behaviour):
    async def flights(destination, departure_date, party_size, budget):
        offer = {"airline": "TestAir", "price": 300.0}
        return {"flights": [offer], "best_option": offer}

    async def hotels(destination, budget):
        return {"hotels": [{"name": "Hotel Test", "url": "https://example.com"}]}

    async def weather(destination, start, end):
        return {
            "forecast": [{"date": start, "temp_max": 22, "temp_min": 14, "condition": "Clear sky"}],
            "packing_advice": "Light layers.",
        }

    monkeypatch.setattr(graph_module, "search_flights", flights)
    monkeypatch.setattr(graph_module, "search_hotels", hotels)
    monkeypatch.setattr(graph_module, "get_weather", weather)

    async def supervisor(state: Any) -> dict[str, Any]:
        return await behaviour.supervisor(state)

    monkeypatch.setattr(graph_module, "supervisor_agent", supervisor)
    monkeypatch.setattr(
        graph_module, "llm_factory", SimpleNamespace(get_llm=lambda: FakeLLM(_revised("Museum")))
    )


@pytest.fixture
def planner(fake_tools):
    runtime = PlannerRuntime()
    runtime.start(timeout=TURN_WAIT)
    yield runtime
    runtime.stop()


def _request(thread_id: str, message: str = "Plan a trip to Rome"):
    return new_request_state(message, thread_id, "u-1")


def _finish(handle: TurnHandle):
    assert handle.wait(TURN_WAIT), "the run did not end"
    return handle.result()


def test_a_new_request_pauses_for_approval(planner):
    handle = planner.start_turn(_request("t-pause"), "t-pause")
    result = _finish(handle)

    assert result.plan["status"] == "awaiting_approval"
    assert result.plan["trip"]["destination"] == "Rome"
    assert result.approval_request is not None
    assert result.approval_request["kind"] == "plan_approval"
    assert result.approval_request["revision"] == 0
    assert result.approval_request["max_revisions"] == settings.mcp.max_revisions
    assert {"supervisor", "flight", "itinerary"} <= set(handle.nodes)
    assert "final_response" not in handle.nodes
    assert "__interrupt__" not in handle.nodes


def test_approving_ends_the_plan(planner):
    _finish(planner.start_turn(_request("t-ok"), "t-ok"))

    handle = planner.start_turn(Command(resume={"approved": True, "feedback": ""}), "t-ok")
    result = _finish(handle)

    assert result.plan["status"] == "approved"
    assert result.approval_request is None
    assert "final_response" in handle.nodes


def test_asking_for_changes_returns_a_new_draft_and_pauses_again(planner):
    _finish(planner.start_turn(_request("t-rev"), "t-rev"))

    resume = Command(resume={"approved": False, "feedback": "More museums"})
    result = _finish(planner.start_turn(resume, "t-rev"))

    assert result.plan["status"] == "awaiting_approval"
    assert result.approval_request is not None
    assert result.approval_request["revision"] == 1
    assert result.plan["approval"]["feedback_applied"] is True
    activities = result.plan["itinerary"]["itinerary"][0]["activities"]
    assert activities == ["Museum"]


def test_the_revision_limit_ends_the_loop(planner, monkeypatch):
    monkeypatch.setattr(settings.mcp, "max_revisions", 1)
    _finish(planner.start_turn(_request("t-cap"), "t-cap"))

    resume = Command(resume={"approved": False, "feedback": "Change it"})
    first = _finish(planner.start_turn(resume, "t-cap"))
    assert first.plan["status"] == "awaiting_approval"
    assert first.approval_request is not None

    # the one allowed revision is used up, so the next rejection ends the loop
    again = Command(resume={"approved": False, "feedback": "Change it again"})
    last = _finish(planner.start_turn(again, "t-cap"))

    assert last.approval_request is None
    assert last.plan["status"] == "revision_limit"


def test_a_request_the_supervisor_refuses_is_a_rejected_plan_not_an_error(planner, behaviour):
    behaviour.supervisor = _supervisor(allowed=False, reason="Not a trip")
    result = _finish(planner.start_turn(_request("t-no", "Write a script"), "t-no"))

    assert result.plan["status"] == "rejected"
    assert result.plan["reason"] == "Not a trip"
    assert result.approval_request is None


def test_two_threads_do_not_share_a_plan(planner):
    _finish(planner.start_turn(_request("t-a"), "t-a"))
    _finish(planner.start_turn(_request("t-b"), "t-b"))

    approve = Command(resume={"approved": True, "feedback": ""})
    first = _finish(planner.start_turn(approve, "t-a"))
    other = planner.start_turn(
        Command(resume={"approved": False, "feedback": "More museums"}), "t-b"
    )
    second = _finish(other)

    assert first.plan["status"] == "approved"
    assert second.plan["status"] == "awaiting_approval"


def test_a_failing_run_raises_a_safe_message(planner, behaviour):
    async def broken(state: Any) -> dict[str, Any]:
        raise RuntimeError("provider exploded with secret detail")

    behaviour.supervisor = broken
    handle = planner.start_turn(_request("t-err"), "t-err")
    assert handle.wait(TURN_WAIT)

    with pytest.raises(PlanningError) as error:
        handle.result()
    assert str(error.value) == PLANNING_FAILED
    assert "secret detail" not in str(error.value)


def test_a_run_that_takes_too_long_is_stopped(planner, behaviour, monkeypatch):
    async def slow(state: Any) -> dict[str, Any]:
        await asyncio.sleep(30)
        return {}

    behaviour.supervisor = slow
    monkeypatch.setattr(runtime_module, "TURN_TIMEOUT_SECONDS", 0.3)
    handle = planner.start_turn(_request("t-slow"), "t-slow")
    assert handle.wait(TURN_WAIT)

    with pytest.raises(PlanningError):
        handle.result()


def test_the_runtime_still_works_after_a_failed_run(planner, behaviour):
    async def broken(state: Any) -> dict[str, Any]:
        raise RuntimeError("boom")

    behaviour.supervisor = broken
    failed = planner.start_turn(_request("t-bad"), "t-bad")
    assert failed.wait(TURN_WAIT)
    with pytest.raises(PlanningError):
        failed.result()

    behaviour.supervisor = _supervisor()
    result = _finish(planner.start_turn(_request("t-good"), "t-good"))
    assert result.plan["status"] == "awaiting_approval"


def test_tools_run_in_process_when_mcp_is_off(planner):
    assert planner.tool_status() == {"mode": "in-process"}


def test_starting_twice_is_harmless(planner):
    planner.start(timeout=TURN_WAIT)
    result = _finish(planner.start_turn(_request("t-twice"), "t-twice"))
    assert result.plan["status"] == "awaiting_approval"


def test_a_main_model_with_a_key_needs_nothing(monkeypatch):
    monkeypatch.setattr(settings.llm, "runtime_model", ModelEnum.DEEPSEEK_FLASH)
    monkeypatch.setattr(settings.llm, "deepseek_api_key", "some-key")
    assert missing_llm_key() is None


def test_a_missing_deepseek_key_is_named_but_a_missing_fallback_key_is_not(monkeypatch):
    monkeypatch.setattr(settings.llm, "runtime_model", ModelEnum.DEEPSEEK_FLASH)
    monkeypatch.setattr(settings.llm, "deepseek_api_key", None)
    monkeypatch.setattr(settings.llm, "openai_api_key", "present")
    problem = missing_llm_key()
    assert problem is not None
    assert "DEEPSEEK_API_KEY" in problem
    assert "deepseek:deepseek-flash" in problem

    monkeypatch.setattr(settings.llm, "deepseek_api_key", "present")
    monkeypatch.setattr(settings.llm, "openai_api_key", None)
    assert missing_llm_key() is None


def test_an_openai_main_model_asks_for_the_openai_key(monkeypatch):
    monkeypatch.setattr(settings.llm, "runtime_model", ModelEnum.OPENAI_GPT41_MINI)
    monkeypatch.setattr(settings.llm, "openai_api_key", None)
    problem = missing_llm_key()
    assert problem is not None
    assert "OPENAI_API_KEY" in problem


def test_the_message_never_contains_a_key_value(monkeypatch):
    monkeypatch.setattr(settings.llm, "runtime_model", ModelEnum.OPENAI_GPT41_MINI)
    monkeypatch.setattr(settings.llm, "openai_api_key", None)
    monkeypatch.setattr(settings.llm, "deepseek_api_key", "sk-do-not-print")
    problem = missing_llm_key()
    assert problem is not None
    assert "sk-do-not-print" not in problem
