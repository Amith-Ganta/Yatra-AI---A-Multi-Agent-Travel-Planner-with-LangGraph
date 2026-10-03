"""Tests for configuration module."""

import pytest

from src.core.config import ModelEnum, Settings
from src.core.errors import ConfigError


def test_settings_load_from_env(monkeypatch):
    """Settings load from .env file."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-test_key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-deepseek")
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/yatra")

    settings = Settings()
    assert settings.llm.runtime_model == ModelEnum.DEEPSEEK_FLASH
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
    """Missing OPENAI_API_KEY at startup is allowed (lazy validation)."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/yatra")

    # Should not raise during initialization; error happens when key is actually used
    settings = Settings()
    assert settings.llm.openai_api_key is None


def test_settings_missing_database_url(monkeypatch):
    """Missing DATABASE_URL raises ConfigError."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

    with pytest.raises(ConfigError, match="DATABASE_URL is required"):
        Settings()


def test_settings_invalid_database_url(monkeypatch):
    """Invalid DATABASE_URL raises ConfigError."""
    monkeypatch.setenv("DATABASE_URL", "mysql://localhost:5432/yatra")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

    with pytest.raises(ConfigError, match="must use postgresql"):
        Settings()


def test_short_postgres_scheme_is_accepted_and_normalised(monkeypatch):
    """Hosts such as Heroku hand out postgres://, which psycopg rejects."""
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pw@db.example:5432/yatra?sslmode=require")

    settings = Settings()

    assert settings.database.url == "postgresql://user:pw@db.example:5432/yatra?sslmode=require"


def test_port_defaults_to_8000(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/yatra")
    monkeypatch.delenv("APP_PORT", raising=False)
    monkeypatch.delenv("PORT", raising=False)

    assert Settings().app.port == 8000


def test_port_is_read_from_the_host_injected_port_variable(monkeypatch):
    """Render, Railway and Cloud Run tell the container which port to bind through PORT."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/yatra")
    monkeypatch.delenv("APP_PORT", raising=False)
    monkeypatch.setenv("PORT", "10000")

    assert Settings().app.port == 10000


def test_app_port_wins_over_port(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/yatra")
    monkeypatch.setenv("APP_PORT", "9001")
    monkeypatch.setenv("PORT", "10000")

    assert Settings().app.port == 9001


def test_cors_origins_are_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/yatra")
    monkeypatch.setenv("CORS_ORIGINS", "https://yatra-ai.vercel.app/, https://yatra.example.com")
    monkeypatch.setenv("CORS_ORIGIN_REGEX", r"https://yatra-ai-[a-z0-9-]+\.vercel\.app")

    app = Settings().app

    assert app.cors_origin_list == ["https://yatra-ai.vercel.app", "https://yatra.example.com"]
    assert app.cors_origin_regex == r"https://yatra-ai-[a-z0-9-]+\.vercel\.app"


def test_blank_cors_origin_regex_means_no_regex(monkeypatch):
    """docker compose passes an unset ${CORS_ORIGIN_REGEX:-} as an empty string."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/yatra")
    monkeypatch.setenv("CORS_ORIGIN_REGEX", "")

    assert Settings().app.cors_origin_regex is None


def test_llm_config_override(monkeypatch):
    """LLM config can be overridden via env."""
    monkeypatch.setenv("LLM_RUNTIME_MODEL", "openai:gpt-4o-mini")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/yatra")

    settings = Settings()
    assert settings.llm.runtime_model == ModelEnum.OPENAI_GPT4O_MINI


def test_eval_config_thresholds(monkeypatch):
    """Eval thresholds are configurable."""
    monkeypatch.setenv("EVAL_SAFETY_THRESHOLD", "0.99")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/yatra")

    settings = Settings()
    assert settings.eval.safety_threshold == 0.99


def test_deepseek_model_support(monkeypatch):
    """DeepSeek model is supported."""
    monkeypatch.setenv("LLM_RUNTIME_MODEL", "deepseek:deepseek-chat")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-deepseek")
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/yatra")

    settings = Settings()
    assert settings.llm.runtime_model == ModelEnum.DEEPSEEK_CHAT


def test_deepseek_missing_key(monkeypatch):
    """Missing DEEPSEEK_API_KEY at startup is allowed (lazy validation)."""
    monkeypatch.setenv("LLM_RUNTIME_MODEL", "deepseek:deepseek-chat")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-test")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/yatra")

    # Should not raise during initialization; error happens when key is actually used
    settings = Settings()
    assert settings.llm.deepseek_api_key is None


def test_new_model_ids_are_accepted(monkeypatch):
    """The cheap current models load as runtime and as eval model ids."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/yatra")

    monkeypatch.setenv("LLM_RUNTIME_MODEL", "openai:gpt-4.1-mini")
    assert Settings().llm.runtime_model == ModelEnum.OPENAI_GPT41_MINI

    monkeypatch.setenv("LLM_RUNTIME_MODEL", "deepseek:deepseek-flash")
    assert Settings().llm.runtime_model == ModelEnum.DEEPSEEK_FLASH


def test_unknown_model_rejected(monkeypatch):
    """An id outside the allow-list fails fast at startup."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/yatra")
    monkeypatch.setenv("LLM_RUNTIME_MODEL", "mistral:large")

    with pytest.raises(ConfigError, match="Unknown model"):
        Settings()


def test_fallback_models_default(monkeypatch):
    """Default fallback order is gpt-4.1-mini, then deepseek-flash."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/yatra")
    monkeypatch.delenv("LLM_FALLBACK_MODELS", raising=False)

    assert Settings().llm.fallback_models == [
        ModelEnum.OPENAI_GPT41_MINI,
        ModelEnum.DEEPSEEK_FLASH,
    ]


def test_fallback_models_from_comma_separated_env(monkeypatch):
    """LLM_FALLBACK_MODELS is a comma separated list; spaces and blanks are ignored."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/yatra")
    monkeypatch.setenv("LLM_FALLBACK_MODELS", " deepseek:deepseek-flash , ,openai:gpt-4o-mini ")

    assert Settings().llm.fallback_models == [
        ModelEnum.DEEPSEEK_FLASH,
        ModelEnum.OPENAI_GPT4O_MINI,
    ]


def test_fallback_models_blank_means_none(monkeypatch):
    """An empty LLM_FALLBACK_MODELS (as a PaaS dashboard may pass it) turns fallbacks off."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/yatra")
    monkeypatch.setenv("LLM_FALLBACK_MODELS", "")

    assert Settings().llm.fallback_models == []


def test_fallback_models_reject_forbidden_and_unknown(monkeypatch):
    """The allow-list applies to every fallback entry, not only the primary."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/yatra")

    monkeypatch.setenv("LLM_FALLBACK_MODELS", "openai:gpt-4.1-mini,claude-3-opus")
    with pytest.raises(ConfigError, match="Forbidden model"):
        Settings()

    monkeypatch.setenv("LLM_FALLBACK_MODELS", "openai:gpt-4.1-mini,mistral:large")
    with pytest.raises(ConfigError, match="Unknown model"):
        Settings()


def test_llm_timeout_and_retry_defaults_and_override(monkeypatch):
    """Fast-failover defaults, both overridable."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/yatra")
    monkeypatch.delenv("LLM_REQUEST_TIMEOUT", raising=False)
    monkeypatch.delenv("LLM_MAX_RETRIES", raising=False)

    llm = Settings().llm
    assert llm.request_timeout == 45.0
    assert llm.max_retries == 1

    monkeypatch.setenv("LLM_REQUEST_TIMEOUT", "10")
    monkeypatch.setenv("LLM_MAX_RETRIES", "0")
    llm = Settings().llm
    assert llm.request_timeout == 10.0
    assert llm.max_retries == 0
