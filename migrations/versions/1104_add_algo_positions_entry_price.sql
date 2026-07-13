-- Migration 1104: Add missing entry_price column to algo_positions
--
-- CONTEXT: algo_positions.entry_price exists in the local dev database but was never
-- captured in a migration, so it was never applied to AWS RDS -- classic out-of-band
-- schema drift (same class of bug as migration 1103's algo_positions_with_risk fix).
--
-- Concretely broken because of this drift: reconciliation.py's open-trades query
-- (algo/infrastructure/reconciliation.py, ~line 505) does
-- COALESCE(NULLIF(at.entry_price, 0), ap.entry_price) as avg_entry_price, falling back
-- to algo_positions.entry_price for positions created before algo_trades.entry_price
-- was consistently populated. On AWS this fails outright with:
--   UndefinedColumn: column ap.entry_price does not exist
-- which crashes Phase 9 (reconciliation) on every orchestrator run.

ALTER TABLE algo_positions ADD COLUMN IF NOT EXISTS entry_price NUMERIC;
