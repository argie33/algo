-- Migration 0044: Complete - Add quality_score and all unavailable_reason columns to quality_metrics
-- Description: Support new financial metrics for stock score computation
-- Created: 2026-06-28
-- Updated: 2026-07-01
-- Impact: Enables quality_metrics loader to store composite quality score, debt-to-assets ratio,
--         and explicit unavailability reasons for each metric.
--         CRITICAL: Originally incomplete (only 2/11 columns). Now complete with all required columns.

-- Metric score columns
ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS debt_to_assets DECIMAL(8, 4);
ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS quality_score DECIMAL(5, 2);

-- Unavailability reason columns (required by load_quality_metrics.py when metrics cannot be computed)
ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS operating_margin_unavailable_reason VARCHAR(255);
ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS net_margin_unavailable_reason VARCHAR(255);
ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS roe_unavailable_reason VARCHAR(255);
ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS roa_unavailable_reason VARCHAR(255);
ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS debt_to_equity_unavailable_reason VARCHAR(255);
ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS current_ratio_unavailable_reason VARCHAR(255);
ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS quick_ratio_unavailable_reason VARCHAR(255);
ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS interest_coverage_unavailable_reason VARCHAR(255);
ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS debt_to_assets_unavailable_reason VARCHAR(255);

-- Create index for quality_score queries (used in stock score sorting)
CREATE INDEX IF NOT EXISTS idx_quality_metrics_quality_score ON quality_metrics(quality_score DESC);
