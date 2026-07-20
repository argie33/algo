-- Migration 104: Add general data_unavailable flag to market_health_daily
-- GOVERNANCE COMPLIANCE: market_health_daily must have a general data_unavailable flag
-- to indicate when the entire row (market_stage, market_trend, etc.) is unavailable
--
-- Previous specific flags (put_call_ratio_data_unavailable, etc.) only mark individual fields.
-- This flag marks the entire row as unavailable when the loader fails completely.
-- Per GOVERNANCE.md: "Every record must have `data_unavailable` flag (BOOLEAN, default FALSE)"
-- ═══════════════════════════════════════════════════════════════════════════════

ALTER TABLE market_health_daily
ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE;

ALTER TABLE market_health_daily
ADD COLUMN IF NOT EXISTS reason VARCHAR(255);

-- Index for queries that filter on data_unavailable
CREATE INDEX IF NOT EXISTS idx_market_health_daily_data_unavailable
ON market_health_daily(date DESC, data_unavailable);

ANALYZE market_health_daily;
