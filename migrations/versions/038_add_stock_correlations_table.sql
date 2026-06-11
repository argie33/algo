-- Migration: Add stock_correlations table for pre-computed correlation matrix
--
-- PHASE 2 ARCHITECTURAL FIX: Move correlation matrix calculation from API
-- (market.js /api/market/correlation) to pre-computed database table.
--
-- Current issue: /api/market/correlation calculates O(N²) Pearson correlations
-- in-memory (1225 calculations for 50 symbols × 365 days = ~900k data points).
-- Response time: 5-15 seconds.
--
-- Solution: Pre-compute correlations in load_stock_correlations.py loader
-- (runs daily after market close). API fetches from table in ~100ms.

CREATE TABLE IF NOT EXISTS stock_correlations (
    symbol1 VARCHAR(20) NOT NULL,
    symbol2 VARCHAR(20) NOT NULL,
    correlation_1m NUMERIC(8, 4),          -- 1-month correlation
    correlation_3m NUMERIC(8, 4),          -- 3-month correlation
    correlation_6m NUMERIC(8, 4),          -- 6-month correlation
    correlation_1y NUMERIC(8, 4),          -- 1-year correlation
    days_overlapped INTEGER,                -- Number of overlapping trading days
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol1, symbol2),
    CHECK (symbol1 < symbol2)              -- Enforce symmetric pairs (symbol1 < symbol2)
);

-- Index for efficient lookups by symbol
CREATE INDEX IF NOT EXISTS idx_stock_correlations_symbol1 ON stock_correlations(symbol1);
CREATE INDEX IF NOT EXISTS idx_stock_correlations_symbol2 ON stock_correlations(symbol2);
CREATE INDEX IF NOT EXISTS idx_stock_correlations_updated ON stock_correlations(updated_at);
