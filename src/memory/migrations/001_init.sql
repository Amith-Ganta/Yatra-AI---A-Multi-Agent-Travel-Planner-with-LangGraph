-- Migration 001: Initial schema for threads and message history

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

-- LangGraph checkpoints are not created here: the saver (AsyncPostgresSaver.setup) owns those
-- tables. See migration 002 for the legacy table this file used to create.

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
