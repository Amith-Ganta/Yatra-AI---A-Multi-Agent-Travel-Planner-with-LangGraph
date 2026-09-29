#!/usr/bin/env python3
"""CI evaluation gate script."""

import sys
import asyncio
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.evals.gate import run_eval_gate
from src.core.telemetry import logger


async def run_ci_gate():
    """Run evaluation gate in CI pipeline."""

    # Read artifact (would come from workflow)
    # For now, use dummy data
    response = "Travel plan itinerary"
    context = {"destination": "Paris", "budget": 2000}

    verdict = await run_eval_gate(response, context)

    print("\n" + "=" * 60)
    print("EVALUATION GATE RESULTS")
    print("=" * 60)

    # Print scores
    if verdict.scores:
        print("\nScores:")
        for key, score in verdict.scores.items():
            print(f"  {key:15} {score:.2f}")

    # Print verdict
    if verdict.passed:
        print("\n✓ EVAL GATE PASSED")
        return 0
    else:
        print("\n✗ EVAL GATE FAILED")
        if verdict.failures:
            print("\nFailures:")
            for failure in verdict.failures:
                print(f"  - {failure}")

        if verdict.warnings:
            print("\nWarnings:")
            for warning in verdict.warnings:
                print(f"  - {warning}")

        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_ci_gate())
    sys.exit(exit_code)
