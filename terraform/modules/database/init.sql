-- ============================================================
-- Database Initialization Script for Stocks Analytics Platform
-- ============================================================

-- Create TimescaleDB extension (if not exists)
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS uuid-ossp;

-- ============================================================
-- 1. Users & Authentication
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP NULL
);

-- ============================================================
-- 2. Stock Master Data
-- ============================================================

CREATE TABLE IF NOT EXISTS stocks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ticker VARCHAR(10) UNIQUE NOT NULL,
    company_name VARCHAR(255) NOT NULL,
    sector VARCHAR(100),
    industry VARCHAR(100),
    market_cap BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 3. Price Data (TimescaleDB Hypertable)
-- ============================================================

CREATE TABLE IF NOT EXISTS stock_prices (
    time TIMESTAMP NOT NULL,
    stock_id UUID NOT NULL REFERENCES stocks(id),
    open DECIMAL(10,2),
    high DECIMAL(10,2),
    low DECIMAL(10,2),
    close DECIMAL(10,2),
    volume BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create TimescaleDB hypertable for efficient time-series queries
SELECT create_hypertable('stock_prices', 'time', if_not_exists => TRUE);

-- ============================================================
-- 4. Financial Data
-- ============================================================

CREATE TABLE IF NOT EXISTS financials (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    stock_id UUID NOT NULL REFERENCES stocks(id),
    fiscal_year INT,
    fiscal_quarter INT,
    revenue DECIMAL(15,2),
    gross_profit DECIMAL(15,2),
    operating_income DECIMAL(15,2),
    net_income DECIMAL(15,2),
    eps DECIMAL(10,2),
    debt DECIMAL(15,2),
    cash_and_equivalents DECIMAL(15,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 5. Backtest Results
-- ============================================================

CREATE TABLE IF NOT EXISTS backtest_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_name VARCHAR(255),
    start_date DATE,
    end_date DATE,
    total_return DECIMAL(10,4),
    sharpe_ratio DECIMAL(10,4),
    max_drawdown DECIMAL(10,4),
    win_rate DECIMAL(10,4),
    total_trades INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 6. Trading Signals & Recommendations
-- ============================================================

CREATE TABLE IF NOT EXISTS trading_signals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    stock_id UUID NOT NULL REFERENCES stocks(id),
    signal_type VARCHAR(50), -- 'BUY', 'SELL', 'HOLD'
    confidence_score DECIMAL(5,2),
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- Indexes for Performance
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_stocks_ticker ON stocks(ticker);
CREATE INDEX IF NOT EXISTS idx_stock_prices_stock_id ON stock_prices(stock_id);
CREATE INDEX IF NOT EXISTS idx_financials_stock_id ON financials(stock_id);
CREATE INDEX IF NOT EXISTS idx_trading_signals_stock_id ON trading_signals(stock_id);

