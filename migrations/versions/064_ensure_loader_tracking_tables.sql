-- Migration 064: Ensure data_loader_runs and loader_execution_history tables exist
-- Both are referenced in code but were only in schema.sql (db-init), not versioned migrations.
-- data_loader_runs: used by load_swing_trader_scores_vectorized.py to log run outcomes.
-- loader_execution_history: used by OptimalLoader._log_execution_history() for all loaders.

CREATE TABLE IF NOT EXISTS data_loader_runs (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(100),
    loader_name VARCHAR(255) NOT NULL,
    table_name VARCHAR(255),
    source_api VARCHAR(255),
    parameters JSONB,
    run_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    start_at TIMESTAMP,
    status VARCHAR(20) NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    records_loaded INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    error_message TEXT,
    duration_seconds DECIMAL(10, 2),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(loader_name, run_date)
);
CREATE INDEX IF NOT EXISTS idx_data_loader_runs_name ON data_loader_runs(loader_name);
CREATE INDEX IF NOT EXISTS idx_data_loader_runs_date ON data_loader_runs(run_date DESC);

CREATE TABLE IF NOT EXISTS loader_execution_history (
    id SERIAL PRIMARY KEY,
    loader_name VARCHAR(255) NOT NULL,
    table_name VARCHAR(255),
    execution_start TIMESTAMP,
    execution_end TIMESTAMP,
    rows_processed INTEGER DEFAULT 0,
    rows_inserted INTEGER DEFAULT 0,
    rows_updated INTEGER DEFAULT 0,
    rows_failed INTEGER DEFAULT 0,
    status VARCHAR(50),
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_loader_history_loader_name ON loader_execution_history(loader_name);
CREATE INDEX IF NOT EXISTS idx_loader_history_execution_start ON loader_execution_history(execution_start);
