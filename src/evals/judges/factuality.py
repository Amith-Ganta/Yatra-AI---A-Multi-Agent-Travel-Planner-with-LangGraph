"""Factuality evaluation judge."""

import json
from typing import Optional

from pydantic import BaseModel

from src.core.llm import LLMFactory
from src.core.telemetry import logger


class FactualityResult(BaseModel):
    """Factuality evaluation result."""

    score: float
    is_factual: bool
    errors: list[dict]
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

    judge = LLMFactory.get_eval_judge()

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
        result = await judge.ainvoke({"messages": [{"role": "user", "content": prompt}]})

        content = result.get("content", "{}")
        if isinstance(result, dict) and "content" in result:
            content = result["content"]

        parsed = json.loads(content)

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
