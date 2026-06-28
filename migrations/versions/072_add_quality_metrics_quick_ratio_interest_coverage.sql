-- Migration 071: Add quick_ratio and interest_coverage to quality_metrics
-- These columns exist in schema.sql but CREATE TABLE IF NOT EXISTS won't add them to an existing table.
-- Required by: /api/stocks/deep-value and /api/scores endpoints.

ALTER TABLE quality_metrics
    ADD COLUMN IF NOT EXISTS quick_ratio DECIMAL(8, 4),
    ADD COLUMN IF NOT EXISTS interest_coverage DECIMAL(8, 4);
