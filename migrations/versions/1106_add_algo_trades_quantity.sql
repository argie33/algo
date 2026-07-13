-- Migration 1106: Add missing quantity column to algo_trades
--
-- CONTEXT: algo_trades.quantity exists in the local dev database (alongside the
-- required entry_quantity) but was never captured in a migration, so it was never
-- applied to AWS RDS -- same class of out-of-band schema drift as migration 1104
-- (algo_positions.entry_price).
--
-- Concretely broken because of this drift: phase9_reconciliation.py's quantity-sync
-- step does UPDATE algo_trades SET quantity = entry_quantity, ... WHERE status = 'open'
-- AND (quantity IS NULL OR quantity != entry_quantity), which fails outright on AWS with:
--   UndefinedColumn: column "quantity" does not exist
-- crashing Phase 9 on every orchestrator run once it gets past the earlier weight-
-- optimization halt.

ALTER TABLE algo_trades ADD COLUMN IF NOT EXISTS quantity INTEGER;
