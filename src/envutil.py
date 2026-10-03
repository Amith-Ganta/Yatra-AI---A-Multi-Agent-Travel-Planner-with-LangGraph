"""Clean API keys that were pasted with stray whitespace.

A key copied into a GitHub secret or a Render dashboard often carries a trailing newline. The
HTTP stack then refuses to send it (`Illegal header value`), and the failure looks like a bad
key. Stripping the value once, at start-up, removes the whole class of problem.

This module must not import `src.core`: that package builds `settings` on import, and the
environment has to be clean before that happens.
"""

import os

API_KEY_VARS = ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "TAVILY_API_KEY")


def strip_api_keys(names: tuple[str, ...] = API_KEY_VARS) -> list[str]:
    """Strip surrounding whitespace from the named variables in `os.environ`.

    A variable that is blank after stripping is removed, so "not set" and "set to nothing" mean
    the same thing. Returns the names that were changed (never the values).
    """
    changed: list[str] = []
    for name in names:
        value = os.environ.get(name)
        if value is None:
            continue
        cleaned = value.strip()
        if cleaned == value:
            continue
        if cleaned:
            os.environ[name] = cleaned
        else:
            del os.environ[name]
        changed.append(name)
    return changed
