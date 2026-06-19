-- Migration 087: Alpaca import failures tracking and retry logic
-- Addresses Issue #5: Orphan Import Retry Logic Missing
-- ════════════════════════════════════════════════════════════════════════════

-- Track failed Alpaca position imports with retry metadata
-- Enables detection and re-attempt of positions that failed mid-transaction
-- This prevents orphaned positions from being permanently lost
CREATE TABLE IF NOT EXISTS alpaca_import_failures (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    failed_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    last_retry_at TIMESTAMP WITHOUT TIME ZONE,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP WITHOUT TIME ZONE
);

-- Composite index for finding failed imports by day (for retry logic)
-- and alerting on >5 failures
CREATE INDEX IF NOT EXISTS idx_alpaca_import_failures_failed_at
ON alpaca_import_failures(failed_at DESC)
WHERE resolved = FALSE;

-- Index for finding retryable failures by symbol
CREATE INDEX IF NOT EXISTS idx_alpaca_import_failures_symbol_unresolved
ON alpaca_import_failures(symbol, retry_count)
WHERE resolved = FALSE;

-- Index for cleanup queries (failures >7 days old)
CREATE INDEX IF NOT EXISTS idx_alpaca_import_failures_cleanup
ON alpaca_import_failures(resolved, failed_at ASC)
WHERE resolved = TRUE;

-- Analyze the table to update planner statistics
ANALYZE alpaca_import_failures;
