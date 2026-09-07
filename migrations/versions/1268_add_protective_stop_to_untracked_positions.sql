-- Migration: Add protective-stop tracking columns to algo_untracked_positions
-- Purpose: real-money-readiness audit finding - an orphaned broker position (found at
-- Alpaca, no matching algo_trades/algo_positions row) previously got a critical alert but
-- NO stop-loss protection at all, because every part of the system except the sync loop
-- assumes a position it doesn't know about doesn't exist. This table intentionally stays
-- separate from algo_positions (see migration 1118's comment: "to avoid circuit breaker
-- conflicts" - an untracked position may be a deliberate manual/external holding the
-- operator does not want the algo's signal-driven exit logic (targets, Minervini break,
-- etc.) touching), so the fix is a standalone broker-side protective stop order attached
-- directly to the position - not full algo-managed exit enrollment. These columns let the
-- sync loop recognize a stop it already submitted instead of resubmitting one every cycle.

BEGIN;

ALTER TABLE algo_untracked_positions
    ADD COLUMN IF NOT EXISTS protective_stop_order_id TEXT,
    ADD COLUMN IF NOT EXISTS protective_stop_price NUMERIC(18, 6),
    ADD COLUMN IF NOT EXISTS protective_stop_submitted_at TIMESTAMP;

COMMENT ON COLUMN algo_untracked_positions.protective_stop_order_id IS
    'Alpaca order id of the standalone (non-bracket) protective sell-stop this system submitted for this orphaned position, if any. NULL until submitted or if submission failed/was skipped.';
COMMENT ON COLUMN algo_untracked_positions.protective_stop_price IS
    'Stop price used for protective_stop_order_id, computed as current_price * (1 - imported_position_default_stop_loss_pct/100) at submission time.';
COMMENT ON COLUMN algo_untracked_positions.protective_stop_submitted_at IS
    'When protective_stop_order_id was submitted. NULL until submitted.';

COMMIT;
