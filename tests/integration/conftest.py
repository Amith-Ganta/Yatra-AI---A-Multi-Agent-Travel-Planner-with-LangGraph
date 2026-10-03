"""Integration test configuration.

These tests need a real PostgreSQL (DATABASE_URL), like the CI `Postgres 15` service. Start the
database first; nothing here mocks the pool.
"""

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from src.api import create_app
from src.core.config import settings
from src.memory import db_pool
from src.memory.migrations import run_migrations


@pytest_asyncio.fixture
async def database():
    """Open the pool and apply migrations for an async test, then close it again."""
    db_pool.database_url = settings.database.url
    await db_pool.init(timeout=10)
    await run_migrations()
    try:
        yield db_pool
    finally:
        await db_pool.close()


@pytest.fixture
def client():
    """API client. `with` runs the app lifespan, which opens the pool and runs migrations."""
    with TestClient(create_app()) as test_client:
        yield test_client
