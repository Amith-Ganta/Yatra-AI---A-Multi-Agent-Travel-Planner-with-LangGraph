"""Small helper for parsing the JSON an LLM returns."""

import json
from typing import Any


def parse_llm_json(content: Any) -> dict[str, Any]:
    """Parse a JSON object from an LLM reply, tolerating a markdown code fence.

    Raises ValueError (or json.JSONDecodeError, a subclass) when the reply is not a JSON object.
    """
    text = content if isinstance(content, str) else str(content)
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("LLM reply is not a JSON object")
    return dict(data)  # pyright: ignore[reportUnknownArgumentType]
