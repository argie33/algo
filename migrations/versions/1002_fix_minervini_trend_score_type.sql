-- Fix minervini_trend_score column type from INTEGER to NUMERIC
-- minervini_trend_score is calculated as sum of 8 boolean components (0-8 range)
-- and cast to float in load_trend_criteria_data.py, so must be NUMERIC not INTEGER

-- Drop dependent materialized view first
DROP MATERIALIZED VIEW IF EXISTS algo_positions_with_risk CASCADE;

ALTER TABLE trend_template_data
  ALTER COLUMN minervini_trend_score TYPE numeric(5,1);

-- Recreate the materialized view
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
  lp.current_price,
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

  COALESCE(lt.sector, cp.sector, 'Unknown'::VARCHAR) AS sector,
  COALESCE(lt.industry, cp.industry, 'Unknown'::VARCHAR) AS industry,

  lt_tech.minervini_trend_score,
  lt_tech.weinstein_stage,
  lt_tech.percent_from_52w_low,
  lt_tech.percent_from_52w_high,

  CASE
    WHEN lp.current_price IS NULL OR ap.stop_loss_price IS NULL AND ap.current_stop_price IS NULL OR ap.avg_entry_price = 0
    THEN NULL
    WHEN ap.avg_entry_price - COALESCE(ap.stop_loss_price, ap.current_stop_price) <= 0
    THEN NULL
    ELSE (lp.current_price - ap.avg_entry_price) /
         NULLIF(ap.avg_entry_price - COALESCE(ap.stop_loss_price, ap.current_stop_price), 0)
  END::DECIMAL(8, 4) AS r_multiple,

  CASE
    WHEN ap.stop_loss_price IS NULL AND ap.current_stop_price IS NULL
    THEN NULL
    ELSE (ap.avg_entry_price - COALESCE(ap.stop_loss_price, ap.current_stop_price, ap.avg_entry_price))::DECIMAL(12, 4)
  END AS initial_risk_per_share,

  CASE
    WHEN ap.stop_loss_price IS NULL AND ap.current_stop_price IS NULL
    THEN NULL
    ELSE ((ap.avg_entry_price - COALESCE(ap.stop_loss_price, ap.current_stop_price, ap.avg_entry_price)) * ap.quantity)::DECIMAL(14, 2)
  END AS open_risk_dollars,

  CASE
    WHEN lp.current_price IS NULL OR lp.current_price = 0 OR COALESCE(ap.stop_loss_price, ap.current_stop_price) IS NULL
    THEN NULL
    ELSE (lp.current_price - COALESCE(ap.stop_loss_price, ap.current_stop_price)) / NULLIF(lp.current_price, 0) * 100
  END::DECIMAL(8, 4) AS distance_to_stop_pct,

  CASE
    WHEN lp.current_price IS NULL OR lp.current_price = 0 OR lt.target_1_price IS NULL
    THEN NULL
    ELSE (lt.target_1_price - lp.current_price) / NULLIF(lp.current_price, 0) * 100
  END::DECIMAL(8, 4) AS distance_to_t1_pct,

  CASE
    WHEN lp.current_price IS NULL OR lp.current_price = 0 OR lt.target_2_price IS NULL
    THEN NULL
    ELSE (lt.target_2_price - lp.current_price) / NULLIF(lp.current_price, 0) * 100
  END::DECIMAL(8, 4) AS distance_to_t2_pct,

  CASE
    WHEN lp.current_price IS NULL OR lp.current_price = 0 OR lt.target_3_price IS NULL
    THEN NULL
    ELSE (lt.target_3_price - lp.current_price) / NULLIF(lp.current_price, 0) * 100
  END::DECIMAL(8, 4) AS distance_to_t3_pct

FROM algo_positions ap
INNER JOIN latest_prices lp ON ap.symbol = lp.symbol
LEFT JOIN latest_trades lt ON ap.symbol = lt.symbol
LEFT JOIN latest_technical lt_tech ON ap.symbol = lt_tech.symbol
LEFT JOIN company_profile cp ON ap.symbol = cp.ticker
WHERE ap.quantity > 0 AND ap.status NOT IN ('archived', 'deleted');

CREATE UNIQUE INDEX IF NOT EXISTS idx_algo_positions_with_risk_symbol
ON algo_positions_with_risk(symbol);

CREATE INDEX IF NOT EXISTS idx_algo_positions_with_risk_created
ON algo_positions_with_risk(status);

-- Refresh the materialized view immediately
REFRESH MATERIALIZED VIEW algo_positions_with_risk;

-- Update data_loader_status to record this migration
INSERT INTO data_loader_status (table_name, status, last_updated)
VALUES ('trend_template_data', 'SCHEMA_FIXED', NOW())
ON CONFLICT (table_name) DO UPDATE
SET status = 'SCHEMA_FIXED', last_updated = NOW();
