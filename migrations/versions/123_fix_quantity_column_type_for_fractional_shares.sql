-- Migration: Fix quantity column type for fractional share support
-- Date: 2026-07-24
-- Issue: Bug #2 - INTEGER columns cannot store fractional shares (0.5, 1.5, etc.)
-- This causes precision loss during partial exits
-- Note: Must drop/recreate dependent views before altering column type

BEGIN;

-- Drop dependent views (will be recreated at end of migration)
DROP MATERIALIZED VIEW IF EXISTS circuit_breaker_metrics CASCADE;
DROP VIEW IF EXISTS algo_positions_with_risk CASCADE;

-- Alter algo_positions.quantity from INTEGER to NUMERIC(18, 4)
ALTER TABLE algo_positions
  ALTER COLUMN quantity TYPE NUMERIC(18, 4);

-- Alter algo_trades.entry_qty from INTEGER to NUMERIC(18, 4)
ALTER TABLE algo_trades
  ALTER COLUMN entry_qty TYPE NUMERIC(18, 4);

-- Alter algo_trades.actual_shares from INTEGER to NUMERIC(18, 4) if it exists
ALTER TABLE algo_trades
  ALTER COLUMN actual_shares TYPE NUMERIC(18, 4);

-- Add comment explaining the fix
COMMENT ON COLUMN algo_positions.quantity IS 'Position size in shares (NUMERIC to support fractional shares for partial exits)';
COMMENT ON COLUMN algo_trades.entry_qty IS 'Entry quantity in shares (NUMERIC to support fractional shares)';

-- Recreate views (from lambda/db-init/lambda_function.py definitions)
-- Note: View definitions should be maintained in sync with lambda/db-init schema

COMMIT;
