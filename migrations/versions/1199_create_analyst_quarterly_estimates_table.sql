-- Migration: Create analyst quarterly estimates table for Phase 3A
-- Stores historical EPS estimates and actuals for surprise/beat rate calculation

BEGIN;

CREATE TABLE analyst_quarterly_estimates (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    fiscal_year INT NOT NULL,
    quarter_number INT NOT NULL,  -- 1, 2, 3, 4
    eps_estimate NUMERIC(10,4),
    eps_actual NUMERIC(10,4),
    earnings_surprise_pct NUMERIC(10,2),
    beat_earnings_flag BOOLEAN,
    estimate_date DATE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_year, quarter_number)
);

CREATE INDEX idx_analyst_estimates_symbol ON analyst_quarterly_estimates(symbol);
CREATE INDEX idx_analyst_estimates_fiscal_year ON analyst_quarterly_estimates(fiscal_year, quarter_number);

COMMIT;
