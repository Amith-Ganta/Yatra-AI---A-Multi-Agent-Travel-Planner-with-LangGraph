"""Telemetry: structured logging, trace ID propagation, metrics."""

import logging
import threading
from contextvars import ContextVar
from typing import Any, TextIO
from uuid import uuid4

from pythonjsonlogger.json import JsonFormatter

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


class _TraceIdFilter(logging.Filter):
    """Stamp every record with the active trace id unless the caller already passed one."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "trace_id", None):
            record.__dict__["trace_id"] = trace_id_var.get() or None
        return True


def build_handler(stream: TextIO | None = None) -> logging.Handler:
    """A handler that writes one JSON object per record: ts, level, name, trace_id, message."""
    handler = logging.StreamHandler(stream)
    handler.addFilter(_TraceIdFilter())
    handler.setFormatter(
        JsonFormatter(
            # These are the LogRecord attribute names; "level" and "ts" are the output keys
            fmt="%(levelname)s %(name)s %(trace_id)s %(message)s",
            rename_fields={"levelname": "level"},
            timestamp="ts",
        )
    )
    return handler


def setup_logging() -> logging.Logger:
    """Configure JSON logging at startup."""
    logger = logging.getLogger("yatra")
    logger.setLevel(logging.DEBUG if settings.app.debug else logging.INFO)

    if logger.handlers:
        return logger

    logger.addHandler(build_handler())

    return logger


logger = setup_logging()


def log_with_context(level: int, msg: str, **kwargs: Any) -> None:
    """Log with trace ID."""
    extra: dict[str, Any] = kwargs.pop("extra", {})
    extra["trace_id"] = TraceContext.get()
    logger.log(level, msg, extra=extra, **kwargs)
