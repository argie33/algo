-- Migration 1156: Add insider transaction velocity table
-- Purpose: Track insider buying/selling activity patterns
-- Useful for detecting insider confidence or concerns

BEGIN;

-- Create insider_transaction_velocity table
CREATE TABLE IF NOT EXISTS insider_transaction_velocity (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    measurement_date DATE NOT NULL,

    -- Transaction counts in recent periods
    buy_transactions_30d INT DEFAULT 0,
    sell_transactions_30d INT DEFAULT 0,
    net_buy_transactions_30d INT DEFAULT 0,

    buy_transactions_90d INT DEFAULT 0,
    sell_transactions_90d INT DEFAULT 0,
    net_buy_transactions_90d INT DEFAULT 0,

    -- Transaction amounts (when available)
    total_buy_shares_30d BIGINT DEFAULT 0,
    total_sell_shares_30d BIGINT DEFAULT 0,
    net_buy_shares_30d BIGINT DEFAULT 0,

    total_buy_shares_90d BIGINT DEFAULT 0,
    total_sell_shares_90d BIGINT DEFAULT 0,
    net_buy_shares_90d BIGINT DEFAULT 0,

    -- Velocity metrics
    buy_sell_ratio_30d DECIMAL(5, 2),  -- Buy transactions / Sell transactions
    buy_sell_ratio_90d DECIMAL(5, 2),
    insider_confidence_score INT,  -- 0-100 based on buy/sell velocity

    -- Data quality
    data_unavailable BOOLEAN DEFAULT FALSE,
    data_unavailable_reason VARCHAR(255),

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT uq_insider_velocity UNIQUE(symbol, measurement_date),
    CONSTRAINT fk_insider_velocity_symbol FOREIGN KEY(symbol) REFERENCES stock_symbols(symbol) ON DELETE CASCADE
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_insider_velocity_symbol_date ON insider_transaction_velocity(symbol, measurement_date DESC);
CREATE INDEX IF NOT EXISTS idx_insider_velocity_date ON insider_transaction_velocity(measurement_date DESC);
CREATE INDEX IF NOT EXISTS idx_insider_velocity_confidence ON insider_transaction_velocity(insider_confidence_score DESC);
CREATE INDEX IF NOT EXISTS idx_insider_velocity_updated ON insider_transaction_velocity(updated_at DESC);

-- Register in loader status tracking
INSERT INTO data_loader_status (table_name, completion_pct, last_updated)
VALUES ('insider_transaction_velocity', 0.0, NOW())
ON CONFLICT (table_name) DO UPDATE
SET last_updated = NOW();

COMMIT;
