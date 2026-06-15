-- Migration 068: Ensure data_loader_status has all loader tracking columns
-- Migration 002 added these columns but they are absent from some environments,
-- causing every loader invocation to fail with "column does not exist" before
-- doing any actual work. Adding IF NOT EXISTS makes this safe to apply anywhere.

ALTER TABLE data_loader_status
    ADD COLUMN IF NOT EXISTS execution_started TIMESTAMP NULL,
    ADD COLUMN IF NOT EXISTS execution_completed TIMESTAMP NULL,
    ADD COLUMN IF NOT EXISTS completion_pct NUMERIC NULL,
    ADD COLUMN IF NOT EXISTS symbol_count INTEGER NULL,
    ADD COLUMN IF NOT EXISTS symbols_loaded INTEGER NULL;
