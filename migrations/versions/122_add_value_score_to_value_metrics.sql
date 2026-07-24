-- Migration 122: Add value_score column to value_metrics
-- Enables syncing value_score from stock_scores to value_metrics for API convenience

BEGIN;

ALTER TABLE value_metrics
ADD COLUMN IF NOT EXISTS value_score NUMERIC(5, 2);

COMMIT;
