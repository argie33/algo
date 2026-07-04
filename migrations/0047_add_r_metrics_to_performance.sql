-- Migration 0047: Add R-metrics columns to algo_performance_metrics
-- Purpose: Adds expectancy, avg_win_r, and avg_loss_r columns required by dashboard perf_anl endpoint
-- Used by: /api/algo/performance-analytics endpoint (fetch_perf_analytics dashboard function)

ALTER TABLE algo_performance_metrics
    ADD COLUMN IF NOT EXISTS expectancy DECIMAL(8, 4),
    ADD COLUMN IF NOT EXISTS avg_win_r DECIMAL(8, 4),
    ADD COLUMN IF NOT EXISTS avg_loss_r DECIMAL(8, 4);

-- Create index for performance analytics queries
CREATE INDEX IF NOT EXISTS idx_algo_performance_metrics_expectancy
ON algo_performance_metrics(expectancy DESC);
