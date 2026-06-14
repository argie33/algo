-- Migration 059: Create algo_runtime_state table for halt flag dual-storage
-- Purpose: RDS backup for halt flag when DynamoDB is unavailable
-- The halt_flag_manager writes to both DynamoDB (primary) and RDS (fallback).
-- schema.sql covers new installs; this migration covers existing production DBs.

CREATE TABLE IF NOT EXISTS algo_runtime_state (
    state_key VARCHAR(64) PRIMARY KEY,
    state_value JSONB NOT NULL,
    last_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255),
    halt_flag BOOLEAN,
    halt_triggered_at TIMESTAMP,
    halt_reason TEXT,
    halt_count INTEGER DEFAULT 0,
    dynamodb_check_failure_count INTEGER DEFAULT 0,
    dynamodb_last_failure_at TIMESTAMP,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_algo_runtime_state_halt ON algo_runtime_state(state_key, halt_flag);
CREATE INDEX IF NOT EXISTS idx_algo_runtime_state_expires ON algo_runtime_state(expires_at);
