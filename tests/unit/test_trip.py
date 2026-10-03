"""Tests for trip constraint normalization (F2)."""

from datetime import date

import pytest

from src.agents.trip import (
    DEFAULT_BUDGET_USD,
    DEFAULT_PARTY_SIZE,
    DEFAULT_TRIP_DAYS,
    normalize_trip_constraints,
)

TODAY = date(2026, 10, 1)


def test_supervisor_field_names_are_mapped():
    trip = normalize_trip_constraints(
        {
            "destination": "Rome",
            "start_date": "2026-12-01",
            "end_date": "2026-12-05",
            "budget_usd": 2500,
            "party_size": 3,
            "trip_type": "business",
        },
        today=TODAY,
    )
    assert trip.destination == "Rome"
    assert (trip.start_date, trip.end_date) == ("2026-12-01", "2026-12-05")
    assert trip.days == 5
    assert trip.budget == 2500.0
    assert trip.party_size == 3
    assert trip.trip_type == "business"


def test_legacy_field_names_still_work():
    trip = normalize_trip_constraints(
        {"departure_date": "2026-11-01", "return_date": "2026-11-03", "budget": 900},
        today=TODAY,
    )
    assert (trip.start_date, trip.end_date, trip.budget) == ("2026-11-01", "2026-11-03", 900.0)


def test_all_null_values_use_defaults():
    trip = normalize_trip_constraints(
        {
            "destination": None,
            "start_date": None,
            "end_date": None,
            "budget_usd": None,
            "party_size": None,
            "trip_type": None,
        },
        today=TODAY,
    )
    assert trip.destination is None
    assert trip.budget == DEFAULT_BUDGET_USD
    assert trip.party_size == DEFAULT_PARTY_SIZE
    assert trip.trip_type == "leisure"
    assert trip.days == DEFAULT_TRIP_DAYS + 1
    assert date.fromisoformat(trip.start_date) > TODAY


@pytest.mark.parametrize("raw", [None, {}])
def test_empty_input_does_not_crash(raw):
    assert normalize_trip_constraints(raw, today=TODAY).budget == DEFAULT_BUDGET_USD


@pytest.mark.parametrize(
    "value, expected",
    [
        ("$2,000", 2000.0),
        ("1500", 1500.0),
        (750.5, 750.5),
        (0, DEFAULT_BUDGET_USD),
        (-5, DEFAULT_BUDGET_USD),
        (True, DEFAULT_BUDGET_USD),
        ("lots", DEFAULT_BUDGET_USD),
    ],
)
def test_budget_parsing(value, expected):
    assert normalize_trip_constraints({"budget_usd": value}, today=TODAY).budget == expected


def test_past_dates_are_moved_to_the_future_keeping_trip_length():
    trip = normalize_trip_constraints(
        {"start_date": "2020-01-01", "end_date": "2020-01-04"}, today=TODAY
    )
    assert date.fromisoformat(trip.start_date) > TODAY
    assert trip.days == 4


def test_end_before_start_is_repaired():
    trip = normalize_trip_constraints(
        {"start_date": "2026-12-10", "end_date": "2026-12-01"}, today=TODAY
    )
    assert trip.end_date > trip.start_date


def test_invalid_date_strings_fall_back():
    trip = normalize_trip_constraints(
        {"start_date": "next friday", "end_date": "soon"}, today=TODAY
    )
    date.fromisoformat(trip.start_date)  # does not raise


def test_party_size_is_an_int_of_at_least_one():
    assert normalize_trip_constraints({"party_size": "4"}, today=TODAY).party_size == 4
    assert normalize_trip_constraints({"party_size": 0}, today=TODAY).party_size == 1
