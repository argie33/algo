-- Migration 1148: Fix value_metrics date column to be GENERATED
-- Issue: value_metrics.date was not a GENERATED column (unlike quality/growth metrics),
-- so it stayed NULL. This breaks data freshness tracking since the monitor can't
-- determine the age of value_metrics.
--
-- Solution: Recreate the date column as GENERATED from updated_at.
-- This requires dropping and recreating the column in a single transaction.

BEGIN;

-- Drop the existing non-generated date column
ALTER TABLE value_metrics DROP COLUMN date CASCADE;

-- Recreate it as GENERATED ALWAYS from updated_at (matching growth_metrics pattern)
ALTER TABLE value_metrics ADD COLUMN date DATE GENERATED ALWAYS AS (CAST(updated_at AS DATE)) STORED;

COMMIT;

-- After this migration, value_metrics.date will automatically be set whenever
-- updated_at changes, and the monitor can correctly track data freshness.
