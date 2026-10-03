"""Evaluation module: LLM-based judges for response quality."""

from .gate import EvalVerdict, run_eval_gate

__all__ = ["run_eval_gate", "EvalVerdict"]
