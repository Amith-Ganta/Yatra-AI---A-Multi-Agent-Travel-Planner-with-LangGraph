"""Evaluation gate that combines all judges."""

import json
from dataclasses import dataclass, field
from typing import Optional

from src.core.config import settings
from src.core.telemetry import logger
from src.evals.judges import judge_safety, judge_factuality, judge_budget


@dataclass
class EvalVerdict:
    """Evaluation verdict combining all judge results."""

    passed: bool
    scores: dict = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


async def run_eval_gate(response: str, context: Optional[dict] = None) -> EvalVerdict:
    """Run all evaluation judges and return pass/fail verdict.

    Context dict should include:
    - destination: travel destination
    - budget: trip budget
    """

    context = context or {}
    scores = {}
    failures = []
    warnings = []

    logger.info("Running evaluation gate", extra={"response_length": len(response)})

    try:
        # Safety judgment
        logger.info("Running safety judge")
        safety_result = await judge_safety(response)
        scores["safety"] = safety_result.score

        if safety_result.score < settings.eval.safety_threshold:
            failures.append(
                f"Safety score {safety_result.score:.2f} below "
                f"threshold {settings.eval.safety_threshold}"
            )
            if safety_result.harmful_content:
                failures.append(f"Harmful content detected: {safety_result.harmful_content}")
        else:
            logger.info("Safety check passed", extra={"score": safety_result.score})

        # Factuality judgment
        logger.info("Running factuality judge")
        factuality_result = await judge_factuality(response, destination=context.get("destination"))
        scores["factuality"] = factuality_result.score

        if factuality_result.score < settings.eval.factuality_threshold:
            failures.append(
                f"Factuality score {factuality_result.score:.2f} below "
                f"threshold {settings.eval.factuality_threshold}"
            )
            if factuality_result.errors:
                for error in factuality_result.errors:
                    warnings.append(f"Factuality issue: {error.get('claim')} - {error.get('issue')}")
        else:
            logger.info("Factuality check passed", extra={"score": factuality_result.score})

        # Budget judgment (if budget provided)
        if "budget" in context:
            logger.info("Running budget judge")
            budget_result = await judge_budget(response, context["budget"])
            scores["budget"] = budget_result.score

            if budget_result.score < settings.eval.budget_threshold:
                failures.append(
                    f"Budget score {budget_result.score:.2f} below "
                    f"threshold {settings.eval.budget_threshold}"
                )
                warnings.append(
                    f"Estimated cost: ${budget_result.estimated_cost}, "
                    f"variance: {budget_result.variance:.1f}%"
                )
            else:
                logger.info("Budget check passed", extra={"score": budget_result.score})

    except Exception as e:
        logger.error("Eval gate error", extra={"error": str(e)})
        failures.append(f"Evaluation error: {str(e)}")

    passed = len(failures) == 0

    logger.info(
        "Evaluation gate complete",
        extra={"passed": passed, "scores": scores, "failure_count": len(failures)},
    )

    return EvalVerdict(
        passed=passed,
        scores=scores,
        failures=failures,
        warnings=warnings,
    )
