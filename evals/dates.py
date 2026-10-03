"""Trip dates that stay realistic.

The supervisor refuses a request whose dates are far in the past or the future (it knows today's
date), so goldens cannot hold fixed dates: a date that is fine today is stale next year, and one
set in 2099 is refused at once. A golden writes `{d+60}` instead, meaning "60 days from today",
and the placeholder is resolved when the goldens are loaded.

`EVAL_TODAY=YYYY-MM-DD` pins "today", so two runs on different days can be compared like for like.
"""

import os
import re
from datetime import date, timedelta

_PLACEHOLDER = re.compile(r"\{d\+(\d+)\}")


def today() -> date:
    pinned = os.getenv("EVAL_TODAY", "").strip()
    return date.fromisoformat(pinned) if pinned else date.today()


def day(offset: int) -> str:
    """The ISO date `offset` days from today."""
    return (today() + timedelta(days=offset)).isoformat()


def resolve_dates(text: str) -> str:
    """Replace every `{d+N}` in `text` with the ISO date N days from today."""
    return _PLACEHOLDER.sub(lambda m: day(int(m.group(1))), text)
