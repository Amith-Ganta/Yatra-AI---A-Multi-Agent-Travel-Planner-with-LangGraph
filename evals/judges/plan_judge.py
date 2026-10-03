"""A custom plan judge for Yatra, built on DeepEval's GEval.

DeepEval's own `PlanQualityMetric` reads only the trace. It cannot see what the traveller asked
for in numbers (dates, budget, party size), so it cannot say whether the supervisor left out an
agent the trip needed. This judge is given that missing context, plus a list of the agents the
plan never mentions that is worked out by code, so the judge does not have to guess.

In Yatra the "plan" is the supervisor's choice of agents, in the order the graph runs them,
followed by the fixed itinerary, approval and final-answer steps.
"""

import re
from datetime import date
from typing import Any

from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, SingleTurnParams

from src.agents.routing import AGENT_ORDER

THRESHOLD = 0.7

AGENT_DESCRIPTIONS = {
    "flight": "Search flights to the destination for the departure date and party size.",
    "hotel": "Search hotels at the destination that fit the budget.",
    "weather": "Fetch the forecast for the destination across the trip dates.",
    "budget": "Split the budget across hotels, food, activities and extras, and check that the "
    "flight cost fits.",
    "itinerary": "Write a day-by-day itinerary from the research results.",
}

FIXED_TAIL = [
    "human_approval: Pause and ask the traveller to approve or reject the draft plan.",
    "final_response: Return the approved plan, or the latest draft if the revision limit is hit.",
]

TOOL_LIST = """\
- flight: needs the destination, departure date, party size and budget. Flight data is a mock.
- hotel: needs the destination and budget. Only useful when the trip is longer than one day.
- weather: needs the destination and the trip start and end dates.
- budget: needs a budget the traveller mentioned, or a party larger than one person.
- itinerary: always runs. It turns the research into one entry per trip day.
- human_approval: always runs. The traveller can reject, and the itinerary is then revised.
- final_response: always runs last."""

GRADING_STEPS = [
    # 1. What the judge has.
    "You are grading a PLAN for a travel-planning system. The input is the traveller's request. "
    "The actual output is the plan: the numbered steps the system chose to run, in order. The "
    "context holds the trip details the system understood, a list of agents the plan never "
    "mentions (worked out by code, exact), and the agents available.",
    # 2. Ambiguity.
    "If the request is ambiguous, accept any reasonable reading of it. Do not punish a plan "
    "for how it filled a gap the request left open, such as a missing date or budget.",
    # 3. Completeness.
    "Check completeness against the list of agents the plan never mentions. Trust that list. "
    "Deduct for each omitted agent the request clearly needed, and name each serious omission in "
    "your reason. An agent that is correctly absent, such as a hotel search for a one-day trip, "
    "is not an omission.",
    # 4. Real names only.
    "Every step must name a real agent from the available list. Deduct heavily for a step that "
    "invents an agent or a capability the system does not have.",
    # 5. Fit.
    "Check each agent is used for what it is for, using the argument needs in the tool list. "
    "A weather step in a plan for a trip with no dates, or a budget step for a request with no "
    "budget and one traveller, does not fit.",
    # 6. Dependencies.
    "Check the order. Research steps come before the budget check, and the budget check comes "
    "before the itinerary, because each one reads the results of the step before it.",
    # 7. Unneeded work.
    "Deduct for steps the request did not need. Running every agent is not better than running "
    "the right ones.",
    # 8. Tail.
    "Deduct if the plan lacks the approval step or the final-response step, or if they come "
    "before the research. These are fixed in this system, so a plan without them is broken.",
    # 9. What not to punish.
    "Do NOT deduct for missing error handling, missing retries, or small natural work the system "
    "does by itself. Judge the choice and the order of agents, not how well they run.",
]


def plan_steps(selected_agents: list[str]) -> list[str]:
    """The plan as numbered-step text: chosen agents in graph order, then the fixed tail."""
    chosen = set(selected_agents)
    steps = [
        f"{agent}: {AGENT_DESCRIPTIONS[agent]}"
        for agent in AGENT_ORDER
        if agent == "itinerary" or agent in chosen
    ]
    return steps + FIXED_TAIL


def _trip_days(constraints: dict[str, Any]) -> int:
    try:
        start = date.fromisoformat(str(constraints.get("start_date")))
        end = date.fromisoformat(str(constraints.get("end_date")))
    except ValueError:
        return 1
    return max((end - start).days + 1, 1)


_BUDGET_WORDS = re.compile(r"budget|\$|usd|eur|gbp|€|£|dollar|euro|pound|cheap|afford", re.I)


def agents_the_trip_needs(task: str, constraints: dict[str, Any]) -> list[str]:
    """Which selectable agents the request implies, by the supervisor's own rules, in code."""
    needed = ["flight"]
    if _trip_days(constraints) > 1:
        needed.append("hotel")
    needed.append("weather")
    party = constraints.get("party_size") or 1
    if _BUDGET_WORDS.search(task) or int(party) > 1:
        needed.append("budget")
    return needed


def agents_not_in_plan(task: str, constraints: dict[str, Any], selected: list[str]) -> list[str]:
    chosen = set(selected)
    return [a for a in agents_the_trip_needs(task, constraints) if a not in chosen]


def plan_test_case(
    task: str,
    selected_agents: list[str],
    constraints: dict[str, Any],
    steps: list[str] | None = None,
) -> LLMTestCase:
    """The judge's test case: request, numbered plan, and the context the judge needs.

    `steps` replaces the plan text. Only the sanity check uses it, to hand the judge plans the
    real supervisor could never produce (an invented agent, a wrong order).
    """
    steps = steps if steps is not None else plan_steps(selected_agents)
    missing = agents_not_in_plan(task, constraints, selected_agents)
    details = ", ".join(f"{k}={v}" for k, v in constraints.items())
    return LLMTestCase(
        input=task,
        actual_output="\n".join(f"{n}. {step}" for n, step in enumerate(steps, 1)),
        context=[
            f"TRIP DETAILS THE SYSTEM UNDERSTOOD: {details}",
            "AGENTS THE PLAN NEVER MENTIONS (worked out by code, exact; they are the ones the "
            f"request implies): {', '.join(missing) if missing else '(none)'}",
            f"AGENTS AVAILABLE:\n{TOOL_LIST}",
        ],
    )


def make_plan_judge(model: Any, threshold: float = THRESHOLD) -> GEval:
    """A fresh judge (a metric keeps its score, so each task needs its own)."""
    return GEval(
        name="Plan Quality (sees trip details)",
        evaluation_steps=GRADING_STEPS,
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.CONTEXT,
        ],
        model=model,
        threshold=threshold,
        async_mode=False,
    )
