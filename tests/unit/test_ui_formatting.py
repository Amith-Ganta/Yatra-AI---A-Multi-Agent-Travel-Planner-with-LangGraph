"""The Streamlit page helpers: pure functions, so they need no Streamlit."""

from datetime import date, timedelta

import pytest

from src.ui.formatting import (
    EXAMPLE_REQUESTS,
    MAX_FEEDBACK_LENGTH,
    MAX_MESSAGE_LENGTH,
    MAX_TRAVELLERS,
    MIN_BUDGET_USD,
    NODE_LABELS,
    as_dict,
    budget_rows,
    build_plan_message,
    dict_rows,
    escape_markdown,
    flight_rows,
    format_date,
    format_money,
    node_label,
    safe_link,
    text_list,
    validate_feedback,
    validate_trip_form,
    weather_rows,
)

TODAY = date(2026, 10, 4)
LEAVE = TODAY + timedelta(days=30)
BACK = TODAY + timedelta(days=34)


def test_every_graph_node_has_a_plain_label():
    graph_nodes = {
        "supervisor",
        "flight",
        "hotel",
        "weather",
        "budget",
        "itinerary",
        "human_approval",
        "revise",
        "final_response",
    }
    assert graph_nodes <= set(NODE_LABELS)
    assert node_label("flight") == "Searched flights"


def test_unknown_node_gets_a_readable_label():
    assert node_label("visa_check") == "Visa check"


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (1234.5, "$1,234"),
        (1235, "$1,235"),
        (0, "$0"),
        (-80.0, "$-80"),
        (None, "-"),
        ("12", "-"),
        (True, "-"),
        (float("nan"), "-"),
        (float("inf"), "-"),
    ],
)
def test_format_money(value, text):
    assert format_money(value) == text


def test_format_date_reads_iso_dates_and_leaves_other_text_alone():
    assert format_date("2026-10-08") == "8 Oct 2026"
    assert format_date("2026-10-08T09:30:00") == "8 Oct 2026"
    assert format_date("next spring") == "next spring"
    assert format_date(None) == "None"


def test_valid_trip_form_has_no_problem():
    assert validate_trip_form("Lisbon", LEAVE, BACK, 2, 2500.0, TODAY) is None


def test_same_day_return_is_allowed():
    assert validate_trip_form("Lisbon", LEAVE, LEAVE, 1, MIN_BUDGET_USD, TODAY) is None


@pytest.mark.parametrize(
    ("destination", "departure", "returning", "travellers", "budget", "expected"),
    [
        ("   ", LEAVE, BACK, 2, 2500.0, "destination"),
        ("Lisbon", None, BACK, 2, 2500.0, "both travel dates"),
        ("Lisbon", LEAVE, None, 2, 2500.0, "both travel dates"),
        ("Lisbon", TODAY - timedelta(days=1), BACK, 2, 2500.0, "in the past"),
        ("Lisbon", BACK, LEAVE, 2, 2500.0, "before the departure"),
        ("Lisbon", LEAVE, BACK, 0, 2500.0, "Travellers"),
        ("Lisbon", LEAVE, BACK, MAX_TRAVELLERS + 1, 2500.0, "Travellers"),
        ("Lisbon", LEAVE, BACK, 2, MIN_BUDGET_USD - 1, "at least $100"),
        ("Lisbon", LEAVE, BACK, 2, float("nan"), "at least $100"),
    ],
)
def test_trip_form_names_the_first_problem(
    destination, departure, returning, travellers, budget, expected
):
    problem = validate_trip_form(destination, departure, returning, travellers, budget, TODAY)
    assert problem is not None
    assert expected in problem


def test_plan_message_carries_every_field():
    message = build_plan_message(" Lisbon ", LEAVE, BACK, 2, 2500.0, "  food and trams ")
    assert "trip to Lisbon for 2 travellers" in message
    assert LEAVE.isoformat() in message
    assert BACK.isoformat() in message
    assert "total budget of 2500 USD" in message
    assert message.endswith("Preferences: food and trams")


def test_plan_message_without_notes_has_no_preferences_line():
    message = build_plan_message("Rome", LEAVE, BACK, 1, 1800.5)
    assert "1 traveller," in message
    assert "1800.5 USD" in message
    assert "Preferences" not in message


def test_feedback_must_say_something_and_stay_short():
    assert validate_feedback("") is not None
    assert validate_feedback("   \n ") is not None
    assert validate_feedback("More museums, please.") is None
    assert validate_feedback("x" * MAX_FEEDBACK_LENGTH) is None
    assert validate_feedback("x" * (MAX_FEEDBACK_LENGTH + 1)) is not None


def test_dollar_signs_are_escaped_so_prices_do_not_become_maths():
    assert escape_markdown("$1,200 to $300") == "\\$1,200 to \\$300"
    assert escape_markdown(42) == "42"


@pytest.mark.parametrize(
    ("value", "items"),
    [
        ("  one  ", ["one"]),
        ("   ", []),
        (["a", " b ", "", None, 3], ["a", "b", "None", "3"]),
        (None, []),
        ({"a": 1}, []),
    ],
)
def test_text_list_copes_with_whatever_an_agent_returned(value, items):
    assert text_list(value) == items


@pytest.mark.parametrize(
    ("url", "link"),
    [
        ("https://example.com/hotel", "https://example.com/hotel"),
        ("  HTTP://example.com  ", "HTTP://example.com"),
        ("javascript:alert(1)", None),
        ("ftp://example.com", None),
        ("https://exa mple.com", None),
        ("", None),
        (None, None),
    ],
)
def test_only_plain_web_links_are_clickable(url, link):
    assert safe_link(url) == link


def test_as_dict_and_dict_rows_ignore_the_wrong_shapes():
    assert as_dict({"a": 1}) == {"a": 1}
    assert as_dict(None) == {}
    assert as_dict([1]) == {}
    assert dict_rows([{"a": 1}, "x", None, {"b": 2}]) == [{"a": 1}, {"b": 2}]
    assert dict_rows("not a list") == []


def test_flight_rows_fill_gaps_with_dashes():
    rows = flight_rows([{"airline": "TestAir", "price": 300.0, "duration": "2h"}, {}])
    assert rows[0] == {
        "Airline": "TestAir",
        "Departs": "-",
        "Arrives": "-",
        "Duration": "2h",
        "Price per person": "$300",
    }
    assert rows[1]["Airline"] == "-"
    assert rows[1]["Price per person"] == "-"
    assert flight_rows(None) == []


def test_weather_rows_format_each_day():
    rows = weather_rows(
        [
            {
                "date": "2026-10-08",
                "condition": "Clear sky",
                "temp_max": 22.4,
                "temp_min": 14,
                "precipitation_mm": 0.5,
            },
            {"date": "2026-10-09"},
        ]
    )
    assert rows[0] == {
        "Date": "8 Oct 2026",
        "Condition": "Clear sky",
        "High": "22\N{DEGREE SIGN}C",
        "Low": "14\N{DEGREE SIGN}C",
        "Rain": "0.5 mm",
    }
    assert rows[1]["High"] == "-"
    assert rows[1]["Rain"] == "-"


def test_budget_rows_put_the_biggest_cost_first_and_skip_non_numbers():
    rows = budget_rows(
        {"food": 300, "flights": 900.0, "local_transport": 80, "note": "n/a", "flag": True}
    )
    assert [row["Category"] for row in rows] == ["Flights", "Food", "Local Transport"]
    assert rows[0]["Amount"] == 900.0
    assert budget_rows(None) == []
    assert budget_rows([("flights", 1)]) == []


def test_example_requests_fit_the_message_limit():
    assert len(EXAMPLE_REQUESTS) == 3
    for label, text in EXAMPLE_REQUESTS:
        assert label
        assert 0 < len(text) <= MAX_MESSAGE_LENGTH
