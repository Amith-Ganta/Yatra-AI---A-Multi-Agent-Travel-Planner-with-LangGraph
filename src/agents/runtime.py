"""The compiled graph the API runs, built once per process.

Compiling is cheap but not free, and the graph is stateless (state lives in the checkpointer), so
one instance serves every request. Startup builds it with the Postgres saver; unit tests install
a graph with an in-memory saver through ``init_graph``.
"""

from typing import Any, Optional

from langgraph.checkpoint.base import BaseCheckpointSaver

from .graph import CompiledGraph, build_graph

_graph: Optional[CompiledGraph] = None


def init_graph(checkpointer: BaseCheckpointSaver[Any]) -> CompiledGraph:
    """Compile the graph with ``checkpointer`` and keep it for ``get_graph``."""
    global _graph
    _graph = build_graph(checkpointer)
    return _graph


def get_graph() -> CompiledGraph:
    """The compiled graph; raises if the application has not been initialised."""
    if _graph is None:
        raise RuntimeError("Graph not initialized. Call init_graph() first.")
    return _graph


def close_graph() -> None:
    """Forget the graph (shutdown, and test isolation)."""
    global _graph
    _graph = None
