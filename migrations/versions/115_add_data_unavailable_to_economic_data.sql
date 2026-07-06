-- Migration 115: Add data_unavailable flag to economic data tables
-- Enables operator visibility into incomplete/degraded FRED series loads
-- Per GOVERNANCE.md: Explicit availability markers required; fail-fast on <80% coverage

ALTER TABLE economic_data_daily ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE;
ALTER TABLE economic_data_daily ADD COLUMN IF NOT EXISTS data_unavailable_reason VARCHAR(255);
ALTER TABLE economic_data_daily ADD COLUMN IF NOT EXISTS coverage_pct NUMERIC(5,2);

-- Create index for data quality monitoring
CREATE INDEX IF NOT EXISTS idx_economic_data_unavailable ON economic_data_daily(series_name, data_unavailable);

-- Add constraint: if data_unavailable=true, reason must be present
ALTER TABLE economic_data_daily ADD CONSTRAINT economic_data_unavailable_reason_check
  CHECK (data_unavailable = false OR data_unavailable_reason IS NOT NULL);

-- Add check: coverage_pct must be 0-100 when present, or NULL
ALTER TABLE economic_data_daily ADD CONSTRAINT economic_data_coverage_pct_check
  CHECK (coverage_pct IS NULL OR (coverage_pct >= 0 AND coverage_pct <= 100));

-- Add constraint: mark data_unavailable=true if coverage_pct < 80
-- (enforced in application code via load_fred_economic_data.py line ~280)
