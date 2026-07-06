-- Migration 0084: Create algo_positions_with_risk materialized view
-- This view is required by Phase 9 reconciliation
-- Without it, Phase 9 fails when trying to REFRESH MATERIALIZED VIEW

CREATE MATERIALIZED VIEW IF NOT EXISTS algo_positions_with_risk AS
WITH latest_prices AS (
  SELECT DISTINCT ON (symbol) symbol, close AS current_price, date AS price_date
  FROM price_daily
  ORDER BY symbol, date DESC
),
latest_trades AS (
  SELECT DISTINCT ON (symbol) symbol, stop_loss_price, target_1_price, target_1_r_multiple,
         target_2_price, target_2_r_multiple, target_3_price, target_3_r_multiple,
         sector, industry, stage_phase, trade_date
  FROM algo_trades
  ORDER BY symbol, trade_date DESC
),
latest_technical AS (
  SELECT DISTINCT ON (symbol) symbol, minervini_trend_score, weinstein_stage,
         percent_from_52w_low, percent_from_52w_high
  FROM trend_template_data
  ORDER BY symbol, date DESC
)
SELECT ap.id, ap.position_id, ap.symbol, ap.quantity, ap.avg_entry_price,
       lp.current_price, ap.position_value, ap.unrealized_pnl, ap.unrealized_pnl_pct,
       ap.status, ap.stage_in_exit_plan, ap.days_since_entry,
       COALESCE(ap.stop_loss_price, ap.current_stop_price) AS stop_loss_price,
       lt.target_1_price, lt.target_2_price, lt.target_3_price,
       lt.target_1_r_multiple, lt.target_2_r_multiple, lt.target_3_r_multiple,
       COALESCE(lt.sector, cp.sector, 'Unknown'::VARCHAR) AS sector,
       COALESCE(lt.industry, cp.industry, 'Unknown'::VARCHAR) AS industry,
       lt_tech.minervini_trend_score, lt_tech.weinstein_stage,
       lt_tech.percent_from_52w_low, lt_tech.percent_from_52w_high,
       ap.created_at, ap.updated_at
FROM algo_positions ap
LEFT JOIN latest_prices lp ON lp.symbol = ap.symbol
LEFT JOIN latest_trades lt ON lt.symbol = ap.symbol
LEFT JOIN company_profile cp ON cp.ticker = ap.symbol
LEFT JOIN latest_technical lt_tech ON lt_tech.symbol = ap.symbol;
