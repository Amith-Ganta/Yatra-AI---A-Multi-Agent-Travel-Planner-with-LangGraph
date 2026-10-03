"""Tests for the DeepEval agent evals (`evals/`) and their merge gate. No API key is needed.

Everything here checks code that decides what a score means: how a trace is cut down for the
judge, how the deterministic checks grade a run, and how the gate reads a summary. The judge
model itself is never called, so these tests prove the harness, not the agent's quality. The
live run is `python -m evals.eval_agent`.
"""

import csv
import importlib.util
import json
import math
import re
import threading
from datetime import date
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("deepeval")

from deepeval.dataset import Golden  # noqa: E402

import evals.report as report  # noqa: E402
import src.agents.graph as graph_module  # noqa: E402
from evals import dates, eval_agent, harness  # noqa: E402
from evals.judges import plan_judge  # noqa: E402
from evals.slim_trace import (  # noqa: E402
    PAUSED_OUTPUT,
    _SlimDict,  # pyright: ignore[reportPrivateUsage]
    slim_test_case,
    slim_trace,
    with_slim_trace,
)
from src.agents.state import new_request_state  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
GOLDENS = json.loads((ROOT / "evals" / "datasets" / "goldens.json").read_text(encoding="utf-8"))

gate_spec = importlib.util.spec_from_file_location(
    "eval_gate", ROOT / ".github" / "scripts" / "eval_gate.py"
)
assert gate_spec and gate_spec.loader
eval_gate = importlib.util.module_from_spec(gate_spec)
gate_spec.loader.exec_module(eval_gate)


def state(**changes: Any) -> dict[str, Any]:
    """A fresh request state with some fields changed."""
    return {**new_request_state("Plan a trip", "t-1", "u-1"), **changes}


def finished(approved: bool, revisions: int) -> dict[str, Any]:
    return {"plan": {}, "summary": "done", "approved": approved, "revisions": revisions}


# --- goldens -------------------------------------------------------------------------------


def test_goldens_are_consistent() -> None:
    assert len(GOLDENS) == 15
    for golden in GOLDENS:
        meta = golden["additional_metadata"]
        assert golden["input"].strip()
        assert meta["difficulty"] in {"easy", "medium", "difficult"}
        if meta["expect_allowed"]:
            assert meta["hitl"] in harness.HITL_SCRIPTS
            assert set(meta["expected_agents"]) <= set(harness.SELECTABLE_AGENTS)
            assert "flight" in meta["expected_agents"]
        else:
            assert meta["expected_agents"] == []


def test_goldens_split_is_ten_allowed_and_five_refused() -> None:
    # The docs quote this split. The $500 Tokyo trip for 4 people is a refusal: the first live run
    # (3 Oct 2026) showed the supervisor correctly rejects it as an unrealistic budget.
    allowed = [g for g in GOLDENS if g["additional_metadata"]["expect_allowed"]]
    refused = [g for g in GOLDENS if not g["additional_metadata"]["expect_allowed"]]
    assert (len(allowed), len(refused)) == (10, 5)
    assert any("$500 budget" in g["input"] for g in refused)
    hitl = sorted(g["additional_metadata"]["hitl"] for g in allowed)
    assert hitl == ["approve"] * 6 + ["reject_always"] + ["reject_once"] * 3


def test_goldens_cover_every_approval_script_and_refusals() -> None:
    allowed = [
        g["additional_metadata"] for g in GOLDENS if g["additional_metadata"]["expect_allowed"]
    ]
    assert {m["hitl"] for m in allowed} == set(harness.HITL_SCRIPTS)
    assert any(not g["additional_metadata"]["expect_allowed"] for g in GOLDENS)


def test_goldens_load_into_deepeval() -> None:
    golden = Golden(
        input=GOLDENS[0]["input"], additional_metadata=GOLDENS[0]["additional_metadata"]
    )
    assert golden.additional_metadata and golden.additional_metadata["hitl"] == "approve"


# --- the approval script -------------------------------------------------------------------


def test_decisions_for_each_script() -> None:
    assert [d["approved"] for d in harness.decisions_for("approve")] == [True]
    assert [d["approved"] for d in harness.decisions_for("reject_once")] == [False, True]
    always = harness.decisions_for("reject_always")
    assert len(always) == harness.MAX_REVISIONS + 1
    assert not any(d["approved"] for d in always)


def test_decisions_are_copies() -> None:
    harness.decisions_for("approve")[0]["approved"] = False
    assert harness.decisions_for("approve")[0]["approved"] is True


def test_unknown_script_is_an_error() -> None:
    with pytest.raises(ValueError, match="Unknown HITL script"):
        harness.decisions_for("approve_maybe")


def test_expected_ending_for_each_script() -> None:
    assert harness.expected_hitl("approve") == ("approved", 0)
    assert harness.expected_hitl("reject_once") == ("approved", 1)
    assert harness.expected_hitl("reject_always") == ("revision_limit", harness.MAX_REVISIONS)


def test_supervisor_failure_reason_matches_the_supervisor() -> None:
    source = (ROOT / "src" / "agents" / "supervisor.py").read_text(encoding="utf-8")
    assert harness.SUPERVISOR_FAILURE_REASON in source


# --- the plan document ---------------------------------------------------------------------


def test_final_plan_is_empty_without_state() -> None:
    assert harness.RunResult(thread_id="t").final_plan == {}


def test_final_plan_statuses() -> None:
    constraints = {"destination": "Lisbon", "start_date": "2099-04-10", "end_date": "2099-04-12"}
    refused = harness.RunResult(
        "t", state(allowed=False, reason="Off topic", final_response={"x": 1})
    )
    awaiting = harness.RunResult("t", state(allowed=True, trip_constraints=constraints))
    approved = harness.RunResult(
        "t",
        state(allowed=True, trip_constraints=constraints, final_response=finished(True, 0)),
    )
    limit = harness.RunResult(
        "t",
        state(allowed=True, trip_constraints=constraints, final_response=finished(False, 3)),
    )
    assert refused.final_plan["status"] == "rejected"
    assert awaiting.final_plan["status"] == "awaiting_approval"
    assert approved.final_plan["status"] == "approved"
    assert limit.final_plan["status"] == "revision_limit"


def test_outcome_text_for_a_crash_and_a_stall() -> None:
    crashed = harness.RunResult("t", state(), error="RuntimeError: boom")
    assert "crashed" in harness.outcome_text(crashed)
    assert "RuntimeError: boom" in harness.outcome_text(crashed)
    stalled = harness.RunResult("t", state(allowed=True), stalled=True)
    assert "no answer" in harness.outcome_text(stalled)


def test_outcome_text_reports_status_and_sections() -> None:
    constraints = {"destination": "Lisbon", "start_date": "2099-04-10", "end_date": "2099-04-12"}
    result = harness.RunResult(
        "t",
        state(
            allowed=True,
            trip_constraints=constraints,
            flight_output={"best_option": {"airline": "Fixture Air"}},
            final_response=finished(True, 0),
        ),
    )
    text = harness.outcome_text(result)
    assert "Plan status: approved" in text
    assert "Lisbon" in text
    assert "Fixture Air" in text


def test_outcome_text_keeps_long_sections_short() -> None:
    long_itinerary = {"days": ["x" * 400] * 20}
    result = harness.RunResult(
        "t",
        state(allowed=True, itinerary_output=long_itinerary, final_response=finished(True, 0)),
    )
    line = next(
        line for line in harness.outcome_text(result).splitlines() if line.startswith("Itinerary:")
    )
    assert len(line) <= len("Itinerary: ") + 1500


# --- guardrail, routing and approval checks ------------------------------------------------


def test_guardrail_passes_an_allowed_request() -> None:
    result = harness.RunResult("t", state(allowed=True))
    check = harness.check_guardrail(True, result)
    assert check.score == 1.0


def test_guardrail_fails_when_the_verdict_is_wrong() -> None:
    leaked = harness.check_guardrail(False, harness.RunResult("t", state(allowed=True)))
    blocked = harness.check_guardrail(True, harness.RunResult("t", state(reason="no")))
    assert leaked.score == 0.0 and "should have been refused" in str(leaked.reason)
    assert blocked.score == 0.0 and "should have been allowed" in str(blocked.reason)


def test_guardrail_passes_a_clean_refusal() -> None:
    refused = harness.RunResult("t", state(reason="Off topic", final_response={"x": 1}))
    assert harness.check_guardrail(False, refused).score == 1.0


def test_guardrail_fails_a_refusal_that_still_asked_for_approval() -> None:
    refused = harness.RunResult("t", state(reason="Off topic"), interrupts=1)
    check = harness.check_guardrail(False, refused)
    assert check.score == 0.0 and "approval" in str(check.reason)


def test_guardrail_reports_an_outage_as_an_error_not_a_verdict() -> None:
    outage = harness.RunResult("t", state(reason=harness.SUPERVISOR_FAILURE_REASON))
    for expect_allowed in (True, False):
        check = harness.check_guardrail(expect_allowed, outage)
        assert check.score is None and check.error


def test_checks_report_a_crashed_run_as_an_error() -> None:
    crashed = harness.RunResult("t", state(), error="ValueError: x")
    for check in (
        harness.check_guardrail(True, crashed),
        harness.check_routing(["flight"], crashed),
        harness.check_hitl("approve", crashed),
    ):
        assert check.score is None and "ValueError: x" in str(check.error)


def test_routing_passes_when_the_expected_agents_ran() -> None:
    result = harness.RunResult(
        "t",
        state(
            selected_agents=["flight", "weather", "itinerary"],
            flight_output={"ok": 1},
            weather_output={"ok": 1},
        ),
    )
    assert harness.check_routing(["flight", "weather"], result).score == 1.0


def test_routing_fails_when_the_graph_ran_something_else() -> None:
    result = harness.RunResult(
        "t", state(selected_agents=["flight", "hotel"], flight_output={"ok": 1})
    )
    check = harness.check_routing(["flight", "hotel"], result)
    assert check.score == 0.0 and "ran" in str(check.reason)


def test_routing_gives_partial_credit_for_a_missing_agent() -> None:
    result = harness.RunResult(
        "t",
        state(
            selected_agents=["flight", "weather"],
            flight_output={"ok": 1},
            weather_output={"ok": 1},
        ),
    )
    check = harness.check_routing(["flight", "hotel", "weather"], result)
    assert check.score == 0.67
    assert "missing ['hotel']" in str(check.reason)


def approval_result(script: str, **changes: Any) -> harness.RunResult:
    asked = len(harness.decisions_for(script))
    status, revisions = harness.expected_hitl(script)
    defaults: dict[str, Any] = {
        "interrupts": asked,
        "decisions_used": asked,
        "state": state(
            allowed=True,
            revision_count=revisions,
            final_response=finished(status == "approved", revisions),
        ),
    }
    return harness.RunResult("t", **{**defaults, **changes})


@pytest.mark.parametrize("script", harness.HITL_SCRIPTS)
def test_approval_loop_passes_when_every_script_ends_correctly(script: str) -> None:
    assert harness.check_hitl(script, approval_result(script)).score == 1.0


def test_approval_loop_fails_a_stalled_run() -> None:
    result = approval_result("approve", stalled=True, decisions_used=0)
    check = harness.check_hitl("approve", result)
    assert check.score is not None and check.score < 1.0
    assert "approval question" in str(check.reason)


def test_approval_loop_fails_a_wrong_revision_count() -> None:
    result = approval_result("reject_once")
    result.state["revision_count"] = 0
    check = harness.check_hitl("reject_once", result)
    assert check.score is not None and check.score < 1.0
    assert "revision" in str(check.reason)


def test_approval_loop_fails_when_a_rejection_loop_is_called_approved() -> None:
    result = approval_result("reject_always")
    result.state["final_response"] = finished(True, harness.MAX_REVISIONS)
    check = harness.check_hitl("reject_always", result)
    assert check.score is not None and check.score < 1.0
    assert "revision_limit" in str(check.reason)


# --- fixtures and environment --------------------------------------------------------------


def test_fixture_tools_swap_and_restore() -> None:
    names = ("search_flights", "search_hotels", "get_weather")
    originals = {name: getattr(graph_module, name) for name in names}
    with harness.fixture_tools():
        for name in names:
            assert getattr(graph_module, name) is not originals[name]
    for name in names:
        assert getattr(graph_module, name) is originals[name]


def test_fixture_tools_restore_after_an_error() -> None:
    original = graph_module.search_flights
    with pytest.raises(RuntimeError), harness.fixture_tools():
        raise RuntimeError("boom")
    assert graph_module.search_flights is original


async def test_fixture_tools_return_stable_data() -> None:
    with harness.fixture_tools():
        first = await graph_module.search_flights("Lisbon", "2099-04-10", 2, 1500.0)  # type: ignore[call-arg]
        again = await graph_module.search_flights("Lisbon", "2099-04-10", 2, 1500.0)  # type: ignore[call-arg]
        forecast = await graph_module.get_weather("Lisbon", "2099-04-10", "2099-04-12")  # type: ignore[call-arg]
    assert first == again
    assert first["best_option"]["price"] == min(f["price"] for f in first["flights"])
    assert [day["date"] for day in forecast["forecast"]] == [
        "2099-04-10",
        "2099-04-11",
        "2099-04-12",
    ]


def test_missing_keys_names_what_is_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert harness.missing_keys() == ["DEEPSEEK_API_KEY", "OPENAI_API_KEY"]
    monkeypatch.setenv("DEEPSEEK_API_KEY", "x")
    assert harness.missing_keys() == ["OPENAI_API_KEY"]
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    assert harness.missing_keys() == []


def test_missing_keys_treats_a_blank_value_as_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "  \n")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-real")
    assert harness.missing_keys() == ["DEEPSEEK_API_KEY"]


# --- dates that stay realistic ---------------------------------------------------------------


def test_resolve_dates_counts_from_the_pinned_day(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVAL_TODAY", "2026-10-03")
    assert dates.day(0) == "2026-10-03"
    assert dates.day(60) == "2026-12-02"
    assert dates.resolve_dates("from {d+60} to {d+64}") == "from 2026-12-02 to 2026-12-06"


def test_resolve_dates_leaves_plain_text_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVAL_TODAY", "2026-10-03")
    text = "Plan a trip to Lisbon next spring, budget $900 {not a date} {d+x}"
    assert dates.resolve_dates(text) == text


def test_today_ignores_a_blank_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVAL_TODAY", "  ")
    assert dates.today() == date.today()


def test_every_golden_resolves_to_realistic_dates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVAL_TODAY", "2026-10-03")
    for golden in GOLDENS:
        resolved = dates.resolve_dates(golden["input"])
        assert "{d+" not in resolved
        assert "2099" not in resolved
        for stamp in re.findall(r"\d{4}-\d{2}-\d{2}", resolved):
            offset = (date.fromisoformat(stamp) - date(2026, 10, 3)).days
            assert 30 <= offset <= 180


def test_a_trip_never_ends_before_it_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVAL_TODAY", "2026-10-03")
    for golden in GOLDENS:
        found = re.findall(r"\{d\+(\d+)\}", golden["input"])
        assert found == sorted(found, key=int)


def test_load_goldens_resolves_the_placeholders(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVAL_TODAY", "2026-10-03")
    loaded = eval_agent.load_goldens(None).goldens
    assert len(loaded) == len(GOLDENS)
    assert all("{d+" not in g.input for g in loaded)
    assert "2026-12-02" in loaded[0].input


def test_judge_model_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVAL_JUDGE_MODEL", raising=False)
    default = harness.judge_model_name()
    assert default and ":" not in default
    monkeypatch.setenv("EVAL_JUDGE_MODEL", "  gpt-4.1-mini ")
    assert harness.judge_model_name() == "gpt-4.1-mini"


# --- slimming a trace ----------------------------------------------------------------------


def span(name: str, kind: str = "chain", **fields: Any) -> dict[str, Any]:
    return {"name": name, "type": kind, "input": {"big": "x" * 50}, "children": [], **fields}


def sample_trace() -> dict[str, Any]:
    first_run = span(
        "LangGraph",
        children=[
            span("supervisor", output={"allowed": True}),
            span("route_from_supervisor", output="flight"),
            span("search_flights", "tool", input="Lisbon", output={"price": 120}),
            span("planner-llm", "llm", output="text"),
        ],
    )
    resumed = span("LangGraph", children=[span("human_approval", output=None)])
    return {
        "name": "yatra_run",
        "type": "agent",
        "input": {"args": "noise"},
        "output": "noise",
        "metrics": [threading.RLock()],
        "metric_collection": "should-never-reach-a-judge",
        "children": [first_run, resumed],
    }


def test_slim_trace_flattens_and_drops_noise() -> None:
    slim = slim_trace(sample_trace(), task="Plan a trip", outcome="Done")
    assert slim["input"] == "Plan a trip" and slim["output"] == "Done"
    assert "metrics" not in slim and "metric_collection" not in slim
    names = [child["name"] for child in slim["children"]]
    assert names == ["supervisor", "search_flights", "planner-llm", "human_approval"]


def test_slim_trace_keeps_what_each_node_needs() -> None:
    children = {c["name"]: c for c in slim_trace(sample_trace(), task="t", outcome="o")["children"]}
    assert "input" not in children["supervisor"]
    assert children["supervisor"]["output"] == {"allowed": True}
    assert children["search_flights"]["input"] == "Lisbon"
    assert children["search_flights"]["output"] == {"price": 120}
    assert children["planner-llm"]["output"] == "text"


def test_slim_trace_marks_the_paused_approval_step() -> None:
    children = {c["name"]: c for c in slim_trace(sample_trace(), task="t", outcome="o")["children"]}
    assert children["human_approval"]["output"] == PAUSED_OUTPUT


def test_slim_trace_does_not_change_the_original() -> None:
    trace = sample_trace()
    slim_trace(trace, task="t", outcome="o")
    assert trace["input"] == {"args": "noise"}
    assert len(trace["children"]) == 2 and "metrics" in trace


class FakeCase:
    def __init__(self, trace: Any) -> None:
        self.input = "Plan a trip"
        self.actual_output = "Done"
        self._trace_dict = trace


def test_slim_test_case_is_idempotent_and_survives_metric_locks() -> None:
    case = FakeCase(sample_trace())
    slim_test_case(case)
    assert isinstance(case._trace_dict, _SlimDict)
    first = dict(case._trace_dict)
    slim_test_case(case)
    assert dict(case._trace_dict) == first


@pytest.mark.parametrize("trace", [None, "text", 3])
def test_slim_test_case_ignores_a_case_without_a_trace(trace: Any) -> None:
    case = FakeCase(trace)
    slim_test_case(case)
    assert case._trace_dict == trace


def test_slim_test_case_can_save_the_trace(tmp_path: Path) -> None:
    case = FakeCase(sample_trace())
    slim_test_case(case, tmp_path)
    assert (tmp_path / "plan_a_trip.judge.json").exists()
    assert (tmp_path / "plan_a_trip.raw.json").exists()


def test_with_slim_trace_keeps_the_metric_name_and_slims_first() -> None:
    seen: list[Any] = []

    class TaskCompletionMetric:
        def measure(self, test_case: Any, *args: Any, **kwargs: Any) -> str:
            seen.append(test_case._trace_dict)
            return "scored"

    slim_cls = with_slim_trace(TaskCompletionMetric)
    # DeepEval picks its judge prompt by class name, so the subclass must answer to it.
    assert slim_cls.__name__ == "TaskCompletionMetric"
    assert slim_cls.__qualname__ == TaskCompletionMetric.__qualname__
    case = FakeCase(sample_trace())
    assert slim_cls().measure(case) == "scored"
    assert isinstance(seen[0], _SlimDict)


# --- the plan judge's inputs ---------------------------------------------------------------


def test_plan_steps_follow_graph_order_then_the_fixed_tail() -> None:
    steps = plan_judge.plan_steps(["weather", "flight"])
    assert [s.split(":")[0] for s in steps] == [
        "flight",
        "weather",
        "itinerary",
        "human_approval",
        "final_response",
    ]


def test_plan_steps_skip_unselected_agents_but_always_plan_the_itinerary() -> None:
    names = [s.split(":")[0] for s in plan_judge.plan_steps([])]
    assert names == ["itinerary", "human_approval", "final_response"]


def test_agents_the_trip_needs_follow_the_supervisor_rules() -> None:
    one_day = {"start_date": "2099-04-10", "end_date": "2099-04-10", "party_size": 1}
    long_trip = {"start_date": "2099-04-10", "end_date": "2099-04-14", "party_size": 1}
    assert plan_judge.agents_the_trip_needs("Fly to Rome", one_day) == ["flight", "weather"]
    assert "hotel" in plan_judge.agents_the_trip_needs("Fly to Rome", long_trip)
    assert "budget" in plan_judge.agents_the_trip_needs("Rome on a $900 budget", long_trip)
    assert "budget" in plan_judge.agents_the_trip_needs("Rome", {**long_trip, "party_size": 3})
    assert "budget" not in plan_judge.agents_the_trip_needs("Rome", long_trip)


def test_agents_the_trip_needs_survives_missing_dates() -> None:
    assert "hotel" not in plan_judge.agents_the_trip_needs("Rome", {})


def test_agents_not_in_plan() -> None:
    constraints = {"start_date": "2099-04-10", "end_date": "2099-04-14", "party_size": 2}
    missing = plan_judge.agents_not_in_plan("Rome", constraints, ["flight"])
    assert missing == ["hotel", "weather", "budget"]
    assert (
        plan_judge.agents_not_in_plan("Rome", constraints, ["flight", "hotel", "weather", "budget"])
        == []
    )


def test_plan_test_case_carries_the_context_the_judge_needs() -> None:
    constraints = {"destination": "Rome", "start_date": "2099-04-10", "end_date": "2099-04-14"}
    case = plan_judge.plan_test_case("Rome please", ["flight"], constraints)
    assert case.input == "Rome please"
    assert case.actual_output and case.actual_output.startswith("1. flight:")
    assert case.context and "destination=Rome" in case.context[0]
    assert "hotel" in case.context[1]
    complete = plan_judge.plan_test_case(
        "Rome", ["flight", "hotel", "weather"], {**constraints, "party_size": 1}
    )
    assert complete.context and "(none)" in complete.context[1]


def test_plan_test_case_accepts_hand_written_steps() -> None:
    case = plan_judge.plan_test_case("Rome", ["flight"], {}, steps=["teleport: invented agent"])
    assert case.actual_output == "1. teleport: invented agent"


def test_plan_judge_is_built_with_the_agreed_threshold() -> None:
    judge = plan_judge.make_plan_judge("gpt-4o-mini")
    assert judge.name == "Plan Quality (sees trip details)"
    assert judge.threshold == plan_judge.THRESHOLD == 0.7
    assert plan_judge.make_plan_judge("gpt-4o-mini") is not judge


# --- the report ----------------------------------------------------------------------------


def rows_for_report() -> list[tuple[Golden, dict[str, Any]]]:
    refused = Golden(input="Write me a poem", additional_metadata={"difficulty": "easy"})
    allowed = Golden(input="Rome trip", additional_metadata={"difficulty": "medium"})
    failing = harness.CheckMetric("Routing").failed("wrong agents")
    broken = harness.CheckMetric("Approval Loop").errored("The run crashed")
    return [
        (refused, {"Guardrail": harness.CheckMetric("Guardrail").passed("refused")}),
        (
            allowed,
            {
                "Guardrail": harness.CheckMetric("Guardrail").passed("allowed"),
                "Routing": failing,
                "Approval Loop": broken,
                "Plan Quality": harness.CheckMetric("Plan Quality", 0.7),
            },
        ),
    ]


def test_summarize_counts_passed_errors_and_unscored() -> None:
    summary = report.summarize(rows_for_report())
    assert summary["Guardrail"] == {
        "average": 1.0,
        "passed": 2,
        "errors": 0,
        "total": 2,
        "threshold": 1.0,
    }
    assert summary["Routing"]["passed"] == 0 and summary["Routing"]["average"] == 0.0
    assert summary["Approval Loop"]["errors"] == 1 and summary["Approval Loop"]["average"] is None
    assert summary["Plan Quality"]["errors"] == 1  # never scored: counts as an error
    assert summary["Plan Quality"]["total"] == 1


def test_write_report_handles_tasks_without_every_metric(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(report, "REPORT_DIR", tmp_path)
    markdown = report.write_report(rows_for_report(), "agent_eval")
    assert markdown.exists() and markdown.suffix == ".md"
    csv_file = next(tmp_path.glob("agent_eval_*.csv"))
    with csv_file.open(encoding="utf-8") as handle:
        lines = list(csv.DictReader(handle))
    assert [row["guardrail_status"] for row in lines] == ["PASS", "PASS"]
    assert lines[0]["routing_status"] == "" and lines[1]["routing_status"] == "FAIL"
    assert lines[1]["approval_loop_status"] == "ERROR"
    text = markdown.read_text(encoding="utf-8")
    assert "n/a" in text and "The run crashed" in text


# --- the merge gate ------------------------------------------------------------------------

ALLOWED = sum(1 for g in GOLDENS if g["additional_metadata"]["expect_allowed"])


def metric(passed: int, total: int, average: float = 1.0, errors: int = 0) -> dict[str, Any]:
    return {
        "average": average,
        "passed": passed,
        "errors": errors,
        "total": total,
        "threshold": 0.7,
    }


def good_summary() -> dict[str, Any]:
    judged = metric(ALLOWED, ALLOWED, 0.85)
    return {
        "judge_model": "gpt-4o-mini",
        "tools": "fixture",
        "tasks": len(GOLDENS),
        "metrics": {
            "Guardrail": metric(len(GOLDENS), len(GOLDENS)),
            "Routing": metric(ALLOWED, ALLOWED),
            "Approval Loop": metric(ALLOWED, ALLOWED),
            "Task Completion": dict(judged),
            "Plan Quality": dict(judged),
            "Plan Adherence": dict(judged),
            "Plan Quality (sees trip details)": dict(judged),
        },
    }


def test_gate_passes_a_good_run() -> None:
    assert eval_gate.evaluate(good_summary(), GOLDENS) == []


def test_gate_refuses_a_stub_judge() -> None:
    summary = {**good_summary(), "judge_model": "stub"}
    assert "stub judge" in eval_gate.evaluate(summary, GOLDENS)[0]


def test_gate_refuses_a_partial_run() -> None:
    summary = {**good_summary(), "tasks": 3}
    assert any("covered 3" in f for f in eval_gate.evaluate(summary, GOLDENS))


def test_gate_needs_every_guardrail_and_approval_task() -> None:
    summary = good_summary()
    summary["metrics"]["Guardrail"]["passed"] -= 1
    summary["metrics"]["Approval Loop"]["passed"] -= 1
    failures = eval_gate.evaluate(summary, GOLDENS)
    assert any(f.startswith("Guardrail") for f in failures)
    assert any(f.startswith("Approval Loop") for f in failures)


def test_gate_allows_routing_at_eighty_percent_and_no_lower() -> None:
    ok, bad = good_summary(), good_summary()
    ok["metrics"]["Routing"]["passed"] = math.ceil(0.8 * ALLOWED)  # exactly on the bar
    bad["metrics"]["Routing"]["passed"] = math.ceil(0.8 * ALLOWED) - 1  # one task short
    assert eval_gate.evaluate(ok, GOLDENS) == []
    assert any(f.startswith("Routing") for f in eval_gate.evaluate(bad, GOLDENS))


def test_gate_fails_a_low_judged_average() -> None:
    summary = good_summary()
    summary["metrics"]["Plan Quality (sees trip details)"]["average"] = 0.65
    failures = eval_gate.evaluate(summary, GOLDENS)
    assert [f.split(":")[0] for f in failures] == ["Plan Quality (sees trip details)"]


def test_gate_only_reports_the_two_built_in_plan_metrics() -> None:
    # The scores of the first live run (3 Oct 2026). Task Completion and the custom judge are fine.
    assert set(eval_gate.REPORT_ONLY) == {"Plan Quality", "Plan Adherence"}
    assert not {name for name, _, _ in eval_gate.RULES} & set(eval_gate.REPORT_ONLY)
    summary = good_summary()
    summary["metrics"]["Plan Quality"].update(average=0.55, passed=1)
    summary["metrics"]["Plan Adherence"].update(average=0.16, passed=1)
    assert eval_gate.evaluate(summary, GOLDENS) == []
    # Missing entirely is fine too: a report-only metric never decides the gate.
    del summary["metrics"]["Plan Adherence"]
    assert eval_gate.evaluate(summary, GOLDENS) == []


def test_gate_report_labels_the_report_only_rows() -> None:
    text = eval_gate.describe(good_summary())
    assert "Plan Quality (report only)" in text
    assert "Plan Adherence (report only)" in text
    assert "Plan Quality (sees trip details) " in text  # the gated judge keeps its plain name


def test_gate_counts_a_judge_outage_as_zero() -> None:
    summary = good_summary()
    # 7 of 10 tasks scored 0.85; the other 3 errored. The mean over all 10 is about 0.6.
    summary["metrics"]["Task Completion"].update(average=0.85, errors=3, passed=ALLOWED - 3)
    failures = eval_gate.evaluate(summary, GOLDENS)
    assert any(f.startswith("Task Completion") and "3 error" in f for f in failures)


def test_gate_fails_when_every_task_errored() -> None:
    summary = good_summary()
    judge = "Plan Quality (sees trip details)"
    summary["metrics"][judge].update(average=None, errors=ALLOWED, passed=0)
    assert any(f.startswith(judge) for f in eval_gate.evaluate(summary, GOLDENS))


def test_gate_fails_a_missing_or_short_metric() -> None:
    summary = good_summary()
    del summary["metrics"]["Plan Quality (sees trip details)"]
    summary["metrics"]["Routing"]["total"] = ALLOWED - 2
    failures = eval_gate.evaluate(summary, GOLDENS)
    assert any(f.startswith("Plan Quality (sees") and "not scored" in f for f in failures)
    assert any(f.startswith("Routing") and "expected" in f for f in failures)


def write_files(tmp_path: Path, summary: dict[str, Any]) -> list[str]:
    summary_file = tmp_path / "summary.json"
    summary_file.write_text(json.dumps(summary), encoding="utf-8")
    return ["--summary", str(summary_file)]


def test_gate_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert eval_gate.main(write_files(tmp_path, good_summary())) == 0
    assert "EVAL GATE PASSED" in capsys.readouterr().out

    low = good_summary()
    low["metrics"]["Task Completion"]["average"] = 0.2
    assert eval_gate.main(write_files(tmp_path, low)) == 1
    assert "EVAL GATE FAILED" in capsys.readouterr().out

    assert eval_gate.main(write_files(tmp_path, {**good_summary(), "judge_model": "stub"})) == 2
    assert eval_gate.main(write_files(tmp_path, {**good_summary(), "tasks": 1})) == 2


def test_gate_without_a_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    missing = ["--summary", str(tmp_path / "nothing.json")]
    assert eval_gate.main(missing) == 2
    assert eval_gate.main([*missing, "--allow-skip"]) == 0
    assert "SKIPPED" in capsys.readouterr().out
