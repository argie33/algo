-- ════════════════════════════════════════════════════════════════════════════
-- MIGRATION: 043_create_equity_curve_daily
-- ════════════════════════════════════════════════════════════════════════════
--
-- PURPOSE: Create pre-computed daily equity curve metrics table to eliminate
-- O(n²) Sharpe/Sortino calculations and O(n) max drawdown in dashboard.
--
-- SCHEMA:
-- - date: Trading day (primary key)
-- - total_portfolio_value: EOD portfolio value
-- - daily_return_pct: Daily percentage return
-- - daily_return_dollars: Daily dollar return
-- - rolling_sharpe_252d: 252-day rolling Sharpe ratio
-- - rolling_sortino_252d: 252-day rolling Sortino ratio
-- - max_drawdown_ytd_pct: Year-to-date max drawdown
-- - calmar_ratio: Annual return / max drawdown
--
-- CONSUMED BY: Dashboard fetch_perf(), panel_perf_metrics()
--
-- CREATED: 2026-06-12

CREATE TABLE IF NOT EXISTS equity_curve_daily (
  date DATE PRIMARY KEY,
  total_portfolio_value DECIMAL(15, 2) NOT NULL,
  daily_return_pct DECIMAL(8, 4),
  daily_return_dollars DECIMAL(15, 2),
  rolling_sharpe_252d DECIMAL(8, 4),
  rolling_sortino_252d DECIMAL(8, 4),
  max_drawdown_ytd_pct DECIMAL(8, 4),
  calmar_ratio DECIMAL(8, 4),
  equity_curve_sparkline TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE equity_curve_daily IS
'Pre-computed daily equity curve metrics. Eliminates O(n²) Sharpe/Sortino calculations in dashboard fetch_perf(). Updated by loaders EOD.';

COMMENT ON COLUMN equity_curve_daily.date IS
'Trading date (primary key). Ensures one record per trading day.';

COMMENT ON COLUMN equity_curve_daily.total_portfolio_value IS
'Portfolio value at end of trading day. Source: algo_portfolio_snapshots aggregation.';

COMMENT ON COLUMN equity_curve_daily.daily_return_pct IS
'Daily percentage return: (today_value - yesterday_value) / yesterday_value * 100.';

COMMENT ON COLUMN equity_curve_daily.rolling_sharpe_252d IS
'252-day rolling Sharpe ratio. Pre-computed to eliminate O(n) stat calculations.';

COMMENT ON COLUMN equity_curve_daily.rolling_sortino_252d IS
'252-day rolling Sortino ratio (downside volatility). Pre-computed to eliminate O(n) stat calculations.';

COMMENT ON COLUMN equity_curve_daily.max_drawdown_ytd_pct IS
'Year-to-date maximum drawdown as percentage. Resets on 2026-01-01.';

COMMENT ON COLUMN equity_curve_daily.calmar_ratio IS
'Calmar ratio: annual return / max drawdown YTD. Risk-adjusted return metric.';

COMMENT ON COLUMN equity_curve_daily.equity_curve_sparkline IS
'Last 7-day sparkline for terminal display. Pre-computed characters (▁▂▃▄▅▆▇█).';

CREATE INDEX IF NOT EXISTS idx_equity_curve_date
  ON equity_curve_daily(date DESC);

-- Backfill from existing snapshots (optional, remove if data not yet available)
-- WITH daily_values AS (
--   SELECT DISTINCT ON (DATE(snapshot_date))
--     DATE(snapshot_date) as date,
--     total_portfolio_value,
--     daily_return_pct
--   FROM algo_portfolio_snapshots
--   WHERE snapshot_date >= CURRENT_DATE - INTERVAL '365 days'
--   ORDER BY DATE(snapshot_date) DESC, snapshot_date DESC
-- )
-- INSERT INTO equity_curve_daily (date, total_portfolio_value, daily_return_pct)
-- SELECT date, total_portfolio_value, daily_return_pct FROM daily_values
-- ON CONFLICT (date) DO NOTHING;
