"""Shared helpers for the LLM judges."""

import json
from typing import Any, cast

from langchain_core.messages import BaseMessage


def _message_text(message: BaseMessage) -> str:
    """Plain text of a chat message (content is a str or a list of content blocks)."""
    content = message.content
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        else:
            parts.append(str(block.get("text", "")))
    return "".join(parts)


def parse_judge_json(message: BaseMessage) -> dict[str, Any]:
    """Parse the JSON object a judge model returned.

    Models often wrap JSON in a markdown fence even when told not to, so the fence is
    stripped first. Raises ValueError if the reply is not a JSON object.
    """
    text = _message_text(message).strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.removesuffix("```").strip()

    parsed: Any = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Judge reply is not a JSON object")
    return cast(dict[str, Any], parsed)
