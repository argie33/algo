-- Migration 066: Create orchestrator_execution_log table
-- Records each run of the algo orchestrator (phases, status, results).
-- Referenced by /api/algo/execution/recent, /api/algo/execution/stats,
-- /api/algo/last-run — all used by AlgoTradingDashboard. Was in schema.sql
-- but never added as a versioned migration.

CREATE TABLE IF NOT EXISTS orchestrator_execution_log (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(50) NOT NULL UNIQUE,
    run_date DATE NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    overall_status VARCHAR(20) NOT NULL,
    phase_results JSONB,
    summary TEXT,
    halt_reason TEXT,
    phases_completed INTEGER,
    phases_halted INTEGER,
    phases_errored INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_orchestrator_execution_run_date ON orchestrator_execution_log(run_date DESC);
CREATE INDEX IF NOT EXISTS idx_orchestrator_execution_status ON orchestrator_execution_log(overall_status);
CREATE INDEX IF NOT EXISTS idx_orchestrator_execution_started ON orchestrator_execution_log(started_at DESC);

-- market_sentiment: also in schema.sql but not versioned; queried by /api/algo/markets
CREATE TABLE IF NOT EXISTS market_sentiment (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    fear_greed_index DECIMAL(8, 4),
    put_call_ratio DECIMAL(8, 4),
    vix DECIMAL(8, 4),
    sentiment_score DECIMAL(8, 4),
    bullish_pct DECIMAL(8, 2),
    bearish_pct DECIMAL(8, 2),
    neutral_pct DECIMAL(8, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
