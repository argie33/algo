-- Fix: Expand sector_rotation_signal.signal column from VARCHAR(20) to VARCHAR(50)
--
-- Issue: Code was attempting to insert signal values like "severe_defensive_rotation" (25 chars)
-- into a column with max length 20, causing StringDataRightTruncation errors.
-- This prevented sector rotation signals from being persisted, causing incomplete dashboard data.
--
-- Impact: Without this fix, market exposure calculations would fail with database errors
-- when computing sector rotation signals, causing exposure panels to show "unavailable".

ALTER TABLE sector_rotation_signal
ALTER COLUMN signal TYPE VARCHAR(50);

-- Clean up any truncated signal values from failed inserts
DELETE FROM sector_rotation_signal
WHERE signal IS NULL OR LENGTH(TRIM(signal)) = 0;
