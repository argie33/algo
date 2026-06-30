-- Migration 109: Add data_unavailable and unavailability_reason columns to swing_trader_scores
--
-- swing_trader_scores loader now inserts rows with data_unavailable=TRUE and unavailability_reason
-- when upstream dependencies are missing or data quality issues prevent score computation.
-- This provides visibility into WHY scores aren't available instead of silently skipping symbols.
--
-- Examples of unavailability_reason values:
-- - upstream_dependency_missing:trend_template_data (no trend data found)
-- - upstream_dependency_missing:technical_data_daily (no RSI/technical data)
-- - upstream_dependency_missing:signal_quality_scores (no signal data)
-- - upstream_dependency_missing:sector_ranking (no sector data)
-- - filtered_by_minervini_gate:score=2.5 (trend too weak, minervini < 5)
-- - filtered_by_weinstein_gate:stage=1 (not in uptrend, stage != 2)
-- - upstream_data_quality:rsi_nan (RSI value is NULL)
-- - upstream_data_quality:minervini_nan (minervini value is NULL)
-- - upstream_data_quality:sector_momentum_null (sector momentum is NULL)

ALTER TABLE swing_trader_scores
ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE;

ALTER TABLE swing_trader_scores
ADD COLUMN IF NOT EXISTS unavailability_reason VARCHAR(255);

-- Index to efficiently find unavailable scores for monitoring/debugging
CREATE INDEX IF NOT EXISTS idx_swing_trader_scores_unavailable
ON swing_trader_scores(symbol) WHERE data_unavailable = TRUE;

-- Analyze table to update planner statistics
ANALYZE swing_trader_scores;
