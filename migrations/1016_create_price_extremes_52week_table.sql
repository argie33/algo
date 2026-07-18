-- Create price_extremes_52week table for quick-win optimization
-- Computes 52-week high/low from price_daily (replaces yfinance)
-- Reduces yfinance API calls by ~2-3%

CREATE TABLE IF NOT EXISTS price_extremes_52week (
    symbol VARCHAR(20) PRIMARY KEY,
    fifty_two_week_high NUMERIC(10, 2),
    fifty_two_week_low NUMERIC(10, 2),
    bar_count INTEGER,
    data_unavailable BOOLEAN DEFAULT FALSE,
    reason VARCHAR(50),
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_price_extremes_computed_at ON price_extremes_52week(computed_at DESC);
