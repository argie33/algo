-- ════════════════════════════════════════════════════════════════════════════
-- MIGRATION: 047_track_reconciled_exit_prices
-- ════════════════════════════════════════════════════════════════════════════
--
-- PURPOSE: Track estimated vs actual exit prices for Phase 4 → Phase 7 reconciliation
--
-- PROBLEM: Phase 4 marks trades 'closed' using estimated prices ("last known market price")
-- when placing market exit orders before market open. Phase 7 should reconcile these with
-- actual Alpaca fill prices, but if Phase 7 fails/delays, estimated prices become permanent
-- with no way to distinguish them from actual prices or identify reconciliation status.
--
-- SOLUTION:
-- 1. estimated_exit_price: Store original Phase 4 estimated price (NULL if no pre-market exit)
-- 2. exit_price_reconciled_at: Timestamp when reconciliation completed (NULL if pending/failed)
-- 3. reconciliation_note: Optional text explaining reconciliation status or failure reason
--
-- LOGIC:
-- - When Phase 4 exits before market open: estimated_exit_price = cur_price (estimated)
-- - exit_price = cur_price (same initially)
-- - When Phase 7 reconciles: exit_price = actual_alpaca_filled_price
-- - exit_price_reconciled_at = CURRENT_TIMESTAMP
--
-- QUERIES:
-- - Pending reconciliation: WHERE estimated_exit_price IS NOT NULL AND exit_price_reconciled_at IS NULL
-- - Reconciliation variance: (exit_price - estimated_exit_price) / estimated_exit_price * 100
-- - Failed reconciliation: WHERE estimated_exit_price IS NOT NULL AND exit_price_reconciled_at IS NULL AND exit_date < CURRENT_DATE - 1
--
-- CREATED: 2026-06-12

ALTER TABLE algo_trades
ADD COLUMN IF NOT EXISTS estimated_exit_price DECIMAL(12, 4),
ADD COLUMN IF NOT EXISTS exit_price_reconciled_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS reconciliation_note TEXT;

COMMENT ON COLUMN algo_trades.estimated_exit_price IS
'Original estimated exit price from Phase 4 (set when trade exited before market open). NULL if trade was not a pre-market exit or reconciliation has not been tracked. Used to measure variance between estimated and actual fill prices.';

COMMENT ON COLUMN algo_trades.exit_price_reconciled_at IS
'Timestamp when Phase 7 reconciliation completed and actual Alpaca fill price updated exit_price. NULL if reconciliation is pending or failed. Enables identifying trades needing reconciliation or failed reconciliations.';

COMMENT ON COLUMN algo_trades.reconciliation_note IS
'Optional context about reconciliation (e.g., failure reason, variance notes). Used for debugging and audit trail when Phase 7 reconciliation has issues.';

-- Create index to quickly identify trades pending reconciliation
CREATE INDEX IF NOT EXISTS idx_algo_trades_pending_reconciliation
ON algo_trades(symbol, exit_date)
WHERE estimated_exit_price IS NOT NULL AND exit_price_reconciled_at IS NULL;

COMMENT ON INDEX idx_algo_trades_pending_reconciliation IS
'Index to identify trades with estimated exit prices awaiting Phase 7 reconciliation. Supports Phase 7 queries for trades needing price updates.';
