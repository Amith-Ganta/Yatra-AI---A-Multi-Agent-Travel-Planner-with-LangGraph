"""Run the travel graph for the Streamlit app, inside the app's own process.

Streamlit re-runs its script from the top on every click, in a worker thread that has no event
loop and may change between runs. The graph, its MCP tool sessions and the LLM clients are all
async and long-lived, so they live on one dedicated event loop in a background thread, started
once per process. The script only hands work to that loop and polls for the result.

There is no database. The graph keeps its checkpoints in memory, which is enough for the approve
and revise loop within one session, and they are lost when the app restarts or goes to sleep.
"""

import asyncio
import threading
from concurrent.futures import Future
from concurrent.futures import wait as wait_for_futures
from dataclasses import dataclass, field
from typing import Any, Optional, Union

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from src.agents.graph import CompiledGraph, build_graph
from src.agents.plan import build_plan
from src.agents.state import TravelState
from src.core.config import settings
from src.core.telemetry import logger
from src.tools.gateway import mcp_status, start_mcp, stop_mcp

PLANNING_FAILED = "We could not plan this trip right now. Please try again."

# langgraph reports a pause as an update under this key instead of a node name
INTERRUPT_KEY = "__interrupt__"

# One run may call several LLMs and tools, each with its own timeout; this is the outer limit
TURN_TIMEOUT_SECONDS = 300.0
STARTUP_TIMEOUT_SECONDS = 120.0
SHUTDOWN_TIMEOUT_SECONDS = 15.0


class PlanningError(Exception):
    """A run failed. The message is safe to show; the cause is in the log."""


def missing_llm_key() -> Optional[str]:
    """What to fix when the main model has no API key, or None when the app can plan.

    Only the main model is required: a fallback without a key is skipped by the LLM factory, but a
    main model without one fails on the first request. The text names the secret, never its value.
    """
    model = settings.llm.runtime_model
    if model.value.startswith("deepseek:"):
        name, key = "DEEPSEEK_API_KEY", settings.llm.deepseek_api_key
    else:
        name, key = "OPENAI_API_KEY", settings.llm.openai_api_key
    if key:
        return None
    return f"The main model ({model.value}) needs {name}. Add it to the app's secrets and reload."


@dataclass(frozen=True)
class TurnResult:
    """How a run ended: the plan so far, and the approval request when it paused for one."""

    plan: dict[str, Any]
    approval_request: Optional[dict[str, Any]]


@dataclass
class TurnHandle:
    """A run in flight. The page keeps it in session state, so a re-run can pick it up again."""

    future: "Future[TurnResult]"
    nodes: list[str] = field(default_factory=lambda: [])  # finished graph nodes, in order

    def wait(self, timeout: float) -> bool:
        """Block up to ``timeout`` seconds; True once the run has ended."""
        wait_for_futures([self.future], timeout=timeout)
        return self.future.done()

    def result(self) -> TurnResult:
        """The finished run. Raises ``PlanningError`` when it failed."""
        return self.future.result()


class PlannerRuntime:
    """The compiled graph, its MCP tool servers and the event loop they run on."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._serve, name="yatra-planner", daemon=True)
        self._ready = threading.Event()
        self._stop: Optional[asyncio.Event] = None
        self._graph: Optional[CompiledGraph] = None

    def start(self, timeout: float = STARTUP_TIMEOUT_SECONDS) -> None:
        """Start the loop, the MCP servers and the graph; return when they are ready."""
        if self._thread.is_alive():
            return
        self._thread.start()
        if not self._ready.wait(timeout) or self._graph is None:
            raise RuntimeError("The planner did not start in time")

    def stop(self) -> None:
        """Stop the MCP servers and the loop (tests only; the app lives as long as its process)."""
        stop = self._stop
        if stop is not None and self._thread.is_alive():
            self._loop.call_soon_threadsafe(stop.set)
            self._thread.join(SHUTDOWN_TIMEOUT_SECONDS)

    def tool_status(self) -> dict[str, str]:
        """``{"mode": "in-process"}`` or one entry per MCP server (``ready`` or the reason not)."""
        return mcp_status()

    def start_turn(
        self, graph_input: Union[TravelState, Command[Any]], thread_id: str
    ) -> TurnHandle:
        """Begin a new request, or resume a paused one, and return at once."""
        nodes: list[str] = []
        future = asyncio.run_coroutine_threadsafe(
            self._run_turn(graph_input, thread_id, nodes), self._loop
        )
        return TurnHandle(future=future, nodes=nodes)

    def _serve(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._lifespan())
        finally:
            self._cancel_leftovers()
            self._loop.close()

    def _cancel_leftovers(self) -> None:
        tasks = asyncio.all_tasks(self._loop)
        for task in tasks:
            task.cancel()
        if tasks:
            self._loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))

    async def _lifespan(self) -> None:
        """Own the MCP sessions for the life of the loop.

        The MCP SDK opens task groups that must be closed by the task that opened them, so start
        and stop happen in this one coroutine rather than in whichever request comes first.
        """
        self._stop = asyncio.Event()
        try:
            try:
                await start_mcp()
            except Exception as exc:  # the tools then fall back to in-process calls
                logger.warning("MCP start-up failed; tools run in-process: %s", exc)
            self._graph = build_graph(InMemorySaver())
            self._ready.set()
            await self._stop.wait()
        finally:
            self._ready.set()  # never leave start() waiting after a failure
            await stop_mcp()

    async def _run_turn(
        self,
        graph_input: Union[TravelState, Command[Any]],
        thread_id: str,
        nodes: list[str],
    ) -> TurnResult:
        try:
            return await asyncio.wait_for(
                self._drive(graph_input, thread_id, nodes), TURN_TIMEOUT_SECONDS
            )
        except Exception as exc:
            logger.error("Planning run failed", extra={"error": repr(exc), "thread_id": thread_id})
            raise PlanningError(PLANNING_FAILED) from exc

    async def _drive(
        self,
        graph_input: Union[TravelState, Command[Any]],
        thread_id: str,
        nodes: list[str],
    ) -> TurnResult:
        graph = self._graph
        if graph is None:
            raise RuntimeError("The planner has not started")
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        # langgraph's astream signature carries an unparameterised Command, hence the ignore
        stream = graph.astream(  # pyright: ignore[reportUnknownMemberType]
            graph_input, config, stream_mode="updates"
        )
        async for event in stream:
            nodes.extend(node for node in event if node != INTERRUPT_KEY)

        # The checkpoint says how the run ended and holds the full state, paused or not
        snapshot = await graph.aget_state(config)
        pending = [item.value for item in snapshot.interrupts]
        plan = build_plan(
            dict(snapshot.values),
            awaiting_approval=bool(pending),
            max_revisions=settings.mcp.max_revisions,
        )
        return TurnResult(plan=plan, approval_request=pending[0] if pending else None)
