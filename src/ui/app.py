"""The Streamlit page: ask for a trip, watch the agents work, then approve or ask for changes.

``streamlit_app.py`` prepares the environment and calls ``main``. Each browser session keeps its
own thread id, so people sharing one running app never see each other's plans.
"""

import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Optional
from uuid import uuid4

import streamlit as st
from langgraph.types import Command

from src.agents.state import new_request_state
from src.core.config import settings
from src.ui.formatting import (
    EXAMPLE_REQUESTS,
    MAX_FEEDBACK_LENGTH,
    MAX_MESSAGE_LENGTH,
    MAX_NOTES_LENGTH,
    MAX_TRAVELLERS,
    MIN_BUDGET_USD,
    build_plan_message,
    escape_markdown,
    node_label,
    validate_feedback,
    validate_trip_form,
)
from src.ui.runtime import (
    PLANNING_FAILED,
    PlannerRuntime,
    PlanningError,
    TurnHandle,
    missing_llm_key,
)
from src.ui.views import render_plan

POLL_SECONDS = 0.4
FINAL_STATUSES = ("approved", "revision_limit", "rejected")


@dataclass
class Session:
    """One browser session's place in the plan, approve and revise loop."""

    user_id: str = field(default_factory=lambda: f"streamlit-{uuid4().hex[:8]}")
    thread_id: str = ""
    turn: Optional[TurnHandle] = None
    resuming: bool = False  # the run in flight applies a decision rather than a new request
    plan: Optional[dict[str, Any]] = None
    approval_request: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    steps: list[str] = field(default_factory=lambda: [])  # finished graph nodes, all runs


def get_session() -> Session:
    existing = st.session_state.get("session")
    if isinstance(existing, Session):
        return existing
    created = Session()
    st.session_state["session"] = created
    return created


@st.cache_resource(show_spinner="Starting the planner and its tool servers...")
def get_runtime() -> PlannerRuntime:
    """One runtime per server process, shared by every browser session."""
    runtime = PlannerRuntime()
    runtime.start()
    return runtime


def main() -> None:
    st.set_page_config(
        page_title="Yatra AI travel planner",
        page_icon=":material/flight_takeoff:",
        layout="wide",
    )
    st.title("Yatra AI travel planner")
    st.caption(
        "A supervisor checks your request, then flight, hotel, weather, budget and itinerary "
        "agents build a plan. Nothing is final until you approve it."
    )

    problem = missing_llm_key()
    if problem:
        st.error(problem, icon=":material/key:")
        st.markdown(
            "On Streamlit Community Cloud, open **Manage app > Settings > Secrets** and add the "
            'key as a line such as `DEEPSEEK_API_KEY = "..."`. Running locally, put it in '
            "`.streamlit/secrets.toml` (see `.streamlit/secrets.toml.example`) or in `.env`."
        )
        st.stop()

    try:
        runtime = get_runtime()
    except RuntimeError as exc:
        st.error(f"The planner could not start: {escape_markdown(exc)}")
        st.stop()

    session = get_session()
    _sidebar(runtime, session)
    _settle(session)

    if session.turn is not None:
        _watch(session)  # blocks until the run ends, then re-runs the page
        return

    if session.error:
        st.error(escape_markdown(session.error), icon=":material/error:")

    if session.plan is None:
        _ask_for_trip(runtime, session)
        return

    render_plan(session.plan)
    _show_steps(session)
    if session.plan.get("status") in FINAL_STATUSES:
        if st.button("Plan another trip", type="primary", icon=":material/add:"):
            _reset(session)
            st.rerun()
    elif session.approval_request is not None:
        _decide(runtime, session)


def _sidebar(runtime: PlannerRuntime, session: Session) -> None:
    llm = settings.llm
    with st.sidebar:
        st.header("Yatra AI")
        if st.button("New trip", icon=":material/add:", width="stretch"):
            _reset(session)
            st.rerun()

        st.subheader("Models")
        chain = [llm.runtime_model.value, *(model.value for model in llm.fallback_models)]
        st.caption("Main model, then fallbacks in order:")
        for model in dict.fromkeys(chain):
            st.caption(f"- {model}")
        st.caption(
            "Keys: DeepSeek "
            + ("set" if llm.deepseek_api_key else "not set")
            + ", OpenAI "
            + ("set" if llm.openai_api_key else "not set")
        )

        st.subheader("Tools")
        for name, status in runtime.tool_status().items():
            st.caption(f"{name}: {escape_markdown(status)}")

        st.caption(
            "Plans live in memory only. They are lost when the app restarts or goes to sleep."
        )


def _reset(session: Session) -> None:
    """Forget the current plan; a run still in flight finishes in the background unseen."""
    session.thread_id = ""
    session.turn = None
    session.resuming = False
    session.plan = None
    session.approval_request = None
    session.error = None
    session.steps = []


def _start_request(runtime: PlannerRuntime, session: Session, message: str) -> None:
    _reset(session)
    session.thread_id = uuid4().hex
    state = new_request_state(message, session.thread_id, session.user_id)
    session.turn = runtime.start_turn(state, session.thread_id)
    st.rerun()


def _start_decision(
    runtime: PlannerRuntime, session: Session, approved: bool, feedback: str
) -> None:
    session.error = None
    session.resuming = True
    resume = Command(resume={"approved": approved, "feedback": feedback})
    session.turn = runtime.start_turn(resume, session.thread_id)
    st.rerun()


def _settle(session: Session) -> None:
    """Take in a run that has finished since the last page run."""
    turn = session.turn
    if turn is None or not turn.future.done():
        return
    session.turn = None
    session.steps.extend(turn.nodes)
    try:
        result = turn.result()
    except PlanningError as exc:
        session.error = str(exc)
        return
    except Exception:  # a cancelled run, for example
        session.error = PLANNING_FAILED
        return
    session.plan = result.plan
    session.approval_request = result.approval_request


def _watch(session: Session) -> None:
    """Show each agent as it finishes. Blocks until the run ends, then re-runs the page."""
    turn = session.turn
    if turn is None:
        return
    label = "Applying your decision..." if session.resuming else "Planning your trip..."
    started = time.monotonic()
    with st.status(label, expanded=True) as status:
        shown = 0
        while not turn.wait(POLL_SECONDS):
            for node in turn.nodes[shown:]:
                st.markdown(f":material/check: {node_label(node)}")
                shown += 1
        for node in turn.nodes[shown:]:
            st.markdown(f":material/check: {node_label(node)}")
        status.update(label=f"Finished in {time.monotonic() - started:.0f} s", state="complete")
    st.rerun()


def _show_steps(session: Session) -> None:
    if not session.steps:
        return
    with st.expander("How this plan was made"):
        for number, node in enumerate(session.steps, start=1):
            st.caption(f"{number}. {node_label(node)}")


def _ask_for_trip(runtime: PlannerRuntime, session: Session) -> None:
    form_tab, text_tab = st.tabs(["Trip form", "Describe your trip"])
    message: Optional[str] = None
    with form_tab:
        message = _trip_form()
    with text_tab:
        message = _free_text_form() or message
    if message:
        _start_request(runtime, session, message)


def _trip_form() -> Optional[str]:
    today = date.today()
    with st.form("trip_form"):
        destination = st.text_input("Destination", placeholder="Lisbon", max_chars=80)
        left, right = st.columns(2)
        departure = left.date_input(
            "Departure", value=today + timedelta(days=30), min_value=today, key="departure"
        )
        returning = right.date_input(
            "Return", value=today + timedelta(days=34), min_value=today, key="returning"
        )
        left, right = st.columns(2)
        travellers = left.number_input(
            "Travellers", min_value=1, max_value=MAX_TRAVELLERS, value=2, step=1
        )
        budget = right.number_input(
            "Total budget (USD)", min_value=float(MIN_BUDGET_USD), value=2500.0, step=100.0
        )
        notes = st.text_area("Preferences (optional)", max_chars=MAX_NOTES_LENGTH)
        submitted = st.form_submit_button("Plan my trip", type="primary")
    if not submitted:
        return None
    problem = validate_trip_form(
        destination, _as_date(departure), _as_date(returning), int(travellers), float(budget), today
    )
    if problem:
        st.error(problem)
        return None
    return build_plan_message(
        destination, departure, returning, int(travellers), float(budget), notes
    )


def _as_date(value: object) -> Optional[date]:
    """A date picker gives back a date, or nothing while the field is empty."""
    return value if isinstance(value, date) else None


def _use_example(text: str) -> None:
    st.session_state["free_text"] = text


def _free_text_form() -> Optional[str]:
    st.caption("Try an example:")
    columns = st.columns(len(EXAMPLE_REQUESTS))
    for column, (label, text) in zip(columns, EXAMPLE_REQUESTS):
        column.button(label, key=f"example-{label}", on_click=_use_example, args=(text,))
    with st.form("free_text_form"):
        text = st.text_area(
            "What trip do you have in mind?",
            key="free_text",
            max_chars=MAX_MESSAGE_LENGTH,
            height=140,
            placeholder="Destination, dates, number of people, budget and what you enjoy.",
        )
        submitted = st.form_submit_button("Plan my trip", type="primary")
    if not submitted:
        return None
    if not text.strip():
        st.error("Describe the trip first.")
        return None
    return text.strip()


def _decide(runtime: PlannerRuntime, session: Session) -> None:
    request = session.approval_request or {}
    revision = request.get("revision", 0)
    limit = request.get("max_revisions", settings.mcp.max_revisions)
    st.divider()
    st.subheader("Your decision")
    st.markdown(escape_markdown(request.get("question") or "Do you approve this plan?"))
    st.caption(f"Revisions used: {revision} of {limit}")
    # Not an ``st.form``: Ctrl+Enter in a form's text area presses its first submit button, which
    # here would approve the plan while someone is still typing feedback. The key changes with each
    # revision so the box starts empty for the new draft.
    feedback = st.text_area(
        "What should change? (required to ask for changes)",
        key=f"feedback-{session.thread_id}-{revision}",
        max_chars=MAX_FEEDBACK_LENGTH,
        placeholder="For example: more time outdoors, and keep the hotel cheaper.",
    )
    approve_col, revise_col = st.columns(2)
    approved = approve_col.button(
        "Approve plan", type="primary", icon=":material/check:", width="stretch"
    )
    revised = revise_col.button("Request changes", icon=":material/edit:", width="stretch")
    if approved:
        _start_decision(runtime, session, True, "")
    elif revised:
        problem = validate_feedback(feedback)
        if problem:
            st.error(problem)
        else:
            _start_decision(runtime, session, False, feedback.strip())
