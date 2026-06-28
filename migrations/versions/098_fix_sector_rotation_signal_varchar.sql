-- Migration 098: Fix sector_rotation_signal varchar truncation
-- Issue: Signal column VARCHAR(20) was truncating "severe_defensive_rotation" (28 chars)
-- This prevented signal detection in market exposure calculations
-- Solution: Increase signal column to VARCHAR(30)

ALTER TABLE sector_rotation_signal ALTER COLUMN signal TYPE VARCHAR(30);

-- Index to ensure signal lookups remain fast
CREATE INDEX IF NOT EXISTS idx_sector_rotation_signal_lookup
ON sector_rotation_signal(date, sector, signal);
