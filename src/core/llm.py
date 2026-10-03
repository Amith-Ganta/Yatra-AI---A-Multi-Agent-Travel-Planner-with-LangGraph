"""LLM factory: instantiate and cache chat models, with an ordered fallback chain."""

import logging
from typing import Dict, List, Optional

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from .config import LLMConfig, ModelEnum, settings
from .errors import ConfigError, LLMError

logger = logging.getLogger("yatra.llm")

DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"

# Provider model name sent on the wire, for each allowed id.
_WIRE_NAME: Dict[ModelEnum, str] = {
    ModelEnum.DEEPSEEK_FLASH: "deepseek-flash",
    ModelEnum.DEEPSEEK_CHAT: "deepseek-chat",
    ModelEnum.OPENAI_GPT41_MINI: "gpt-4.1-mini",
    ModelEnum.OPENAI_GPT4O_MINI: "gpt-4o-mini",
}

ChatRunnable = Runnable[LanguageModelInput, BaseMessage]


def _is_deepseek(model_id: ModelEnum) -> bool:
    return model_id.value.startswith("deepseek:")


class LLMFactory:
    """Factory for LLM instances with caching and failover."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self._cache: Dict[ModelEnum, ChatOpenAI] = {}
        self._chain_cache: Dict[ModelEnum, ChatRunnable] = {}

    def _api_key(self, model_id: ModelEnum) -> Optional[str]:
        if _is_deepseek(model_id):
            return self.config.deepseek_api_key
        return self.config.openai_api_key

    def _build(self, model_id: ModelEnum) -> ChatOpenAI:
        """Build (or reuse) the client for exactly one model. No fallbacks."""
        if model_id in self._cache:
            return self._cache[model_id]

        try:
            wire_name = _WIRE_NAME.get(model_id)
            if wire_name is None:
                raise LLMError(f"Unknown model: {model_id}")

            if _is_deepseek(model_id):
                if not self.config.deepseek_api_key:
                    raise ConfigError("DEEPSEEK_API_KEY required for DeepSeek model")
                llm = ChatOpenAI(
                    model=wire_name,
                    base_url=DEEPSEEK_BASE_URL,
                    api_key=SecretStr(self.config.deepseek_api_key),
                    temperature=self.config.temperature,
                    max_completion_tokens=self.config.max_tokens,
                    timeout=self.config.request_timeout,
                    max_retries=self.config.max_retries,
                )
            else:
                llm = ChatOpenAI(
                    model=wire_name,
                    api_key=(
                        SecretStr(self.config.openai_api_key)
                        if self.config.openai_api_key
                        else None
                    ),
                    temperature=self.config.temperature,
                    max_completion_tokens=self.config.max_tokens,
                    timeout=self.config.request_timeout,
                    max_retries=self.config.max_retries,
                )
        except Exception as e:
            if isinstance(e, (ConfigError, LLMError)):
                raise
            raise LLMError(f"Failed to instantiate LLM {model_id}: {str(e)}")

        self._cache[model_id] = llm
        return llm

    def fallback_chain(self, primary: ModelEnum) -> List[ModelEnum]:
        """Fallback models to try after `primary`, in order.

        A model is dropped when it repeats the primary or an earlier entry, or when its API key
        is not set. A missing fallback key is a warning, never an error: it must not break a
        primary model that works.
        """
        chain: List[ModelEnum] = []
        for candidate in self.config.fallback_models:
            if candidate == primary or candidate in chain:
                continue
            if not self._api_key(candidate):
                logger.warning("Skipping fallback model %s: no API key configured", candidate.value)
                continue
            chain.append(candidate)
        return chain

    def get_llm(self, model_id: Optional[ModelEnum] = None, fallbacks: bool = True) -> ChatRunnable:
        """Get the chat model for `model_id` (default: the runtime model).

        With `fallbacks` (the default) the result is a runnable that retries the same call on
        each fallback model when the primary raises. Use `fallbacks=False` for the bare client.
        """
        model_id = model_id or self.config.runtime_model
        primary = self._build(model_id)
        if not fallbacks:
            return primary

        if model_id in self._chain_cache:
            return self._chain_cache[model_id]

        backups: List[ChatOpenAI] = []
        for candidate in self.fallback_chain(model_id):
            try:
                backups.append(self._build(candidate))
            except (ConfigError, LLMError) as exc:
                logger.warning("Skipping fallback model %s: %s", candidate.value, exc)
        runnable: ChatRunnable = primary.with_fallbacks(backups) if backups else primary
        self._chain_cache[model_id] = runnable
        return runnable

    def get_eval_judge(self) -> ChatRunnable:
        """Get the eval judge: always gpt-4o-mini, never a fallback.

        A judge that silently switched model would change what a score means.
        """
        return self.get_llm(ModelEnum.OPENAI_GPT4O_MINI, fallbacks=False)


llm_factory = LLMFactory(settings.llm)
