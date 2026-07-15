-- Migration: Add algo_untracked_positions table for broker-held positions
-- Purpose: Track positions held at broker but not entered by algo
-- Mirrors algo_positions schema for consistency

BEGIN;

-- Create table for untracked positions (manual/external holdings)
CREATE TABLE IF NOT EXISTS algo_untracked_positions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol TEXT NOT NULL,
    quantity NUMERIC(18, 4) NOT NULL,
    current_price NUMERIC(18, 6),
    position_value NUMERIC(18, 2),
    detected_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Index for fast lookups and sync operations
CREATE INDEX IF NOT EXISTS idx_untracked_positions_symbol ON algo_untracked_positions(symbol);
CREATE INDEX IF NOT EXISTS idx_untracked_positions_updated_at ON algo_untracked_positions(updated_at);
CREATE INDEX IF NOT EXISTS idx_untracked_positions_last_seen ON algo_untracked_positions(last_seen_at);

-- Comment for clarity
COMMENT ON TABLE algo_untracked_positions IS 'Positions held at Alpaca broker but not entered by algo (manual/external). Detected during sync but stored separately to avoid circuit breaker conflicts.';
COMMENT ON COLUMN algo_untracked_positions.detected_at IS 'When this position was first detected in Alpaca';
COMMENT ON COLUMN algo_untracked_positions.last_seen_at IS 'Last sync confirmation (used to detect closed positions)';

COMMIT;
