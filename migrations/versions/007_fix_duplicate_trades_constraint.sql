-- Migration 007: Fix duplicate open trades bug
--
-- PROBLEM:
-- The existing UNIQUE constraint on (symbol, signal_date, entry_price) doesn't work
-- because signal_date is nullable. In SQL, NULL != NULL, so multiple rows with
-- NULL signal_date are allowed, creating duplicate open positions for the same symbol.
--
-- IMPACT:
-- XYL had 3 open records, NMRK had 2, preventing proper position tracking
-- and confusing the positions sync logic
--
-- SOLUTION:
-- 1. Add a partial unique index on (symbol) WHERE status = 'open'
--    This ensures only ONE open position per symbol across any signal_date
-- 2. Mark existing duplicates as 'cancelled' to keep the most recent valid trade
-- 3. Update insertion logic to use proper duplicate checks

BEGIN;

-- 1. Mark duplicate open trades as cancelled (keep only the most recent per symbol)
WITH duplicates AS (
    SELECT trade_id, symbol,
           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY entry_date DESC NULLS LAST, created_at DESC) as rn
    FROM algo_trades
    WHERE status = 'open'
)
UPDATE algo_trades SET status = 'cancelled', exit_date = CURRENT_DATE
FROM duplicates
WHERE algo_trades.trade_id = duplicates.trade_id AND duplicates.rn > 1;

-- 2. Add partial unique index to prevent future duplicates
CREATE UNIQUE INDEX IF NOT EXISTS algo_trades_symbol_open_positions_idx
ON algo_trades(symbol)
WHERE status = 'open';

-- 3. Add comment explaining the fix
COMMENT ON INDEX algo_trades_symbol_open_positions_idx IS
'Partial unique index ensuring only ONE open position per symbol.
Uses OPEN status filter to allow multiple closed/cancelled trades.
Replaces broken (symbol, signal_date, entry_price) constraint where NULL signal_date allowed duplicates.';

COMMIT;
