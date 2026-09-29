"""Tests for LLM factory."""

import pytest
from unittest.mock import MagicMock, patch

from src.core.llm import LLMFactory
from src.core.config import LLMConfig, ModelEnum
from src.core.errors import ConfigError, LLMError


@pytest.fixture
def llm_config():
    """LLM config for testing."""
    return LLMConfig(
        runtime_model=ModelEnum.OPENAI_GPT4O_MINI,
        eval_model=ModelEnum.OPENAI_GPT4O_MINI,
        groq_api_key="gsk_test",
        openai_api_key="sk-proj-test",
    )


@pytest.fixture
def factory(llm_config):
    """LLM factory for testing."""
    return LLMFactory(llm_config)


def test_get_llm_openai(factory):
    """Get OpenAI LLM instance."""
    with patch("src.core.llm.ChatOpenAI"):
        llm = factory.get_llm(ModelEnum.OPENAI_GPT4O_MINI)
        assert llm is not None


def test_get_llm_caching(factory):
    """LLM instances are cached by model_id."""
    with patch("src.core.llm.ChatOpenAI"):
        llm1 = factory.get_llm(ModelEnum.OPENAI_GPT4O_MINI)
        llm2 = factory.get_llm(ModelEnum.OPENAI_GPT4O_MINI)
        assert llm1 is llm2  # Same cached instance


def test_get_llm_missing_groq_key(llm_config):
    """Missing GROQ_API_KEY raises ConfigError."""
    llm_config.groq_api_key = None
    factory = LLMFactory(llm_config)

    with pytest.raises(ConfigError, match="GROQ_API_KEY"):
        factory.get_llm(ModelEnum.GROQ_MIXTRAL)


def test_get_eval_judge(factory):
    """Eval judge is always gpt-4o-mini."""
    with patch("src.core.llm.ChatOpenAI"):
        judge = factory.get_eval_judge()
        assert judge is not None


def test_get_eval_judge_model(factory):
    """Eval judge uses correct model."""
    with patch("src.core.llm.ChatOpenAI") as mock_openai:
        factory.get_eval_judge()
        mock_openai.assert_called_once()
        call_kwargs = mock_openai.call_args[1]
        assert call_kwargs["model_name"] == "gpt-4o-mini"
