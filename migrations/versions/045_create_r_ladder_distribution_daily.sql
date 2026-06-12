-- ════════════════════════════════════════════════════════════════════════════
-- MIGRATION: 045_create_r_ladder_distribution_daily
-- ════════════════════════════════════════════════════════════════════════════
--
-- PURPOSE: Create pre-computed daily R-ladder distribution table to eliminate
-- real-time R-multiple bucketing logic and enable historical risk tracking.
--
-- SCHEMA:
-- - date: Trading date (not null)
-- - r_multiple_bucket: R-multiple range bucket (not null)
--   Valid values: "< -2R", "-2R to -1R", "-1R to 0R", "0R to 1R", "1R to 2R", "> 2R"
-- - position_count: Number of positions in this bucket
-- - total_position_value: Total $ value of positions in bucket
-- - avg_days_in_trade: Average age of positions in bucket
-- - avg_unrealized_pnl_pct: Average win % in bucket
--
-- PRIMARY KEY: (date, r_multiple_bucket)
--
-- CONSUMED BY: Dashboard panel_risk_ladder()
--
-- CREATED: 2026-06-12

CREATE TABLE IF NOT EXISTS r_ladder_distribution_daily (
  date DATE NOT NULL,
  r_multiple_bucket VARCHAR(20) NOT NULL,
  position_count INTEGER,
  total_position_value DECIMAL(15, 2),
  avg_days_in_trade DECIMAL(8, 2),
  avg_unrealized_pnl_pct DECIMAL(8, 4),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (date, r_multiple_bucket)
);

COMMENT ON TABLE r_ladder_distribution_daily IS
'Pre-computed daily R-ladder distribution across 6 risk buckets. Eliminates real-time bucketing logic. Updated by loaders when positions change.';

COMMENT ON COLUMN r_ladder_distribution_daily.date IS
'Trading date. Composite key with bucket ensures one distribution row per bucket per day (6 rows total per date).';

COMMENT ON COLUMN r_ladder_distribution_daily.r_multiple_bucket IS
'R-multiple range: "< -2R", "-2R to -1R", "-1R to 0R", "0R to 1R", "1R to 2R", "> 2R". Defines risk distribution.';

COMMENT ON COLUMN r_ladder_distribution_daily.position_count IS
'Number of open positions in this R bucket.';

COMMENT ON COLUMN r_ladder_distribution_daily.total_position_value IS
'Total $ value of positions in this bucket. Shows amount of capital at each risk level.';

COMMENT ON COLUMN r_ladder_distribution_daily.avg_days_in_trade IS
'Average number of days positions in bucket have been held. Age indicator.';

COMMENT ON COLUMN r_ladder_distribution_daily.avg_unrealized_pnl_pct IS
'Average unrealized gain/loss for positions in bucket. Correlation of R-multiple to performance.';

CREATE INDEX IF NOT EXISTS idx_r_ladder_date
  ON r_ladder_distribution_daily(date DESC);

CREATE INDEX IF NOT EXISTS idx_r_ladder_bucket
  ON r_ladder_distribution_daily(date DESC, r_multiple_bucket);

-- Add constraint to ensure valid bucket values
ALTER TABLE r_ladder_distribution_daily
ADD CONSTRAINT check_r_multiple_bucket
CHECK (r_multiple_bucket IN ('< -2R', '-2R to -1R', '-1R to 0R', '0R to 1R', '1R to 2R', '> 2R'));

-- Backfill empty distribution (6 rows per date) if needed
-- This ensures consistent structure even if no positions in a bucket
-- WITH date_range AS (
--   SELECT DISTINCT DATE(trade_date) as date FROM algo_trades WHERE trade_date >= CURRENT_DATE - INTERVAL '365 days'
-- ),
-- buckets AS (
--   SELECT UNNEST(ARRAY['< -2R', '-2R to -1R', '-1R to 0R', '0R to 1R', '1R to 2R', '> 2R']) as bucket
-- ),
-- date_bucket_combo AS (
--   SELECT dr.date, b.bucket FROM date_range dr CROSS JOIN buckets b
-- )
-- INSERT INTO r_ladder_distribution_daily (date, r_multiple_bucket, position_count, total_position_value, avg_days_in_trade, avg_unrealized_pnl_pct)
-- SELECT date, bucket, 0, 0, 0, 0 FROM date_bucket_combo
-- ON CONFLICT (date, r_multiple_bucket) DO NOTHING;
