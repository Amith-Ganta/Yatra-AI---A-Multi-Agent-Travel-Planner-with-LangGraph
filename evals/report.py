"""Write an eval run as a CSV (to sort and filter) and a Markdown file (to read).

Every row is `(golden, {metric name: metric})`. A metric is anything with `score`, `threshold`,
`reason` and `error`: a DeepEval metric, the plan judge, or a deterministic `CheckMetric`.
A task does not have to carry every metric (a refused request has no plan to grade).
"""

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

REPORT_DIR = Path(__file__).resolve().parent / "reports"

# Extra facts some DeepEval metrics keep about what the judge understood. Shown when present.
EXTRAS = [
    ("task", "Task (as the judge understood it)"),
    ("outcome", "Outcome (as the judge summarised it)"),
    ("extracted_plan", "Plan (as the judge extracted it)"),
]


def _slug(name: str) -> str:
    return name.lower().replace(" ", "_")


def _flat(value: Any) -> str:
    if isinstance(value, list):
        items = [str(v) for v in value]  # pyright: ignore[reportUnknownVariableType]
        return " ".join(f"({i}) {step}" for i, step in enumerate(items, 1))
    return str(value).replace("\n", " ")


def _result(metric: Any) -> dict[str, Any]:
    score = getattr(metric, "score", None)
    threshold = getattr(metric, "threshold", None)
    error = getattr(metric, "error", None)
    if score is None:
        status = "ERROR" if error else "NOT SCORED"
    elif threshold is not None and score >= threshold:
        status = "PASS"
    else:
        status = "FAIL"
    reason = error or getattr(metric, "reason", None)
    if not reason and score is None:
        reason = "The run stopped before this task was graded."
    extras = [
        (label, _flat(getattr(metric, key))) for key, label in EXTRAS if getattr(metric, key, None)
    ]
    return {
        "score": "" if score is None else round(score, 2),
        "status": status,
        "reason": _flat(reason or ""),
        "extras": extras,
        "threshold": threshold,
    }


def _tasks(rows: list[tuple[Any, dict[str, Any]]]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for index, (golden, metrics) in enumerate(rows, 1):
        metadata = getattr(golden, "additional_metadata", None) or {}
        tasks.append(
            {
                "#": index,
                "difficulty": metadata.get("difficulty", ""),
                "task": golden.input,
                "results": {name: _result(metric) for name, metric in metrics.items()},
            }
        )
    return tasks


def _metric_names(tasks: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for task in tasks:
        for name in task["results"]:
            if name not in names:
                names.append(name)
    return names


def _all_pass(task: dict[str, Any]) -> bool:
    return all(r["status"] == "PASS" for r in task["results"].values())


def _cell(task: dict[str, Any], name: str) -> str:
    result = task["results"].get(name)
    return "n/a" if result is None else f"{result['score']} {result['status']}"


def summarize(rows: list[tuple[Any, dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    """Per metric: average score (of scored tasks), passed, errors, tasks with it, threshold."""
    tasks = _tasks(rows)
    summary: dict[str, dict[str, Any]] = {}
    for name in _metric_names(tasks):
        results = [t["results"][name] for t in tasks if name in t["results"]]
        scores = [r["score"] for r in results if r["score"] != ""]
        summary[name] = {
            "average": sum(scores) / len(scores) if scores else None,
            "passed": sum(1 for r in results if r["status"] == "PASS"),
            "errors": sum(1 for r in results if r["status"] in ("ERROR", "NOT SCORED")),
            "total": len(results),
            "threshold": results[0]["threshold"] if results else None,
        }
    return summary


def write_report(rows: list[tuple[Any, dict[str, Any]]], report_name: str) -> Path:
    """Write `<report_name>_<timestamp>.csv` and `.md` to `evals/reports/`; return the .md path."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    tasks = _tasks(rows)
    names = _metric_names(tasks)
    summary = summarize(rows)

    csv_path = REPORT_DIR / f"{report_name}_{stamp}.csv"
    fields = ["#", "difficulty", "task"]
    for name in names:
        fields += [f"{_slug(name)}_score", f"{_slug(name)}_status", f"{_slug(name)}_reason"]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for task in tasks:
            line: dict[str, Any] = {k: task[k] for k in ("#", "difficulty", "task")}
            for name, result in task["results"].items():
                line[f"{_slug(name)}_score"] = result["score"]
                line[f"{_slug(name)}_status"] = result["status"]
                line[f"{_slug(name)}_reason"] = result["reason"]
            writer.writerow(line)

    lines = [f"# {report_name.replace('_', ' ').title()}", ""]
    lines += ["| Metric | Average score | Passed | Threshold |", "|---|---|---|---|"]
    for name in names:
        item = summary[name]
        average = "n/a" if item["average"] is None else f"{item['average']:.2f}"
        lines.append(
            f"| {name} | {average} | {item['passed']}/{item['total']} | {item['threshold']} |"
        )
    lines += ["", "| # | Difficulty | Task | " + " | ".join(names) + " |"]
    lines.append("|---|---|---|" + "---|" * len(names))
    for task in tasks:
        cells = " | ".join(_cell(task, name) for name in names)
        short = str(task["task"]).replace("|", "/")
        lines.append(f"| {task['#']} | {task['difficulty']} | {short} | {cells} |")

    lines += ["", "## Details (tasks with a failure first)", ""]
    for task in sorted(tasks, key=lambda t: (_all_pass(t), t["#"])):
        lines += [f"### {task['#']}. {task['task']}", f"*Difficulty: {task['difficulty']}*", ""]
        for name, result in task["results"].items():
            lines.append(f"**{name}: {result['status']} ({result['score']})**")
            lines += [f"- {label}: {value}" for label, value in result["extras"]]
            lines += [f"- Reason: {result['reason']}", ""]
    md_path = REPORT_DIR / f"{report_name}_{stamp}.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"Report written:\n  {md_path}\n  {csv_path}")
    return md_path
