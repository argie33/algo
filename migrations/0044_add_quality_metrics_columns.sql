-- Migration 0044: Add quality_score and debt_to_assets columns to quality_metrics table
-- Description: Support new financial metrics for stock score computation
-- Created: 2026-06-28
-- Impact: Enables quality_metrics loader to store composite quality score and debt-to-assets ratio
--         Fixes data loading issues where these metrics were computed but not persisted

-- Add debt_to_assets column (total_liabilities / total_assets)
ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS debt_to_assets DECIMAL(8, 4);

-- Add quality_score column (composite 0-100 score from operating margin, net margin, ROE)
ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS quality_score DECIMAL(5, 2);

-- Create index for quality_score queries (used in stock score sorting)
CREATE INDEX IF NOT EXISTS idx_quality_metrics_quality_score ON quality_metrics(quality_score DESC);
