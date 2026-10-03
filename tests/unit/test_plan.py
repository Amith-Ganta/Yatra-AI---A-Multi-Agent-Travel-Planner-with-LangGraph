"""The plan document is what the frontend renders and what is stored with the thread."""

from src.agents.plan import (
    DRAFT_SUMMARY,
    REJECTED_FALLBACK,
    build_plan,
    plan_message_text,
)

APPROVED_STATE = {
    "allowed": True,
    "reason": "Valid trip",
    "trip_constraints": {
        "destination": "Rome",
        "start_date": "2026-12-01",
        "end_date": "2026-12-04",
        "budget_usd": 2000,
        "party_size": 2,
    },
    "flight_output": {"flights": [], "best_option": None, "source": "mock"},
    "hotel_output": {"hotels": [], "status": "error", "error": "Hotel search is not configured."},
    "weather_output": {"forecast": [], "status": "success", "source": "forecast"},
    "budget_output": {"total": 2000.0, "feasibility": "Within budget"},
    "itinerary_output": {"itinerary": [{"day": 1}]},
    "revision_count": 0,
    "final_response": {"summary": "Trip plan approved.", "approved": True},
}


def test_approved_plan_carries_every_section_and_a_normalised_trip():
    plan = build_plan(APPROVED_STATE)

    assert plan["status"] == "approved"
    assert plan["summary"] == "Trip plan approved."
    assert plan["trip"]["destination"] == "Rome"
    assert plan["trip"]["budget"] == 2000.0
    assert plan["trip"]["party_size"] == 2
    assert plan["flights"]["source"] == "mock"
    assert plan["hotels"]["status"] == "error"
    assert plan["weather"]["source"] == "forecast"
    assert plan["budget"]["total"] == 2000.0
    assert plan["itinerary"]["itinerary"] == [{"day": 1}]
    assert plan["approval"]["approved"] is True


def test_plan_waiting_for_a_decision_is_a_draft():
    state = {**APPROVED_STATE, "final_response": {}, "revision_count": 1}
    plan = build_plan(state, awaiting_approval=True, max_revisions=3)

    assert plan["status"] == "awaiting_approval"
    assert plan["summary"] == DRAFT_SUMMARY
    assert plan["approval"] == {
        "approved": None,
        "revision": 1,
        "max_revisions": 3,
        "feedback_applied": None,
        "revision_note": None,
    }


def test_plan_that_hit_the_revision_cap_is_not_approved():
    state = {
        **APPROVED_STATE,
        "revision_count": 3,
        "final_response": {"summary": "Revision limit reached.", "approved": False},
    }
    plan = build_plan(state, max_revisions=3)

    assert plan["status"] == "revision_limit"
    assert plan["approval"]["approved"] is False
    assert plan["approval"]["revision"] == 3


def test_approval_reports_whether_the_feedback_was_applied():
    state = {
        **APPROVED_STATE,
        "itinerary_output": {
            "itinerary": [{"day": 1}],
            "feedback_applied": False,
            "revision_note": "Could not apply the change.",
        },
    }
    approval = build_plan(state, awaiting_approval=True)["approval"]

    assert approval["feedback_applied"] is False
    assert approval["revision_note"] == "Could not apply the change."


def test_sections_that_never_ran_are_none_not_missing():
    state = {"allowed": True, "trip_constraints": {"destination": "Rome"}}
    plan = build_plan(state, awaiting_approval=True)
    assert plan["status"] == "awaiting_approval"
    for section in ("flights", "hotels", "weather", "budget", "itinerary"):
        assert section in plan and plan[section] is None


def test_rejected_request_keeps_the_reason_and_has_no_sections():
    plan = build_plan({"allowed": False, "reason": "Not a travel request"})
    assert plan["status"] == "rejected"
    assert plan["reason"] == "Not a travel request"
    assert plan["trip"] is None and plan["itinerary"] is None
    assert plan["approval"] is None


def test_missing_allowed_flag_counts_as_rejected():
    plan = build_plan({})
    assert plan["status"] == "rejected"
    assert plan["reason"] == REJECTED_FALLBACK


def test_message_text_describes_the_trip_or_the_rejection():
    assert (
        plan_message_text(build_plan(APPROVED_STATE))
        == "Trip plan for Rome, 2026-12-01 to 2026-12-04."
    )
    assert plan_message_text(build_plan({"allowed": False, "reason": "Nope"})) == "Nope"


def test_message_text_marks_a_draft():
    draft = build_plan(APPROVED_STATE, awaiting_approval=True)
    assert plan_message_text(draft) == "Draft: Trip plan for Rome, 2026-12-01 to 2026-12-04."
