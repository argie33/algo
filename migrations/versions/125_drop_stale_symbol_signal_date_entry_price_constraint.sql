-- Migration 125: Drop stale (symbol, signal_date, entry_price) unique constraint on algo_trades
--
-- PROBLEM:
-- Migration 007 (fix_duplicate_trades_constraint) documented that this constraint was
-- "broken" (NULL signal_date let duplicates through) and said it would be "replaced" by
-- a partial unique index on (symbol) WHERE status='open'. It added the replacement index
-- but never actually dropped the old constraint - both have coexisted ever since.
--
-- IMPACT (live-confirmed 2026-08-03):
-- The stale constraint blocks legitimate same-day re-entries: KARO and NBIX each opened,
-- closed (health-flag early exit), cleared their 30-minute re-entry cooldown, and
-- re-qualified for entry later the same trading day at the same computed entry_price
-- (identical signal_date, same-day price). Phase 8 raised an uncaught UniqueViolation on
-- (symbol, signal_date, entry_price) on every retry (5 consecutive orchestrator runs,
-- 13:00-13:16 ET), logged as an unexplained "Unexpected error" execution_failed rejection
-- and marking the run 'degraded' - a real trade the algo wanted to place was silently
-- dropped, not because of any real duplicate-order risk (that's what
-- algo_trades_idempotency_key_key and the partial open-position index already guard
-- against - see executor_entry_handler.py's idempotency_key, hashed from
-- symbol+entry_price+stop_loss_price+signal_date) but because of this leftover, coarser
-- constraint from before that mechanism existed.
--
-- SOLUTION:
-- Drop the stale constraint. Duplicate-order protection is already covered by:
--   1. algo_trades_idempotency_key_key (UNIQUE idempotency_key) - true request-level
--      dedup, includes stop_loss_price unlike the constraint being dropped here.
--   2. algo_trades_symbol_live_status_idx / algo_positions_symbol_live_status_idx -
--      partial unique indexes preventing more than one simultaneously-open
--      position/trade per symbol.

BEGIN;

ALTER TABLE algo_trades DROP CONSTRAINT IF EXISTS algo_trades_symbol_signal_date_entry_price_key;

COMMIT;
