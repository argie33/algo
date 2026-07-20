-- Migration 1133: Fix running_peak backfill for all historical snapshots
-- Date: 2026-07-20
--
-- ISSUE: Only 2 of 559 portfolio snapshots have running_peak populated.
-- Migration 042 was supposed to backfill all historical values but failed/incomplete.
--
-- SIGNS INCONSISTENT:
-- - Migration 042 calculated drawdown_pct as NEGATIVE
-- - Reconciliation code calculates as POSITIVE
-- - Need to standardize to POSITIVE per circuit breaker expectations
--
-- FIX:
-- 1. Backfill running_peak for ALL snapshots (using chronological max)
-- 2. Standardize drawdown_pct to be POSITIVE (consistent with circuit breaker code)
-- 3. Recalculate for all 559 snapshots

BEGIN;

-- First, clear and recalculate all running_peak and drawdown_pct values
UPDATE algo_portfolio_snapshots
SET
  running_peak = NULL,
  drawdown_pct = NULL;

-- Recalculate running_peak as max portfolio_value up to and including this date
WITH peak_calc AS (
  SELECT
    id,
    snapshot_date,
    total_portfolio_value,
    MAX(total_portfolio_value) OVER (
      ORDER BY snapshot_date
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) as calculated_peak
  FROM algo_portfolio_snapshots
  WHERE total_portfolio_value > 0
)
UPDATE algo_portfolio_snapshots
SET
  running_peak = pc.calculated_peak,
  drawdown_pct = CASE
    WHEN pc.calculated_peak > 0
      THEN ((pc.calculated_peak - pc.total_portfolio_value) / pc.calculated_peak * 100)::DECIMAL(8, 4)
    ELSE 0
  END
FROM peak_calc pc
WHERE algo_portfolio_snapshots.id = pc.id;

-- Verify the backfill worked
-- SELECT COUNT(*) as total_snapshots,
--        COUNT(*) FILTER (WHERE running_peak IS NOT NULL) as with_peak,
--        COUNT(*) FILTER (WHERE drawdown_pct IS NOT NULL) as with_drawdown,
--        MAX(running_peak) as max_peak,
--        MIN(drawdown_pct) as min_drawdown,
--        MAX(drawdown_pct) as max_drawdown
-- FROM algo_portfolio_snapshots;

COMMIT;
