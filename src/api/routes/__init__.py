"""API routes module."""

from .approval import router as approval_router
from .health import router as health_router
from .planning import router as planning_router

__all__ = ["health_router", "planning_router", "approval_router"]
