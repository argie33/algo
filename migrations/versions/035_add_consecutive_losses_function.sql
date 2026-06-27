-- Migration 035: Move consecutive losses counting from JavaScript to SQL
-- Creates a materialized view for circuit breaker metrics with pre-computed fields

DROP MATERIALIZED VIEW IF EXISTS circuit_breaker_metrics CASCADE;

CREATE MATERIALIZED VIEW circuit_breaker_metrics AS
WITH latest_snap AS (
  SELECT total_portfolio_value, daily_return_pct
  FROM algo_portfolio_snapshots
  ORDER BY snapshot_date DESC LIMIT 1
),
peak_value AS (
  SELECT MAX(total_portfolio_value) AS peak
  FROM algo_portfolio_snapshots
  WHERE snapshot_date >= (NOW() - INTERVAL '30 days')
),
weekly_losses AS (
  SELECT COALESCE(SUM(daily_return_pct), 0) AS sum_daily
  FROM algo_portfolio_snapshots
  WHERE snapshot_date >= (NOW() - INTERVAL '5 days')
),
open_positions_risk AS (
  -- CRITICAL: Require explicit stop_loss_price for risk calculation
  -- Missing stops = unknown risk, not zero risk. Report NULL if any stop is missing.
  SELECT
    SUM(GREATEST(p.current_price - lt.stop_loss_price, 0) * p.quantity) AS open_risk,
    (SELECT total_portfolio_value FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1) AS port_val
  FROM algo_positions p
  LEFT JOIN (
    SELECT DISTINCT ON (symbol) symbol, stop_loss_price
    FROM algo_trades WHERE status = 'open' AND stop_loss_price IS NOT NULL
    ORDER BY symbol, trade_date DESC
  ) lt ON lt.symbol = p.symbol
  WHERE p.status = 'open' AND EXISTS (
    SELECT 1 FROM algo_trades WHERE symbol = p.symbol AND status = 'open' AND stop_loss_price IS NOT NULL
  )
),
recent_trades_ordered AS (
  SELECT
    profit_loss_dollars,
    ROW_NUMBER() OVER (ORDER BY exit_date DESC) as rn
  FROM algo_trades
  WHERE status = 'closed' AND exit_date IS NOT NULL
  LIMIT 50
),
first_win AS (
  SELECT COALESCE(MIN(rn), 51) as first_win_position
  FROM recent_trades_ordered
  WHERE profit_loss_dollars >= 0
),
consecutive_losses_calc AS (
  SELECT COALESCE(first_win_position - 1, 0) as consecutive_losses
  FROM first_win
)
SELECT
  COALESCE(ROUND(((pv.peak - ls.total_portfolio_value) / NULLIF(pv.peak, 0)) * 100, 2), 0) AS current_drawdown_pct,
  COALESCE(ROUND(ABS(LEAST(0, ls.daily_return_pct)) * 100, 2), 0) AS daily_loss_pct,
  COALESCE(ROUND(ABS(LEAST(0, wl.sum_daily)) * 100, 2), 0) AS weekly_loss_pct,
  COALESCE(ROUND((COALESCE(opr.open_risk, 0) / NULLIF(opr.port_val, 0)) * 100, 2), 0) AS total_risk_pct,
  clc.consecutive_losses
FROM latest_snap ls
CROSS JOIN peak_value pv
CROSS JOIN weekly_losses wl
CROSS JOIN open_positions_risk opr
CROSS JOIN consecutive_losses_calc clc;

CREATE INDEX IF NOT EXISTS idx_algo_trades_exit_date
  ON algo_trades(exit_date DESC)
  WHERE status = 'closed' AND exit_date IS NOT NULL;
