-- Migration 103: Add data_unavailable columns to market_health_daily
-- Fixes schema mismatch: load_market_health_daily writes these columns but they don't exist in the DB
-- BulkInsertManager silently skips them (warning in logs); this migration adds them properly
-- ════════════════════════════════════════════════════════════════════════════

ALTER TABLE market_health_daily
ADD COLUMN IF NOT EXISTS put_call_ratio_data_unavailable BOOLEAN DEFAULT FALSE;

ALTER TABLE market_health_daily
ADD COLUMN IF NOT EXISTS put_call_ratio_unavailable_reason VARCHAR(255);

ALTER TABLE market_health_daily
ADD COLUMN IF NOT EXISTS yield_curve_data_unavailable BOOLEAN DEFAULT FALSE;

ALTER TABLE market_health_daily
ADD COLUMN IF NOT EXISTS yield_curve_unavailable_reason VARCHAR(255);

ALTER TABLE market_health_daily
ADD COLUMN IF NOT EXISTS fed_rate_data_unavailable BOOLEAN DEFAULT FALSE;

ALTER TABLE market_health_daily
ADD COLUMN IF NOT EXISTS fed_rate_unavailable_reason VARCHAR(255);

ANALYZE market_health_daily;
