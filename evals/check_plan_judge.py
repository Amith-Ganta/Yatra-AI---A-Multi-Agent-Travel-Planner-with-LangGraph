"""Sanity-check the custom plan judge before trusting its scores.

    python -m evals.check_plan_judge

It hands the judge plans whose quality is already known: five that are clearly broken (it must
score them below the threshold) and four that are clearly fine (it must score them at or above
it). No agent runs, so it is cheap. A judge that cannot tell these apart is not worth using on
real runs. Every case is repeated, because a judge model can wobble from call to call.
"""

import sys
from typing import Any

from evals.harness import judge_model_name, missing_keys
from evals.judges.plan_judge import (
    FIXED_TAIL,
    THRESHOLD,
    agents_not_in_plan,
    make_plan_judge,
    plan_steps,
    plan_test_case,
)

REPEATS = 3

ROME = {
    "destination": "Rome",
    "start_date": "2099-05-08",
    "end_date": "2099-05-12",
    "budget_usd": 2000,
    "party_size": 2,
    "trip_type": "leisure",
}
PARIS_DAY = {
    "destination": "Paris",
    "start_date": "2099-06-12",
    "end_date": "2099-06-12",
    "budget_usd": 1000,
    "party_size": 1,
    "trip_type": "leisure",
}
PRAGUE = {
    "destination": "Prague",
    "start_date": "2099-09-05",
    "end_date": "2099-09-07",
    "budget_usd": 1000,
    "party_size": 1,
    "trip_type": "leisure",
}
BARCELONA = {
    "destination": "Barcelona",
    "start_date": "2099-07-01",
    "end_date": "2099-07-06",
    "budget_usd": 3000,
    "party_size": 4,
    "trip_type": "family",
}

ROME_TASK = "Plan a 5-day trip to Rome from 2099-05-08 to 2099-05-12 for two, budget $2000."
FULL = ["flight", "hotel", "weather", "budget"]

# `expect` is what the judge must do. `selected` feeds the plan text unless `steps` is given.
CASES: list[dict[str, Any]] = [
    {
        "name": "bad: skips hotel and budget",
        "expect": "FAIL",
        "flaw": "a 5-day trip for two with a budget has no hotel search and no budget check",
        "task": ROME_TASK,
        "constraints": ROME,
        "selected": ["flight", "weather"],
    },
    {
        "name": "bad: only the budget check",
        "expect": "FAIL",
        "flaw": "no flight, hotel or weather research at all",
        "task": ROME_TASK,
        "constraints": ROME,
        "selected": ["budget"],
    },
    {
        "name": "bad: invents agents",
        "expect": "FAIL",
        "flaw": "visa and restaurant_booking are not agents this system has",
        "task": ROME_TASK,
        "constraints": ROME,
        "selected": FULL,
        "steps": [
            "flight: Search flights to the destination for the departure date and party size.",
            "visa: Check visa requirements and apply for the traveller.",
            "restaurant_booking: Book a table for every dinner of the trip.",
            "itinerary: Write a day-by-day itinerary from the research results.",
            *FIXED_TAIL,
        ],
    },
    {
        "name": "bad: itinerary before research",
        "expect": "FAIL",
        "flaw": "the itinerary is written before any research exists to build it from",
        "task": ROME_TASK,
        "constraints": ROME,
        "selected": FULL,
        "steps": [
            "itinerary: Write a day-by-day itinerary from the research results.",
            "budget: Split the budget and check that the flight cost fits.",
            "flight: Search flights to the destination for the departure date and party size.",
            "hotel: Search hotels at the destination that fit the budget.",
            "weather: Fetch the forecast for the destination across the trip dates.",
            *FIXED_TAIL,
        ],
    },
    {
        "name": "bad: no approval or final step",
        "expect": "FAIL",
        "flaw": "the plan ends at the itinerary, so the traveller never approves anything",
        "task": ROME_TASK,
        "constraints": ROME,
        "selected": FULL,
        "steps": plan_steps(FULL)[:-2],
    },
    {
        "name": "good: full trip",
        "expect": "PASS",
        "flaw": "none",
        "task": ROME_TASK,
        "constraints": ROME,
        "selected": FULL,
    },
    {
        "name": "good: solo day trip, no hotel or budget",
        "expect": "PASS",
        "flaw": "none: one day, one traveller, no budget, so flight and weather are enough",
        "task": "Plan a day trip to Paris on 2099-06-12 for just me.",
        "constraints": PARIS_DAY,
        "selected": ["flight", "weather"],
    },
    {
        "name": "good: solo trip, no budget mentioned",
        "expect": "PASS",
        "flaw": "none: three days, so a hotel, but no budget was given and the party is one",
        "task": "Plan 3 days in Prague from 2099-09-05 to 2099-09-07 for me.",
        "constraints": PRAGUE,
        "selected": ["flight", "hotel", "weather"],
    },
    {
        "name": "good: family trip",
        "expect": "PASS",
        "flaw": "none",
        "task": "Plan a 6-day trip to Barcelona for a family of 4, from 2099-07-01 to 2099-07-06.",
        "constraints": BARCELONA,
        "selected": FULL,
    },
]


def case_test_case(case: dict[str, Any]) -> Any:
    return plan_test_case(case["task"], case["selected"], case["constraints"], case.get("steps"))


def main() -> int:
    missing = missing_keys()
    if "OPENAI_API_KEY" in missing:
        print("Cannot run the plan judge check: OPENAI_API_KEY is not set. Nothing was scored.")
        return 2
    model = judge_model_name()
    print(f"Judge: {model} | threshold {THRESHOLD} | {REPEATS} runs per case\n")

    bad_scores: list[float] = []
    good_scores: list[float] = []
    wrong = 0
    for case in CASES:
        scores: list[float] = []
        for _ in range(REPEATS):
            judge = make_plan_judge(model)
            judge.measure(case_test_case(case))
            scores.append(float(judge.score or 0.0))
        average = sum(scores) / len(scores)
        failed = average < THRESHOLD
        right = failed == (case["expect"] == "FAIL")
        wrong += 0 if right else 1
        (bad_scores if case["expect"] == "FAIL" else good_scores).append(average)
        omitted = agents_not_in_plan(case["task"], case["constraints"], case["selected"])
        print(f"{'OK   ' if right else 'WRONG'} {case['name']}")
        print(f"      expected {case['expect']} | scores {[round(s, 2) for s in scores]}")
        print(f"      flaw: {case['flaw']} | code says never mentioned: {omitted or 'none'}")

    separated = max(bad_scores) < min(good_scores)
    print(f"\nWrong verdicts: {wrong}/{len(CASES)}")
    print(f"Highest bad score: {max(bad_scores):.2f} | lowest good score: {min(good_scores):.2f}")
    print(f"Every bad plan scored below every good plan: {separated}")
    return 0 if wrong == 0 and separated else 1


if __name__ == "__main__":
    sys.exit(main())
