-- PostgreSQL initialization for local development
-- Run on startup to create tables and enable extensions

-- Enable TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- ============================================================
-- Core Schema
-- ============================================================

-- Stock symbols and metadata
CREATE TABLE IF NOT EXISTS stock_symbols (
    symbol VARCHAR(20) PRIMARY KEY,
    name VARCHAR(255),
    sector VARCHAR(100),
    industry VARCHAR(100),
    market_cap BIGINT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- Price Data (Time-Series)
-- ============================================================

-- Daily prices (converted to hypertable)
CREATE TABLE IF NOT EXISTS price_daily (
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(12,2),
    high DECIMAL(12,2),
    low DECIMAL(12,2),
    close DECIMAL(12,2),
    volume BIGINT,
    PRIMARY KEY (symbol, date)
);

-- Convert to hypertable if not already
SELECT create_hypertable('price_daily', 'date', if_not_exists => TRUE);
SELECT set_chunk_time_interval('price_daily', INTERVAL '1 month');
CREATE INDEX IF NOT EXISTS idx_price_daily_symbol_date ON price_daily (symbol, date DESC);

-- Weekly prices
CREATE TABLE IF NOT EXISTS price_weekly (
    symbol VARCHAR(20) NOT NULL,
    week_start DATE NOT NULL,
    open DECIMAL(12,2),
    high DECIMAL(12,2),
    low DECIMAL(12,2),
    close DECIMAL(12,2),
    volume BIGINT,
    PRIMARY KEY (symbol, week_start)
);

SELECT create_hypertable('price_weekly', 'week_start', if_not_exists => TRUE);
SELECT set_chunk_time_interval('price_weekly', INTERVAL '3 months');

-- Monthly prices
CREATE TABLE IF NOT EXISTS price_monthly (
    symbol VARCHAR(20) NOT NULL,
    month_start DATE NOT NULL,
    open DECIMAL(12,2),
    high DECIMAL(12,2),
    low DECIMAL(12,2),
    close DECIMAL(12,2),
    volume BIGINT,
    PRIMARY KEY (symbol, month_start)
);

SELECT create_hypertable('price_monthly', 'month_start', if_not_exists => TRUE);
SELECT set_chunk_time_interval('price_monthly', INTERVAL '6 months');

-- ETF prices
CREATE TABLE IF NOT EXISTS etf_price_daily (
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(12,2),
    high DECIMAL(12,2),
    low DECIMAL(12,2),
    close DECIMAL(12,2),
    volume BIGINT,
    PRIMARY KEY (symbol, date)
);

SELECT create_hypertable('etf_price_daily', 'date', if_not_exists => TRUE);
SELECT set_chunk_time_interval('etf_price_daily', INTERVAL '1 month');

-- ============================================================
-- Trading Signals (Time-Series)
-- ============================================================

CREATE TABLE IF NOT EXISTS buy_sell_daily (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    signal_date DATE NOT NULL,
    signal VARCHAR(10),  -- 'buy' or 'sell'
    base_type VARCHAR(50),
    confidence DECIMAL(5,3),
    reason TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

SELECT create_hypertable('buy_sell_daily', 'signal_date', if_not_exists => TRUE);
SELECT set_chunk_time_interval('buy_sell_daily', INTERVAL '1 month');
CREATE INDEX IF NOT EXISTS idx_buy_sell_daily_symbol_date ON buy_sell_daily (symbol, signal_date DESC);

-- ============================================================
-- Financial Data
-- ============================================================

CREATE TABLE IF NOT EXISTS balance_sheet (
    symbol VARCHAR(20) NOT NULL,
    period_date DATE NOT NULL,
    period_type VARCHAR(10),  -- 'annual' or 'quarterly'
    total_assets BIGINT,
    total_liabilities BIGINT,
    total_equity BIGINT,
    current_assets BIGINT,
    current_liabilities BIGINT,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (symbol, period_date, period_type)
);

CREATE TABLE IF NOT EXISTS income_statement (
    symbol VARCHAR(20) NOT NULL,
    period_date DATE NOT NULL,
    period_type VARCHAR(10),
    revenue BIGINT,
    operating_income BIGINT,
    net_income BIGINT,
    gross_profit BIGINT,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (symbol, period_date, period_type)
);

CREATE TABLE IF NOT EXISTS cash_flow (
    symbol VARCHAR(20) NOT NULL,
    period_date DATE NOT NULL,
    period_type VARCHAR(10),
    operating_cash_flow BIGINT,
    investing_cash_flow BIGINT,
    financing_cash_flow BIGINT,
    free_cash_flow BIGINT,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (symbol, period_date, period_type)
);

-- ============================================================
-- Loader State Tracking
-- ============================================================

CREATE TABLE IF NOT EXISTS loader_watermarks (
    id SERIAL PRIMARY KEY,
    loader VARCHAR(100) NOT NULL,
    symbol VARCHAR(20),
    granularity VARCHAR(50) DEFAULT 'default',
    watermark TEXT NOT NULL,
    rows_loaded BIGINT DEFAULT 0,
    last_run_at TIMESTAMPTZ DEFAULT NOW(),
    last_success_at TIMESTAMPTZ,
    error_count INT DEFAULT 0,
    last_error TEXT,
    UNIQUE (loader, symbol, granularity)
);

CREATE INDEX IF NOT EXISTS idx_loader_watermarks_loader_run
    ON loader_watermarks (loader, last_run_at DESC);

-- ============================================================
-- Staging (for bulk operations)
-- ============================================================

-- Temporary table for S3 staging
CREATE TABLE IF NOT EXISTS staging_prices (
    symbol VARCHAR(20),
    date DATE,
    open DECIMAL(12,2),
    high DECIMAL(12,2),
    low DECIMAL(12,2),
    close DECIMAL(12,2),
    volume BIGINT,
    source VARCHAR(20)
);

-- ============================================================
-- Analytics
-- ============================================================

-- Sample data for testing
INSERT INTO stock_symbols (symbol, name, sector, industry, market_cap)
VALUES
    ('AAPL', 'Apple Inc.', 'Technology', 'Consumer Electronics', 2800000000000),
    ('MSFT', 'Microsoft', 'Technology', 'Software', 2700000000000),
    ('GOOGL', 'Alphabet Inc.', 'Technology', 'Internet Search', 1700000000000)
ON CONFLICT (symbol) DO NOTHING;

-- ============================================================
-- Compression & Retention (optional, for production parity)
-- ============================================================

-- Enable compression for historical data (optional, can cause performance issues in dev)
-- ALTER TABLE price_daily SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol');
-- SELECT add_compression_policy('price_daily', INTERVAL '7 days', if_not_exists => TRUE);

-- Add retention policy (optional)
-- SELECT add_retention_policy('price_daily', INTERVAL '5 years', if_not_exists => TRUE);

-- ============================================================
-- Analyze
-- ============================================================

ANALYZE;

-- Print summary
\echo ''
\echo '=========================================='
\echo 'PostgreSQL setup complete!'
\echo '=========================================='
\echo 'Tables created: stock_symbols, price_daily, price_weekly, price_monthly,'
\echo '                etf_price_daily, buy_sell_daily, balance_sheet,'
\echo '                income_statement, cash_flow, loader_watermarks'
\echo 'TimescaleDB:    Enabled (hypertables for time-series data)'
\echo 'Sample data:    3 stocks loaded (AAPL, MSFT, GOOGL)'
\echo ''
\echo 'Connect: psql -h localhost -U stocks -d stocks'
\echo 'Query example: SELECT * FROM stock_symbols;'
\echo '=========================================='
\echo ''
