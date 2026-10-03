"""Tests for LLM-based evaluation judges."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from src.evals.gate import run_eval_gate
from src.evals.judges import judge_budget, judge_factuality, judge_safety


class TestSafetyJudge:
    """Tests for safety evaluation judge."""

    @pytest.mark.asyncio
    async def test_safety_judge_returns_result(self):
        """Safety judge returns SafetyResult."""
        response = "Visit Paris and enjoy local cafes"

        with patch("src.evals.judges.safety.llm_factory") as mock_factory:
            mock_judge = AsyncMock()
            mock_judge.ainvoke = AsyncMock(
                return_value=AIMessage(
                    content=json.dumps(
                        {
                            "score": 0.98,
                            "is_safe": True,
                            "reasons": [],
                            "harmful_content": [],
                        }
                    )
                )
            )
            mock_factory.get_eval_judge.return_value = mock_judge

            result = await judge_safety(response)

            assert result.score == 0.98
            assert result.is_safe is True
            assert len(result.harmful_content) == 0

    @pytest.mark.asyncio
    async def test_safety_judge_detects_unsafe_content(self):
        """Safety judge flags unsafe recommendations."""
        response = "Visit dangerous areas at night without precautions"

        with patch("src.evals.judges.safety.llm_factory") as mock_factory:
            mock_judge = AsyncMock()
            mock_judge.ainvoke = AsyncMock(
                return_value=AIMessage(
                    content=json.dumps(
                        {
                            "score": 0.2,
                            "is_safe": False,
                            "reasons": ["Risky safety advice"],
                            "harmful_content": ["night visits"],
                        }
                    )
                )
            )
            mock_factory.get_eval_judge.return_value = mock_judge

            result = await judge_safety(response)

            assert result.score == 0.2
            assert result.is_safe is False


class TestJudgeRobustness:
    """The judges must call the model the way LangChain expects and fail closed."""

    @pytest.mark.asyncio
    async def test_judge_sends_a_plain_prompt_string(self):
        """Regression: judges used to pass a dict to ainvoke, which ChatOpenAI rejects."""
        with patch("src.evals.judges.safety.llm_factory") as mock_factory:
            mock_judge = AsyncMock()
            mock_judge.ainvoke = AsyncMock(
                return_value=AIMessage(
                    content=json.dumps(
                        {"score": 1.0, "is_safe": True, "reasons": [], "harmful_content": []}
                    )
                )
            )
            mock_factory.get_eval_judge.return_value = mock_judge

            await judge_safety("Visit Rome")

            (prompt,) = mock_judge.ainvoke.call_args.args
            assert isinstance(prompt, str)
            assert "Visit Rome" in prompt

    @pytest.mark.asyncio
    async def test_markdown_fenced_json_is_accepted(self):
        payload = '{"score": 0.9, "is_safe": true, "reasons": [], "harmful_content": []}'
        reply = "```json\n" + payload + "\n```"
        with patch("src.evals.judges.safety.llm_factory") as mock_factory:
            mock_judge = AsyncMock()
            mock_judge.ainvoke = AsyncMock(return_value=AIMessage(content=reply))
            mock_factory.get_eval_judge.return_value = mock_judge

            result = await judge_safety("Visit Rome")

            assert result.score == 0.9
            assert result.is_safe is True

    @pytest.mark.asyncio
    async def test_unparseable_reply_fails_closed(self):
        with patch("src.evals.judges.safety.llm_factory") as mock_factory:
            mock_judge = AsyncMock()
            mock_judge.ainvoke = AsyncMock(return_value=AIMessage(content="not json at all"))
            mock_factory.get_eval_judge.return_value = mock_judge

            result = await judge_safety("Visit Rome")

            assert result.score == 0.0
            assert result.is_safe is False

    @pytest.mark.asyncio
    async def test_missing_judge_credentials_fail_closed(self):
        """A misconfigured judge (no API key) must not crash the gate or let a plan through."""
        with patch("src.evals.judges.budget.llm_factory") as mock_factory:
            mock_factory.get_eval_judge.side_effect = RuntimeError("no key")

            result = await judge_budget("5 nights in Paris", stated_budget=2000)

            assert result.score == 0.0
            assert result.within_budget is False


class TestFactualityJudge:
    """Tests for factuality evaluation judge."""

    @pytest.mark.asyncio
    async def test_factuality_judge_returns_result(self):
        """Factuality judge returns FactualityResult."""
        response = "Paris has the Eiffel Tower and good museums"

        with patch("src.evals.judges.factuality.llm_factory") as mock_factory:
            mock_judge = AsyncMock()
            mock_judge.ainvoke = AsyncMock(
                return_value=AIMessage(
                    content=json.dumps(
                        {
                            "score": 0.92,
                            "is_factual": True,
                            "errors": [],
                            "confidence": "high",
                        }
                    )
                )
            )
            mock_factory.get_eval_judge.return_value = mock_judge

            result = await judge_factuality(response, destination="Paris")

            assert result.score == 0.92
            assert result.is_factual is True
            assert result.confidence == "high"

    @pytest.mark.asyncio
    async def test_factuality_judge_identifies_errors(self):
        """Factuality judge identifies false claims."""
        response = "Tokyo is the capital of South Korea"

        with patch("src.evals.judges.factuality.llm_factory") as mock_factory:
            mock_judge = AsyncMock()
            mock_judge.ainvoke = AsyncMock(
                return_value=AIMessage(
                    content=json.dumps(
                        {
                            "score": 0.0,
                            "is_factual": False,
                            "errors": [
                                {
                                    "claim": "Tokyo is capital of SK",
                                    "issue": "Tokyo is Japan's capital",
                                }
                            ],
                            "confidence": "high",
                        }
                    )
                )
            )
            mock_factory.get_eval_judge.return_value = mock_judge

            result = await judge_factuality(response)

            assert result.is_factual is False
            assert len(result.errors) > 0


class TestBudgetJudge:
    """Tests for budget evaluation judge."""

    @pytest.mark.asyncio
    async def test_budget_judge_within_budget(self):
        """Budget judge approves itinerary within budget."""
        response = "5 nights Paris: flights $400, hotels $1000, meals $300"

        with patch("src.evals.judges.budget.llm_factory") as mock_factory:
            mock_judge = AsyncMock()
            mock_judge.ainvoke = AsyncMock(
                return_value=AIMessage(
                    content=json.dumps(
                        {
                            "score": 0.92,
                            "within_budget": True,
                            "estimated_cost": 1700,
                            "breakdown": {
                                "flights": 400,
                                "hotels": 1000,
                                "food": 300,
                            },
                            "variance": -15.0,
                        }
                    )
                )
            )
            mock_factory.get_eval_judge.return_value = mock_judge

            result = await judge_budget(response, stated_budget=2000)

            assert result.within_budget is True
            assert result.estimated_cost == 1700
            assert result.variance == -15.0

    @pytest.mark.asyncio
    async def test_budget_judge_over_budget(self):
        """Budget judge flags over-budget itineraries."""
        response = "Luxury hotels $5000, flights $1500"

        with patch("src.evals.judges.budget.llm_factory") as mock_factory:
            mock_judge = AsyncMock()
            mock_judge.ainvoke = AsyncMock(
                return_value=AIMessage(
                    content=json.dumps(
                        {
                            "score": 0.3,
                            "within_budget": False,
                            "estimated_cost": 6500,
                            "breakdown": {"flights": 1500, "hotels": 5000},
                            "variance": 225.0,
                        }
                    )
                )
            )
            mock_factory.get_eval_judge.return_value = mock_judge

            result = await judge_budget(response, stated_budget=2000)

            assert result.within_budget is False
            assert result.estimated_cost == 6500


class TestEvalGate:
    """Tests for evaluation gate combining judges."""

    @pytest.mark.asyncio
    async def test_eval_gate_passes_all_judges(self):
        """Eval gate passes when all judges pass."""
        response = "Safe, factual trip plan within budget"

        with (
            patch("src.evals.gate.judge_safety") as mock_safety,
            patch("src.evals.gate.judge_factuality") as mock_factuality,
            patch("src.evals.gate.judge_budget") as mock_budget,
        ):

            # Mock the functions to return proper result objects
            async def mock_safety_judge(*args, **kwargs):
                from src.evals.judges.safety import SafetyResult

                return SafetyResult(score=0.98, is_safe=True, reasons=[], harmful_content=[])

            async def mock_factuality_judge(*args, **kwargs):
                from src.evals.judges.factuality import FactualityResult

                return FactualityResult(score=0.92, is_factual=True, errors=[], confidence="high")

            async def mock_budget_judge(*args, **kwargs):
                from src.evals.judges.budget import BudgetResult

                return BudgetResult(
                    score=0.97,
                    within_budget=True,
                    estimated_cost=1800,
                    breakdown={},
                    variance=-10.0,
                )

            mock_safety.side_effect = mock_safety_judge
            mock_factuality.side_effect = mock_factuality_judge
            mock_budget.side_effect = mock_budget_judge

            verdict = await run_eval_gate(response, {"budget": 2000})

            assert verdict.passed is True
            assert verdict.failures == []
            assert verdict.scores == {"safety": 0.98, "factuality": 0.92, "budget": 0.97}

    @pytest.mark.asyncio
    async def test_eval_gate_fails_on_safety_violation(self):
        """Eval gate fails when safety threshold not met."""
        response = "Unsafe recommendation"

        with (
            patch("src.evals.gate.judge_safety") as mock_safety,
            patch("src.evals.gate.judge_factuality") as mock_factuality,
        ):

            async def mock_safety_judge(*args, **kwargs):
                from src.evals.judges.safety import SafetyResult

                return SafetyResult(
                    score=0.3, is_safe=False, reasons=["Risky"], harmful_content=["content"]
                )

            async def mock_factuality_judge(*args, **kwargs):
                from src.evals.judges.factuality import FactualityResult

                return FactualityResult(score=0.9, is_factual=True, errors=[], confidence="high")

            mock_safety.side_effect = mock_safety_judge
            mock_factuality.side_effect = mock_factuality_judge

            verdict = await run_eval_gate(response)

            assert len(verdict.failures) > 0
            assert not verdict.passed
