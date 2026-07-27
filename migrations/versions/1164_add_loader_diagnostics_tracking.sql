-- Migration 1164: Add loader diagnostics tracking for API health and performance
--
-- Gap: data_loader_status lacks fields to track API diagnostics (HTTP status codes,
-- rate limit status, retry counts) and performance metrics (execution duration,
-- throughput). Without these, dashboard cannot distinguish transient failures
-- (retry) from permanent issues (auth/rate-limit/service down).
--
-- New columns (all nullable, populated going forward only):
-- - http_status_code: HTTP status from last API call (429=rate limit, 401=auth, 503=service down)
-- - rate_limit_quota: String like "98/100 daily calls" for informational display
-- - retry_count: Number of retries performed on last execution
-- - execution_duration_sec: Duration of last execution in seconds (for performance trending)
-- - symbols_per_second: Throughput metric (symbols_loaded / duration) for bottleneck detection
--
-- Also creates data_loader_status_history table for tracking failure patterns:
-- - Retention: last 100 runs per table (rolling window, auto-purges old entries)
-- - Used for: failure rate %, failure window analysis, MTTR calculation, recovery trends

ALTER TABLE data_loader_status
    ADD COLUMN IF NOT EXISTS http_status_code INTEGER NULL,
    ADD COLUMN IF NOT EXISTS rate_limit_quota TEXT NULL,
    ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS execution_duration_sec DECIMAL(10, 2) NULL,
    ADD COLUMN IF NOT EXISTS symbols_per_second DECIMAL(10, 2) NULL;

-- Create history table for failure pattern analysis
CREATE TABLE IF NOT EXISTS data_loader_status_history (
    id SERIAL PRIMARY KEY,
    table_name VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,  -- NOT_STARTED, RUNNING, COMPLETED, FAILED, TIMEOUT
    execution_started TIMESTAMP NULL,
    execution_completed TIMESTAMP NULL,
    error_message TEXT NULL,
    http_status_code INTEGER NULL,
    row_count BIGINT NULL,
    completion_pct DECIMAL(5, 2) NULL,
    symbols_loaded INTEGER NULL,
    symbol_count INTEGER NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_table_name FOREIGN KEY (table_name) REFERENCES data_loader_status(table_name)
);

-- Index for efficient history lookups (most recent runs first)
CREATE INDEX IF NOT EXISTS idx_loader_history_table_date
    ON data_loader_status_history(table_name, execution_completed DESC NULLS LAST);

-- Index for time-based queries (failure window analysis)
CREATE INDEX IF NOT EXISTS idx_loader_history_by_hour
    ON data_loader_status_history(table_name, EXTRACT(HOUR FROM execution_completed));
