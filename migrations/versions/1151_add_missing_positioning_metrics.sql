-- Migration 1151: Add missing positioning metrics columns
-- Adds institutional holdings (13F) and derived short metrics
-- These fields are intentionally left NULL with reason codes
-- explaining why data is unavailable

BEGIN;

-- Add institutional holdings metrics (unavailable until 13F CUSIP crosswalk is implemented)
ALTER TABLE positioning_metrics
ADD COLUMN IF NOT EXISTS top_10_institutions_pct NUMERIC,
ADD COLUMN IF NOT EXISTS top_10_institutions_pct_unavailable_reason VARCHAR(255),
ADD COLUMN IF NOT EXISTS institutional_holders_count NUMERIC,
ADD COLUMN IF NOT EXISTS institutional_holders_count_unavailable_reason VARCHAR(255),

-- Add derived short metrics (short data available but these aren't calculated yet)
ADD COLUMN IF NOT EXISTS short_percent_of_float NUMERIC,
ADD COLUMN IF NOT EXISTS short_percent_of_float_unavailable_reason VARCHAR(255),
ADD COLUMN IF NOT EXISTS short_ratio NUMERIC,
ADD COLUMN IF NOT EXISTS short_ratio_unavailable_reason VARCHAR(255),

-- Add A/D rating (no data source defined)
ADD COLUMN IF NOT EXISTS ad_rating NUMERIC,
ADD COLUMN IF NOT EXISTS ad_rating_unavailable_reason VARCHAR(255);

COMMIT;
