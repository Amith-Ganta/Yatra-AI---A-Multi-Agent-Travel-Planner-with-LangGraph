"""Budget evaluation judge."""

from typing import Any

from pydantic import BaseModel

from src.core.llm import llm_factory
from src.core.telemetry import logger

from ._common import parse_judge_json


class BudgetResult(BaseModel):
    """Budget evaluation result."""

    score: float
    within_budget: bool
    estimated_cost: float
    breakdown: dict[str, Any]
    variance: float  # percentage over/under budget


async def judge_budget(
    response: str, stated_budget: float, threshold: float = 0.95
) -> BudgetResult:
    """Evaluate if itinerary stays within stated budget.

    Analyzes:
    - Flight costs
    - Accommodation costs
    - Food/dining costs
    - Activity costs
    - Total variance from budget
    """

    prompt = f"""Analyze cost adherence for this trip plan (stated budget: ${stated_budget}).

Trip plan:
{response}

Estimate costs for:
1. Flights
2. Hotels/accommodation
3. Food/dining
4. Activities and attractions
5. Transportation/transit

Calculate estimated total cost and variance from stated budget ${stated_budget}.

Return JSON with:
- score (0-1, where 1 means exactly on budget)
- within_budget (boolean, true if estimated cost <= stated budget)
- estimated_cost (total estimated cost)
- breakdown (dict with categories: flights, hotels, food, activities, transit)
- variance (percentage difference from budget, negative means under budget)

Example:
{{
    "score": 0.9,
    "within_budget": true,
    "estimated_cost": 1800,
    "breakdown": {{"flights": 400, "hotels": 1000, "food": 300, "activities": 50, "transit": 50}},
    "variance": -10.0
}}

Return ONLY valid JSON, no other text."""

    try:
        judge = llm_factory.get_eval_judge()
        parsed = parse_judge_json(await judge.ainvoke(prompt))

        return BudgetResult(
            score=float(parsed.get("score", 0.5)),
            within_budget=bool(parsed.get("within_budget", False)),
            estimated_cost=float(parsed.get("estimated_cost", 0)),
            breakdown=parsed.get("breakdown", {}),
            variance=float(parsed.get("variance", 0)),
        )

    except Exception as e:
        logger.error("Budget judge error", extra={"error": str(e)})
        return BudgetResult(
            score=0.0,
            within_budget=False,
            estimated_cost=0,
            breakdown={},
            variance=0,
        )
