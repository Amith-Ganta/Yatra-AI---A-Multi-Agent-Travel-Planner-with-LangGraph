"""Start-up for the Streamlit app: secrets reach the environment before ``Settings`` is built."""

import os
import subprocess
import sys
from pathlib import Path

import src.ui.bootstrap as bootstrap
from src.ui.bootstrap import UNUSED_DATABASE_URL, apply_secrets, prepare_environment

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_scalar_secrets_become_upper_case_variables():
    environ: dict[str, str] = {}
    applied = apply_secrets(
        {"deepseek_api_key": "ds-key", "MCP_ENABLED": False, "MAX_REVISIONS": 2, "ratio": 0.5},
        environ,
    )
    assert environ == {
        "DEEPSEEK_API_KEY": "ds-key",
        "MCP_ENABLED": "False",
        "MAX_REVISIONS": "2",
        "RATIO": "0.5",
    }
    assert applied == list(environ)


def test_a_variable_that_is_already_set_wins():
    environ = {"OPENAI_API_KEY": "from-the-shell"}
    applied = apply_secrets({"OPENAI_API_KEY": "from-secrets", "TAVILY_API_KEY": "t"}, environ)
    assert environ["OPENAI_API_KEY"] == "from-the-shell"
    assert applied == ["TAVILY_API_KEY"]


def test_nested_tables_are_skipped():
    environ: dict[str, str] = {}
    applied = apply_secrets({"connections": {"db": {"url": "x"}}, "items": [1, 2]}, environ)
    assert environ == {}
    assert applied == []


def test_applied_names_never_include_values():
    applied = apply_secrets({"DEEPSEEK_API_KEY": "sk-very-secret"}, {})
    assert "sk-very-secret" not in "".join(applied)


def test_prepare_environment_reads_secrets_and_cleans_keys(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "pasted-key\n")
    monkeypatch.setattr(bootstrap, "load_dotenv", lambda **_: False)
    monkeypatch.setattr(bootstrap, "_streamlit_secrets", lambda: {"TAVILY_API_KEY": " tav \n"})

    applied = prepare_environment()

    assert applied == ["TAVILY_API_KEY"]
    assert os.environ["TAVILY_API_KEY"] == "tav"
    assert os.environ["DEEPSEEK_API_KEY"] == "pasted-key"
    assert os.environ["DATABASE_URL"] == UNUSED_DATABASE_URL


def test_prepare_environment_keeps_a_real_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://real:real@db:5432/real")
    monkeypatch.setattr(bootstrap, "load_dotenv", lambda **_: False)
    monkeypatch.setattr(bootstrap, "_streamlit_secrets", lambda: {})
    prepare_environment()
    assert os.environ["DATABASE_URL"] == "postgresql://real:real@db:5432/real"


def test_placeholder_database_url_passes_the_settings_check():
    assert UNUSED_DATABASE_URL.startswith("postgresql://")


def test_missing_streamlit_secrets_file_is_not_an_error(monkeypatch):
    """A plain local run has no secrets.toml; reading st.secrets then raises."""
    import streamlit as st

    class NoSecrets:
        def __iter__(self):
            raise FileNotFoundError("no secrets file")

    monkeypatch.setattr(st, "secrets", NoSecrets())
    assert bootstrap._streamlit_secrets() == {}


def test_bootstrap_does_not_import_the_settings_module():
    """Settings read the environment once, on import, so the env must be ready before it."""
    code = (
        "import sys\n"
        "import src.ui.bootstrap\n"
        "loaded = [m for m in sys.modules if m == 'src.core' or m.startswith('src.core.')]\n"
        "sys.exit(1 if loaded else 0)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr
