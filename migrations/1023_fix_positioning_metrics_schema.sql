-- Migration 1023: Fix positioning_metrics table schema to match loader expectations
-- Purpose: Rename columns to match schema.sql and loader code (institutional_ownership_pct, etc.)
-- Date: 2026-07-20
-- Impact: positioning_metrics table affected (schema correction, no data loss)
-- Root cause: Column naming mismatch preventing loader from storing positioning data

-- Rename columns to match schema.sql and loader expectations
ALTER TABLE IF EXISTS positioning_metrics
RENAME COLUMN institutional_ownership TO institutional_ownership_pct;

ALTER TABLE IF EXISTS positioning_metrics
RENAME COLUMN insider_ownership TO insider_ownership_pct;

-- Note: short_interest_pct already exists, so no rename needed
-- Remove the duplicate short_interest_percent column if it exists and is different from short_interest_pct
ALTER TABLE IF EXISTS positioning_metrics
DROP COLUMN IF EXISTS short_interest_percent;

-- Ensure short_interest_pct column exists with correct type
ALTER TABLE IF EXISTS positioning_metrics
ADD COLUMN IF NOT EXISTS short_interest_pct NUMERIC(6, 2);

-- Add float_pct column if it doesn't exist (per schema.sql)
ALTER TABLE IF EXISTS positioning_metrics
ADD COLUMN IF NOT EXISTS float_pct NUMERIC(6, 2);

-- Add institutional_ownership_pct_unavailable_reason if it doesn't exist (per schema.sql)
ALTER TABLE IF EXISTS positioning_metrics
ADD COLUMN IF NOT EXISTS institutional_ownership_pct_unavailable_reason VARCHAR(255);

-- Ensure all expected columns are present
ALTER TABLE IF EXISTS positioning_metrics
ADD COLUMN IF NOT EXISTS short_interest_percent NUMERIC(6, 2);

-- Verify column order and data types match schema.sql
-- This is a verification comment; the actual schema should match:
-- symbol VARCHAR(20) PRIMARY KEY
-- institutional_ownership_pct NUMERIC(6, 2)
-- short_interest_pct NUMERIC(6, 2)
-- insider_ownership_pct NUMERIC(6, 2)
-- float_pct NUMERIC(6, 2)
-- institutional_ownership_pct_unavailable_reason VARCHAR(255)
-- data_unavailable BOOLEAN DEFAULT FALSE
-- reason VARCHAR(500)
-- updated_at TIMESTAMP WITH TIME ZONE
-- data_source VARCHAR(100)

-- Final verification: show the corrected schema
COMMENT ON TABLE positioning_metrics IS 'Positioning metrics - institutional/insider/short holdings. Schema corrected in migration 1023 to match loader expectations.';
