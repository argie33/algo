-- Migration 1155: Add dividend data table
-- Purpose: Track dividend events and yields for position management
-- Includes ex-dates, payment dates, and dividend amounts

BEGIN;

-- Create dividend_data table for dividend events
CREATE TABLE IF NOT EXISTS dividend_data (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    declaration_date DATE,
    ex_dividend_date DATE NOT NULL,
    record_date DATE,
    payment_date DATE,
    dividend_per_share DECIMAL(10, 4),
    dividend_yield_pct DECIMAL(5, 2),
    total_dividend_amount DECIMAL(15, 2),

    -- Dividend classification
    dividend_type VARCHAR(50),  -- e.g., 'regular', 'special', 'stock'
    currency VARCHAR(3) DEFAULT 'USD',

    -- Data quality tracking
    data_unavailable BOOLEAN DEFAULT FALSE,
    data_unavailable_reason VARCHAR(255),
    source VARCHAR(50) DEFAULT 'SEC',

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT uq_dividend_event UNIQUE(symbol, ex_dividend_date),
    CONSTRAINT fk_dividend_symbol FOREIGN KEY(symbol) REFERENCES stock_symbols(symbol) ON DELETE CASCADE
);

-- Create indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_dividend_symbol_ex_date ON dividend_data(symbol, ex_dividend_date DESC);
CREATE INDEX IF NOT EXISTS idx_dividend_ex_date ON dividend_data(ex_dividend_date DESC);
CREATE INDEX IF NOT EXISTS idx_dividend_payment_date ON dividend_data(payment_date DESC);
CREATE INDEX IF NOT EXISTS idx_dividend_updated ON dividend_data(updated_at DESC);

-- Register in loader status tracking
INSERT INTO data_loader_status (table_name, completion_pct, last_updated)
VALUES ('dividend_data', 0.0, NOW())
ON CONFLICT (table_name) DO UPDATE
SET last_updated = NOW();

COMMIT;
