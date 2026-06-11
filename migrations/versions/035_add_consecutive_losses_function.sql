-- Migration 035: Move consecutive losses counting from JavaScript to SQL
-- Creates a function to calculate current consecutive losses from closed trades
-- Also creates a materialized view for circuit breaker metrics

DROP FUNCTION IF EXISTS calculate_consecutive_losses() CASCADE;
DROP MATERIALIZED VIEW IF EXISTS circuit_breaker_metrics CASCADE;

CREATE FUNCTION calculate_consecutive_losses()
RETURNS TABLE(consecutive_losses INT) AS
$$
  WITH recent_trades AS (
    SELECT profit_loss_dollars
    FROM algo_trades
    WHERE status = 'closed' AND exit_date IS NOT NULL
    ORDER BY exit_date DESC
    LIMIT 50
  ),
  losing_streak AS (
    SELECT COUNT(*) as consecutive_loss_count
    FROM (
      SELECT 1
      FROM recent_trades
      WHERE profit_loss_dollars < 0
      ORDER BY rowid
      LIMIT CASE
        WHEN (
          SELECT COUNT(*) FROM recent_trades
          WHERE profit_loss_dollars < 0
          UNION ALL
          SELECT 0
        ) = 0 THEN 50
        ELSE (
          SELECT COUNT(*) FROM (
            SELECT 1 FROM recent_trades
            WHERE profit_loss_dollars < 0
          ) t1
        )
      END
    ) t
  )
  SELECT consecutive_loss_count::INT FROM losing_streak
$$
LANGUAGE SQL STABLE;

-- Create materialized view for circuit breaker metrics
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
consecutive_losses_calc AS (
  SELECT COALESCE((
    SELECT COUNT(*) FROM (
      SELECT 1 FROM (
        SELECT profit_loss_dollars
        FROM algo_trades
        WHERE status = 'closed' AND exit_date IS NOT NULL
        ORDER BY exit_date DESC
        LIMIT 50
      ) recent
      WHERE profit_loss_dollars < 0
    ) losing
  ), 0) AS consecutive_losses
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
