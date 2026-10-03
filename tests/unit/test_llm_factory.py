"""Tests for LLM factory: client construction, caching and the fallback chain."""

import logging
from typing import Any, List, Optional
from unittest.mock import patch

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables.fallbacks import RunnableWithFallbacks

from src.core.config import LLMConfig, ModelEnum
from src.core.errors import ConfigError
from src.core.llm import LLMFactory


def _config(**overrides: Any) -> LLMConfig:
    """Config with both keys set, the new default order and no environment influence."""
    values: dict[str, Any] = {
        "runtime_model": ModelEnum.DEEPSEEK_FLASH,
        "fallback_models": [ModelEnum.OPENAI_GPT41_MINI, ModelEnum.DEEPSEEK_FLASH],
        "eval_model": ModelEnum.OPENAI_GPT4O_MINI,
        "openai_api_key": "sk-proj-test",
        "deepseek_api_key": "sk-test-deepseek",
    }
    values.update(overrides)
    return LLMConfig(**values)


@pytest.fixture
def llm_config() -> LLMConfig:
    """LLM config for testing."""
    return _config()


@pytest.fixture
def factory(llm_config: LLMConfig) -> LLMFactory:
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


def test_bare_client_is_built_once_per_model(factory):
    """Primary and fallback clients are each constructed once, however often they are asked."""
    with patch("src.core.llm.ChatOpenAI") as mock_openai:
        factory.get_llm(ModelEnum.OPENAI_GPT41_MINI)
        factory.get_llm(ModelEnum.OPENAI_GPT41_MINI)
        factory.get_llm(ModelEnum.OPENAI_GPT41_MINI, fallbacks=False)
        # gpt-4.1-mini (primary) + deepseek-flash (its one fallback): two clients, no repeats
        assert mock_openai.call_count == 2


def test_get_eval_judge(factory):
    """Eval judge is always gpt-4o-mini."""
    with patch("src.core.llm.ChatOpenAI"):
        judge = factory.get_eval_judge()
        assert judge is not None


def test_get_eval_judge_model(factory):
    """Eval judge uses correct model and builds nothing else."""
    with patch("src.core.llm.ChatOpenAI") as mock_openai:
        factory.get_eval_judge()
        mock_openai.assert_called_once()
        call_kwargs = mock_openai.call_args[1]
        assert call_kwargs["model"] == "gpt-4o-mini"


def test_eval_judge_has_no_fallback(factory):
    """A judge that silently switched model would change what a score means."""
    judge = factory.get_eval_judge()
    assert not isinstance(judge, RunnableWithFallbacks)
    assert getattr(judge, "model_name", None) == "gpt-4o-mini"


def test_get_llm_deepseek(factory):
    """Get DeepSeek LLM instance."""
    with patch("src.core.llm.ChatOpenAI"):
        llm = factory.get_llm(ModelEnum.DEEPSEEK_CHAT)
        assert llm is not None


def test_get_llm_deepseek_config(factory):
    """DeepSeek flash uses the DeepSeek base_url and its own wire name."""
    with patch("src.core.llm.ChatOpenAI") as mock_openai:
        factory.get_llm(ModelEnum.DEEPSEEK_FLASH, fallbacks=False)
        mock_openai.assert_called_once()
        call_kwargs = mock_openai.call_args[1]
        assert call_kwargs["model"] == "deepseek-flash"
        assert call_kwargs["base_url"] == "https://api.deepseek.com/v1"


def test_legacy_deepseek_chat_wire_name(factory):
    """The legacy alias still reaches the API under its old name."""
    with patch("src.core.llm.ChatOpenAI") as mock_openai:
        factory.get_llm(ModelEnum.DEEPSEEK_CHAT, fallbacks=False)
        call_kwargs = mock_openai.call_args[1]
        assert call_kwargs["model"] == "deepseek-chat"
        assert call_kwargs["base_url"] == "https://api.deepseek.com/v1"


def test_client_gets_fast_failover_settings(factory):
    """Timeout and retries come from config, so a dead provider hands over quickly."""
    with patch("src.core.llm.ChatOpenAI") as mock_openai:
        factory.get_llm(ModelEnum.OPENAI_GPT41_MINI, fallbacks=False)
        call_kwargs = mock_openai.call_args[1]
        assert call_kwargs["model"] == "gpt-4.1-mini"
        assert call_kwargs["timeout"] == 45.0
        assert call_kwargs["max_retries"] == 1


def test_get_llm_missing_deepseek_key(llm_config):
    """Missing DEEPSEEK_API_KEY raises ConfigError when DeepSeek is the primary."""
    llm_config.deepseek_api_key = None
    factory = LLMFactory(llm_config)

    with pytest.raises(ConfigError, match="DEEPSEEK_API_KEY"):
        factory.get_llm(ModelEnum.DEEPSEEK_CHAT)


# --- fallback chain -----------------------------------------------------------------------


def test_default_runtime_model_is_deepseek_flash(factory):
    """No model id means the configured runtime model."""
    with patch("src.core.llm.ChatOpenAI") as mock_openai:
        factory.get_llm(fallbacks=False)
        assert mock_openai.call_args[1]["model"] == "deepseek-flash"


def test_fallback_chain_skips_the_primary(factory):
    """The primary never appears in its own fallback list."""
    assert factory.fallback_chain(ModelEnum.DEEPSEEK_FLASH) == [ModelEnum.OPENAI_GPT41_MINI]
    assert factory.fallback_chain(ModelEnum.OPENAI_GPT41_MINI) == [ModelEnum.DEEPSEEK_FLASH]


def test_fallback_chain_drops_duplicates():
    """A model listed twice is tried once."""
    factory = LLMFactory(
        _config(
            fallback_models=[
                ModelEnum.OPENAI_GPT41_MINI,
                ModelEnum.OPENAI_GPT41_MINI,
                ModelEnum.OPENAI_GPT4O_MINI,
            ]
        )
    )
    assert factory.fallback_chain(ModelEnum.DEEPSEEK_FLASH) == [
        ModelEnum.OPENAI_GPT41_MINI,
        ModelEnum.OPENAI_GPT4O_MINI,
    ]


def test_fallback_chain_skips_models_without_a_key(caplog):
    """A missing fallback key is a warning, never an error."""
    factory = LLMFactory(_config(openai_api_key=None))
    with caplog.at_level(logging.WARNING, logger="yatra.llm"):
        chain = factory.fallback_chain(ModelEnum.DEEPSEEK_FLASH)

    assert chain == []
    assert "openai:gpt-4.1-mini" in caplog.text
    assert "no API key" in caplog.text


def test_get_llm_without_usable_fallbacks_returns_the_bare_client():
    """No fallback key and no other model: nothing to wrap."""
    factory = LLMFactory(_config(openai_api_key=None))
    llm = factory.get_llm(ModelEnum.DEEPSEEK_FLASH)
    assert not isinstance(llm, RunnableWithFallbacks)


def test_get_llm_wraps_primary_with_fallbacks(factory):
    """Primary plus fallbacks come back as one runnable with the backups attached."""
    llm = factory.get_llm(ModelEnum.DEEPSEEK_FLASH)

    assert isinstance(llm, RunnableWithFallbacks)
    assert getattr(llm.runnable, "model_name", None) == "deepseek-flash"
    assert [getattr(m, "model_name", None) for m in llm.fallbacks] == ["gpt-4.1-mini"]


def test_fallbacks_can_be_switched_off(factory):
    """fallbacks=False returns the bare client, not the chain."""
    llm = factory.get_llm(ModelEnum.DEEPSEEK_FLASH, fallbacks=False)
    assert not isinstance(llm, RunnableWithFallbacks)


def test_chain_is_cached(factory):
    """The wrapped chain is built once per primary model."""
    assert factory.get_llm(ModelEnum.DEEPSEEK_FLASH) is factory.get_llm(ModelEnum.DEEPSEEK_FLASH)


def test_failing_fallback_build_does_not_break_the_primary(factory, caplog):
    """If one backup cannot be built the primary still works and the reason is logged."""
    real_build = factory._build

    def flaky_build(model_id: ModelEnum) -> Any:
        if model_id == ModelEnum.OPENAI_GPT41_MINI:
            raise ConfigError("boom")
        return real_build(model_id)

    with patch.object(factory, "_build", side_effect=flaky_build):
        with caplog.at_level(logging.WARNING, logger="yatra.llm"):
            llm = factory.get_llm(ModelEnum.DEEPSEEK_FLASH)

    assert not isinstance(llm, RunnableWithFallbacks)
    assert "Skipping fallback model openai:gpt-4.1-mini" in caplog.text


class _AlwaysDown(FakeListChatModel):
    """A provider that is down: every call raises."""

    def _generate(  # type: ignore[override]
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise RuntimeError("provider down")


@pytest.mark.asyncio
async def test_call_falls_over_to_the_next_model(factory):
    """End to end: the primary raises, the call is answered by the first fallback."""
    down = _AlwaysDown(responses=["never"])
    backup = FakeListChatModel(responses=["from-fallback"])
    models = {ModelEnum.DEEPSEEK_FLASH: down, ModelEnum.OPENAI_GPT41_MINI: backup}

    with patch.object(factory, "_build", side_effect=lambda m: models[m]):
        llm = factory.get_llm(ModelEnum.DEEPSEEK_FLASH)

    result = await llm.ainvoke("plan a trip")
    assert result.content == "from-fallback"


@pytest.mark.asyncio
async def test_call_raises_when_every_model_is_down(factory):
    """If the whole chain fails the caller still gets the error (and handles it)."""
    models = {
        ModelEnum.DEEPSEEK_FLASH: _AlwaysDown(responses=["x"]),
        ModelEnum.OPENAI_GPT41_MINI: _AlwaysDown(responses=["x"]),
    }
    with patch.object(factory, "_build", side_effect=lambda m: models[m]):
        llm = factory.get_llm(ModelEnum.DEEPSEEK_FLASH)

    with pytest.raises(RuntimeError, match="provider down"):
        await llm.ainvoke("plan a trip")
