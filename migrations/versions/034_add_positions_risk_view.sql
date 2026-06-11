-- Migration 034: Move position-level risk calculations from API to database
-- Creates a materialized view that pre-computes all risk metrics
-- Allows API layer to be a pure display layer (not calculation engine)

-- Drop existing view if it exists (for re-runs/updates)
DROP MATERIALIZED VIEW IF EXISTS algo_positions_with_risk CASCADE;

-- Create materialized view with all risk calculations computed in SQL
CREATE MATERIALIZED VIEW algo_positions_with_risk AS
WITH latest_trade AS (
  SELECT DISTINCT ON (symbol)
    symbol,
    stop_loss_price,
    target_1_price,
    target_2_price,
    target_3_price,
    target_1_r_multiple,
    target_2_r_multiple,
    target_3_r_multiple,
    signal_date
  FROM algo_trades
  WHERE status = 'open'
  ORDER BY symbol, trade_date DESC
),
latest_trend AS (
  SELECT DISTINCT ON (symbol)
    symbol,
    weinstein_stage,
    minervini_trend_score,
    percent_from_52w_low,
    percent_from_52w_high
  FROM trend_template_data
  ORDER BY symbol, date DESC
)
SELECT
  p.position_id,
  p.id,
  p.symbol,
  p.quantity,
  p.avg_entry_price,
  p.current_price,
  p.position_value,
  p.unrealized_pnl,
  p.unrealized_pnl_pct,
  p.status,
  p.stage_in_exit_plan,
  p.days_since_entry,

  -- Stop & targets from latest_trade
  lt.stop_loss_price,
  lt.target_1_price,
  lt.target_2_price,
  lt.target_3_price,
  lt.target_1_r_multiple,
  lt.target_2_r_multiple,
  lt.target_3_r_multiple,

  -- Company profile
  cp.sector,
  cp.industry,

  -- Technical indicators
  ltt.weinstein_stage,
  ltt.minervini_trend_score,
  ltt.percent_from_52w_low,
  ltt.percent_from_52w_high,

  -- ═══════════════════════════════════════════════════════════════════════
  -- COMPUTED RISK METRICS (previously calculated in Node.js)
  -- ═══════════════════════════════════════════════════════════════════════

  -- Initial Risk per Share: entry - stop (raw dollar risk per share)
  CASE
    WHEN p.avg_entry_price IS NOT NULL AND lt.stop_loss_price IS NOT NULL
      AND p.avg_entry_price > lt.stop_loss_price
    THEN p.avg_entry_price - lt.stop_loss_price
    ELSE NULL
  END AS initial_risk_per_share,

  -- R-Multiple: (current - entry) / (entry - stop)
  -- Measures how many risk units the trade has moved in our favor/against us
  CASE
    WHEN p.avg_entry_price IS NOT NULL
      AND lt.stop_loss_price IS NOT NULL
      AND p.current_price IS NOT NULL
      AND p.avg_entry_price > lt.stop_loss_price
      AND (p.avg_entry_price - lt.stop_loss_price) > 0
    THEN ROUND((p.current_price - p.avg_entry_price)::NUMERIC /
              (p.avg_entry_price - lt.stop_loss_price), 2)
    ELSE NULL
  END AS r_multiple,

  -- Open Risk Dollars: (current - stop) * quantity
  -- Total dollars at risk if stop is hit NOW
  CASE
    WHEN p.current_price IS NOT NULL
      AND lt.stop_loss_price IS NOT NULL
      AND p.quantity IS NOT NULL
    THEN ROUND(
      GREATEST(0, p.current_price - lt.stop_loss_price)::NUMERIC *
      p.quantity, 2)
    ELSE NULL
  END AS open_risk_dollars,

  -- Distance to Stop (percentage): (current - stop) / current * 100
  -- How close we are to hitting the stop loss
  CASE
    WHEN p.current_price IS NOT NULL
      AND lt.stop_loss_price IS NOT NULL
      AND p.current_price > 0
    THEN ROUND(
      ((p.current_price - lt.stop_loss_price)::NUMERIC / p.current_price) * 100, 2)
    ELSE NULL
  END AS distance_to_stop_pct,

  -- Distance to Target 1 (percentage): (t1 - current) / current * 100
  CASE
    WHEN p.current_price IS NOT NULL
      AND lt.target_1_price IS NOT NULL
      AND p.current_price > 0
    THEN ROUND(
      ((lt.target_1_price - p.current_price)::NUMERIC / p.current_price) * 100, 2)
    ELSE NULL
  END AS distance_to_t1_pct,

  -- Distance to Target 2 (percentage): (t2 - current) / current * 100
  CASE
    WHEN p.current_price IS NOT NULL
      AND lt.target_2_price IS NOT NULL
      AND p.current_price > 0
    THEN ROUND(
      ((lt.target_2_price - p.current_price)::NUMERIC / p.current_price) * 100, 2)
    ELSE NULL
  END AS distance_to_t2_pct,

  -- Distance to Target 3 (percentage): (t3 - current) / current * 100
  CASE
    WHEN p.current_price IS NOT NULL
      AND lt.target_3_price IS NOT NULL
      AND p.current_price > 0
    THEN ROUND(
      ((lt.target_3_price - p.current_price)::NUMERIC / p.current_price) * 100, 2)
    ELSE NULL
  END AS distance_to_t3_pct

FROM algo_positions p
LEFT JOIN latest_trade lt ON lt.symbol = p.symbol
LEFT JOIN company_profile cp ON cp.ticker = p.symbol
LEFT JOIN latest_trend ltt ON ltt.symbol = p.symbol
WHERE p.status = 'open'
ORDER BY p.position_value DESC;

-- Create indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_algo_positions_with_risk_symbol
  ON algo_positions_with_risk(symbol);
CREATE INDEX IF NOT EXISTS idx_algo_positions_with_risk_position_id
  ON algo_positions_with_risk(position_id);
