"""Run the graph and report its progress as server-sent events.

Both ``POST /api/plan`` (a new request) and ``PUT /api/threads/{id}/approve`` (the person's
decision) go through ``graph_events``. Every event is one JSON object with a ``type``:

    {"type": "thread",            "thread_id": "..."}   first event, so the client knows the thread
    {"type": "progress",          "node": "flight"}     one per finished graph node
    {"type": "plan",              "plan": {...}}        the plan so far (stored on the thread)
    {"type": "approval_required", "request": {...}}     the run is paused for a human decision
    {"type": "done"}                                    last event of a successful run
    {"type": "error",             "error": "..."}       last event of a failed run (generic text)

A run ends in one of two ways. Either it finishes (``plan`` then ``done``) or it pauses at the
approval step (``plan`` with status ``awaiting_approval``, ``approval_required``, then ``done``).
The pause is a saved checkpoint, not an open connection: the person answers later with the
approve endpoint, which resumes the same thread.

If the client disconnects mid-stream the run is cancelled; the checkpointer keeps the state of
the last finished step, and no plan is stored for the interrupted run.
"""

import json
from typing import Any, AsyncIterator, Union

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from src.agents.plan import build_plan, plan_message_text
from src.agents.runtime import get_graph
from src.agents.state import TravelState
from src.core.config import settings
from src.core.telemetry import logger
from src.memory import add_message

PLANNING_FAILED = "We could not plan this trip right now. Please try again."
THREAD_BUSY = "This trip is already being worked on. Please wait for it to finish."

# langgraph reports a pause as an update under this key instead of a node name
INTERRUPT_KEY = "__interrupt__"

# Threads with a run in flight in this process. Two runs on one thread would both resume the same
# checkpoint; the claim is per process, which matches the single-instance deployment.
_running: set[str] = set()


def is_running(thread_id: str) -> bool:
    """True while a run on this thread is in flight in this process."""
    return thread_id in _running


def sse(payload: dict[str, Any]) -> str:
    """One server-sent-event frame."""
    return f"data: {json.dumps(payload, default=str)}\n\n"


async def graph_events(
    graph_input: Union[TravelState, Command[Any]], thread_id: str
) -> AsyncIterator[str]:
    """Run (or resume) the graph on ``thread_id`` and yield SSE frames.

    The plan is persisted before it is announced, so a client that sees a ``plan`` frame can
    always reload it from the thread.
    """
    if thread_id in _running:
        yield sse({"type": "error", "error": THREAD_BUSY})
        return

    _running.add(thread_id)
    try:
        yield sse({"type": "thread", "thread_id": thread_id})

        graph = get_graph()
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        # langgraph's astream signature carries an unparameterised Command, hence the ignore
        stream = graph.astream(  # pyright: ignore[reportUnknownMemberType]
            graph_input, config, stream_mode="updates"
        )
        async for event in stream:
            for node in event:
                if node != INTERRUPT_KEY:
                    yield sse({"type": "progress", "node": node})

        # The checkpoint tells us how the run ended and holds the full state, whether or not it
        # paused, so nothing has to be merged by hand from the per-node updates.
        snapshot = await graph.aget_state(config)
        pending = [item.value for item in snapshot.interrupts]
        plan = build_plan(
            dict(snapshot.values),
            awaiting_approval=bool(pending),
            max_revisions=settings.mcp.max_revisions,
        )
        await add_message(
            thread_id,
            "assistant",
            plan_message_text(plan),
            {"kind": "plan", "plan": plan},
        )
        yield sse({"type": "plan", "plan": plan})
        if pending:
            yield sse({"type": "approval_required", "request": pending[0]})
        yield sse({"type": "done"})
    except Exception as exc:
        logger.error("Stream error", extra={"error": str(exc), "thread_id": thread_id})
        yield sse({"type": "error", "error": PLANNING_FAILED})
    finally:
        _running.discard(thread_id)
