-- Migration: Add unique constraint on symbol in algo_untracked_positions
-- Purpose: Ensure one untracked position per symbol, enable efficient lookups

BEGIN;

-- Add unique constraint on symbol (only one untracked position per symbol).
-- Guarded (not a plain ADD CONSTRAINT): Postgres has no "ADD CONSTRAINT IF NOT EXISTS",
-- and this constraint was already present on the live DB (added by hand outside this
-- migration) before this migration was ever recorded as applied - a bare ADD CONSTRAINT
-- would fail with "constraint already exists" and abort the whole migration run.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'untracked_positions_symbol_unique'
    ) THEN
        ALTER TABLE algo_untracked_positions
        ADD CONSTRAINT untracked_positions_symbol_unique UNIQUE (symbol);
    END IF;
END $$;

-- Update the index comment
COMMENT ON INDEX untracked_positions_symbol_unique IS 'Ensures one untracked position per symbol';

COMMIT;
