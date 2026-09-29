"""Typed exception hierarchy for Yatra AI."""


class YatraException(Exception):
    """Base exception for all Yatra errors."""
    pass


class ConfigError(YatraException):
    """Configuration validation failure (startup)."""
    pass


class MissingAPIKeyError(ConfigError):
    """Required API key not found in .env."""
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
