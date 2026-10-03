"""Normalize supervisor-extracted trip constraints into the shape the workers consume.

The supervisor LLM emits start_date / end_date / budget_usd (and any of them may be null).
Workers need concrete values, so every agent reads constraints through this module instead
of poking at the raw dict.
"""

import re
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any, Optional

DEFAULT_BUDGET_USD = 1000.0
DEFAULT_PARTY_SIZE = 1
DEFAULT_TRIP_DAYS = 7
DEFAULT_LEAD_DAYS = 30


@dataclass(frozen=True)
class TripParams:
    """Concrete, validated trip parameters."""

    destination: Optional[str]
    start_date: str  # YYYY-MM-DD
    end_date: str  # YYYY-MM-DD
    days: int
    budget: float
    party_size: int
    trip_type: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_date(value: Any) -> Optional[date]:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def _parse_positive_number(value: Any) -> Optional[float]:
    """Accept 2000, 2000.0, "2000", "$2,000"; reject null, bool, zero and negatives."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        cleaned = re.sub(r"[^0-9.]", "", value)
        if not cleaned:
            return None
        try:
            number = float(cleaned)
        except ValueError:
            return None
    else:
        return None
    return number if number > 0 else None


def _first(raw: dict[str, Any], *keys: str) -> Any:
    """First non-null value among the given keys (supports legacy key names)."""
    for key in keys:
        if raw.get(key) is not None:
            return raw[key]
    return None


def normalize_trip_constraints(
    raw: Optional[dict[str, Any]], today: Optional[date] = None
) -> TripParams:
    """Turn raw supervisor constraints into validated TripParams.

    Missing or invalid values fall back to documented defaults: start in 30 days, a 7 day
    trip, a 1000 USD budget, one traveller.
    """
    raw = raw or {}
    today = today or date.today()

    start = _parse_date(_first(raw, "start_date", "departure_date"))
    end = _parse_date(_first(raw, "end_date", "return_date"))

    if start is None:
        start = (end - timedelta(days=DEFAULT_TRIP_DAYS)) if end else None
    if start is None or start < today:
        # Never plan in the past; keep the trip length if both dates were given.
        length = (end - start).days if (end and start and end > start) else DEFAULT_TRIP_DAYS
        start = today + timedelta(days=DEFAULT_LEAD_DAYS)
        end = start + timedelta(days=length)
    if end is None or end < start:
        end = start + timedelta(days=DEFAULT_TRIP_DAYS)

    budget = _parse_positive_number(_first(raw, "budget_usd", "budget"))
    party = _parse_positive_number(raw.get("party_size"))

    raw_destination: Any = raw.get("destination")
    destination = raw_destination.strip() if isinstance(raw_destination, str) else None

    raw_trip_type: Any = raw.get("trip_type")
    trip_type = raw_trip_type if isinstance(raw_trip_type, str) and raw_trip_type else "leisure"

    return TripParams(
        destination=destination or None,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        days=(end - start).days + 1,
        budget=budget if budget is not None else DEFAULT_BUDGET_USD,
        party_size=int(party) if party is not None else DEFAULT_PARTY_SIZE,
        trip_type=trip_type,
    )
