-- Migration: Add updated_at columns to tables for pipeline health monitoring
-- Session 350: Enable date-based health checks on orchestrator/performance tables

-- algo_orchestrator_runs: Track when run records are last updated
ALTER TABLE algo_orchestrator_runs
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- algo_performance_metrics: Track when performance data is last updated
ALTER TABLE algo_performance_metrics
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- circuit_breaker_status: Track when breaker status records are last updated
ALTER TABLE circuit_breaker_status
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Create indexes on updated_at for efficient health monitoring queries
CREATE INDEX IF NOT EXISTS idx_algo_orchestrator_runs_updated_at
  ON algo_orchestrator_runs(updated_at);

CREATE INDEX IF NOT EXISTS idx_algo_performance_metrics_updated_at
  ON algo_performance_metrics(updated_at);

CREATE INDEX IF NOT EXISTS idx_circuit_breaker_status_updated_at
  ON circuit_breaker_status(updated_at);
