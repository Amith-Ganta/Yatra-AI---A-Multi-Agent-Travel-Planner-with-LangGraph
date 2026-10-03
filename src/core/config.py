"""Configuration module: environment-driven settings via pydantic-settings."""

from enum import Enum
from typing import Annotated, Any, Optional

from pydantic import AliasChoices, Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from .errors import ConfigError


class ModelEnum(str, Enum):
    """Allowed LLM models (STRICT policy: only these ids are accepted)."""

    DEEPSEEK_FLASH = "deepseek:deepseek-flash"
    # Legacy DeepSeek alias. Kept so an old LLM_RUNTIME_MODEL value still loads; the
    # fallback chain absorbs the call if DeepSeek has retired the name.
    DEEPSEEK_CHAT = "deepseek:deepseek-chat"
    OPENAI_GPT41_MINI = "openai:gpt-4.1-mini"
    OPENAI_GPT4O_MINI = "openai:gpt-4o-mini"


def _coerce_model(v: Any) -> Any:
    """Apply the model allow-list to one raw value (string or already a ModelEnum)."""
    if isinstance(v, str) and not isinstance(v, ModelEnum):
        v = v.strip()
        if v.startswith("claude-") or v.startswith("gpt-4") or v.startswith("gpt-5"):
            raise ConfigError(f"Forbidden model: {v}")
        try:
            return ModelEnum(v)
        except ValueError:
            raise ConfigError(f"Unknown model: {v}") from None
    return v


class LLMConfig(BaseSettings):
    """LLM configuration."""

    runtime_model: ModelEnum = Field(
        default=ModelEnum.DEEPSEEK_FLASH,
        alias="llm_runtime_model",
        description="Primary LLM for agent runtime",
    )
    fallback_models: Annotated[list[ModelEnum], NoDecode] = Field(
        default_factory=lambda: [ModelEnum.OPENAI_GPT41_MINI, ModelEnum.DEEPSEEK_FLASH],
        alias="llm_fallback_models",
        description=(
            "Models tried, in order, when the primary call fails. Comma separated in the "
            "environment. The primary itself and models without an API key are skipped."
        ),
    )
    eval_model: ModelEnum = Field(
        default=ModelEnum.OPENAI_GPT4O_MINI,
        alias="llm_eval_model",
        description="LLM judge for evaluation",
    )
    openai_api_key: Optional[str] = Field(
        default=None,
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
    request_timeout: float = Field(
        default=45.0,
        gt=0,
        alias="llm_request_timeout",
        description="Seconds to wait for one model call before the fallback chain takes over",
    )
    max_retries: int = Field(
        default=1,
        ge=0,
        alias="llm_max_retries",
        description="Same-model retries inside the client, before falling back to the next model",
    )

    @field_validator("runtime_model", "eval_model", mode="before")
    @classmethod
    def validate_model(cls, v: Any) -> Any:
        return _coerce_model(v)

    @field_validator("fallback_models", mode="before")
    @classmethod
    def validate_fallback_models(cls, v: Any) -> Any:
        """Accept a comma separated string (the env form) or a list; blank means none."""
        if isinstance(v, str):
            v = [item for item in (part.strip() for part in v.split(",")) if item]
        if isinstance(v, (list, tuple)):
            items: list[Any] = list(v)  # pyright: ignore[reportUnknownArgumentType]
            return [_coerce_model(item) for item in items]
        return v

    @field_validator("openai_api_key", mode="before")
    @classmethod
    def validate_openai_key(cls, v: Any) -> Any:
        # Optional at startup; fail when actually used by eval model
        return v

    @field_validator("deepseek_api_key", mode="before")
    @classmethod
    def validate_deepseek_key(cls, v: Any, info: ValidationInfo) -> Any:
        # Optional at startup; fail when actually used by runtime model
        return v

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore", populate_by_name=True)


class DatabaseConfig(BaseSettings):
    """Database configuration."""

    url: Optional[str] = Field(
        default=None,
        alias="database_url",
        description="PostgreSQL connection string",
    )
    echo: bool = False
    pool_size: int = 20
    max_overflow: int = 0

    @field_validator("url", mode="before")
    @classmethod
    def validate_database_url(cls, v: Any) -> Any:
        if not v:
            raise ConfigError("DATABASE_URL is required")
        # Heroku-style hosts hand out the short scheme; psycopg only accepts the long one.
        if isinstance(v, str) and v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://") :]
        # The value is never echoed: a DATABASE_URL carries credentials.
        if not isinstance(v, str) or not v.startswith("postgresql://"):
            raise ConfigError("DATABASE_URL must use postgresql:// scheme")
        return v

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")


class AppConfig(BaseSettings):
    """Application configuration."""

    name: str = "Yatra AI"
    env: str = Field(default="development", alias="app_env")
    debug: bool = Field(default=True, alias="app_debug")
    host: str = Field(default="0.0.0.0", alias="app_host")
    # APP_PORT wins; PORT is what Render, Railway and Cloud Run inject
    port: int = Field(default=8000, validation_alias=AliasChoices("app_port", "port"))
    cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        alias="cors_origins",
        description="Comma-separated browser origins allowed to call the API",
    )
    cors_origin_regex: Optional[str] = Field(
        default=None,
        alias="cors_origin_regex",
        description="Optional pattern for origins that change, such as Vercel preview URLs",
    )

    @field_validator("cors_origin_regex", mode="before")
    @classmethod
    def blank_regex_means_none(cls, v: Any) -> Any:
        # Compose and PaaS dashboards pass an unset variable as an empty string
        return v or None

    @property
    def cors_origin_list(self) -> list[str]:
        """`cors_origins` as a clean list: trimmed, no trailing slash, no blanks."""
        return [item.strip().rstrip("/") for item in self.cors_origins.split(",") if item.strip()]

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")


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

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")


class MCPConfig(BaseSettings):
    """MCP tool servers and the human-approval loop."""

    enabled: bool = Field(
        default=True,
        alias="mcp_enabled",
        description="Run the tool servers as MCP subprocesses; off means in-process tool calls",
    )
    startup_timeout: float = Field(
        default=20.0,
        alias="mcp_startup_timeout",
        description="Seconds to wait for each MCP server to start and list its tools",
    )
    call_timeout: float = Field(
        default=25.0,
        alias="mcp_call_timeout",
        description="Seconds a single MCP tool call may take before the fallback runs",
    )
    max_revisions: int = Field(
        default=3,
        alias="max_revisions",
        ge=0,
        description="How many times a rejected plan is regenerated before it is accepted as is",
    )

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")


class Settings(BaseSettings):
    """Root settings combining all config sections."""

    llm: LLMConfig = Field(default_factory=LLMConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    app: AppConfig = Field(default_factory=AppConfig)
    eval: EvalConfig = Field(default_factory=EvalConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )


settings = Settings()
