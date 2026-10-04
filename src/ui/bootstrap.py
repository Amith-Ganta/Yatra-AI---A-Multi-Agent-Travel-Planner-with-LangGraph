"""Prepare the process environment for the Streamlit app.

``streamlit_app.py`` calls ``prepare_environment`` before it imports anything from ``src.core``:
``Settings`` is built when that package is imported and reads the environment once. Streamlit
Cloud keeps keys in its Secrets box, a local run keeps them in ``.streamlit/secrets.toml`` or
``.env``, and the tools and MCP server subprocesses read them from ``os.environ``.

This module must not import ``src.core``, for the same reason.
"""

import os
from collections.abc import Mapping, MutableMapping
from typing import Any, Optional

from dotenv import load_dotenv

from src.envutil import strip_api_keys

_SCALARS = (str, int, float, bool)

# ``Settings`` insists on a database URL because the API needs one. The Streamlit app keeps its
# plans in memory and never opens a connection, so an unused placeholder satisfies the check.
UNUSED_DATABASE_URL = "postgresql://unused:unused@localhost:5432/unused"


def apply_secrets(
    secrets: Mapping[str, Any], environ: Optional[MutableMapping[str, str]] = None
) -> list[str]:
    """Copy the top-level scalar secrets into the environment, upper-cased.

    A variable that is already set wins, the same rule ``load_dotenv(override=False)`` follows.
    Nested tables are skipped. Returns the names that were set (never the values).
    """
    target: MutableMapping[str, str] = os.environ if environ is None else environ
    applied: list[str] = []
    for key, value in secrets.items():
        name = str(key).upper()
        if not isinstance(value, _SCALARS) or name in target:
            continue
        target[name] = str(value)
        applied.append(name)
    return applied


def _streamlit_secrets() -> dict[str, Any]:
    """The app's secrets, or nothing when there is no secrets file (a plain local run)."""
    try:
        import streamlit as st

        return dict(st.secrets)
    except Exception:
        return {}


def prepare_environment() -> list[str]:
    """Load ``.env`` and Streamlit secrets into ``os.environ`` and clean the API keys.

    Returns the names taken from Streamlit secrets.
    """
    load_dotenv(override=False)
    applied = apply_secrets(_streamlit_secrets())
    os.environ.setdefault("DATABASE_URL", UNUSED_DATABASE_URL)
    strip_api_keys()  # a key pasted with a trailing newline would fail at the first HTTP call
    return applied
