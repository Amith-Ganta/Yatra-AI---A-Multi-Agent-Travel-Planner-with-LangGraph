# Config & LLM Factory Specification

**Phase:** 2  
**Version:** 1.0  
**Status:** Implementation  
**Dependencies:** Phase 1 (specs/00-overview.spec.md)

---

## Overview

This phase establishes the configuration layer and LLM abstraction. All runtime behavior (models, API keys, logging, feature flags) is controlled via environment variables, validated at startup, and exposed through typed Python interfaces.

**Principles:**
- Environment-driven (12-factor app)
- Fail-fast validation (startup, not runtime)
- Model pinning (no model string inference)
- Structured logging (JSON, trace IDs)
- No secrets in code (pydantic-settings from `.env`)

---

## Architecture

```
.env (secrets, not in repo)
  ↓
pydantic_settings.BaseSettings
  ↓
src/core/config.py (Settings class)
  ├─ llm_config: LLMConfig
  ├─ database_config: DatabaseConfig
  ├─ app_config: AppConfig
  └─ eval_config: EvalConfig
  ↓
src/core/llm.py (LLM factory)
  ├─ get_llm(model_id) → BaseChatModel
  └─ get_eval_judge() → BaseChatModel
  ↓
Agents, API, Evals (use via dependency injection)
```

---

## src/core/config.py

**Responsibility:** Load and validate all environment variables at startup.

**Structure:**

```python
from pydantic_settings import BaseSettings
from enum import Enum

class ModelEnum(str, Enum):
    GROQ_DEEPSEEK = "deepseek:deepseek-chat"
    OPENAI_GPT4O_MINI = "openai:gpt-4o-mini"
    OPENAI_GPT4_1_MINI = "openai:gpt-4.1-mini"
    # No claude-*, gpt-4*, gpt-5.* allowed

class LLMConfig(BaseModel):
    runtime_model: ModelEnum  # Primary LLM (from LLM_RUNTIME_MODEL env)
    eval_model: ModelEnum     # Eval judge (from LLM_EVAL_MODEL env)
    groq_api_key: str | None  # From GROQ_API_KEY
    openai_api_key: str       # Required, from OPENAI_API_KEY
    deepseek_api_key: str | None
    max_tokens: int = 2000
    temperature: float = 0.7
    top_p: float = 0.9

class DatabaseConfig(BaseModel):
    url: str  # From DATABASE_URL (required)
    echo: bool = False
    pool_size: int = 20
    max_overflow: int = 0

class AppConfig(BaseModel):
    name: str = "Yatra AI"
    env: str = "development"  # development, staging, production
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000

class EvalConfig(BaseModel):
    safety_threshold: float = 0.95
    factuality_threshold: float = 0.90
    budget_threshold: float = 0.95
    code_coverage_threshold: float = 0.80
    judge_tpm: int = 90000  # Tokens per minute limiter

class Settings(BaseSettings):
    llm: LLMConfig
    database: DatabaseConfig
    app: AppConfig
    eval: EvalConfig
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

# Singleton instance
settings = Settings()
```

**Validation:**
- Startup check: If `OPENAI_API_KEY` missing → raise `ConfigError`
- Startup check: If `DATABASE_URL` missing → raise `ConfigError`
- Startup check: If `LLM_RUNTIME_MODEL` not in `ModelEnum` → raise `ConfigError`
- Startup check: If model is `claude-*`, `gpt-4*`, `gpt-5.*` → raise `ConfigError`

---

## src/core/llm.py

**Responsibility:** Factory for ChatModel instances. Encapsulates model initialization, error handling, rate limiting.

**Structure:**

```python
from langchain_core.language_models import BaseChatModel
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from config import settings, ModelEnum

class LLMFactory:
    def __init__(self, config: LLMConfig):
        self.config = config
        self._cache = {}
    
    def get_llm(self, model_id: ModelEnum | None = None) -> BaseChatModel:
        """Get LLM instance. Cache by model_id."""
        model_id = model_id or self.config.runtime_model
        
        if model_id in self._cache:
            return self._cache[model_id]
        
        if model_id == ModelEnum.GROQ_DEEPSEEK:
            if not self.config.groq_api_key:
                raise ConfigError("GROQ_API_KEY required for deepseek model")
            llm = ChatGroq(
                model_name="mixtral-8x7b-32768",  # Or deepseek if available
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
        elif model_id == ModelEnum.OPENAI_GPT4_1_MINI:
            llm = ChatOpenAI(
                model_name="gpt-4-turbo",  # Closest to 4.1-mini
                api_key=self.config.openai_api_key,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )
        else:
            raise ConfigError(f"Unknown model: {model_id}")
        
        self._cache[model_id] = llm
        return llm
    
    def get_eval_judge(self) -> BaseChatModel:
        """Get eval judge (always gpt-4o-mini primary)."""
        return self.get_llm(ModelEnum.OPENAI_GPT4O_MINI)

# Singleton
llm_factory = LLMFactory(settings.llm)
```

---

## src/core/telemetry.py

**Responsibility:** Structured logging, trace ID propagation, metrics collection.

**Structure:**

```python
import logging
import json
from uuid import uuid4
from pythonjsonlogger import jsonlogger
from config import settings

class TraceContext:
    """Thread-local trace ID."""
    _trace_id: str = None
    
    @classmethod
    def set(cls, trace_id: str):
        cls._trace_id = trace_id
    
    @classmethod
    def get(cls):
        if not cls._trace_id:
            cls._trace_id = str(uuid4())
        return cls._trace_id

def setup_logging():
    """Configure JSON logging at startup."""
    logger = logging.getLogger()
    logger.setLevel(settings.app.debug and logging.DEBUG or logging.INFO)
    
    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        fmt='%(timestamp)s %(level)s %(name)s %(trace_id)s %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger

# Singleton
logger = setup_logging()
```

---

## src/core/errors.py

**Responsibility:** Typed exception hierarchy for config, LLM, and runtime errors.

**Structure:**

```python
class YatraException(Exception):
    """Base exception for all Yatra errors."""
    pass

class ConfigError(YatraException):
    """Configuration validation failure (startup)."""
    pass

class LLMError(YatraException):
    """LLM invocation or factory error."""
    pass

class DatabaseError(YatraException):
    """Database operation failure."""
    pass

class ValidationError(YatraException):
    """Input validation failure."""
    pass

class MissingAPIKeyError(ConfigError):
    """Required API key not found in .env."""
    pass
```

---

## requirements.txt (Phase 2)

```
# Core
python-dotenv==1.0.0
pydantic==2.5.0
pydantic-settings==2.1.0

# LLM
langchain==0.1.10
langchain-core==0.1.20
langchain-groq==0.1.0
langchain-openai==0.1.0

# Database
sqlalchemy==2.0.23
psycopg==3.1.13
psycopg-binary==3.1.13

# Async
asyncio-contextmanager==1.0.0

# Logging
python-json-logger==2.0.7

# Type checking
pydantic-extra-types==2.1.0
```

---

## pyproject.toml

```toml
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "yatra-ai"
version = "1.0.0"
description = "Production-grade multi-agent travel planner"
readme = "README.md"
requires-python = ">=3.11"
license = {text = "MIT"}
authors = [
    {name = "Amith Ganta", email = "gantaamith007@gmail.com"}
]

[project.urls]
Repository = "https://github.com/Amith-Ganta/Yatra-AI---A-Multi-Agent-Travel-Planner-with-LangGraph"

[tool.setuptools]
packages = ["src"]
```

---

## Test: test_config.py

**Validates:** Settings loading, validation, env overrides.

```python
import pytest
from config import Settings, ModelEnum, ConfigError

def test_settings_load():
    """Settings load from .env."""
    settings = Settings()
    assert settings.llm.runtime_model == ModelEnum.GROQ_DEEPSEEK
    assert settings.llm.openai_api_key
    assert settings.database.url.startswith("postgresql://")

def test_settings_validation():
    """Invalid model raises ConfigError."""
    import os
    os.environ["LLM_RUNTIME_MODEL"] = "claude-3-opus"  # FORBIDDEN
    with pytest.raises(ConfigError):
        Settings()

def test_missing_openai_key():
    """Missing OPENAI_API_KEY raises ConfigError."""
    import os
    del os.environ["OPENAI_API_KEY"]
    with pytest.raises(ConfigError):
        Settings()
```

---

## Test: test_llm_factory.py

**Validates:** LLM factory instantiation, model pinning, caching.

```python
import pytest
from llm import llm_factory, LLMFactory
from config import ModelEnum

def test_get_llm_groq():
    """Get Groq/Deepseek LLM."""
    llm = llm_factory.get_llm(ModelEnum.GROQ_DEEPSEEK)
    assert llm is not None
    assert llm.model_name  # Has a model name

def test_get_llm_openai():
    """Get OpenAI LLM."""
    llm = llm_factory.get_llm(ModelEnum.OPENAI_GPT4O_MINI)
    assert llm is not None

def test_llm_caching():
    """LLM instances cached by model_id."""
    llm1 = llm_factory.get_llm(ModelEnum.OPENAI_GPT4O_MINI)
    llm2 = llm_factory.get_llm(ModelEnum.OPENAI_GPT4O_MINI)
    assert llm1 is llm2  # Same instance

def test_eval_judge():
    """Eval judge is always gpt-4o-mini."""
    judge = llm_factory.get_eval_judge()
    assert judge.model_name == "gpt-4o-mini"
```

---

## Success Criteria

- ✅ Settings loads from `.env` without secrets in code
- ✅ All required keys validated at startup (fail-fast)
- ✅ Model pinning: no string inference, only enum
- ✅ No forbidden models (claude-*, gpt-4*, gpt-5.*)
- ✅ LLM factory caches instances
- ✅ Tests pass (pytest)
- ✅ Linting passes (ruff)
- ✅ Type checking passes (pyright)

---

**Next Phase:** Phase 3 (Agents + LangGraph)
