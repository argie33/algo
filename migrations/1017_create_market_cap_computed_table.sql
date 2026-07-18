-- Create market_cap_computed table for quick-win optimization
-- Computes market cap from price_daily + sec_valuations (replaces yfinance)
-- Reduces yfinance API calls by ~2-3% and improves accuracy

CREATE TABLE IF NOT EXISTS market_cap_computed (
    symbol VARCHAR(20) PRIMARY KEY,
    market_cap NUMERIC(20, 2),
    latest_price NUMERIC(10, 2),
    shares_outstanding NUMERIC(18, 0),
    data_unavailable BOOLEAN DEFAULT FALSE,
    reason VARCHAR(50),
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_market_cap_computed_at ON market_cap_computed(computed_at DESC);
