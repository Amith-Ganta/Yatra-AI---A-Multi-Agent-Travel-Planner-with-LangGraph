"""Factuality evaluation judge."""

from typing import Any, Optional

from pydantic import BaseModel

from src.core.llm import llm_factory
from src.core.telemetry import logger

from ._common import parse_judge_json


class FactualityResult(BaseModel):
    """Factuality evaluation result."""

    score: float
    is_factual: bool
    errors: list[dict[str, Any]]
    confidence: str  # "high", "medium", "low"


async def judge_factuality(
    response: str, destination: Optional[str] = None, threshold: float = 0.90
) -> FactualityResult:
    """Evaluate factuality of travel recommendations.

    Checks:
    - Correct information about attractions
    - Accurate dates/seasons
    - Real transportation options
    - Accurate pricing estimates
    """

    destination_text = f"for {destination}" if destination else ""

    prompt = f"""Evaluate factuality of this travel recommendation {destination_text}.

Response text:
{response}

Check for accuracy of:
1. Attractions and landmarks
2. Season/weather information
3. Transportation options
4. Pricing estimates
5. Opening hours/accessibility

Return JSON with:
- score (0-1, where 1 is completely accurate)
- is_factual (boolean)
- errors (list of {{"claim": "...", "issue": "..."}})
- confidence ("high", "medium", or "low")

Example:
{{"score": 0.85, "is_factual": true, "errors": [], "confidence": "medium"}}

Return ONLY valid JSON, no other text."""

    try:
        judge = llm_factory.get_eval_judge()
        parsed = parse_judge_json(await judge.ainvoke(prompt))

        return FactualityResult(
            score=float(parsed.get("score", 0.5)),
            is_factual=bool(parsed.get("is_factual", False)),
            errors=parsed.get("errors", []),
            confidence=parsed.get("confidence", "low"),
        )

    except Exception as e:
        logger.error("Factuality judge error", extra={"error": str(e)})
        return FactualityResult(
            score=0.0,
            is_factual=False,
            errors=[{"claim": "unknown", "issue": "Evaluation error"}],
            confidence="low",
        )
