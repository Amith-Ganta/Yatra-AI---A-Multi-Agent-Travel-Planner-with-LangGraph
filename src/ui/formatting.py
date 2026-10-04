"""Text and table helpers for the Streamlit pages, kept free of Streamlit so they can be tested.

The wording and the checks mirror the Next.js frontend (``frontend/src/lib/format.ts``), so both
front ends send the API the same kind of request.
"""

import math
from datetime import date
from typing import Any, Optional, cast

MAX_TRAVELLERS = 10
MIN_BUDGET_USD = 100
MAX_NOTES_LENGTH = 500
MAX_FEEDBACK_LENGTH = 1000

NODE_LABELS = {
    "supervisor": "Understood your request",
    "flight": "Searched flights",
    "hotel": "Found hotels",
    "weather": "Checked the weather",
    "budget": "Worked out the budget",
    "itinerary": "Drafted the itinerary",
    "human_approval": "Recorded your decision",
    "revise": "Applied your changes",
    "final_response": "Put the plan together",
}

MAX_MESSAGE_LENGTH = 1500

# (button label, request text); the last one is meant to be refused by the supervisor guardrail
EXAMPLE_REQUESTS = (
    (
        "Four days in Lisbon",
        "Plan a 4 day trip to Lisbon for 2 travellers, leaving in 6 weeks, with a total budget "
        "of 2500 USD. We like food and old neighbourhoods.",
    ),
    (
        "A week in Tokyo",
        "I want a week in Tokyo in the spring for one person with about 3000 USD, mostly "
        "museums and quiet places.",
    ),
    ("Off-topic request", "Write me a Python script that sorts a list."),
)


def node_label(node: str) -> str:
    """What a finished graph node did, in plain words."""
    return NODE_LABELS.get(node, node.replace("_", " ").capitalize())


def format_money(value: Any) -> str:
    """``1234.56`` -> ``$1,235``; anything that is not a finite number -> ``-``."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return "-"
    return f"${value:,.0f}"


def format_date(value: Any) -> str:
    """``2026-10-08`` -> ``8 Oct 2026``; anything that is not an ISO date is returned as text."""
    text = str(value)
    try:
        parsed = date.fromisoformat(text[:10])
    except ValueError:
        return text
    return f"{parsed.day} {parsed:%b %Y}"


def validate_trip_form(
    destination: str,
    departure: Optional[date],
    returning: Optional[date],
    travellers: int,
    budget: float,
    today: date,
) -> Optional[str]:
    """The first problem with the trip form, or None when it is valid."""
    if not destination.strip():
        return "Enter a destination."
    if departure is None or returning is None:
        return "Choose both travel dates."
    if departure < today:
        return "The departure date is in the past."
    if returning < departure:
        return "The return date cannot be before the departure date."
    if travellers < 1 or travellers > MAX_TRAVELLERS:
        return f"Travellers must be a whole number from 1 to {MAX_TRAVELLERS}."
    if not math.isfinite(budget) or budget < MIN_BUDGET_USD:
        return f"The budget must be at least {format_money(MIN_BUDGET_USD)}."
    return None


def build_plan_message(
    destination: str,
    departure: date,
    returning: date,
    travellers: int,
    budget: float,
    notes: str = "",
) -> str:
    """The form written out as one clear request; the supervisor reads free text."""
    people = "1 traveller" if travellers == 1 else f"{travellers} travellers"
    text = (
        f"Plan a trip to {destination.strip()} for {people}, leaving on {departure.isoformat()} "
        f"and returning on {returning.isoformat()}, with a total budget of {budget:g} USD."
    )
    extra = notes.strip()
    return f"{text}\nPreferences: {extra}" if extra else text


def validate_feedback(feedback: str) -> Optional[str]:
    """Asking for changes needs a reason the itinerary can act on."""
    text = feedback.strip()
    if not text:
        return "Say what should change before you request changes."
    if len(text) > MAX_FEEDBACK_LENGTH:
        return f"Keep the feedback under {MAX_FEEDBACK_LENGTH} characters."
    return None


def escape_markdown(text: Any) -> str:
    """Stop Streamlit reading a pair of dollar signs ($1,200 ... $300) as a maths formula."""
    return str(text).replace("$", "\\$")


def text_list(value: Any) -> list[str]:
    """A list of non-empty strings, whatever the agent returned (a string, a list or nothing)."""
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    items = [str(item).strip() for item in value]  # pyright: ignore
    return [item for item in items if item]


def safe_link(url: Any) -> Optional[str]:
    """The URL when it is plain http(s); hotel links come from web search results."""
    text = str(url or "").strip()
    return text if text.lower().startswith(("http://", "https://")) and " " not in text else None


def as_dict(value: Any) -> dict[str, Any]:
    """The value when it is a dict, else an empty one; a section the agents skipped is None."""
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def dict_rows(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    return [dict(item) for item in items if isinstance(item, dict)]  # pyright: ignore


def flight_rows(flights: Any) -> list[dict[str, Any]]:
    """One table row per flight offer."""
    return [
        {
            "Airline": row.get("airline", "-"),
            "Departs": row.get("departure", "-"),
            "Arrives": row.get("arrival", "-"),
            "Duration": row.get("duration", "-"),
            "Price per person": format_money(row.get("price")),
        }
        for row in dict_rows(flights)
    ]


def weather_rows(forecast: Any) -> list[dict[str, Any]]:
    """One table row per forecast day."""
    return [
        {
            "Date": format_date(row.get("date", "-")),
            "Condition": row.get("condition", "-"),
            "High": _degrees(row.get("temp_max")),
            "Low": _degrees(row.get("temp_min")),
            "Rain": _millimetres(row.get("precipitation_mm")),
        }
        for row in dict_rows(forecast)
    ]


def budget_rows(categories: Any) -> list[dict[str, Any]]:
    """One table row per budget category, largest first."""
    if not isinstance(categories, dict):
        return []
    pairs: list[tuple[str, float]] = [
        (str(name), float(amount))  # pyright: ignore
        for name, amount in categories.items()  # pyright: ignore
        if isinstance(amount, (int, float)) and not isinstance(amount, bool)
    ]
    pairs.sort(key=lambda pair: pair[1], reverse=True)
    return [
        {"Category": name.replace("_", " ").title(), "Amount": amount} for name, amount in pairs
    ]


def _degrees(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "-"
    return f"{value:.0f}\N{DEGREE SIGN}C"


def _millimetres(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "-"
    return f"{value:g} mm"
