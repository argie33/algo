-- ════════════════════════════════════════════════════════════════════════════
-- MIGRATION: 040_algo_positions_with_risk_view
-- ════════════════════════════════════════════════════════════════════════════
--
-- PURPOSE: Create the algo_positions_with_risk view that enriches positions
-- with stop/target levels, sector, technical scores, and risk metrics.
--
-- FIXES:
-- - Issue #1: Sector allocation data now available for dashboard
-- - Issue #2: R-ladder percentages can be computed from complete data
-- - Issue #3: Distance-to-target fields now available for position health table
--
-- CREATED: 2026-06-11

-- Drop any existing relation (table, view, or materialized view) by the same name.
-- In PostgreSQL, DROP TABLE/MATERIALIZED VIEW with IF EXISTS still errors when the
-- relation exists but is the wrong type. Use a DO block to detect the relkind first.
DO $$
DECLARE v_relkind char;
BEGIN
    SELECT relkind INTO v_relkind
    FROM pg_class
    WHERE relname = 'algo_positions_with_risk'
      AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public');
    IF v_relkind = 'r' THEN
        EXECUTE 'DROP TABLE algo_positions_with_risk CASCADE';
    ELSIF v_relkind IN ('m', 'v') THEN
        EXECUTE 'DROP MATERIALIZED VIEW algo_positions_with_risk CASCADE';
    END IF;
END $$;

CREATE MATERIALIZED VIEW algo_positions_with_risk AS
WITH latest_prices AS (
  -- Get most recent price for each symbol
  SELECT DISTINCT ON (symbol)
    symbol,
    close as current_price,
    date as price_date
  FROM price_daily
  ORDER BY symbol, date DESC
),
latest_trades AS (
  -- Get the most recent trade for each symbol (not filtered by status)
  -- This gives us stops, targets, sector, and stage info
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
  -- Get the most recent technical data for each symbol
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
  COALESCE(lp.current_price, ap.current_price) as current_price,
  ap.position_value,
  ap.unrealized_pnl,
  ap.unrealized_pnl_pct,
  ap.status,
  ap.stage_in_exit_plan,
  ap.days_since_entry,

  -- Stop and target levels (from latest trade)
  -- CRITICAL: Keep NULL for missing stop_loss_price (don't default to 0)
  -- A stop loss of 0 would liquidate position immediately — this must fail-fast
  lt.stop_loss_price::DECIMAL(12, 4) as stop_loss_price,
  lt.target_1_price,
  lt.target_2_price,
  lt.target_3_price,
  lt.target_1_r_multiple,
  lt.target_2_r_multiple,
  lt.target_3_r_multiple,

  -- Sector and industry context
  COALESCE(lt.sector, 'Unknown') as sector,
  COALESCE(lt.industry, 'Unknown') as industry,

  -- Technical scores from latest data
  lt_tech.minervini_trend_score,
  lt_tech.weinstein_stage,
  lt_tech.percent_from_52w_low,
  lt_tech.percent_from_52w_high,

  -- R-multiple calculation (entry - stop relative to position value)
  -- CRITICAL: Require stop_loss_price to be explicitly set (NULL if missing)
  CASE
    WHEN lt.stop_loss_price IS NULL OR ap.avg_entry_price <= 0
    THEN NULL
    ELSE (ap.avg_entry_price - lt.stop_loss_price) / NULLIF(ap.avg_entry_price, 0)
  END::DECIMAL(8, 4) as r_multiple,

  -- Initial risk per share (entry - stop)
  -- CRITICAL: Require explicit stop_loss_price (NULL if missing)
  CASE
    WHEN lt.stop_loss_price IS NULL OR ap.avg_entry_price <= 0
    THEN NULL
    ELSE (ap.avg_entry_price - lt.stop_loss_price)::DECIMAL(12, 4)
  END as initial_risk_per_share,

  -- Open risk in dollars (initial_risk_per_share × quantity)
  -- CRITICAL: Require explicit stop_loss_price (NULL if missing)
  CASE
    WHEN lt.stop_loss_price IS NULL OR ap.avg_entry_price <= 0
    THEN NULL
    ELSE ((ap.avg_entry_price - lt.stop_loss_price) * ap.quantity)::DECIMAL(14, 2)
  END as open_risk_dollars,

  -- Distance to stop/target levels (percentage distance, always positive)
  -- Formatted as: distance_to_stop = (current - stop) / current * 100 (cushion to stop)
  --                distance_to_tx = (target - current) / current * 100 (distance to target)
  -- CRITICAL: Require explicit stop_loss_price (NULL if missing)
  CASE
    WHEN COALESCE(lp.current_price, ap.current_price) = 0 OR lt.stop_loss_price IS NULL
    THEN NULL
    ELSE (COALESCE(lp.current_price, ap.current_price) - lt.stop_loss_price) / NULLIF(COALESCE(lp.current_price, ap.current_price), 0) * 100
  END::DECIMAL(8, 4) as distance_to_stop_pct,

  CASE
    WHEN COALESCE(lp.current_price, ap.current_price) = 0 OR lt.target_1_price IS NULL
    THEN NULL
    ELSE (lt.target_1_price - COALESCE(lp.current_price, ap.current_price)) / NULLIF(COALESCE(lp.current_price, ap.current_price), 0) * 100
  END::DECIMAL(8, 4) as distance_to_t1_pct,

  CASE
    WHEN COALESCE(lp.current_price, ap.current_price) = 0 OR lt.target_2_price IS NULL
    THEN NULL
    ELSE (lt.target_2_price - COALESCE(lp.current_price, ap.current_price)) / NULLIF(COALESCE(lp.current_price, ap.current_price), 0) * 100
  END::DECIMAL(8, 4) as distance_to_t2_pct,

  CASE
    WHEN COALESCE(lp.current_price, ap.current_price) = 0 OR lt.target_3_price IS NULL
    THEN NULL
    ELSE (lt.target_3_price - COALESCE(lp.current_price, ap.current_price)) / NULLIF(COALESCE(lp.current_price, ap.current_price), 0) * 100
  END::DECIMAL(8, 4) as distance_to_t3_pct

FROM algo_positions ap
LEFT JOIN latest_prices lp ON ap.symbol = lp.symbol
LEFT JOIN latest_trades lt ON ap.symbol = lt.symbol
LEFT JOIN latest_technical lt_tech ON ap.symbol = lt_tech.symbol
WHERE ap.quantity > 0 AND ap.status NOT IN ('archived', 'deleted');

-- Create index for performance
CREATE INDEX IF NOT EXISTS idx_algo_positions_with_risk_symbol
ON algo_positions(symbol);

COMMENT ON MATERIALIZED VIEW algo_positions_with_risk IS
'Enriched positions with stops, targets, sector, technical scores, and risk metrics. Single source of truth for dashboard.';
