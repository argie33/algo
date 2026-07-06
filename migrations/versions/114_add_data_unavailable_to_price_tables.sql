-- Migration 114: Add data_unavailable flag to price tables
-- Enables operator visibility into which symbols have incomplete/failed price loads
-- Per GOVERNANCE.md: explicit availability markers required for all data sources

ALTER TABLE price_daily ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE;
ALTER TABLE price_daily ADD COLUMN IF NOT EXISTS data_unavailable_reason VARCHAR(255);

ALTER TABLE price_weekly ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE;
ALTER TABLE price_weekly ADD COLUMN IF NOT EXISTS data_unavailable_reason VARCHAR(255);

ALTER TABLE price_monthly ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE;
ALTER TABLE price_monthly ADD COLUMN IF NOT EXISTS data_unavailable_reason VARCHAR(255);

-- Create index for data quality monitoring
CREATE INDEX IF NOT EXISTS idx_price_daily_unavailable ON price_daily(symbol, data_unavailable);
CREATE INDEX IF NOT EXISTS idx_price_weekly_unavailable ON price_weekly(symbol, data_unavailable);

-- Add constraint: if data_unavailable=true, reason must be present
ALTER TABLE price_daily ADD CONSTRAINT price_daily_unavailable_reason_check
  CHECK (data_unavailable = false OR data_unavailable_reason IS NOT NULL);
ALTER TABLE price_weekly ADD CONSTRAINT price_weekly_unavailable_reason_check
  CHECK (data_unavailable = false OR data_unavailable_reason IS NOT NULL);
ALTER TABLE price_monthly ADD CONSTRAINT price_monthly_unavailable_reason_check
  CHECK (data_unavailable = false OR data_unavailable_reason IS NOT NULL);
