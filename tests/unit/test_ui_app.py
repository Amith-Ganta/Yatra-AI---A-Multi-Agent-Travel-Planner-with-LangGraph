"""The Streamlit page, driven with Streamlit's own ``AppTest`` and a fake planner runtime.

The page code is production code. Only the runtime behind it is faked, so a click goes through the
same ``Session`` bookkeeping as in the browser and the test can read what was sent to the graph.
"""

import threading
from concurrent.futures import Future
from typing import Any, Optional

import pytest
from langgraph.types import Command
from streamlit.testing.v1 import AppTest

import src.ui.app as app_module
from src.ui.app import Session
from src.ui.runtime import PLANNING_FAILED, PlanningError, TurnHandle, TurnResult

TIMEOUT = 30
THREAD = "t-1"

TRIP = {
    "destination": "Rome",
    "start_date": "2099-05-10",
    "end_date": "2099-05-13",
    "days": 4,
    "party_size": 2,
    "budget": 2000,
}


def _plan(status: str = "awaiting_approval", **overrides: Any) -> dict[str, Any]:
    plan: dict[str, Any] = {
        "status": status,
        "reason": "",
        "summary": "A draft for Rome.",
        "trip": TRIP,
        "flights": {"flights": [{"airline": "TestAir", "price": 300.0}]},
        "hotels": {"hotels": [{"name": "Hotel Test", "url": "https://example.com"}]},
        "weather": {"forecast": [{"date": "2099-05-10", "temp_max": 22, "temp_min": 14}]},
        "budget": {"total": 1800, "feasibility": True, "categories": {"flights": 600}},
        "itinerary": {"itinerary": [{"day": 1, "activities": ["Colosseum"]}]},
        "approval": {
            "approved": None,
            "revision": 0,
            "max_revisions": 3,
            "feedback_applied": False,
            "revision_note": "",
        },
    }
    plan.update(overrides)
    return plan


def _approval_request(revision: int = 0) -> dict[str, Any]:
    return {
        "kind": "plan_approval",
        "revision": revision,
        "max_revisions": 3,
        "question": "Approve this plan?",
    }


def _waiting(revision: int = 0) -> Session:
    """A session that is looking at a draft and has to decide."""
    plan = _plan()
    plan["approval"]["revision"] = revision
    return Session(thread_id=THREAD, plan=plan, approval_request=_approval_request(revision))


class FakeRuntime:
    """Stands in for ``PlannerRuntime``: records each turn and ends it at once."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, str]] = []
        self.outcome: Any = TurnResult(plan=_plan(), approval_request=_approval_request())
        self.nodes: list[str] = ["supervisor", "flight"]

    def tool_status(self) -> dict[str, str]:
        return {"mode": "in-process"}

    def start_turn(self, graph_input: Any, thread_id: str) -> TurnHandle:
        self.calls.append((graph_input, thread_id))
        future: Future[TurnResult] = Future()
        if isinstance(self.outcome, Exception):
            future.set_exception(self.outcome)
        else:
            future.set_result(self.outcome)
        return TurnHandle(future=future, nodes=list(self.nodes))


@pytest.fixture
def runtime(monkeypatch: pytest.MonkeyPatch) -> FakeRuntime:
    fake = FakeRuntime()
    monkeypatch.setattr(app_module, "get_runtime", lambda: fake)
    monkeypatch.setattr(app_module, "missing_llm_key", lambda: None)
    return fake


def _page() -> None:
    from src.ui.app import main

    main()


def _open(session: Optional[Session] = None) -> AppTest:
    page = AppTest.from_function(_page, default_timeout=TIMEOUT)
    if session is not None:
        page.session_state["session"] = session
    return page.run()


def _button(page: AppTest, label: str):
    found = [button for button in page.button if button.label == label]
    assert len(found) == 1, f"expected one {label!r} button, found {len(found)}"
    return found[0]


def _trip_submit(page: AppTest):
    return page.button(key="FormSubmitter:trip_form-Plan my trip")


def _free_text_submit(page: AppTest):
    return page.button(key="FormSubmitter:free_text_form-Plan my trip")


def _texts(elements: Any) -> list[str]:
    return [element.value for element in elements]


def _the_session(page: AppTest) -> Session:
    session = page.session_state["session"]
    assert isinstance(session, Session)
    return session


# --- the start page -------------------------------------------------------------------------


def test_the_start_page_offers_both_forms_and_no_plan(runtime):
    page = _open()

    assert not page.exception
    assert page.title[0].value == "Yatra AI travel planner"
    assert len(page.main.get("form")) == 2
    assert _trip_submit(page) is not None
    assert _free_text_submit(page) is not None
    examples = [button for button in page.button if (button.key or "").startswith("example-")]
    assert [button.label for button in examples] == [
        "Four days in Lisbon",
        "A week in Tokyo",
        "Off-topic request",
    ]
    assert runtime.calls == []


def test_the_sidebar_names_the_models_and_the_tool_mode(runtime):
    page = _open()

    captions = _texts(page.sidebar.caption)
    assert "mode: in-process" in captions
    assert any("deepseek" in line for line in captions)
    assert any("Plans live in memory only" in line for line in captions)


def test_a_missing_key_stops_the_page_before_anything_starts(runtime, monkeypatch):
    monkeypatch.setattr(app_module, "missing_llm_key", lambda: "The main model needs a KEY.")
    page = _open()

    assert not page.exception
    assert _texts(page.error) == ["The main model needs a KEY."]
    assert page.main.get("form") == []
    assert len(page.button) == 0
    assert runtime.calls == []


def test_an_empty_trip_form_names_the_first_problem(runtime):
    page = _open()
    _trip_submit(page).click().run()

    assert _texts(page.error) == ["Enter a destination."]
    assert runtime.calls == []


def test_an_empty_description_asks_for_one(runtime):
    page = _open()
    _free_text_submit(page).click().run()

    assert _texts(page.error) == ["Describe the trip first."]
    assert runtime.calls == []


def test_a_filled_trip_form_starts_a_run_with_the_trip_in_words(runtime):
    page = _open()
    destination = [box for box in page.text_input if box.label == "Destination"][0]
    destination.input(" Lisbon ")
    _trip_submit(page).click().run()

    assert not page.exception
    assert len(runtime.calls) == 1
    state, thread_id = runtime.calls[0]
    assert "trip to Lisbon for 2 travellers" in state["message"]
    assert state["thread_id"] == thread_id
    assert state["user_id"].startswith("streamlit-")
    assert state["revision_count"] == 0

    session = _the_session(page)
    assert session.thread_id == thread_id
    assert session.turn is None  # the fake run ended at once and was taken in
    assert session.plan is not None
    assert session.steps == ["supervisor", "flight"]


def test_an_example_button_fills_the_description_box(runtime):
    page = _open()
    page.button(key="example-A week in Tokyo").click().run()

    assert "week in Tokyo" in page.text_area(key="free_text").value
    assert runtime.calls == []


def test_a_described_trip_is_sent_trimmed(runtime):
    page = _open()
    page.text_area(key="free_text").input("  Three days in Oslo  ")
    _free_text_submit(page).click().run()

    assert [call[0]["message"] for call in runtime.calls] == ["Three days in Oslo"]


def test_a_failed_run_shows_a_safe_message_and_the_forms_again(runtime):
    runtime.outcome = PlanningError(PLANNING_FAILED)
    page = _open()
    page.text_area(key="free_text").input("A week in Tokyo")
    _free_text_submit(page).click().run()

    assert not page.exception
    assert PLANNING_FAILED in _texts(page.error)
    assert len(page.main.get("form")) == 2
    assert _the_session(page).plan is None


def test_an_unexpected_failure_never_shows_its_message(runtime):
    runtime.outcome = RuntimeError("provider exploded with secret detail")
    page = _open()
    page.text_area(key="free_text").input("A week in Tokyo")
    _free_text_submit(page).click().run()

    assert PLANNING_FAILED in _texts(page.error)
    assert "secret detail" not in "".join(_texts(page.error))


def test_a_run_in_flight_is_watched_until_it_ends(runtime):
    """The page blocks on the run, lists each agent as it finishes, then shows the result."""
    future: Future[TurnResult] = Future()
    turn = TurnHandle(future=future, nodes=["supervisor", "flight", "itinerary"])
    session = Session(thread_id=THREAD, turn=turn)
    timer = threading.Timer(
        0.5, future.set_result, args=(TurnResult(_plan(), _approval_request()),)
    )
    timer.start()
    try:
        page = _open(session)
    finally:
        timer.cancel()

    assert not page.exception
    assert session.turn is None
    assert session.plan is not None
    assert session.steps == ["supervisor", "flight", "itinerary"]
    assert [button.label for button in page.button if button.label == "Approve plan"]


# --- the decision ---------------------------------------------------------------------------


def test_a_draft_shows_the_plan_and_both_decision_buttons(runtime):
    page = _open(_waiting())

    assert not page.exception
    assert _texts(page.info) == ["A draft for Rome."]
    assert _button(page, "Approve plan") is not None
    assert _button(page, "Request changes") is not None
    assert "Revisions used: 0 of 3" in _texts(page.caption)
    assert page.main.get("form") == []


def test_the_decision_controls_are_not_in_a_form(runtime):
    """Ctrl+Enter in a form's text area presses its first submit button, which would approve."""
    page = _open(_waiting())

    assert page.main.get("form") == []
    assert page.text_area(key=f"feedback-{THREAD}-0") is not None


def test_requesting_changes_without_a_reason_is_refused(runtime):
    page = _open(_waiting())
    _button(page, "Request changes").click().run()

    assert _texts(page.error) == ["Say what should change before you request changes."]
    assert runtime.calls == []


def test_requesting_changes_with_only_spaces_is_refused(runtime):
    page = _open(_waiting())
    page.text_area(key=f"feedback-{THREAD}-0").input("   \n  ")
    _button(page, "Request changes").click().run()

    assert len(_texts(page.error)) == 1
    assert runtime.calls == []


def test_requesting_changes_sends_the_trimmed_feedback_to_the_same_thread(runtime):
    page = _open(_waiting())
    page.text_area(key=f"feedback-{THREAD}-0").input("  More museums, fewer taxis  ")
    _button(page, "Request changes").click().run()

    assert len(runtime.calls) == 1
    command, thread_id = runtime.calls[0]
    assert isinstance(command, Command)
    assert command.resume == {"approved": False, "feedback": "More museums, fewer taxis"}
    assert thread_id == THREAD


def test_approving_sends_an_approval_without_feedback(runtime):
    runtime.outcome = TurnResult(
        _plan("approved", approval={"approved": True, "revision": 0, "max_revisions": 3}), None
    )
    page = _open(_waiting())
    page.text_area(key=f"feedback-{THREAD}-0").input("typed but not meant as a reason")
    _button(page, "Approve plan").click().run()

    command, thread_id = runtime.calls[0]
    assert isinstance(command, Command)
    assert command.resume == {"approved": True, "feedback": ""}
    assert thread_id == THREAD
    assert _the_session(page).plan is not None
    assert _the_session(page).plan["status"] == "approved"


def test_the_next_draft_gets_a_fresh_feedback_box(runtime):
    runtime.outcome = TurnResult(_plan(), _approval_request(revision=1))
    page = _open(_waiting())
    page.text_area(key=f"feedback-{THREAD}-0").input("More museums")
    _button(page, "Request changes").click().run()

    assert page.text_area(key=f"feedback-{THREAD}-1").value == ""
    assert "Revisions used: 1 of 3" in _texts(page.caption)


# --- what each plan status looks like -------------------------------------------------------


def test_a_revised_draft_says_so_in_words(runtime):
    session = _waiting(revision=1)
    assert session.plan is not None
    session.plan["approval"].update(feedback_applied=True, revision_note="Added a museum.")
    page = _open(session)

    captions = _texts(page.caption)
    assert "Revision 1 of 3 | Your feedback was applied | Added a museum." in captions
    assert not any("True" in line for line in captions)


def test_a_revision_that_changed_nothing_does_not_claim_it_did(runtime):
    session = _waiting(revision=1)
    assert session.plan is not None
    session.plan["approval"].update(feedback_applied=False, revision_note="Kept the old draft.")
    page = _open(session)

    captions = _texts(page.caption)
    assert "Revision 1 of 3 | Kept the old draft." in captions
    assert not any("was applied" in line for line in captions)


def test_dollar_amounts_in_the_summary_are_not_read_as_maths(runtime):
    session = _waiting()
    assert session.plan is not None
    session.plan["summary"] = "About $1,200 for flights and $300 for food."
    page = _open(session)

    assert _texts(page.info) == ["About \\$1,200 for flights and \\$300 for food."]


def test_an_approved_plan_offers_a_new_trip_and_no_decision(runtime):
    session = Session(thread_id=THREAD, plan=_plan("approved", summary="Your Rome plan."))
    page = _open(session)

    assert _texts(page.success) == ["Your Rome plan."]
    assert _button(page, "Plan another trip") is not None
    assert not [b for b in page.button if b.label in ("Approve plan", "Request changes")]


def test_the_revision_limit_is_explained_and_ends_the_loop(runtime):
    approval = {"approved": False, "revision": 3, "max_revisions": 3}
    page = _open(Session(thread_id=THREAD, plan=_plan("revision_limit", approval=approval)))

    assert any("revision limit (3)" in line for line in _texts(page.warning))
    assert _button(page, "Plan another trip") is not None
    assert not [b for b in page.button if b.label == "Approve plan"]


def test_a_refused_request_shows_the_reason_and_no_tabs(runtime):
    plan = {"status": "rejected", "reason": "That is not a trip request."}
    page = _open(Session(thread_id=THREAD, plan=plan))

    assert _texts(page.warning) == ["That is not a trip request."]
    assert len(page.tabs) == 0
    assert _button(page, "Plan another trip") is not None


def test_planning_another_trip_returns_to_the_forms(runtime):
    page = _open(Session(thread_id=THREAD, plan=_plan("approved")))
    _button(page, "Plan another trip").click().run()

    assert len(page.main.get("form")) == 2
    session = _the_session(page)
    assert session.plan is None
    assert session.thread_id == ""


def test_the_new_trip_button_drops_a_draft_that_is_waiting(runtime):
    page = _open(_waiting())
    _button(page, "New trip").click().run()

    assert len(page.main.get("form")) == 2
    assert _the_session(page).approval_request is None


def test_a_plan_with_missing_sections_still_renders(runtime):
    sparse = {"status": "awaiting_approval", "summary": "", "trip": None, "approval": None}
    page = _open(Session(thread_id=THREAD, plan=sparse, approval_request=_approval_request()))

    assert not page.exception
    assert _button(page, "Approve plan") is not None
