"""Run one Yatra request through the real graph, with its approval loop, and keep what evals need.

Three problems are solved here:

1. The approval question. `human_approval` raises a LangGraph interrupt, and DeepEval's stock
   `CallbackHandler` has no `on_chain_error`, so an interrupt leaves spans open and the trace
   crashes at close. `InterruptAwareHandler` closes them.
2. One trace per request. A run, an interrupt and a resume are separate graph runs. An outer
   `@observe` span (`yatra_run`) wraps all of them, so DeepEval sees a single trace and scores
   the whole conversation instead of a partial tree.
3. Deterministic checks. Guardrail, routing and approval-loop behaviour are facts about the
   graph, not opinions, so they are checked by code (`CheckMetric`) and never by a judge model.
"""

import contextlib
import json
import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Optional

from deepeval.integrations.langchain import CallbackHandler
from deepeval.integrations.langchain.utils import exit_current_context
from deepeval.tracing import observe, update_current_trace
from deepeval.tracing.tracing import trace_manager
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphInterrupt
from langgraph.types import Command

import src.agents.graph as graph_module
from src.agents.graph import build_graph
from src.agents.plan import build_plan, plan_message_text
from src.agents.state import new_request_state
from src.core.config import settings

# The exact reason `src/agents/supervisor.py` returns when its LLM call raises. It is an outage,
# not a guardrail verdict, so the guardrail check reports it as an error instead of a pass or fail.
SUPERVISOR_FAILURE_REASON = "We could not process your request right now. Please try again."

# Agents the supervisor can choose. Itinerary always runs, so it is never a choice.
SELECTABLE_AGENTS = ("flight", "hotel", "weather", "budget")

MAX_REVISIONS = settings.mcp.max_revisions

APPROVE: dict[str, Any] = {"approved": True, "feedback": ""}

# How the scripted traveller answers the approval question. Each name is used in the goldens.
HITL_SCRIPTS = ("approve", "reject_once", "reject_always")


def decisions_for(script: str) -> list[dict[str, Any]]:
    """The traveller's answers for one script, in the order the questions are asked."""
    if script == "approve":
        return [dict(APPROVE)]
    if script == "reject_once":
        return [
            {"approved": False, "feedback": "Please add more food and local cuisine stops."},
            dict(APPROVE),
        ]
    if script == "reject_always":
        reject = {"approved": False, "feedback": "Make it cheaper with more free activities."}
        return [dict(reject) for _ in range(MAX_REVISIONS + 1)]
    raise ValueError(f"Unknown HITL script: {script!r} (expected one of {HITL_SCRIPTS})")


def expected_hitl(script: str) -> tuple[str, int]:
    """The plan status and revision count the graph must end with for a script."""
    if script == "reject_always":
        return "revision_limit", MAX_REVISIONS
    return "approved", len(decisions_for(script)) - 1


class InterruptAwareHandler(CallbackHandler):
    """DeepEval's LangChain handler, taught to close spans when a chain ends in an error.

    The stock handler only exits a span on success. A `GraphInterrupt` (the approval question)
    or any other error would leave the span open, and the trace then crashes with
    `TraceApi.endTime None`. An interrupt is a normal pause, so it closes cleanly; a real error
    is recorded on the span.
    """

    def on_chain_error(  # type: ignore[override]
        self, error: BaseException, *, run_id: Any, parent_run_id: Any = None, **kwargs: Any
    ) -> None:
        uuid_str = str(run_id)
        if trace_manager.get_span_by_uuid(uuid_str) is None:
            return
        with self._ctx(run_id=run_id, parent_run_id=parent_run_id):
            if isinstance(error, GraphInterrupt):
                exit_current_context(uuid_str=uuid_str)
            else:
                exit_current_context(uuid_str=uuid_str, exc_type=type(error), exc_val=error)
        self._restore_observe_parent(parent_run_id)


@dataclass
class RunResult:
    """What one request left behind."""

    thread_id: str
    state: dict[str, Any] = field(default_factory=dict)
    interrupts: int = 0
    decisions_used: int = 0
    stalled: bool = False
    error: Optional[str] = None
    outcome: str = ""

    @property
    def final_plan(self) -> dict[str, Any]:
        """The plan document the API would show for this state (status, trip, approval...).

        The graph's own `final_response["plan"]` is only the raw itinerary, so the document is
        built the way the API builds it. A run with no final response is still at the approval
        question.
        """
        if not self.state:
            return {}
        finished = bool(self.state.get("final_response"))
        return build_plan(self.state, awaiting_approval=not finished, max_revisions=MAX_REVISIONS)


def new_thread_id() -> str:
    return f"eval-{uuid.uuid4().hex[:12]}"


def build_eval_graph() -> Any:
    """The real compiled graph with an in-memory checkpointer (no database needed)."""
    return build_graph(InMemorySaver())


async def drive(
    graph: Any,
    graph_input: dict[str, Any],
    thread_id: str,
    decisions: list[dict[str, Any]],
    handler: CallbackHandler,
) -> RunResult:
    """Stream the graph, answering each approval question from `decisions`, until it finishes."""
    result = RunResult(thread_id=thread_id)
    state_config = {"configurable": {"thread_id": thread_id}}
    config = {**state_config, "callbacks": [handler]}
    pending = list(decisions)
    current: Any = graph_input
    try:
        while True:
            async for _ in graph.astream(current, config, stream_mode="updates"):
                pass
            snapshot = await graph.aget_state(state_config)
            result.state = dict(snapshot.values)
            if not snapshot.interrupts:
                break
            result.interrupts += 1
            if not pending:
                result.stalled = True
                break
            current = Command(resume=pending.pop(0))
            result.decisions_used += 1
    except Exception as exc:  # noqa: BLE001 - a crashed run is a result to report, not to raise
        result.error = f"{type(exc).__name__}: {exc}"
        with contextlib.suppress(Exception):
            snapshot = await graph.aget_state(state_config)
            result.state = dict(snapshot.values)
    return result


def _compact(value: Any, limit: int) -> str:
    text = json.dumps(value, default=str, ensure_ascii=False)
    return text if len(text) <= limit else text[: limit - 3] + "..."


_SECTION_LIMITS = {
    "trip": 300,
    "flights": 500,
    "hotels": 500,
    "weather": 500,
    "budget": 500,
    "itinerary": 1500,
    "approval": 300,
}


def outcome_text(result: RunResult) -> str:
    """What the traveller ended up with, as plain text for the judges."""
    if result.error:
        return f"The run crashed before it finished: {result.error}"
    final = result.state.get("final_response")
    plan = result.final_plan
    lines: list[str] = []
    if result.stalled:
        lines.append("The run stopped at the approval question and got no answer.")
    summary = (
        final.get("summary") if isinstance(final, dict) else None
    )  # pyright: ignore[reportUnknownMemberType]
    lines.append(str(summary or plan_message_text(plan)))
    lines.append(f"Plan status: {plan.get('status')}")
    if plan.get("reason"):
        lines.append(f"Reason: {plan['reason']}")
    for key, limit in _SECTION_LIMITS.items():
        if plan.get(key) is not None:
            lines.append(f"{key.title()}: {_compact(plan[key], limit)}")
    return "\n".join(lines)


@observe(type="agent", name="yatra_run")
async def run_traced(
    graph: Any,
    task: str,
    thread_id: str,
    decisions: list[dict[str, Any]],
    handler: CallbackHandler,
    metrics: list[Any],
) -> RunResult:
    """Drive one request under a single root span and attach the trace-level metrics to it."""
    graph_input = new_request_state(task, thread_id, "eval-user")
    result = await drive(graph, graph_input, thread_id, decisions, handler)
    result.outcome = outcome_text(result)
    update_current_trace(input=task, output=result.outcome, metrics=metrics)
    return result


class CheckMetric:
    """A pass/fail fact checked by code, shaped like a DeepEval metric so the report can read it."""

    def __init__(self, name: str, threshold: float = 1.0) -> None:
        self.name = name
        self.threshold = threshold
        self.score: Optional[float] = None
        self.reason: Optional[str] = None
        self.error: Optional[str] = None

    def passed(self, reason: str) -> "CheckMetric":
        self.score, self.reason = 1.0, reason
        return self

    def failed(self, reason: str) -> "CheckMetric":
        self.score, self.reason = 0.0, reason
        return self

    def scored(self, score: float, reason: str) -> "CheckMetric":
        self.score, self.reason = round(score, 2), reason
        return self

    def errored(self, error: str) -> "CheckMetric":
        self.error = error
        return self


def check_guardrail(expect_allowed: bool, result: RunResult) -> CheckMetric:
    """Did the supervisor let travel requests through and stop everything else?"""
    check = CheckMetric("Guardrail")
    state = result.state
    if result.error:
        return check.errored(f"The run crashed: {result.error}")
    reason = str(state.get("reason") or "")
    allowed = bool(state.get("allowed"))
    if not allowed and reason == SUPERVISOR_FAILURE_REASON:
        return check.errored(
            "The supervisor call failed (model or key problem), so there is no guardrail verdict."
        )
    verdict = f"The supervisor {'allowed' if allowed else 'refused'} the request"
    if allowed != expect_allowed:
        wanted = "allowed" if expect_allowed else "refused"
        return check.failed(f"{verdict}, but it should have been {wanted}. Reason: {reason}")
    if expect_allowed:
        return check.passed(f"{verdict}, as expected.")
    problems: list[str] = []
    if result.interrupts:
        problems.append("a refused request still asked for approval")
    if result.final_plan.get("status") != "rejected":
        problems.append("the final plan is not marked rejected")
    if problems:
        return check.failed(f"{verdict}, but " + " and ".join(problems) + ".")
    return check.passed(f"{verdict} and stopped without a plan, as expected. Reason: {reason}")


def check_routing(expected_agents: list[str], result: RunResult) -> CheckMetric:
    """Did the supervisor pick the agents the request needs, and did the graph run exactly those?"""
    check = CheckMetric("Routing")
    state = result.state
    if result.error:
        return check.errored(f"The run crashed: {result.error}")
    chosen = {a for a in (state.get("selected_agents") or []) if a in SELECTABLE_AGENTS}
    wanted = set(expected_agents)
    ran = {a for a in SELECTABLE_AGENTS if state.get(f"{a}_output") is not None}
    if ran != chosen:
        return check.failed(
            f"The graph ran {sorted(ran)} but the supervisor selected {sorted(chosen)}."
        )
    union = chosen | wanted
    score = len(chosen & wanted) / len(union) if union else 1.0
    if chosen == wanted:
        return check.passed(f"Selected exactly {sorted(wanted)}.")
    missing, extra = sorted(wanted - chosen), sorted(chosen - wanted)
    return check.scored(score, f"Expected {sorted(wanted)}; missing {missing}, unexpected {extra}.")


def check_hitl(script: str, result: RunResult) -> CheckMetric:
    """Did the approval loop behave: every question asked once, revisions counted, right ending?"""
    check = CheckMetric("Approval Loop")
    if result.error:
        return check.errored(f"The run crashed: {result.error}")
    status, revisions = expected_hitl(script)
    plan = result.final_plan
    final = result.state.get("final_response")
    final_revisions = (
        final.get("revisions") if isinstance(final, dict) else None
    )  # pyright: ignore[reportUnknownMemberType]
    asked = len(decisions_for(script))
    facts = {
        f"asked {asked} approval question(s) and used every answer": (
            result.interrupts == asked and result.decisions_used == asked and not result.stalled
        ),
        f"ended with status {status!r}": plan.get("status") == status,
        f"counted {revisions} revision(s)": (
            result.state.get("revision_count") == revisions and final_revisions == revisions
        ),
    }
    failed = [name for name, ok in facts.items() if not ok]
    if not failed:
        return check.passed("The loop " + ", ".join(facts) + ".")
    detail = (
        f"got interrupts={result.interrupts}, status={plan.get('status')!r}, "
        f"revision_count={result.state.get('revision_count')}"
    )
    score = (len(facts) - len(failed)) / len(facts)
    return check.scored(score, f"Did not: {', '.join(failed)} ({detail}).")


def _fixture_days(start: str, end: str) -> list[str]:
    try:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        return [start]
    days = max((last - first).days + 1, 1)
    return [(first + timedelta(days=i)).isoformat() for i in range(min(days, 16))]


async def _fixture_flights(
    destination: str, departure_date: str, party_size: int, budget: float
) -> dict[str, Any]:
    base = 120.0 + sum(map(ord, destination.lower())) % 400
    flights = [
        {"airline": "Fixture Air", "price": base, "stops": 0, "departure_date": departure_date},
        {
            "airline": "Fixture Connect",
            "price": round(base * 1.25, 2),
            "stops": 1,
            "departure_date": departure_date,
        },
    ]
    return {
        "flights": flights,
        "best_option": min(flights, key=lambda f: f["price"]),
        "source": "fixture",
    }


async def _fixture_hotels(destination: str, budget: float) -> dict[str, Any]:
    hotels = [
        {"name": f"{destination} Central Hotel", "price_per_night": 110.0, "rating": 4.3},
        {"name": f"{destination} Riverside Inn", "price_per_night": 85.0, "rating": 4.0},
        {"name": f"{destination} Budget Stay", "price_per_night": 55.0, "rating": 3.7},
    ]
    for index, hotel in enumerate(hotels, 1):
        hotel["url"] = f"https://example.com/hotels/{index}"
    return {"hotels": hotels, "status": "ok"}


async def _fixture_weather(destination: str, start: str, end: str) -> dict[str, Any]:
    forecast = [
        {"date": day, "temp_max": 22, "temp_min": 14, "condition": "Partly cloudy"}
        for day in _fixture_days(start, end)
    ]
    return {
        "current": {},
        "forecast": forecast,
        "packing_advice": "Pack light layers and a compact umbrella.",
        "status": "ok",
        "source": "fixture",
        "location": destination,
    }


@contextlib.contextmanager
def fixture_tools() -> Iterator[None]:
    """Swap the flight, hotel and weather tools for deterministic fixtures.

    The tools return different data on every call (flights are mock, hotels need a Tavily key,
    weather depends on the date), which would make scores drift for reasons that have nothing to
    do with the agent. The supervisor and the itinerary revision still call the real model.
    Call before `build_graph`: the graph binds these names when it is built.
    """
    fixtures = {
        "search_flights": _fixture_flights,
        "search_hotels": _fixture_hotels,
        "get_weather": _fixture_weather,
    }
    saved = {name: getattr(graph_module, name) for name in fixtures}
    for name, fixture in fixtures.items():
        setattr(graph_module, name, fixture)
    try:
        yield
    finally:
        for name, original in saved.items():
            setattr(graph_module, name, original)


def judge_model_name() -> str:
    """The model that grades. `EVAL_JUDGE_MODEL` overrides it. It never has fallbacks."""
    override = os.getenv("EVAL_JUDGE_MODEL", "").strip()
    return override or settings.llm.eval_model.value.split(":", 1)[1]


def missing_keys() -> list[str]:
    """API keys a live run needs and does not have (the runtime model and the judge)."""
    return [key for key in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY") if not os.getenv(key)]
