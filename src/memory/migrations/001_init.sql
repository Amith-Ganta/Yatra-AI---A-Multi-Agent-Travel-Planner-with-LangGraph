-- Migration 001: Initial schema for memory and checkpointing

-- Threads (conversation sessions)
CREATE TABLE IF NOT EXISTS threads (
    thread_id UUID PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_user_id ON threads(user_id);
CREATE INDEX IF NOT EXISTS idx_created_at ON threads(created_at);

-- Checkpoints (LangGraph state snapshots)
CREATE TABLE IF NOT EXISTS checkpoints (
    checkpoint_id UUID PRIMARY KEY,
    thread_id UUID NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
    step INTEGER NOT NULL,
    state JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(thread_id, step)
);

CREATE INDEX IF NOT EXISTS idx_thread_id_step ON checkpoints(thread_id, step);

-- Messages (conversation history)
CREATE TABLE IF NOT EXISTS messages (
    message_id UUID PRIMARY KEY,
    thread_id UUID NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_thread_id_created_at ON messages(thread_id, created_at);

-- Checkpointer config (versioning)
CREATE TABLE IF NOT EXISTS checkpointer_config (
    id SERIAL PRIMARY KEY,
    version VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
