-- Migration 1152: Add missing ebitda and ebitda_margin columns to quality_metrics table
-- These columns are used by the load_value_quality_growth_metrics loader but were never
-- added to the database schema, causing the loader to silently fail when trying to INSERT
-- ebitda and ebitda_margin values. This fixes the 0% population rate of these metrics.

DO $$
BEGIN
  -- Add ebitda column if it doesn't exist
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'quality_metrics' AND column_name = 'ebitda'
  ) THEN
    ALTER TABLE quality_metrics ADD COLUMN ebitda NUMERIC(18,2);
    RAISE NOTICE 'Added ebitda column to quality_metrics';
  END IF;

  -- Add ebitda_margin column if it doesn't exist
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'quality_metrics' AND column_name = 'ebitda_margin'
  ) THEN
    ALTER TABLE quality_metrics ADD COLUMN ebitda_margin NUMERIC(6,2);
    RAISE NOTICE 'Added ebitda_margin column to quality_metrics';
  END IF;

  -- Add ebitda_margin_unavailable_reason for consistency with other optional metrics
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'quality_metrics' AND column_name = 'ebitda_margin_unavailable_reason'
  ) THEN
    ALTER TABLE quality_metrics ADD COLUMN ebitda_margin_unavailable_reason VARCHAR(100);
    RAISE NOTICE 'Added ebitda_margin_unavailable_reason column to quality_metrics';
  END IF;
END $$;
