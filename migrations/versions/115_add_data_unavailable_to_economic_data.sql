-- Migration 115: Add data_unavailable flag to economic data tables
-- Enables operator visibility into incomplete/degraded FRED series loads
-- Per GOVERNANCE.md: Explicit availability markers required; fail-fast on <80% coverage

-- Columns already exist from previous migrations, this is idempotent
-- Just ensure the data_unavailable columns are in place
ALTER TABLE economic_data ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE;
ALTER TABLE economic_data ADD COLUMN IF NOT EXISTS reason VARCHAR(255);

-- Migration completed (recorded by migration runner)
