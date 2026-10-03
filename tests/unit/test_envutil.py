"""Tests for API-key cleaning: a key pasted with a trailing newline must not reach a header."""

import os

import pytest

from src.core.config import LLMConfig, Settings
from src.envutil import API_KEY_VARS, strip_api_keys


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in API_KEY_VARS:
        monkeypatch.delenv(name, raising=False)


def test_trailing_newline_is_stripped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key\n")
    assert strip_api_keys() == ["OPENAI_API_KEY"]
    assert os.environ["OPENAI_API_KEY"] == "sk-test-key"


def test_every_kind_of_surrounding_whitespace_is_stripped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "  sk-a\r\n")
    monkeypatch.setenv("TAVILY_API_KEY", "\tkey-b ")
    assert sorted(strip_api_keys()) == ["DEEPSEEK_API_KEY", "TAVILY_API_KEY"]
    assert os.environ["DEEPSEEK_API_KEY"] == "sk-a"
    assert os.environ["TAVILY_API_KEY"] == "key-b"


def test_a_clean_key_is_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-clean")
    assert strip_api_keys() == []
    assert os.environ["OPENAI_API_KEY"] == "sk-clean"


def test_a_blank_key_is_removed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", " \n")
    assert strip_api_keys() == ["OPENAI_API_KEY"]
    assert "OPENAI_API_KEY" not in os.environ


def test_missing_variables_are_ignored() -> None:
    assert strip_api_keys() == []


def test_only_names_are_returned_never_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value\n")
    changed = strip_api_keys()
    assert all(name in API_KEY_VARS for name in changed)
    assert "sk-secret-value" not in " ".join(changed)


def test_custom_names_are_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOME_OTHER_KEY", "abc\n")
    assert strip_api_keys(("SOME_OTHER_KEY",)) == ["SOME_OTHER_KEY"]
    assert os.environ["SOME_OTHER_KEY"] == "abc"
    monkeypatch.delenv("SOME_OTHER_KEY")


# --- the settings layer cleans keys too, so a value that never went through main.py is safe ---


def test_config_strips_a_pasted_openai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-test\n")
    assert LLMConfig().openai_api_key == "sk-proj-test"


def test_config_strips_a_pasted_deepseek_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", " sk-ds-test\r\n")
    assert LLMConfig().deepseek_api_key == "sk-ds-test"


def test_config_treats_a_blank_key_as_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "  ")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "\n")
    config = LLMConfig()
    assert config.openai_api_key is None
    assert config.deepseek_api_key is None


def test_settings_root_uses_the_cleaned_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/yatra")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-test\n")
    assert Settings().llm.openai_api_key == "sk-proj-test"
