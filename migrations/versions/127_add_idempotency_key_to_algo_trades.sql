-- Migration 127: Add idempotency_key column to algo_trades for true request-level deduplication
--
-- PROBLEM:
-- executor_entry_handler.py generates idempotency_key (SHA256 hash of symbol+entry_price+stop_loss_price+signal_date)
-- and references it in TradeInsertionRequest and trade submissions, but the column was never created in the schema.
-- Phase 8 entry execution fails with "duplicate key value violates unique constraint 'algo_trades_idempotency_key_key'"
-- because the constraint exists as a named unique index but the backing column doesn't.
--
-- IMPACT (live-confirmed 2026-08-05):
-- Phase 8 entry execution: 0/19 signals executed, 11/19 failed with UniqueViolation on non-existent idempotency_key.
-- The failed signal list: SCSC, RACE, DCI, PDEX, SHOO, AER (duplicates across orchestrator runs with same prices).
--
-- SOLUTION:
-- Add idempotency_key column as TEXT NOT NULL with UNIQUE constraint.
-- This enables true request-level deduplication (covers stop_loss_price unlike the old symbol+signal_date+entry_price constraint).

BEGIN;

-- Add idempotency_key column initially as nullable
ALTER TABLE algo_trades
ADD COLUMN idempotency_key TEXT;

-- Backfill existing trades with a deterministic hash (symbol+entry_price+stop_loss_price+entry_date)
-- to avoid NOT NULL violations on already-existing rows.
-- Using md5 (built-in) instead of sha256 (requires pgcrypto extension).
UPDATE algo_trades
SET idempotency_key = md5(
    CONCAT(symbol, '_', entry_price::TEXT, '_', stop_loss_price::TEXT, '_', entry_date::TEXT)
)
WHERE idempotency_key IS NULL;

-- Add NOT NULL constraint after backfill
ALTER TABLE algo_trades
ALTER COLUMN idempotency_key SET NOT NULL;

-- Add unique constraint for idempotency_key
ALTER TABLE algo_trades
ADD CONSTRAINT algo_trades_idempotency_key_key UNIQUE (idempotency_key);

-- Add index for lookups by idempotency_key (constraint implicitly creates an index, but explicit for clarity)
CREATE INDEX algo_trades_idempotency_key_idx ON algo_trades (idempotency_key);

COMMIT;
