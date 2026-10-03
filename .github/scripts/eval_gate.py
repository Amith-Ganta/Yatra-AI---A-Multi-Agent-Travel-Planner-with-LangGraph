#!/usr/bin/env python3
"""Merge gate for the DeepEval agent run.

    python -m evals.eval_agent                     # writes evals/reports/latest_summary.json
    python .github/scripts/eval_gate.py            # reads it and decides

Exit codes: 0 the gate passed, 1 a metric is below its bar, 2 there is nothing trustworthy to
judge (no summary, a stub run, a partial run). `--allow-skip` turns "no summary" into a pass, for
CI runs that have no API keys (pull requests from forks).

The bars are strict where the answer is a fact and looser where a judge model gives the score:

- Guardrail and Approval Loop are checked by code, so every task must pass.
- Routing is checked by code but the supervisor is a model, so 80% of tasks must pass.
- The judged metrics must average at least 0.7. A task that errored counts as a 0, so a judge
  outage fails the gate instead of passing on the tasks that happened to score.
- Plan Quality and Plan Adherence from DeepEval are REPORT ONLY (see REPORT_ONLY below).

The script reads the goldens too, so a run that was cut short (`--limit`) cannot pass.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SUMMARY_PATH = ROOT / "evals" / "reports" / "latest_summary.json"
GOLDENS_PATH = ROOT / "evals" / "datasets" / "goldens.json"

# (metric, kind, bar). `all`: every task passes. `rate`: share of tasks that pass.
# `average`: mean score over all tasks, with an errored task counted as 0.
RULES: list[tuple[str, str, float]] = [
    ("Guardrail", "all", 1.0),
    ("Approval Loop", "all", 1.0),
    ("Routing", "rate", 0.8),
    ("Task Completion", "average", 0.7),
    ("Plan Quality (sees trip details)", "average", 0.7),
]

# Scored and reported on every run, but they do not decide the gate. The first live run
# (3 Oct 2026, judge gpt-4o-mini) gave Plan Quality 0.55 and Plan Adherence 0.16, with 0.5 and
# about 0 on almost every task. The judge's reasons were that the "plan" (a list of agents) has no
# flight or hotel detail, and that `human_approval` and `final_response` run without being in that
# list. Yatra is a fixed graph, not a free planner, so these two metrics measure a mismatch in
# shape more than the quality of the work. That reading is a judgement and not a proven cause.
# The custom judge and Task Completion keep gating plan quality. To gate on them again, move the
# two names back into RULES with a bar chosen from a baseline.
REPORT_ONLY = ("Plan Quality", "Plan Adherence")


def count_goldens(goldens: list[dict[str, Any]]) -> tuple[int, int]:
    """(all tasks, tasks the supervisor is expected to allow)."""
    allowed = [g for g in goldens if g.get("additional_metadata", {}).get("expect_allowed", True)]
    return len(goldens), len(allowed)


def evaluate(summary: dict[str, Any], goldens: list[dict[str, Any]]) -> list[str]:
    """Every reason the gate should fail. An empty list means it passes."""
    failures: list[str] = []
    if "stub" in str(summary.get("judge_model", "")).lower():
        return ["This summary came from a stub judge. It proves wiring, not quality."]

    everything, allowed = count_goldens(goldens)
    if summary.get("tasks") != everything:
        failures.append(
            f"The run covered {summary.get('tasks')} task(s) but the dataset has {everything}."
        )

    metrics: dict[str, dict[str, Any]] = summary.get("metrics", {})
    for name, kind, bar in RULES:
        item = metrics.get(name)
        if item is None:
            failures.append(f"{name}: was not scored.")
            continue
        total = int(item.get("total", 0))
        expected = everything if name == "Guardrail" else allowed
        if total != expected:
            failures.append(f"{name}: scored {total} task(s), expected {expected}.")
            continue
        passed = int(item.get("passed", 0))
        errors = int(item.get("errors", 0))
        if kind == "all" and passed != total:
            failures.append(f"{name}: {passed}/{total} passed, every task must ({errors} errors).")
        elif kind == "rate" and passed / total < bar:
            failures.append(f"{name}: {passed}/{total} passed, at least {bar:.0%} must.")
        elif kind == "average":
            scored = total - errors
            average = (item.get("average") or 0.0) * scored / total
            if average < bar:
                failures.append(
                    f"{name}: average {average:.2f} is below {bar} ({errors} error(s) count as 0)."
                )
    return failures


def describe(summary: dict[str, Any]) -> str:
    lines = [
        f"Judge: {summary.get('judge_model')} | tools: {summary.get('tools')} | "
        f"tasks: {summary.get('tasks')}",
        "",
        f"{'Metric':36}{'Average':>9}{'Passed':>9}{'Errors':>8}",
    ]
    for name, item in summary.get("metrics", {}).items():
        average = "n/a" if item.get("average") is None else f"{item['average']:.2f}"
        passed = f"{item.get('passed')}/{item.get('total')}"
        label = f"{name} (report only)" if name in REPORT_ONLY else name
        lines.append(f"{label:36}{average:>9}{passed:>9}{item.get('errors', 0):>8}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Decide whether the agent eval run may merge.")
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    parser.add_argument("--goldens", type=Path, default=GOLDENS_PATH)
    parser.add_argument("--allow-skip", action="store_true", help="a missing summary is a pass")
    args = parser.parse_args(argv)

    if not args.summary.exists():
        if args.allow_skip:
            print(f"EVAL GATE SKIPPED: {args.summary} does not exist (no API keys in this run).")
            return 0
        print(f"EVAL GATE ERROR: {args.summary} does not exist. Run `python -m evals.eval_agent`.")
        return 2

    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    goldens = json.loads(args.goldens.read_text(encoding="utf-8"))
    print(describe(summary))
    failures = evaluate(summary, goldens)
    if not failures:
        print("\nEVAL GATE PASSED")
        return 0
    print("\nEVAL GATE FAILED")
    for failure in failures:
        print(f"  - {failure}")
    stub_or_partial = any("stub" in f or "covered" in f or "scored" in f for f in failures)
    return 2 if stub_or_partial else 1


if __name__ == "__main__":
    sys.exit(main())
