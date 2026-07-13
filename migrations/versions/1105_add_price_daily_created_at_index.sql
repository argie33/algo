-- Migration 1105: Add index on price_daily.created_at
--
-- /api/health/pipeline computes MAX(created_at) over price_daily (8.6M+ rows,
-- growing daily) to report loader freshness. With no index on created_at,
-- Postgres has no way to satisfy MAX() without a full sequential scan, which
-- combined with the other UNION ALL branches reliably exceeded the endpoint's
-- 15s statement_timeout ("QueryCanceled: canceling statement due to statement
-- timeout"). An index lets the planner satisfy MAX(created_at) with a
-- backward index-only scan (LIMIT 1) instead.

CREATE INDEX IF NOT EXISTS idx_price_daily_created_at ON price_daily(created_at DESC);
