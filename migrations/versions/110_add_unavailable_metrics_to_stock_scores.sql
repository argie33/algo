-- Migration 110: Add unavailable_metrics column to stock_scores table
--
-- PURPOSE: Track which factor inputs are unavailable for each stock score
-- The load_stock_scores.py loader returns detailed information about which metrics
-- (quality, growth, value, positioning, stability, momentum) are unavailable for each symbol.
-- This field stores that mapping as JSON for transparency and debugging.
--
-- GOVERNANCE: CLAUDE.md requires explicit data_unavailable markers instead of silent failures.
-- This column enables operators to understand score degradation at a glance.

BEGIN;

-- Add unavailable_metrics column as JSONB for efficient queries
ALTER TABLE stock_scores
ADD COLUMN IF NOT EXISTS unavailable_metrics JSONB DEFAULT NULL;

-- Index on unavailable_metrics for efficient queries on degraded scores
CREATE INDEX IF NOT EXISTS idx_stock_scores_unavailable_metrics
ON stock_scores USING gin(unavailable_metrics);

-- Create function to check if a metric is unavailable
CREATE OR REPLACE FUNCTION has_unavailable_metric(unavailable_metrics JSONB, metric_name TEXT)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN unavailable_metrics IS NOT NULL
           AND unavailable_metrics ? metric_name;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

COMMIT;
