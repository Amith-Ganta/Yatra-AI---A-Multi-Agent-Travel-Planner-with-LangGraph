"""Execution-level tests for the real LangGraph: run order, de-duplication and data flow.

The supervisor LLM and the network tools are replaced with fakes; routing, state merging,
the approval interrupt and every worker node are the production code. The graph runs with an
in-memory checkpointer, so pause and resume behave exactly as they do on Postgres.
"""

import json
from collections import Counter
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

import src.agents.graph as graph_module
from src.agents.graph import build_graph
from src.agents.routing import route_from_approval, route_from_supervisor, route_from_workers
from src.agents.state import new_request_state
from src.core.config import settings

ALL_NODES = [
    "supervisor",
    "flight",
    "hotel",
    "weather",
    "budget",
    "itinerary",
    "human_approval",
    "final_response",
]

CONSTRAINTS = {
    "destination": "Rome",
    "start_date": "2099-05-10",
    "end_date": "2099-05-13",
    "budget_usd": 2000,
    "party_size": 2,
    "trip_type": "leisure",
}


def _supervisor(allowed=True, selected=None, constraints=None):
    async def fake_supervisor(state):
        return {
            "allowed": allowed,
            "reason": "test",
            "selected_agents": selected if selected is not None else [],
            "trip_constraints": constraints if constraints is not None else dict(CONSTRAINTS),
        }

    return fake_supervisor


@pytest.fixture
def calls(monkeypatch):
    """Replace network tools with fakes that record how they were called."""
    recorded = {"flights": [], "hotels": [], "weather": []}

    async def fake_flights(destination, departure_date, party_size, budget):
        recorded["flights"].append((destination, departure_date, party_size, budget))
        flights = [{"airline": "TestAir", "price": 300.0}]
        return {"flights": flights, "best_option": flights[0]}

    async def fake_hotels(destination, budget):
        recorded["hotels"].append((destination, budget))
        return {"hotels": [{"name": "Hotel Test", "url": "https://example.com"}]}

    async def fake_weather(destination, start, end):
        recorded["weather"].append((destination, start, end))
        return {
            "forecast": [{"date": start, "temp_max": 22, "temp_min": 14, "condition": "Clear sky"}],
            "packing_advice": "Light layers.",
        }

    monkeypatch.setattr(graph_module, "search_flights", fake_flights)
    monkeypatch.setattr(graph_module, "search_hotels", fake_hotels)
    monkeypatch.setattr(graph_module, "get_weather", fake_weather)
    return recorded


APPROVE = {"approved": True, "feedback": ""}


def _reject(feedback):
    return {"approved": False, "feedback": feedback}


@dataclass
class Run:
    """What happened while a request ran to the end, answering every approval pause."""

    order: list[str]  # nodes in the order they finished
    state: dict[str, Any]  # the checkpointed state at the end
    pauses: list[dict[str, Any]]  # the interrupt payload of every approval pause


def _config(thread_id: str):
    return {"configurable": {"thread_id": thread_id}}


async def _drive(graph, graph_input, thread_id: str, decisions: list[dict[str, Any]]) -> Run:
    """Stream the graph; at each approval pause send the next decision (approve by default)."""
    config = _config(thread_id)
    pending = list(decisions)
    order: list[str] = []
    pauses: list[dict[str, Any]] = []
    while True:
        async for event in graph.astream(graph_input, config, stream_mode="updates"):
            order.extend(node for node in event if node != "__interrupt__")
        snapshot = await graph.aget_state(config)
        if not snapshot.interrupts:
            return Run(order, dict(snapshot.values), pauses)
        pauses.append(snapshot.interrupts[0].value)
        graph_input = Command(resume=pending.pop(0) if pending else APPROVE)


async def _run_full(monkeypatch, decisions=None, **supervisor_kwargs) -> Run:
    monkeypatch.setattr(graph_module, "supervisor_agent", _supervisor(**supervisor_kwargs))
    graph = build_graph(InMemorySaver())
    initial = new_request_state("Plan a trip to Rome", "t-1", "u-1")
    return await _drive(graph, initial, "t-1", decisions or [])


async def _run(monkeypatch, decisions=None, **supervisor_kwargs):
    """Run the graph; return (node run order, final state)."""
    run = await _run_full(monkeypatch, decisions, **supervisor_kwargs)
    return run.order, run.state


@pytest.mark.asyncio
async def test_every_node_runs_exactly_once(monkeypatch, calls):
    """F1: itinerary, approval and final response used to run twice."""
    order, _ = await _run(monkeypatch, selected=["flight", "hotel", "weather", "budget"])
    counts = Counter(order)
    assert {node: counts[node] for node in ALL_NODES} == {node: 1 for node in ALL_NODES}


@pytest.mark.asyncio
async def test_budget_runs_after_research_and_itinerary_after_budget(monkeypatch, calls):
    """F6: budget used to share a superstep with flight and never saw the flight cost."""
    order, _ = await _run(monkeypatch, selected=["flight", "hotel", "weather", "budget"])
    budget_at = order.index("budget")
    assert all(order.index(w) < budget_at for w in ["flight", "hotel", "weather"])
    assert budget_at < order.index("itinerary") < order.index("human_approval")
    assert order.index("human_approval") < order.index("final_response")


@pytest.mark.asyncio
async def test_budget_uses_real_flight_cost(monkeypatch, calls):
    """Flight price (300 per person x 2 travellers) must appear in the budget."""
    _, state = await _run(monkeypatch, selected=["flight", "budget"])
    budget = state["budget_output"]
    assert budget["categories"]["flights"] == 600.0
    assert budget["feasibility"] is True
    assert budget["total"] == pytest.approx(2000.0)


@pytest.mark.asyncio
async def test_budget_flags_flights_over_budget(monkeypatch, calls):
    _, state = await _run(
        monkeypatch,
        selected=["flight", "budget"],
        constraints={**CONSTRAINTS, "budget_usd": 400},
    )
    assert state["budget_output"]["feasibility"] is False


@pytest.mark.asyncio
async def test_workers_receive_supervisor_field_names(monkeypatch, calls):
    """F2: supervisor emits start_date/end_date/budget_usd; workers read other names."""
    await _run(monkeypatch, selected=["flight", "hotel", "weather"])
    assert calls["flights"] == [("Rome", "2099-05-10", 2, 2000.0)]
    assert calls["hotels"] == [("Rome", 2000.0)]
    assert calls["weather"] == [("Rome", "2099-05-10", "2099-05-13")]


@pytest.mark.asyncio
async def test_null_constraints_do_not_crash(monkeypatch, calls):
    """A supervisor that returns nulls for dates, budget and party size still plans a trip."""
    nulls = {
        "destination": "Rome",
        "start_date": None,
        "end_date": None,
        "budget_usd": None,
        "party_size": None,
        "trip_type": None,
    }
    order, state = await _run(monkeypatch, selected=["flight", "budget"], constraints=nulls)
    assert order[-1] == "final_response"
    assert state["final_response"]["plan"]["itinerary"]
    assert calls["flights"][0][2] == 1  # default party size


@pytest.mark.asyncio
async def test_itinerary_has_one_entry_per_day_with_real_dates(monkeypatch, calls):
    _, state = await _run(monkeypatch, selected=["flight", "weather"])
    days = state["itinerary_output"]["itinerary"]
    assert [d["date"] for d in days] == [
        "2099-05-10",
        "2099-05-11",
        "2099-05-12",
        "2099-05-13",
    ]
    assert "weather" in days[0]  # forecast merged into the matching day


@pytest.mark.asyncio
async def test_rejected_request_skips_workers(monkeypatch, calls):
    order, state = await _run(monkeypatch, allowed=False, selected=[])
    assert order == ["supervisor", "final_response"]
    assert not any(calls.values())
    assert state["final_response"]


@pytest.mark.asyncio
async def test_no_workers_selected_goes_straight_to_itinerary(monkeypatch, calls):
    order, _ = await _run(monkeypatch, selected=[])
    assert order == ["supervisor", "itinerary", "human_approval", "final_response"]


@pytest.mark.asyncio
async def test_budget_only_runs_budget_then_itinerary(monkeypatch, calls):
    order, _ = await _run(monkeypatch, selected=["budget"])
    assert order == ["supervisor", "budget", "itinerary", "human_approval", "final_response"]


def test_supervisor_route_fans_out_to_research_workers_only():
    state = {"allowed": True, "selected_agents": ["budget", "weather", "flight", "bogus"]}
    assert route_from_supervisor(state) == ["flight", "weather"]


def test_supervisor_route_never_returns_itinerary_in_a_list():
    """Returning itinerary in the fan-out list was the root cause of F1."""
    for selected in (["flight"], ["flight", "hotel", "weather", "budget"], []):
        routed = route_from_supervisor({"allowed": True, "selected_agents": selected})
        if isinstance(routed, list):
            assert "itinerary" not in routed
            assert "budget" not in routed


def test_worker_route_targets_budget_only_when_selected():
    assert route_from_workers({"selected_agents": ["flight", "budget"]}) == "budget"
    assert route_from_workers({"selected_agents": ["flight"]}) == "itinerary"
    assert route_from_workers({}) == "itinerary"


# --- Human-in-the-loop: the run pauses at approval and resumes on the person's answer ---


class FakeLLM:
    """Stands in for the chat model that rewrites the itinerary after a rejection."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.prompts: list[str] = []

    async def ainvoke(self, prompt: str) -> Any:
        self.prompts.append(prompt)
        return SimpleNamespace(content=self.reply)


class BrokenLLM:
    async def ainvoke(self, prompt: str) -> Any:
        raise RuntimeError("provider down")


def _use_llm(monkeypatch, llm: Any) -> None:
    monkeypatch.setattr(graph_module, "llm_factory", SimpleNamespace(get_llm=lambda: llm))


def _revised(activity: str, days: int = 4) -> str:
    """An LLM reply for the 4-day CONSTRAINTS trip (``days`` lets a test get the count wrong)."""
    entries = [{"day": n, "activities": [activity]} for n in range(1, days + 1)]
    return json.dumps({"itinerary": entries, "summary": f"Added {activity}."})


async def _advance(graph, graph_input: Any, thread_id: str) -> None:
    """Stream one run to its next stop (a pause or the end) and discard the events."""
    async for _ in graph.astream(graph_input, _config(thread_id), stream_mode="updates"):
        pass


async def _start(monkeypatch, thread_id: str = "t-1"):
    """A graph with an in-memory checkpointer, paused at the approval step."""
    monkeypatch.setattr(graph_module, "supervisor_agent", _supervisor(selected=["flight"]))
    graph = build_graph(InMemorySaver())
    await _advance(graph, new_request_state("Plan a trip to Rome", thread_id, "u-1"), thread_id)
    return graph


@pytest.mark.asyncio
async def test_run_pauses_at_approval_without_a_final_response(monkeypatch, calls):
    graph = await _start(monkeypatch)
    snapshot = await graph.aget_state(_config("t-1"))

    assert snapshot.next == ("human_approval",)
    assert snapshot.values["itinerary_output"]["itinerary"]
    assert not snapshot.values.get("final_response")
    assert snapshot.interrupts[0].value["kind"] == "plan_approval"


@pytest.mark.asyncio
async def test_pause_payload_reports_revision_and_cap(monkeypatch, calls):
    run = await _run_full(monkeypatch, selected=["flight"])
    assert len(run.pauses) == 1
    assert run.pauses[0]["revision"] == 0
    assert run.pauses[0]["max_revisions"] == settings.mcp.max_revisions


@pytest.mark.asyncio
async def test_approval_resumes_to_the_final_response(monkeypatch, calls):
    graph = await _start(monkeypatch)
    config = _config("t-1")

    order: list[str] = []
    async for event in graph.astream(Command(resume=APPROVE), config, stream_mode="updates"):
        order.extend(event)
    snapshot = await graph.aget_state(config)

    assert order == ["human_approval", "final_response"]
    assert snapshot.values["final_response"]["approved"] is True
    assert snapshot.values["final_response"]["revisions"] == 0
    assert snapshot.next == ()


@pytest.mark.asyncio
async def test_rejection_revises_the_itinerary_then_pauses_again(monkeypatch, calls):
    _use_llm(monkeypatch, FakeLLM(_revised("a food tour")))

    run = await _run_full(monkeypatch, [_reject("more food"), APPROVE], selected=["flight"])

    assert run.order.count("itinerary") == 2 and run.order.count("revise") == 1
    assert run.order.count("human_approval") == 2
    assert [p["revision"] for p in run.pauses] == [0, 1]
    itinerary = run.state["itinerary_output"]
    assert itinerary["feedback_applied"] is True
    assert all(day["activities"] == ["a food tour"] for day in itinerary["itinerary"])
    assert itinerary["itinerary"][0]["date"] == "2099-05-10"  # dates stay computed by the graph
    assert run.state["final_response"]["approved"] is True
    assert run.state["final_response"]["revisions"] == 1


@pytest.mark.asyncio
async def test_feedback_reaches_the_llm_inside_its_own_tags(monkeypatch, calls):
    llm = FakeLLM(_revised("a museum"))
    _use_llm(monkeypatch, llm)

    await _run_full(monkeypatch, [_reject("more museums"), APPROVE], selected=["flight"])

    assert len(llm.prompts) == 1
    assert "<feedback>\nmore museums\n</feedback>" in llm.prompts[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reply",
    ["not json at all", json.dumps({"itinerary": []}), _revised("x", days=9)],
    ids=["not-json", "no-days", "wrong-day-count"],
)
async def test_unusable_llm_reply_keeps_the_previous_draft_and_says_so(monkeypatch, calls, reply):
    baseline = await _run_full(monkeypatch, selected=["flight"])
    _use_llm(monkeypatch, FakeLLM(reply))

    run = await _run_full(monkeypatch, [_reject("change it"), APPROVE], selected=["flight"])

    itinerary = run.state["itinerary_output"]
    assert itinerary["feedback_applied"] is False
    assert "unchanged" in itinerary["revision_note"]
    assert itinerary["itinerary"] == baseline.state["itinerary_output"]["itinerary"]


@pytest.mark.asyncio
async def test_llm_outage_during_revision_does_not_crash_the_run(monkeypatch, calls):
    _use_llm(monkeypatch, BrokenLLM())

    run = await _run_full(monkeypatch, [_reject("change it"), APPROVE], selected=["flight"])

    assert run.state["itinerary_output"]["feedback_applied"] is False
    assert run.state["final_response"]["approved"] is True


@pytest.mark.asyncio
async def test_revision_cap_stops_the_loop_with_an_unapproved_plan(monkeypatch, calls):
    monkeypatch.setattr(settings.mcp, "max_revisions", 2)
    _use_llm(monkeypatch, FakeLLM(_revised("a hike")))

    run = await _run_full(
        monkeypatch,
        [_reject("one"), _reject("two"), _reject("three")],
        selected=["flight"],
    )

    assert run.order.count("revise") == 2
    assert [p["revision"] for p in run.pauses] == [0, 1, 2]
    final = run.state["final_response"]
    assert final["approved"] is False and final["revisions"] == 2
    assert "Revision limit" in final["summary"]


@pytest.mark.asyncio
async def test_zero_revisions_means_a_rejection_ends_the_run(monkeypatch, calls):
    monkeypatch.setattr(settings.mcp, "max_revisions", 0)

    run = await _run_full(monkeypatch, [_reject("no")], selected=["flight"])

    assert "revise" not in run.order
    assert run.state["final_response"]["approved"] is False


@pytest.mark.asyncio
async def test_resume_value_that_is_not_a_decision_is_not_an_approval(monkeypatch, calls):
    graph = await _start(monkeypatch)

    await _advance(graph, Command(resume="yes please"), "t-1")
    snapshot = await graph.aget_state(_config("t-1"))

    assert snapshot.next == ("human_approval",)  # paused again, nothing was approved
    assert snapshot.interrupts[0].value["revision"] == 1
    assert not snapshot.values.get("final_response")


@pytest.mark.asyncio
async def test_approved_must_be_exactly_true(monkeypatch, calls):
    graph = await _start(monkeypatch)

    await _advance(graph, Command(resume={"approved": "true", "feedback": "x"}), "t-1")

    assert (await graph.aget_state(_config("t-1"))).next == ("human_approval",)


@pytest.mark.asyncio
async def test_threads_pause_and_resume_independently(monkeypatch, calls):
    monkeypatch.setattr(graph_module, "supervisor_agent", _supervisor(selected=["flight"]))
    graph = build_graph(InMemorySaver())
    for thread in ("a", "b"):
        await _advance(graph, new_request_state("Plan a trip to Rome", thread, "u-1"), thread)

    await _advance(graph, Command(resume=APPROVE), "a")

    assert (await graph.aget_state(_config("a"))).next == ()
    assert (await graph.aget_state(_config("b"))).next == ("human_approval",)


@pytest.mark.asyncio
async def test_new_message_on_a_paused_thread_starts_a_clean_request(monkeypatch, calls):
    _use_llm(monkeypatch, FakeLLM(_revised("a hike")))
    graph = await _start(monkeypatch)
    await _advance(graph, Command(resume=_reject("change")), "t-1")
    assert (await graph.aget_state(_config("t-1"))).values["revision_count"] == 1

    await _advance(graph, new_request_state("Plan another trip", "t-1", "u-1"), "t-1")
    snapshot = await graph.aget_state(_config("t-1"))

    assert snapshot.next == ("human_approval",)
    assert snapshot.values["revision_count"] == 0
    assert snapshot.values["feedback"] == ""
    assert snapshot.interrupts[0].value["revision"] == 0


@pytest.mark.asyncio
async def test_unknown_or_finished_thread_has_nothing_to_resume(monkeypatch, calls):
    graph = await _start(monkeypatch)
    await _advance(graph, Command(resume=APPROVE), "t-1")

    for thread in ("t-1", "never-existed"):
        snapshot = await graph.aget_state(_config(thread))
        assert snapshot.next == () and snapshot.interrupts == ()


@pytest.mark.asyncio
async def test_rejected_request_never_pauses(monkeypatch, calls):
    run = await _run_full(monkeypatch, allowed=False, selected=[])
    assert run.pauses == []


def test_approval_route_follows_the_decision_and_the_cap(monkeypatch):
    monkeypatch.setattr(settings.mcp, "max_revisions", 3)
    assert route_from_approval({"human_approval": True, "revision_count": 0}) == "final_response"
    assert route_from_approval({"human_approval": False, "revision_count": 2}) == "revise"
    assert route_from_approval({"human_approval": False, "revision_count": 3}) == "final_response"
    assert route_from_approval({}) == "revise"
