-- Migration 1023: Add data_source tracking to sec_valuations table
-- Purpose: Track that sec_valuations data is sourced from SEC audited financial data
-- Date: 2026-07-18

ALTER TABLE IF EXISTS sec_valuations
ADD COLUMN data_source VARCHAR(100) DEFAULT 'sec_audited';

-- Create index for data_source tracking
CREATE INDEX IF NOT EXISTS idx_sec_valuations_data_source
    ON sec_valuations(data_source);

-- Comment
COMMENT ON COLUMN sec_valuations.data_source IS 'Always "sec_audited" for sec_valuations (computed from SEC EDGAR audited financial statements)';

-- Backfill existing rows with data_source
UPDATE sec_valuations
SET data_source = 'sec_audited'
WHERE data_source IS NULL;
