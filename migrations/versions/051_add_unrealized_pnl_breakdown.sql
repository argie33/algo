-- Migration 051: Add unrealized PnL breakdown fields to portfolio snapshots
-- Purpose: Clarify unrealized PnL calculation and track winning/losing open positions

BEGIN;

-- Add columns to track unrealized PnL breakdown for open positions only
ALTER TABLE algo_portfolio_snapshots
ADD COLUMN IF NOT EXISTS unrealized_pnl_winning_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS unrealized_pnl_losing_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS unrealized_pnl_breakeven_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS unrealized_pnl_source VARCHAR(50) DEFAULT 'open_positions_only';

-- Backfill existing rows with default values
UPDATE algo_portfolio_snapshots
SET
    unrealized_pnl_winning_count = 0,
    unrealized_pnl_losing_count = 0,
    unrealized_pnl_breakeven_count = 0,
    unrealized_pnl_source = 'open_positions_only'
WHERE unrealized_pnl_winning_count IS NULL;

-- Add comment to clarify what unrealized_pnl_total represents
COMMENT ON COLUMN algo_portfolio_snapshots.unrealized_pnl_total IS
    'Sum of (current_price - entry_price) * quantity for ALL OPEN POSITIONS ONLY. Excludes closed trades and dividends. See unrealized_pnl_winning_count, unrealized_pnl_losing_count for breakdown.';

COMMENT ON COLUMN algo_portfolio_snapshots.unrealized_pnl_source IS
    'Data source: open_positions_only means this calculation includes only positions where exit_price IS NULL in algo_trades table.';

COMMIT;
