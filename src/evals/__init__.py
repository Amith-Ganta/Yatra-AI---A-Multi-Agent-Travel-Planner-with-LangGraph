"""Evaluation module: LLM-based judges for response quality."""

from .gate import run_eval_gate, EvalVerdict

__all__ = ["run_eval_gate", "EvalVerdict"]
