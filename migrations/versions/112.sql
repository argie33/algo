-- Migration 112: Add data_unavailable columns to metric tables
-- Purpose: Enable explicit marking of incomplete/unavailable metric data across all loaders

-- Add data_unavailable columns to quality_metrics
ALTER TABLE quality_metrics
ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS reason VARCHAR(500);

-- Add to growth_metrics
ALTER TABLE growth_metrics
ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS reason VARCHAR(500);

-- Add to value_metrics
ALTER TABLE value_metrics
ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS reason VARCHAR(500);

-- Add to positioning_metrics
ALTER TABLE positioning_metrics
ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS reason VARCHAR(500);

-- Add to stability_metrics
ALTER TABLE stability_metrics
ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS reason VARCHAR(500);

-- Add to momentum_metrics
ALTER TABLE momentum_metrics
ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
ADD COLUMN IF NOT EXISTS reason VARCHAR(500);

-- Create indexes for faster filtering
CREATE INDEX IF NOT EXISTS idx_quality_metrics_data_unavailable
ON quality_metrics(data_unavailable, symbol);

CREATE INDEX IF NOT EXISTS idx_growth_metrics_data_unavailable
ON growth_metrics(data_unavailable, symbol);

CREATE INDEX IF NOT EXISTS idx_value_metrics_data_unavailable
ON value_metrics(data_unavailable, symbol);

CREATE INDEX IF NOT EXISTS idx_positioning_metrics_data_unavailable
ON positioning_metrics(data_unavailable, symbol);

CREATE INDEX IF NOT EXISTS idx_stability_metrics_data_unavailable
ON stability_metrics(data_unavailable, symbol);

CREATE INDEX IF NOT EXISTS idx_momentum_metrics_data_unavailable
ON momentum_metrics(data_unavailable, symbol);

-- Log migration completion
INSERT INTO schema_migrations (version, description, installed_on)
VALUES ('112', 'Add data_unavailable columns to metric tables', NOW())
ON CONFLICT (version) DO NOTHING;
