# Memory & PostgreSQL Specification

**Phase:** 5  
**Version:** 1.0  
**Status:** Implementation  
**Dependencies:** Phase 2 (config), Phase 3 (agents), Phase 4 (tools)

---

## Overview

This phase implements persistent memory via PostgreSQL and LangGraph checkpointing. Enables thread resumption, conversation history, and state recovery.

**Architecture:**
```
Agent workflow
  ↓
LangGraph StateGraph
  ↓
Checkpointer (SavepointTrigger)
  ↓
PostgreSQL async pool (psycopg)
  ↓
Persistent storage (checkpoints, threads, messages)
  ↓
Thread resumption (invoke with thread_id)
```

---

## 1. Database Schema

**PostgreSQL tables for checkpointing and history.**

```sql
-- Threads (conversation sessions)
CREATE TABLE threads (
    thread_id UUID PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}',
    INDEX idx_user_id (user_id),
    INDEX idx_created_at (created_at)
);

-- Checkpoints (LangGraph state snapshots)
CREATE TABLE checkpoints (
    checkpoint_id UUID PRIMARY KEY,
    thread_id UUID NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
    step INTEGER NOT NULL,
    state JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_thread_id_step (thread_id, step),
    UNIQUE(thread_id, step)
);

-- Messages (conversation history)
CREATE TABLE messages (
    message_id UUID PRIMARY KEY,
    thread_id UUID NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL, -- 'user', 'assistant', 'system'
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_thread_id_created_at (thread_id, created_at)
);

-- Checkpointer config (versioning)
CREATE TABLE checkpointer_config (
    id INTEGER PRIMARY KEY DEFAULT 1,
    version VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 2. src/memory/db.py

**Async PostgreSQL connection pool and query interface.**

```python
from contextlib import asynccontextmanager
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

class DatabasePool:
    """Manages async PostgreSQL connection pool."""
    
    def __init__(self, database_url: str):
        self.pool: AsyncConnectionPool | None = None
        self.database_url = database_url
    
    async def init(self):
        """Initialize connection pool."""
        self.pool = AsyncConnectionPool(
            self.database_url,
            min_size=2,
            max_size=20,
        )
        await self.pool.open()
    
    async def close(self):
        """Close all connections."""
        if self.pool:
            await self.pool.close()
    
    @asynccontextmanager
    async def acquire(self):
        """Acquire a connection from pool."""
        async with self.pool.connection() as conn:
            yield conn
    
    async def execute(self, query: str, params: tuple = ()):
        """Execute query and return results."""
        async with self.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params)
                return await cur.fetchall()

db_pool = DatabasePool(...)  # Singleton instance
```

---

## 3. src/memory/checkpointer.py

**LangGraph SavepointsTrigger implementation.**

```python
from langgraph.checkpoint.base import BaseCheckpointer, Checkpoint
from uuid import uuid4

class PostgreSQLCheckpointer(BaseCheckpointer):
    """LangGraph checkpointer backed by PostgreSQL."""
    
    def __init__(self, db_pool: DatabasePool):
        self.db = db_pool
    
    async def put(self, values: dict, metadata: dict) -> str:
        """Save checkpoint for thread."""
        thread_id = metadata.get("thread_id")
        step = metadata.get("step", 0)
        
        checkpoint_id = str(uuid4())
        
        query = """
        INSERT INTO checkpoints (checkpoint_id, thread_id, step, state, created_at)
        VALUES (%s, %s, %s, %s, NOW())
        ON CONFLICT (thread_id, step) DO UPDATE SET state = EXCLUDED.state
        """
        
        await self.db.execute(
            query,
            (checkpoint_id, thread_id, step, json.dumps(values))
        )
        
        return checkpoint_id
    
    async def get(self, thread_id: str, step: int) -> dict | None:
        """Retrieve checkpoint."""
        query = """
        SELECT state FROM checkpoints
        WHERE thread_id = %s AND step = %s
        """
        
        results = await self.db.execute(query, (thread_id, step))
        
        if results:
            return json.loads(results[0][0])
        return None
    
    async def list_checkpoints(self, thread_id: str) -> list[dict]:
        """List all checkpoints for thread."""
        query = """
        SELECT checkpoint_id, step, created_at FROM checkpoints
        WHERE thread_id = %s
        ORDER BY step DESC
        """
        
        results = await self.db.execute(query, (thread_id,))
        return results
```

---

## 4. src/memory/threads.py

**Thread and conversation management.**

```python
from uuid import uuid4
from datetime import datetime

async def create_thread(user_id: str, metadata: dict = None) -> str:
    """Create new conversation thread."""
    thread_id = str(uuid4())
    
    query = """
    INSERT INTO threads (thread_id, user_id, metadata, created_at, updated_at)
    VALUES (%s, %s, %s, NOW(), NOW())
    """
    
    await db_pool.execute(
        query,
        (thread_id, user_id, json.dumps(metadata or {}))
    )
    
    return thread_id

async def get_thread(thread_id: str) -> dict | None:
    """Retrieve thread metadata."""
    query = """
    SELECT thread_id, user_id, created_at, updated_at, metadata
    FROM threads WHERE thread_id = %s
    """
    
    results = await db_pool.execute(query, (thread_id,))
    if results:
        return dict(results[0])
    return None

async def add_message(thread_id: str, role: str, content: str, metadata: dict = None):
    """Add message to conversation history."""
    message_id = str(uuid4())
    
    query = """
    INSERT INTO messages (message_id, thread_id, role, content, metadata, created_at)
    VALUES (%s, %s, %s, %s, %s, NOW())
    """
    
    await db_pool.execute(
        query,
        (message_id, thread_id, role, content, json.dumps(metadata or {}))
    )

async def get_history(thread_id: str, limit: int = 50) -> list[dict]:
    """Retrieve conversation history."""
    query = """
    SELECT role, content, created_at FROM messages
    WHERE thread_id = %s
    ORDER BY created_at DESC
    LIMIT %s
    """
    
    results = await db_pool.execute(query, (thread_id, limit))
    return results
```

---

## 5. src/memory/__init__.py

**Memory module exports.**

```python
from .db import DatabasePool, db_pool
from .checkpointer import PostgreSQLCheckpointer
from .threads import create_thread, get_thread, add_message, get_history

__all__ = [
    "DatabasePool",
    "db_pool",
    "PostgreSQLCheckpointer",
    "create_thread",
    "get_thread",
    "add_message",
    "get_history",
]
```

---

## 6. src/core/config.py (updated)

**Add database pool initialization.**

```python
# In setup() or startup hook:
from src.memory import db_pool

async def init_database():
    """Initialize database connection pool."""
    await db_pool.init()

async def close_database():
    """Close database connections."""
    await db_pool.close()
```

---

## 7. Windows Event Loop Handling

**For Windows asyncio SelectorEventLoop compatibility:**

```python
import asyncio
import sys

# In main.py or app startup:
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```

---

## 8. tests/unit/test_memory.py

**Memory and database tests.**

```python
import pytest
from src.memory import create_thread, get_thread, add_message, get_history

@pytest.mark.asyncio
async def test_create_thread():
    """Create new conversation thread."""
    thread_id = await create_thread("user-123")
    assert thread_id is not None
    assert len(thread_id) == 36  # UUID length

@pytest.mark.asyncio
async def test_get_thread():
    """Retrieve thread metadata."""
    thread_id = await create_thread("user-456")
    thread = await get_thread(thread_id)
    assert thread is not None
    assert thread["user_id"] == "user-456"

@pytest.mark.asyncio
async def test_add_message():
    """Add message to conversation."""
    thread_id = await create_thread("user-789")
    await add_message(thread_id, "user", "Plan a trip to Paris")
    await add_message(thread_id, "assistant", "I'll help you plan!")
    
    history = await get_history(thread_id)
    assert len(history) >= 2

@pytest.mark.asyncio
async def test_get_history_order():
    """History retrieved in creation order."""
    thread_id = await create_thread("user-999")
    await add_message(thread_id, "user", "First message")
    await add_message(thread_id, "assistant", "Response")
    
    history = await get_history(thread_id)
    assert history[-1][0] == "user"  # Last added is first retrieved
    assert history[0][0] == "assistant"
```

---

## 9. Integration with LangGraph

**Use checkpointer in graph.build_graph():**

```python
from langgraph.graph import StateGraph
from src.memory import PostgreSQLCheckpointer, db_pool

async def build_graph():
    """Build LangGraph with PostgreSQL checkpointer."""
    graph = StateGraph(TravelState)
    
    # Add nodes (supervisor, flight, hotel, etc.)
    graph.add_node("supervisor", supervisor_agent)
    ...
    
    # Compile with checkpointer
    checkpointer = PostgreSQLCheckpointer(db_pool)
    compiled = graph.compile(checkpointer=checkpointer)
    
    return compiled
```

**Invoke with thread_id:**

```python
# First call - new thread
result = await graph.ainvoke(
    input_state,
    config={"thread_id": "thread-123"}
)

# Resume - loads checkpoint
result = await graph.ainvoke(
    input_state,
    config={"thread_id": "thread-123"}  # Same thread_id resumes
)
```

---

## Success Criteria

- ✅ PostgreSQL schema created (threads, checkpoints, messages)
- ✅ Async connection pool with psycopg
- ✅ LangGraph SavepointsTrigger implemented
- ✅ Thread CRUD operations
- ✅ Conversation history storage
- ✅ Checkpointer integration with graph
- ✅ Windows event loop compatibility
- ✅ Tests pass (80%+ coverage)
- ✅ No hardcoded credentials

---

**Next Phase:** Phase 6 (API - FastAPI routes, SSE streaming, HITL)

