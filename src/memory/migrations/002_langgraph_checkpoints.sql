-- Migration 002: hand the `checkpoints` table name over to LangGraph's own Postgres saver.
--
-- Migration 001 used to create a custom `checkpoints` table (with a `step` column) that no code
-- ever wrote to. The saver (langgraph-checkpoint-postgres) creates its own table with the same
-- name but a different shape, so the old one has to go before the saver runs `setup()`.
--
-- The check looks for the legacy `step` column, so the saver's table is never touched. This file
-- runs on every boot and is a no-op once the legacy table is gone.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'checkpoints'
          AND column_name = 'step'
    ) THEN
        DROP TABLE checkpoints;
    END IF;
END
$$;

-- Also unused: nothing ever read or wrote it.
DROP TABLE IF EXISTS checkpointer_config;
