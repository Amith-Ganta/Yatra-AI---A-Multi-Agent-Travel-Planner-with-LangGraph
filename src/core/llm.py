"""LLM factory: instantiate and cache ChatModel instances."""

from typing import Dict, Optional

from langchain_core.language_models import BaseChatModel
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

from .config import LLMConfig, ModelEnum, settings
from .errors import ConfigError, LLMError


class LLMFactory:
    """Factory for LLM instances with caching."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self._cache: Dict[ModelEnum, BaseChatModel] = {}

    def get_llm(self, model_id: Optional[ModelEnum] = None) -> BaseChatModel:
        """Get LLM instance, cached by model_id."""
        model_id = model_id or self.config.runtime_model

        if model_id in self._cache:
            return self._cache[model_id]

        try:
            if model_id == ModelEnum.GROQ_MIXTRAL:
                if not self.config.groq_api_key:
                    raise ConfigError("GROQ_API_KEY required for Groq model")
                llm = ChatGroq(
                    model_name="mixtral-8x7b-32768",
                    api_key=self.config.groq_api_key,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                )
            elif model_id == ModelEnum.OPENAI_GPT4O_MINI:
                llm = ChatOpenAI(
                    model_name="gpt-4o-mini",
                    api_key=self.config.openai_api_key,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                )
            else:
                raise LLMError(f"Unknown model: {model_id}")

            self._cache[model_id] = llm
            return llm
        except Exception as e:
            if isinstance(e, (ConfigError, LLMError)):
                raise
            raise LLMError(f"Failed to instantiate LLM {model_id}: {str(e)}")

    def get_eval_judge(self) -> BaseChatModel:
        """Get eval judge (always gpt-4o-mini primary)."""
        return self.get_llm(ModelEnum.OPENAI_GPT4O_MINI)


llm_factory = LLMFactory(settings.llm)
