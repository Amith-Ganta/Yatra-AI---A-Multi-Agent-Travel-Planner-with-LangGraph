"""Score the Yatra travel agent with DeepEval.

    python -m evals.eval_agent                 # all goldens, deterministic tool fixtures
    python -m evals.eval_agent --live-tools    # real flight/hotel/weather tools too
    python -m evals.eval_agent --limit 3       # first three goldens (a cheap smoke run)

Each golden is run through the real LangGraph graph, including the approval loop (a scripted
traveller approves or rejects). One request becomes one DeepEval trace, which is then scored by:

- Task Completion, Plan Quality, Plan Adherence: DeepEval's trace metrics.
- Plan Quality (sees trip details): a custom GEval judge that also sees the trip numbers.
- Guardrail, Routing, Approval Loop: facts checked by code, not by a judge model.

A refused request (off-topic or unsafe) has no plan to grade, so it is only scored on Guardrail.
"""

import argparse
import contextlib
import json
import sys
from pathlib import Path
from typing import Any

from deepeval.dataset import EvaluationDataset, Golden
from deepeval.evaluate.configs import AsyncConfig, DisplayConfig
from deepeval.metrics import PlanAdherenceMetric, PlanQualityMetric, TaskCompletionMetric
from deepeval.utils import get_or_create_event_loop

from evals.dates import resolve_dates
from evals.harness import (
    InterruptAwareHandler,
    build_eval_graph,
    check_guardrail,
    check_hitl,
    check_routing,
    decisions_for,
    fixture_tools,
    judge_model_name,
    missing_keys,
    new_thread_id,
    run_traced,
)
from evals.judges.plan_judge import THRESHOLD, make_plan_judge, plan_test_case
from evals.report import REPORT_DIR, summarize, write_report
from evals.slim_trace import with_slim_trace

ROOT = Path(__file__).resolve().parent
GOLDENS_PATH = ROOT / "datasets" / "goldens.json"
TRACES_DIR = ROOT / "traces"
SUMMARY_PATH = REPORT_DIR / "latest_summary.json"

SlimTaskCompletion = with_slim_trace(TaskCompletionMetric, save_dir=TRACES_DIR)
SlimPlanQuality = with_slim_trace(PlanQualityMetric, save_dir=TRACES_DIR)
SlimPlanAdherence = with_slim_trace(PlanAdherenceMetric, save_dir=TRACES_DIR)


def deepeval_metrics(judge: str) -> dict[str, Any]:
    """Fresh DeepEval trace metrics for one task (a metric keeps its score, so never reuse one)."""
    options: dict[str, Any] = {
        "threshold": THRESHOLD,
        "model": judge,
        "include_reason": True,
        "async_mode": False,
    }
    return {
        "Task Completion": SlimTaskCompletion(**options),
        "Plan Quality": SlimPlanQuality(**options),
        "Plan Adherence": SlimPlanAdherence(**options),
    }


def load_goldens(limit: int | None) -> EvaluationDataset:
    dataset = EvaluationDataset()
    dataset.add_goldens_from_json_file(str(GOLDENS_PATH))
    for golden in dataset.goldens:
        golden.input = resolve_dates(golden.input)  # `{d+60}` becomes a date 60 days from today
    if limit:
        dataset = EvaluationDataset(goldens=list(dataset.goldens)[:limit])
    return dataset


def run_golden(golden: Golden, graph: Any, loop: Any, judge: str) -> tuple[dict[str, Any], Any]:
    """Run one golden. Returns its metrics (some score later, when the trace closes) and result."""
    meta = golden.additional_metadata or {}
    allowed = bool(meta.get("expect_allowed", True))
    script = str(meta.get("hitl", "approve"))
    metrics: dict[str, Any] = deepeval_metrics(judge) if allowed else {}
    result = loop.run_until_complete(
        run_traced(
            graph,
            str(golden.input),
            new_thread_id(),
            decisions_for(script) if allowed else [],
            InterruptAwareHandler(),
            list(metrics.values()),
        )
    )
    checks: dict[str, Any] = {"Guardrail": check_guardrail(allowed, result)}
    if allowed:
        checks["Routing"] = check_routing(list(meta.get("expected_agents", [])), result)
        checks["Approval Loop"] = check_hitl(script, result)
    return {**checks, **metrics}, result


def judge_plan(golden: Golden, result: Any, judge: str) -> Any:
    """The custom plan judge, measured by hand so a judge failure is recorded, not fatal."""
    plan_judge = make_plan_judge(judge)
    constraints = result.state.get("trip_constraints") or {}
    selected = list(result.state.get("selected_agents") or [])
    try:
        plan_judge.measure(plan_test_case(str(golden.input), selected, constraints))
    except Exception as exc:  # noqa: BLE001 - one judge failure must not stop the run
        plan_judge.error = f"{type(exc).__name__}: {exc}"
    return plan_judge


def write_summary(rows: list[tuple[Any, dict[str, Any]]], judge: str, live_tools: bool) -> Path:
    """Machine-readable results for the CI gate (`.github/scripts/eval_gate.py`)."""
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "judge_model": judge,
        "tools": "live" if live_tools else "fixture",
        "tasks": len(rows),
        "metrics": summarize(rows),
    }
    SUMMARY_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return SUMMARY_PATH


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score the Yatra agent with DeepEval.")
    parser.add_argument("--live-tools", action="store_true", help="use the real tools")
    parser.add_argument("--limit", type=int, default=None, help="run only the first N goldens")
    args = parser.parse_args(argv)

    missing = missing_keys()
    if missing:
        print(f"Cannot run live evals: {', '.join(missing)} not set. Nothing was scored.")
        return 2

    judge = judge_model_name()
    dataset = load_goldens(args.limit)
    loop = get_or_create_event_loop()
    rows: list[tuple[Golden, dict[str, Any]]] = []
    tools = contextlib.nullcontext() if args.live_tools else fixture_tools()
    print(f"Judge: {judge} | tools: {'live' if args.live_tools else 'fixture'}")

    with tools:  # patch before build_graph: the graph binds the tools when it is built
        graph = build_eval_graph()
        try:
            for golden in dataset.evals_iterator(
                async_config=AsyncConfig(run_async=False),
                display_config=DisplayConfig(inspect_after_run=False),
            ):
                metrics, result = run_golden(golden, graph, loop, judge)
                rows.append((golden, metrics))
                if result.state.get("allowed") and not result.error:
                    metrics["Plan Quality (sees trip details)"] = judge_plan(golden, result, judge)
        finally:
            if rows:
                report = write_report(rows, "agent_eval")
                summary = write_summary(rows, judge, args.live_tools)
                print(f"Summary for the CI gate: {summary}\nReport: {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
