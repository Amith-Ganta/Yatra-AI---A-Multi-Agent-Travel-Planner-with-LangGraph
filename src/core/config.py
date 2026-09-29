"""Configuration module: environment-driven settings via pydantic-settings."""

from enum import Enum
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

from .errors import ConfigError, MissingAPIKeyError


class ModelEnum(str, Enum):
    """Allowed LLM models (STRICT policy)."""

    GROQ_MIXTRAL = "groq:mixtral-8x7b-32768"
    OPENAI_GPT4O_MINI = "openai:gpt-4o-mini"


class LLMConfig(BaseSettings):
    """LLM configuration."""

    runtime_model: ModelEnum = Field(
        default=ModelEnum.GROQ_MIXTRAL,
        alias="llm_runtime_model",
        description="Primary LLM for agent runtime",
    )
    eval_model: ModelEnum = Field(
        default=ModelEnum.OPENAI_GPT4O_MINI,
        alias="llm_eval_model",
        description="LLM judge for evaluation",
    )
    groq_api_key: Optional[str] = Field(
        default=None,
        alias="groq_api_key",
    )
    openai_api_key: str = Field(
        alias="openai_api_key",
        description="OpenAI API key (required)",
    )
    deepseek_api_key: Optional[str] = Field(
        default=None,
        alias="deepseek_api_key",
    )
    max_tokens: int = 2000
    temperature: float = 0.7
    top_p: float = 0.9

    @field_validator("runtime_model", "eval_model", mode="before")
    @classmethod
    def validate_model(cls, v):
        if isinstance(v, str):
            if v.startswith("claude-") or v.startswith("gpt-4") or v.startswith("gpt-5"):
                raise ConfigError(f"Forbidden model: {v}")
            if v in ["groq:mixtral-8x7b-32768", "openai:gpt-4o-mini"]:
                return ModelEnum(v)
            raise ConfigError(f"Unknown model: {v}")
        return v

    @field_validator("openai_api_key", mode="before")
    @classmethod
    def validate_openai_key(cls, v):
        if not v:
            raise MissingAPIKeyError("OPENAI_API_KEY is required")
        return v

    @field_validator("groq_api_key", mode="before")
    @classmethod
    def validate_groq_key(cls, v, info):
        runtime_model = info.data.get("runtime_model")
        if runtime_model == ModelEnum.GROQ_MIXTRAL and not v:
            raise MissingAPIKeyError("GROQ_API_KEY is required when using Groq models")
        return v

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "case_sensitive": False}


class DatabaseConfig(BaseSettings):
    """Database configuration."""

    url: str = Field(
        alias="database_url",
        description="PostgreSQL connection string",
    )
    echo: bool = False
    pool_size: int = 20
    max_overflow: int = 0

    @field_validator("url", mode="before")
    @classmethod
    def validate_database_url(cls, v):
        if not v:
            raise ConfigError("DATABASE_URL is required")
        if not v.startswith("postgresql://"):
            raise ConfigError(f"DATABASE_URL must use postgresql:// scheme, got: {v}")
        return v

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "case_sensitive": False}


class AppConfig(BaseSettings):
    """Application configuration."""

    name: str = "Yatra AI"
    env: str = Field(default="development", alias="app_env")
    debug: bool = Field(default=True, alias="app_debug")
    host: str = Field(default="0.0.0.0", alias="app_host")
    port: int = Field(default=8000, alias="app_port")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "case_sensitive": False}


class EvalConfig(BaseSettings):
    """Evaluation configuration."""

    safety_threshold: float = Field(
        default=0.95,
        alias="eval_safety_threshold",
    )
    factuality_threshold: float = Field(
        default=0.90,
        alias="eval_factuality_threshold",
    )
    budget_threshold: float = Field(
        default=0.95,
        alias="eval_budget_threshold",
    )
    code_coverage_threshold: float = Field(
        default=0.80,
        alias="eval_code_coverage_threshold",
    )
    judge_tpm: int = Field(
        default=90000,
        alias="eval_judge_tpm",
        description="Tokens per minute limiter for eval judges",
    )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "case_sensitive": False}


class Settings(BaseSettings):
    """Root settings combining all config sections."""

    llm: LLMConfig = Field(default_factory=LLMConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    app: AppConfig = Field(default_factory=AppConfig)
    eval: EvalConfig = Field(default_factory=EvalConfig)

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "case_sensitive": False}


settings = Settings()
