-- Migration 100: Create credit_spreads table for high-yield credit spread tracking
-- Description: Stores HY OAS (Option-Adjusted Spread) for systemic stress assessment
-- This table is CRITICAL for market_exposure calculation (10 points)
-- Data source: FRED (Federal Reserve Economic Data) - series BAMLH0A0HYM2
-- Created: 2026-06-28

CREATE TABLE IF NOT EXISTS credit_spreads (
    date DATE NOT NULL PRIMARY KEY,
    hy_oas NUMERIC(8, 2) NOT NULL,
    ig_oas NUMERIC(8, 2),
    hy_ig_spread NUMERIC(8, 2),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_credit_spreads_date ON credit_spreads(date DESC);
CREATE INDEX IF NOT EXISTS idx_credit_spreads_hy_oas ON credit_spreads(hy_oas);
