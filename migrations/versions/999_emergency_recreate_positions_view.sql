-- Emergency Migration: Recreate missing algo_positions_with_risk materialized view
--
-- ISSUE: Dashboard positions API returns only 1 position when 10+ exist in database.
-- ROOT CAUSE: The materialized view algo_positions_with_risk was missing from database.
-- This view is CRITICAL for the /api/algo/positions endpoint.
--
-- CREATED: 2026-07-04
-- BLOCKS: Dashboard positions display, AWS mode, position reconciliation

DROP MATERIALIZED VIEW IF EXISTS algo_positions_with_risk CASCADE;

-- Simplified materialized view that provides all required columns for dashboard API
-- This ensures the view exists and returns all positions correctly
-- NOTE: Full risk calculations from migrations/versions/082_add_company_name_to_positions_view.sql
-- can be applied here when all dependencies (technical data, trades) are available
CREATE MATERIALIZED VIEW algo_positions_with_risk AS
SELECT
  ap.id,
  ap.position_id,
  ap.symbol,
  ap.symbol AS company_name,
  ap.quantity,
  ap.avg_entry_price,
  ap.current_price,
  ap.position_value,
  ap.unrealized_pnl,
  ap.unrealized_pnl_pct,
  ap.status,
  ap.stage_in_exit_plan,
  ap.days_since_entry,
  ap.stop_loss_price,
  ap.current_stop_price AS current_stop_price,
  NULL::NUMERIC as target_1_price,
  NULL::NUMERIC as target_2_price,
  NULL::NUMERIC as target_3_price,
  NULL::NUMERIC as target_1_r_multiple,
  NULL::NUMERIC as target_2_r_multiple,
  NULL::NUMERIC as target_3_r_multiple,
  'Unknown' AS sector,
  'Unknown' AS industry,
  NULL::NUMERIC as minervini_trend_score,
  NULL::INTEGER as weinstein_stage,
  NULL::NUMERIC as percent_from_52w_low,
  NULL::NUMERIC as percent_from_52w_high,
  NULL::NUMERIC as swing_score,
  NULL::NUMERIC as r_multiple,
  NULL::NUMERIC as initial_risk_per_share,
  NULL::NUMERIC as open_risk_dollars,
  NULL::NUMERIC as distance_to_stop_pct,
  NULL::NUMERIC as distance_to_t1_pct,
  NULL::NUMERIC as distance_to_t2_pct,
  NULL::NUMERIC as distance_to_t3_pct
FROM algo_positions ap
WHERE ap.quantity > 0 AND ap.status NOT IN ('archived', 'deleted');

-- Index for dashboard queries
CREATE INDEX IF NOT EXISTS idx_algo_positions_with_risk_symbol
ON algo_positions(symbol);

-- Document the view purpose
COMMENT ON MATERIALIZED VIEW algo_positions_with_risk IS
'Critical view for dashboard positions API. Returns all open positions with required fields. Must exist for /api/algo/positions endpoint to return correct data.';
