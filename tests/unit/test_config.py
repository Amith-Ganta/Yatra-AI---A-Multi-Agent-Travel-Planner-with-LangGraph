"""Tests for configuration module."""

import os
import pytest

from src.core.config import Settings, ModelEnum, LLMConfig
from src.core.errors import ConfigError, MissingAPIKeyError


def test_settings_load_from_env(monkeypatch):
    """Settings load from .env file."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-test_key")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test_key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/yatra")

    settings = Settings()
    assert settings.llm.runtime_model == ModelEnum.GROQ_DEEPSEEK
    assert settings.llm.openai_api_key == "sk-proj-test_key"
    assert settings.database.url.startswith("postgresql://")


def test_settings_model_validation_forbidden(monkeypatch):
    """Forbidden models raise ConfigError."""
    monkeypatch.setenv("LLM_RUNTIME_MODEL", "claude-3-opus")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/yatra")

    with pytest.raises(ConfigError, match="Forbidden model"):
        Settings()


def test_settings_missing_openai_key(monkeypatch):
    """Missing OPENAI_API_KEY raises MissingAPIKeyError."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/yatra")

    with pytest.raises(MissingAPIKeyError):
        Settings()


def test_settings_missing_database_url(monkeypatch):
    """Missing DATABASE_URL raises ConfigError."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-test")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")

    with pytest.raises(ConfigError, match="DATABASE_URL is required"):
        Settings()


def test_settings_invalid_database_url(monkeypatch):
    """Invalid DATABASE_URL raises ConfigError."""
    monkeypatch.setenv("DATABASE_URL", "mysql://localhost:5432/yatra")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-test")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")

    with pytest.raises(ConfigError, match="must use postgresql"):
        Settings()


def test_llm_config_override(monkeypatch):
    """LLM config can be overridden via env."""
    monkeypatch.setenv("LLM_RUNTIME_MODEL", "openai:gpt-4o-mini")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-test")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/yatra")

    settings = Settings()
    assert settings.llm.runtime_model == ModelEnum.OPENAI_GPT4O_MINI


def test_eval_config_thresholds(monkeypatch):
    """Eval thresholds are configurable."""
    monkeypatch.setenv("EVAL_SAFETY_THRESHOLD", "0.99")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-test")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/yatra")

    settings = Settings()
    assert settings.eval.safety_threshold == 0.99
