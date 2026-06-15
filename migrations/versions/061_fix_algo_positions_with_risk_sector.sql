-- Migration 061: Fix algo_positions_with_risk to use company_profile sector as fallback
-- Previously sectors showed 'Unknown' when algo_trades had no sector data for a position.
-- Now falls back to company_profile.sector → company_profile.industry if trade record lacks sector.

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
)
SELECT
  ap.id,
  ap.position_id,
  ap.symbol,
  ap.quantity,
  ap.avg_entry_price,
  COALESCE(lp.current_price, ap.current_price) AS current_price,
  ap.position_value,
  ap.unrealized_pnl,
  ap.unrealized_pnl_pct,
  ap.status,
  ap.stage_in_exit_plan,
  ap.days_since_entry,
  ap.stop_loss_price,

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

  CASE
    WHEN COALESCE(ap.stop_loss_price, 0) = 0 OR ap.avg_entry_price = 0
    THEN NULL
    ELSE (ap.avg_entry_price - COALESCE(ap.stop_loss_price, ap.avg_entry_price)) / NULLIF(ap.avg_entry_price, 0)
  END::DECIMAL(8, 4) AS r_multiple,

  CASE
    WHEN COALESCE(ap.stop_loss_price, 0) = 0
    THEN NULL
    ELSE (ap.avg_entry_price - COALESCE(ap.stop_loss_price, ap.avg_entry_price))::DECIMAL(12, 4)
  END AS initial_risk_per_share,

  CASE
    WHEN COALESCE(ap.stop_loss_price, 0) = 0
    THEN 0
    ELSE ((ap.avg_entry_price - COALESCE(ap.stop_loss_price, ap.avg_entry_price)) * ap.quantity)::DECIMAL(14, 2)
  END AS open_risk_dollars,

  CASE
    WHEN COALESCE(lp.current_price, ap.current_price) = 0 OR COALESCE(ap.stop_loss_price, 0) = 0
    THEN NULL
    ELSE (COALESCE(lp.current_price, ap.current_price) - COALESCE(ap.stop_loss_price, ap.current_price)) / NULLIF(COALESCE(lp.current_price, ap.current_price), 0) * 100
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
WHERE ap.quantity > 0 AND ap.status NOT IN ('archived', 'deleted');

CREATE INDEX IF NOT EXISTS idx_algo_positions_with_risk_symbol
ON algo_positions(symbol);
