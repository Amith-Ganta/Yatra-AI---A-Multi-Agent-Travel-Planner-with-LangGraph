"""Cut a Yatra trace down to what a DeepEval judge needs to read.

A raw LangGraph trace repeats the whole graph state in every span, so one trip request can run
to tens of thousands of tokens. The judges only need the task, what each node produced, and
the final outcome. `with_slim_trace` wraps a trace-level metric class so the trace is slimmed
just before the metric reads it.

Yatra's approval loop makes one trace span several graph runs (run, interrupt, resume), so the
tree arrives as `yatra_run` -> several `LangGraph` spans -> nodes. The `LangGraph` wrappers are
flattened away so the judge sees one ordered list of node calls.
"""

import json
import re
from pathlib import Path
from typing import Any, Optional

# Spans that only decide where to go next. They carry no work, so the judge never sees them.
ROUTER_SPANS = {"route_from_supervisor", "route_from_workers", "route_from_approval"}

# Wrapper span LangGraph opens around every run of the graph (one per resume).
WRAPPER_SPANS = {"LangGraph"}

# Nodes whose input is the whole graph state. Only their output (the state update) is kept.
OUTPUT_ONLY_NODES = {
    "supervisor",
    "flight",
    "hotel",
    "weather",
    "budget",
    "itinerary",
    "human_approval",
    "revise",
    "final_response",
}

# A run that stops at the approval question never finishes that node, so it has no output.
PAUSED_OUTPUT = "Paused: waiting for the traveller to approve or reject the plan."


# Payload that is rebuilt (input, output, children) or that a judge must never see: the metric
# objects attached to a trace hold the judge model and its locks, and cannot be copied or shown.
_DROPPED_KEYS = {"input", "output", "children", "metrics", "metric_collection"}


class _SlimDict(dict[str, Any]):
    """Marks a trace dict that has already been slimmed, so it is never slimmed twice."""


def _without_payload(node: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in node.items() if k not in _DROPPED_KEYS}


def _slim_children(children: list[dict[str, Any]]) -> list[dict[str, Any]]:
    slim: list[dict[str, Any]] = []
    for child in children:
        name = child.get("name")
        if name in WRAPPER_SPANS:
            slim.extend(_slim_children(child.get("children") or []))
        elif name not in ROUTER_SPANS:
            slim.append(_slim_node(child))
    return slim


def _slim_node(node: dict[str, Any]) -> dict[str, Any]:
    slim = _without_payload(node)
    kind, name = node.get("type"), node.get("name")
    if kind == "tool":
        slim["input"], slim["output"] = node.get("input"), node.get("output")
    elif kind == "llm" or name in OUTPUT_ONLY_NODES:
        slim["output"] = node.get("output")
    if name == "human_approval" and slim.get("output") is None:
        slim["output"] = PAUSED_OUTPUT
    slim["children"] = _slim_children(node.get("children") or [])
    return slim


def slim_trace(root: dict[str, Any], *, task: str, outcome: str) -> dict[str, Any]:
    """The slimmed copy of one trace tree.

    The root span's own input is the arguments of the Python function that drove the graph, which
    means nothing to a judge, so the task and the outcome are written over it.
    """
    slim = _without_payload(root)
    slim["input"], slim["output"] = task, outcome
    slim["children"] = _slim_children(root.get("children") or [])
    return slim


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:60] or "trace"


def _save(folder: Path, test_case: Any, raw: dict[str, Any], slim: dict[str, Any]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    slug = _slug(str(test_case.input))
    judge_text = json.dumps(slim, indent=2, default=str)
    (folder / f"{slug}.judge.json").write_text(judge_text, encoding="utf-8")
    (folder / f"{slug}.raw.json").write_text(json.dumps(raw, indent=2, default=str), "utf-8")
    print(f"[trace saved] {folder / slug} (~{len(judge_text) // 4:,} tokens)")


def slim_test_case(test_case: Any, save_dir: Optional[Path] = None) -> None:
    """Replace the test case's trace with its slim form (once)."""
    trace = getattr(test_case, "_trace_dict", None)
    if not isinstance(trace, dict) or isinstance(trace, _SlimDict):
        return
    slim = _SlimDict(
        slim_trace(
            trace,
            task=str(test_case.input),
            outcome=str(test_case.actual_output or ""),
        )
    )
    if save_dir is not None:
        _save(save_dir, test_case, trace, slim)
    test_case._trace_dict = slim  # noqa: SLF001 - DeepEval reads the trace from this attribute


def with_slim_trace(metric_cls: type, save_dir: Optional[Path] = None) -> type:
    """A subclass of a trace-level DeepEval metric that slims the trace before judging."""

    class SlimTraceMetric(metric_cls):  # type: ignore[misc, valid-type]
        def measure(self, test_case: Any, *args: Any, **kwargs: Any) -> Any:
            slim_test_case(test_case, save_dir)
            return super().measure(test_case, *args, **kwargs)

        async def a_measure(self, test_case: Any, *args: Any, **kwargs: Any) -> Any:
            slim_test_case(test_case, save_dir)
            return await super().a_measure(test_case, *args, **kwargs)

    # DeepEval picks the judge prompt template by metric CLASS NAME, so the subclass has to
    # answer to the original name or it fails with MetricTemplateNotFoundError.
    SlimTraceMetric.__name__ = metric_cls.__name__
    SlimTraceMetric.__qualname__ = metric_cls.__qualname__
    return SlimTraceMetric
