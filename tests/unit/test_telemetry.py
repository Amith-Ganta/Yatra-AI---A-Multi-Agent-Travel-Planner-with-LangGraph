"""Structured logging: every line is one JSON object with a real timestamp, level and trace id.

The formatter used to ask for `%(timestamp)s` and `%(level)s`, which are not LogRecord
attributes, so `ts` and `level` were always null and log search by level found nothing.
"""

import io
import json
import logging

import pytest

from src.core.telemetry import build_handler, trace_id_var


@pytest.fixture
def emit():
    """Log one record through a fresh handler and return the parsed JSON line."""
    stream = io.StringIO()
    handler = build_handler(stream)
    log = logging.getLogger("yatra.test_telemetry")
    log.setLevel(logging.DEBUG)
    log.propagate = False
    log.addHandler(handler)

    def _emit(level: int, message: str, **extra: object) -> dict[str, object]:
        log.log(level, message, extra=extra)
        return json.loads(stream.getvalue().strip().splitlines()[-1])

    yield _emit
    log.removeHandler(handler)


def test_line_has_a_timestamp_a_level_a_name_and_the_message(emit):
    line = emit(logging.WARNING, "disk almost full")

    assert line["level"] == "WARNING"
    assert line["message"] == "disk almost full"
    assert line["name"] == "yatra.test_telemetry"
    assert isinstance(line["ts"], str) and line["ts"].startswith("20")


def test_extra_fields_are_kept(emit):
    line = emit(logging.INFO, "approval recorded", thread_id="t-1", approved=False)

    assert line["thread_id"] == "t-1"
    assert line["approved"] is False


def test_trace_id_comes_from_the_context_when_the_caller_gives_none(emit):
    token = trace_id_var.set("trace-abc")
    try:
        line = emit(logging.INFO, "inside a request")
    finally:
        trace_id_var.reset(token)

    assert line["trace_id"] == "trace-abc"


def test_an_explicit_trace_id_wins_over_the_context(emit):
    token = trace_id_var.set("from-context")
    try:
        line = emit(logging.INFO, "explicit", trace_id="from-caller")
    finally:
        trace_id_var.reset(token)

    assert line["trace_id"] == "from-caller"


def test_trace_id_is_null_outside_a_request(emit):
    line = emit(logging.INFO, "startup")

    assert line["trace_id"] is None
