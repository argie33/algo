-- ════════════════════════════════════════════════════════════════════════════
-- MIGRATION: 046_create_portfolio_exposure_daily
-- ════════════════════════════════════════════════════════════════════════════
--
-- PURPOSE: Create pre-computed daily portfolio exposure metrics table to provide
-- comprehensive portfolio overview without real-time aggregations.
--
-- SCHEMA:
-- - date: Trading date (primary key)
-- - total_portfolio_value: Total portfolio capital (cash + positions)
-- - total_position_value: Sum of all open position values
-- - cash_available: Available cash = portfolio - positions
-- - total_position_count: Number of open positions
-- - avg_position_value: Average position size
-- - avg_days_in_trade: Average holding period
-- - portfolio_heat: Risk level ("cold", "warm", "hot")
-- - largest_position_pct: Concentration risk (largest position %)
-- - total_unrealized_pnl_pct: Portfolio-wide unrealized win %
-- - avg_stop_distance_r: Average R per position
--
-- CONSUMED BY: Dashboard fetch_portfolio(), panel_portfolio_summary()
--
-- CREATED: 2026-06-12

CREATE TABLE IF NOT EXISTS portfolio_exposure_daily (
  date DATE PRIMARY KEY,
  total_portfolio_value DECIMAL(15, 2) NOT NULL,
  total_position_value DECIMAL(15, 2),
  cash_available DECIMAL(15, 2),
  total_position_count INTEGER,
  avg_position_value DECIMAL(15, 2),
  avg_days_in_trade DECIMAL(8, 2),
  portfolio_heat VARCHAR(20),
  largest_position_pct DECIMAL(8, 4),
  total_unrealized_pnl_pct DECIMAL(8, 4),
  avg_stop_distance_r DECIMAL(8, 4),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE portfolio_exposure_daily IS
'Pre-computed daily portfolio exposure metrics. Eliminates real-time aggregation of portfolio snapshot. Updated by loaders when positions/portfolio updated.';

COMMENT ON COLUMN portfolio_exposure_daily.date IS
'Trading date (primary key). One aggregated portfolio state per trading day.';

COMMENT ON COLUMN portfolio_exposure_daily.total_portfolio_value IS
'Total portfolio value including cash and positions. Source: algo_portfolio table.';

COMMENT ON COLUMN portfolio_exposure_daily.total_position_value IS
'Sum of all open position values. = SUM(algo_positions.position_value WHERE status="open").';

COMMENT ON COLUMN portfolio_exposure_daily.cash_available IS
'Available cash = total_portfolio_value - total_position_value. Liquidity indicator.';

COMMENT ON COLUMN portfolio_exposure_daily.total_position_count IS
'Number of open positions. Position count indicator.';

COMMENT ON COLUMN portfolio_exposure_daily.avg_position_value IS
'Average position size = total_position_value / total_position_count. Size distribution.';

COMMENT ON COLUMN portfolio_exposure_daily.avg_days_in_trade IS
'Average number of days positions have been held. Trade age indicator.';

COMMENT ON COLUMN portfolio_exposure_daily.portfolio_heat IS
'Risk/volatility level: "cold" (< 20%), "warm" (20-40%), "hot" (> 40%). Based on portfolio variance.';

COMMENT ON COLUMN portfolio_exposure_daily.largest_position_pct IS
'Largest position as % of total portfolio. Concentration risk metric.';

COMMENT ON COLUMN portfolio_exposure_daily.total_unrealized_pnl_pct IS
'Portfolio-wide unrealized profit/loss %. = (SUM(unrealized_pnl)) / (SUM(entry_value)) * 100.';

COMMENT ON COLUMN portfolio_exposure_daily.avg_stop_distance_r IS
'Average risk per position. = AVG((entry - stop) / (target - entry)).';

CREATE INDEX IF NOT EXISTS idx_portfolio_exposure_date
  ON portfolio_exposure_daily(date DESC);

-- Add constraint for portfolio_heat enum
ALTER TABLE portfolio_exposure_daily
ADD CONSTRAINT check_portfolio_heat
CHECK (portfolio_heat IN ('cold', 'warm', 'hot'));

-- Backfill template record (optional, once loaders implemented)
-- INSERT INTO portfolio_exposure_daily
-- (date, total_portfolio_value, total_position_value, cash_available,
--  total_position_count, avg_position_value, avg_days_in_trade,
--  portfolio_heat, largest_position_pct, total_unrealized_pnl_pct, avg_stop_distance_r)
-- SELECT
--   CURRENT_DATE,
--   (SELECT total_balance FROM algo_portfolio WHERE portfolio_id = 1),
--   (SELECT SUM(position_value) FROM algo_positions WHERE status = 'open'),
--   (SELECT total_balance FROM algo_portfolio WHERE portfolio_id = 1) - (SELECT COALESCE(SUM(position_value), 0) FROM algo_positions WHERE status = 'open'),
--   (SELECT COUNT(*) FROM algo_positions WHERE status = 'open'),
--   (SELECT AVG(position_value) FROM algo_positions WHERE status = 'open'),
--   (SELECT AVG(EXTRACT(DAY FROM (CURRENT_DATE - date_entered))) FROM algo_positions WHERE status = 'open'),
--   'warm',
--   (SELECT MAX(position_value) / (SELECT total_balance FROM algo_portfolio WHERE portfolio_id = 1) * 100 FROM algo_positions WHERE status = 'open'),
--   (SELECT SUM(unrealized_pnl) / SUM(entry_value) * 100 FROM algo_positions WHERE status = 'open'),
--   (SELECT AVG((avg_entry_price - COALESCE(stop_loss_price, avg_entry_price)) / (COALESCE(target_1_price, avg_entry_price) - avg_entry_price)) FROM algo_positions WHERE status = 'open')
-- ON CONFLICT (date) DO NOTHING;
