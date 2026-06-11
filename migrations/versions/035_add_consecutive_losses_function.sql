-- Migration 035: Move consecutive losses counting from JavaScript to SQL
-- Creates a function to calculate current consecutive losses from closed trades
-- Eliminates JavaScript loop in /circuit-breakers endpoint

-- Drop existing function if it exists
DROP FUNCTION IF EXISTS calculate_consecutive_losses() CASCADE;

-- Create function to calculate consecutive losses
CREATE OR REPLACE FUNCTION calculate_consecutive_losses()
RETURNS TABLE(consecutive_losses INT) AS $$
BEGIN
  RETURN QUERY
  WITH recent_trades AS (
    SELECT profit_loss_dollars
    FROM algo_trades
    WHERE status = 'closed' AND exit_date IS NOT NULL
    ORDER BY exit_date DESC
    LIMIT 50  -- Check last 50 closed trades
  ),
  consecutive_count AS (
    SELECT COUNT(*) as count
    FROM (
      SELECT profit_loss_dollars
      FROM recent_trades
      WHERE profit_loss_dollars < 0
      -- Stop at first non-losing trade using window function
      AND ROW_NUMBER() OVER (ORDER BY (SELECT 1)) <= (
        SELECT COALESCE(
          (SELECT ROW_NUMBER() OVER (ORDER BY rt2.profit_loss_dollars)
           FROM recent_trades rt2
           WHERE rt2.profit_loss_dollars >= 0
           ORDER BY profit_loss_dollars DESC
           LIMIT 1),
          999  -- If no wins found, return 999 (all are losses)
        )
      )
    ) losing_sequence
  )
  SELECT COALESCE(count, 0)::INT FROM consecutive_count;
END;
$$ LANGUAGE plpgsql STABLE;

-- Create materialized view for circuit breaker metrics (if not exists)
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
  SELECT
    SUM(GREATEST(p.current_price - COALESCE(lt.stop_loss_price, p.current_price), 0) * p.quantity) AS open_risk,
    (SELECT total_portfolio_value FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1) AS port_val
  FROM algo_positions p
  LEFT JOIN (
    SELECT DISTINCT ON (symbol) symbol, stop_loss_price
    FROM algo_trades WHERE status = 'open'
    ORDER BY symbol, trade_date DESC
  ) lt ON lt.symbol = p.symbol
  WHERE p.status = 'open'
),
consec_losses AS (
  SELECT calculate_consecutive_losses() as consecutive_losses
)
SELECT
  ROUND(((pv.peak - ls.total_portfolio_value) / NULLIF(pv.peak, 0)) * 100, 2) AS current_drawdown_pct,
  ROUND(ABS(LEAST(0, ls.daily_return_pct)) * 100, 2) AS daily_loss_pct,
  ROUND(ABS(LEAST(0, wl.sum_daily)) * 100, 2) AS weekly_loss_pct,
  ROUND((COALESCE(opr.open_risk, 0) / NULLIF(opr.port_val, 0)) * 100, 2) AS total_risk_pct,
  cl.consecutive_losses
FROM latest_snap ls
CROSS JOIN peak_value pv
CROSS JOIN weekly_losses wl
CROSS JOIN open_positions_risk opr
CROSS JOIN consec_losses cl;

-- Create index for performance
CREATE INDEX IF NOT EXISTS idx_algo_trades_exit_date
  ON algo_trades(exit_date DESC)
  WHERE status = 'closed' AND exit_date IS NOT NULL;
