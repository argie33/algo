-- Migration 1007: Ensure algo_positions_with_risk materialized view exists
--
-- This view was missing from the database despite being required by:
-- - Phase 9 reconciliation (refreshes the view)
-- - Dashboard positions panel (queries the view)
-- - API positions endpoint (queries the view)
--
-- Previous migrations (0084, 999, 1005) attempted to create this view but may have
-- failed due to table schema changes or CREATE TABLE IF NOT EXISTS idempotency issues.
--
-- This migration uses DROP + CREATE to ensure a clean state, then validates by querying.

BEGIN;

-- Drop the view if it exists (along with any dependent views)
DROP MATERIALIZED VIEW IF EXISTS algo_positions_with_risk CASCADE;

-- Recreate the view with only essential columns needed by API and dashboard
-- Simplified version using LATERAL joins for latest data per symbol
CREATE MATERIALIZED VIEW algo_positions_with_risk AS
SELECT
  ap.id,
  ap.position_id,
  ap.symbol,
  ap.quantity,
  ap.avg_entry_price,
  pd.close AS current_price,
  ap.position_value,
  ap.unrealized_pnl,
  ap.unrealized_pnl_pct,
  ap.status,
  ap.stage_in_exit_plan,
  ap.days_since_entry,
  ap.stop_loss_price,
  ap.target_1_price,
  ap.target_2_price,
  ap.target_3_price,
  ap.sector,
  ap.industry
FROM algo_positions ap
LEFT JOIN LATERAL (
  SELECT close FROM price_daily
  WHERE symbol = ap.symbol
  ORDER BY date DESC LIMIT 1
) pd ON TRUE
WHERE ap.status = 'open';

-- Verify the view was created successfully
DO $verify$
BEGIN
  PERFORM * FROM algo_positions_with_risk LIMIT 1;
  RAISE NOTICE '[MIGRATION 1007] algo_positions_with_risk view created successfully';
END $verify$;

COMMIT;
