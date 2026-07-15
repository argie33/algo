-- Migration: Add unique constraint on symbol in algo_untracked_positions
-- Purpose: Ensure one untracked position per symbol, enable efficient lookups

BEGIN;

-- Add unique constraint on symbol (only one untracked position per symbol)
ALTER TABLE algo_untracked_positions
ADD CONSTRAINT untracked_positions_symbol_unique UNIQUE (symbol);

-- Update the index comment
COMMENT ON INDEX untracked_positions_symbol_unique IS 'Ensures one untracked position per symbol';

COMMIT;
