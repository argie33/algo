-- Migration: Ensure stock_scores table has all required columns
-- Purpose: Fix schema mismatch between code and RDS database
-- Date: 2025-10-26

BEGIN;

-- Alter stock_scores table to add missing columns if they don't exist
ALTER TABLE stock_scores
ADD COLUMN IF NOT EXISTS roc_10d NUMERIC(8,2),
ADD COLUMN IF NOT EXISTS roc_20d NUMERIC(8,2),
ADD COLUMN IF NOT EXISTS roc_60d NUMERIC(8,2),
ADD COLUMN IF NOT EXISTS roc_120d NUMERIC(8,2),
ADD COLUMN IF NOT EXISTS roc_252d NUMERIC(8,2),
ADD COLUMN IF NOT EXISTS mom NUMERIC(10,2),
ADD COLUMN IF NOT EXISTS mansfield_rs NUMERIC(8,2),
ADD COLUMN IF NOT EXISTS acc_dist_rating NUMERIC(5,2),
ADD COLUMN IF NOT EXISTS value_inputs JSONB,
ADD COLUMN IF NOT EXISTS stability_score NUMERIC(5,2),
ADD COLUMN IF NOT EXISTS stability_inputs JSONB,
ADD COLUMN IF NOT EXISTS score_status VARCHAR(50) DEFAULT 'complete',
ADD COLUMN IF NOT EXISTS available_metrics JSONB,
ADD COLUMN IF NOT EXISTS missing_metrics JSONB,
ADD COLUMN IF NOT EXISTS score_notes TEXT,
ADD COLUMN IF NOT EXISTS estimated_data_ready_date DATE;

-- Ensure momentum_metrics table has required columns
ALTER TABLE momentum_metrics
ADD COLUMN IF NOT EXISTS momentum_12_3 NUMERIC(10,4),
ADD COLUMN IF NOT EXISTS momentum_6m NUMERIC(10,4),
ADD COLUMN IF NOT EXISTS momentum_3m NUMERIC(10,4);

-- Create indexes if they don't exist
CREATE INDEX IF NOT EXISTS idx_stock_scores_composite ON stock_scores(composite_score DESC);
CREATE INDEX IF NOT EXISTS idx_stock_scores_date ON stock_scores(score_date);
CREATE INDEX IF NOT EXISTS idx_stock_scores_updated ON stock_scores(last_updated);
CREATE INDEX IF NOT EXISTS idx_momentum_jt_12_1 ON momentum_metrics(jt_momentum_12_1 DESC);
CREATE INDEX IF NOT EXISTS idx_momentum_symbol ON momentum_metrics(symbol);
CREATE INDEX IF NOT EXISTS idx_momentum_date ON momentum_metrics(date DESC);

COMMIT;
