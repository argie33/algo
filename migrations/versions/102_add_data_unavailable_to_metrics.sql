-- Migration 102: Add data_unavailable column to all metric tables
-- Fixes 503 errors in scores API endpoint which references this column
-- ════════════════════════════════════════════════════════════════════════════

-- Add data_unavailable flag to all metric tables
-- This column tracks whether data was intentionally marked unavailable
-- (versus NULL values which could be legitimate empty/missing data)

ALTER TABLE quality_metrics
ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE;

ALTER TABLE growth_metrics
ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE;

ALTER TABLE value_metrics
ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE;

ALTER TABLE positioning_metrics
ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE;

ALTER TABLE stability_metrics
ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE;

-- Add indexes for efficient JOINs from stock_scores query
-- These indexes speed up LEFT JOIN operations which scan across all symbols
CREATE INDEX IF NOT EXISTS idx_quality_metrics_symbol ON quality_metrics(symbol);
CREATE INDEX IF NOT EXISTS idx_growth_metrics_symbol ON growth_metrics(symbol);
CREATE INDEX IF NOT EXISTS idx_value_metrics_symbol ON value_metrics(symbol);
CREATE INDEX IF NOT EXISTS idx_positioning_metrics_symbol ON positioning_metrics(symbol);
CREATE INDEX IF NOT EXISTS idx_stability_metrics_symbol ON stability_metrics(symbol);

-- Add covering indexes for the data_unavailable flag checks
CREATE INDEX IF NOT EXISTS idx_quality_metrics_symbol_unavailable
ON quality_metrics(symbol, data_unavailable);

CREATE INDEX IF NOT EXISTS idx_growth_metrics_symbol_unavailable
ON growth_metrics(symbol, data_unavailable);

CREATE INDEX IF NOT EXISTS idx_value_metrics_symbol_unavailable
ON value_metrics(symbol, data_unavailable);

CREATE INDEX IF NOT EXISTS idx_positioning_metrics_symbol_unavailable
ON positioning_metrics(symbol, data_unavailable);

CREATE INDEX IF NOT EXISTS idx_stability_metrics_symbol_unavailable
ON stability_metrics(symbol, data_unavailable);

-- Analyze tables to update planner statistics
ANALYZE quality_metrics;
ANALYZE growth_metrics;
ANALYZE value_metrics;
ANALYZE positioning_metrics;
ANALYZE stability_metrics;
