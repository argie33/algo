-- Migration 082: Add company_name to algo_positions_with_risk view
-- The terminal dashboard positions panel now shows company names.
-- company_profile is already joined in the view; this adds the name field.

DROP MATERIALIZED VIEW IF EXISTS algo_positions_with_risk;

CREATE MATERIALIZED VIEW algo_positions_with_risk AS
WITH latest_prices AS (
  SELECT DISTINCT ON (symbol)
    symbol,
    close AS current_price,
    date AS price_date
  FROM price_daily
  ORDER BY symbol, date DESC
),
latest_trades AS (
  SELECT DISTINCT ON (symbol)
    symbol,
    stop_loss_price,
    target_1_price,
    target_1_r_multiple,
    target_2_price,
    target_2_r_multiple,
    target_3_price,
    target_3_r_multiple,
    sector,
    industry,
    stage_phase,
    trade_date
  FROM algo_trades
  ORDER BY symbol, trade_date DESC
),
latest_technical AS (
  SELECT DISTINCT ON (symbol)
    symbol,
    minervini_trend_score,
    weinstein_stage,
    percent_from_52w_low,
    percent_from_52w_high
  FROM trend_template_data
  ORDER BY symbol, date DESC
),
latest_swing AS (
  SELECT DISTINCT ON (symbol)
    symbol,
    score AS swing_score
  FROM swing_trader_scores
  ORDER BY symbol, date DESC
)
SELECT
  ap.id,
  ap.position_id,
  ap.symbol,
  COALESCE(cp.long_name, cp.short_name, ap.symbol) AS company_name,
  ap.quantity,
  ap.avg_entry_price,
  COALESCE(lp.current_price, ap.current_price) AS current_price,
  ap.position_value,
  ap.unrealized_pnl,
  ap.unrealized_pnl_pct,
  ap.status,
  ap.stage_in_exit_plan,
  ap.days_since_entry,

  COALESCE(ap.stop_loss_price, ap.current_stop_price) AS stop_loss_price,

  lt.target_1_price,
  lt.target_2_price,
  lt.target_3_price,
  lt.target_1_r_multiple,
  lt.target_2_r_multiple,
  lt.target_3_r_multiple,

  COALESCE(lt.sector, cp.sector, 'Unknown') AS sector,
  COALESCE(lt.industry, cp.industry, 'Unknown') AS industry,

  lt_tech.minervini_trend_score,
  lt_tech.weinstein_stage,
  lt_tech.percent_from_52w_low,
  lt_tech.percent_from_52w_high,

  ls.swing_score,

  -- Current R-multiple: (current_price - entry) / initial_risk_per_share
  -- Positive = profitable, negative = at loss. NULL if no valid stop.
  CASE
    WHEN COALESCE(ap.stop_loss_price, ap.current_stop_price, 0) = 0 OR ap.avg_entry_price = 0
    THEN NULL
    WHEN ap.avg_entry_price - COALESCE(ap.stop_loss_price, ap.current_stop_price) <= 0
    THEN NULL
    ELSE (COALESCE(lp.current_price, ap.current_price) - ap.avg_entry_price) /
         NULLIF(ap.avg_entry_price - COALESCE(ap.stop_loss_price, ap.current_stop_price), 0)
  END::DECIMAL(8, 4) AS r_multiple,

  -- Initial risk per share: how much we risk if stopped out
  CASE
    WHEN COALESCE(ap.stop_loss_price, ap.current_stop_price, 0) = 0
    THEN NULL
    ELSE (ap.avg_entry_price - COALESCE(ap.stop_loss_price, ap.current_stop_price, ap.avg_entry_price))::DECIMAL(12, 4)
  END AS initial_risk_per_share,

  -- Total open risk in dollars
  CASE
    WHEN COALESCE(ap.stop_loss_price, ap.current_stop_price, 0) = 0
    THEN 0
    ELSE ((ap.avg_entry_price - COALESCE(ap.stop_loss_price, ap.current_stop_price, ap.avg_entry_price)) * ap.quantity)::DECIMAL(14, 2)
  END AS open_risk_dollars,

  -- Distance from current price to stop (positive = still above stop, negative = breached)
  CASE
    WHEN COALESCE(lp.current_price, ap.current_price) = 0 OR COALESCE(ap.stop_loss_price, ap.current_stop_price, 0) = 0
    THEN NULL
    ELSE (COALESCE(lp.current_price, ap.current_price) - COALESCE(ap.stop_loss_price, ap.current_stop_price, ap.current_price)) / NULLIF(COALESCE(lp.current_price, ap.current_price), 0) * 100
  END::DECIMAL(8, 4) AS distance_to_stop_pct,

  CASE
    WHEN COALESCE(lp.current_price, ap.current_price) = 0 OR lt.target_1_price IS NULL
    THEN NULL
    ELSE (lt.target_1_price - COALESCE(lp.current_price, ap.current_price)) / NULLIF(COALESCE(lp.current_price, ap.current_price), 0) * 100
  END::DECIMAL(8, 4) AS distance_to_t1_pct,

  CASE
    WHEN COALESCE(lp.current_price, ap.current_price) = 0 OR lt.target_2_price IS NULL
    THEN NULL
    ELSE (lt.target_2_price - COALESCE(lp.current_price, ap.current_price)) / NULLIF(COALESCE(lp.current_price, ap.current_price), 0) * 100
  END::DECIMAL(8, 4) AS distance_to_t2_pct,

  CASE
    WHEN COALESCE(lp.current_price, ap.current_price) = 0 OR lt.target_3_price IS NULL
    THEN NULL
    ELSE (lt.target_3_price - COALESCE(lp.current_price, ap.current_price)) / NULLIF(COALESCE(lp.current_price, ap.current_price), 0) * 100
  END::DECIMAL(8, 4) AS distance_to_t3_pct

FROM algo_positions ap
LEFT JOIN latest_prices lp ON ap.symbol = lp.symbol
LEFT JOIN latest_trades lt ON ap.symbol = lt.symbol
LEFT JOIN latest_technical lt_tech ON ap.symbol = lt_tech.symbol
LEFT JOIN company_profile cp ON ap.symbol = cp.ticker
LEFT JOIN latest_swing ls ON ap.symbol = ls.symbol
WHERE ap.quantity > 0 AND ap.status NOT IN ('archived', 'deleted');

CREATE INDEX IF NOT EXISTS idx_algo_positions_with_risk_symbol
ON algo_positions(symbol);
