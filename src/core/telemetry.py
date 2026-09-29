"""Telemetry: structured logging, trace ID propagation, metrics."""

import logging
import threading
from contextvars import ContextVar
from uuid import uuid4

from pythonjsonlogger import jsonlogger

from .config import settings

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


class TraceContext:
    """Thread-safe trace ID context."""

    _local = threading.local()

    @classmethod
    def set(cls, trace_id: str) -> None:
        cls._local.trace_id = trace_id
        trace_id_var.set(trace_id)

    @classmethod
    def get(cls) -> str:
        if not hasattr(cls._local, "trace_id") or not cls._local.trace_id:
            cls._local.trace_id = str(uuid4())
            trace_id_var.set(cls._local.trace_id)
        return cls._local.trace_id

    @classmethod
    def reset(cls) -> None:
        cls._local.trace_id = None
        trace_id_var.set("")


def setup_logging() -> logging.Logger:
    """Configure JSON logging at startup."""
    logger = logging.getLogger("yatra")
    logger.setLevel(logging.DEBUG if settings.app.debug else logging.INFO)

    if logger.handlers:
        return logger

    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        fmt="%(timestamp)s %(level)s %(name)s %(trace_id)s %(message)s",
        rename_fields={"timestamp": "ts"},
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


logger = setup_logging()


def log_with_context(level: int, msg: str, **kwargs) -> None:
    """Log with trace ID."""
    extra = kwargs.pop("extra", {})
    extra["trace_id"] = TraceContext.get()
    logger.log(level, msg, extra=extra, **kwargs)
