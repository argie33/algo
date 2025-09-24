-- Database schema that matches the Python loader scripts exactly
-- Based on: loadstocksymbols.py, loadfundamentalmetrics.py, loadpricedaily.py

-- Stock symbols table (from loadstocksymbols.py)
CREATE TABLE IF NOT EXISTS stock_symbols (
    symbol            VARCHAR(50),
    exchange          VARCHAR(100),
    security_name     TEXT,
    cqs_symbol        VARCHAR(50),
    market_category   VARCHAR(50),
    test_issue        CHAR(1),
    financial_status  VARCHAR(50),
    round_lot_size    INT,
    etf               CHAR(1),
    secondary_symbol  VARCHAR(50)
);

-- ETF symbols table (from loadstocksymbols.py)
CREATE TABLE IF NOT EXISTS etf_symbols (
    symbol            VARCHAR(50),
    exchange          VARCHAR(100),
    security_name     TEXT,
    cqs_symbol        VARCHAR(50),
    market_category   VARCHAR(50),
    test_issue        CHAR(1),
    financial_status  VARCHAR(50),
    round_lot_size    INT,
    etf               CHAR(1),
    secondary_symbol  VARCHAR(50)
);

-- Price daily table (from loadpricedaily.py)
CREATE TABLE IF NOT EXISTS price_daily (
    id           SERIAL PRIMARY KEY,
    symbol       VARCHAR(10) NOT NULL,
    date         DATE         NOT NULL,
    open         DOUBLE PRECISION,
    high         DOUBLE PRECISION,
    low          DOUBLE PRECISION,
    close        DOUBLE PRECISION,
    adj_close    DOUBLE PRECISION,
    volume       BIGINT,
    dividends    DOUBLE PRECISION,
    stock_splits DOUBLE PRECISION,
    fetched_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ETF price daily table (from loadpricedaily.py)
CREATE TABLE IF NOT EXISTS etf_price_daily (
    id           SERIAL PRIMARY KEY,
    symbol       VARCHAR(10) NOT NULL,
    date         DATE         NOT NULL,
    open         DOUBLE PRECISION,
    high         DOUBLE PRECISION,
    low          DOUBLE PRECISION,
    close        DOUBLE PRECISION,
    adj_close    DOUBLE PRECISION,
    volume       BIGINT,
    dividends    DOUBLE PRECISION,
    stock_splits DOUBLE PRECISION,
    fetched_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Fundamental metrics table (from loadfundamentalmetrics.py)
CREATE TABLE IF NOT EXISTS fundamental_metrics (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    market_cap BIGINT,
    pe_ratio DECIMAL(10,2),
    forward_pe DECIMAL(10,2),
    peg_ratio DECIMAL(10,2),
    price_to_book DECIMAL(10,2),
    price_to_sales DECIMAL(10,2),
    price_to_cash_flow DECIMAL(10,2),
    dividend_yield DECIMAL(8,4),
    dividend_rate DECIMAL(10,2),
    beta DECIMAL(8,4),
    fifty_two_week_high DECIMAL(10,2),
    fifty_two_week_low DECIMAL(10,2),
    revenue_per_share DECIMAL(10,2),
    revenue BIGINT,
    quarterly_revenue_growth DECIMAL(8,4),
    gross_profit BIGINT,
    ebitda BIGINT,
    operating_income BIGINT,
    net_income BIGINT,
    earnings_per_share DECIMAL(10,2),
    quarterly_earnings_growth DECIMAL(8,4),
    return_on_equity DECIMAL(8,4),
    return_on_assets DECIMAL(8,4),
    debt_to_equity DECIMAL(10,2),
    current_ratio DECIMAL(8,4),
    quick_ratio DECIMAL(8,4),
    book_value DECIMAL(10,2),
    shares_outstanding BIGINT,
    float_shares BIGINT,
    short_ratio DECIMAL(8,2),
    short_interest BIGINT,
    enterprise_value BIGINT,
    enterprise_to_revenue DECIMAL(10,2),
    enterprise_to_ebitda DECIMAL(10,2),
    sector VARCHAR(100),
    industry VARCHAR(200),
    full_time_employees INTEGER,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol)
);

-- Last updated tracking table (from loaders)
CREATE TABLE IF NOT EXISTS last_updated (
    script_name   VARCHAR(255) PRIMARY KEY,
    last_run      TIMESTAMP WITH TIME ZONE
);

-- Indexes for performance (from loaders)
CREATE INDEX IF NOT EXISTS idx_fundamental_metrics_symbol ON fundamental_metrics(symbol);
CREATE INDEX IF NOT EXISTS idx_fundamental_metrics_sector ON fundamental_metrics(sector);
CREATE INDEX IF NOT EXISTS idx_fundamental_metrics_industry ON fundamental_metrics(industry);
CREATE INDEX IF NOT EXISTS idx_fundamental_metrics_updated ON fundamental_metrics(updated_at);

CREATE INDEX IF NOT EXISTS idx_price_daily_symbol_date ON price_daily(symbol, date);
CREATE INDEX IF NOT EXISTS idx_etf_price_daily_symbol_date ON etf_price_daily(symbol, date);

-- New table indexes for performance
CREATE INDEX IF NOT EXISTS idx_market_data_ticker ON market_data(ticker);
CREATE INDEX IF NOT EXISTS idx_stock_news_ticker ON stock_news(ticker);
CREATE INDEX IF NOT EXISTS idx_stock_news_publish_time ON stock_news(publish_time);
CREATE INDEX IF NOT EXISTS idx_earnings_reports_symbol ON earnings_reports(symbol);
CREATE INDEX IF NOT EXISTS idx_earnings_reports_date ON earnings_reports(report_date);
CREATE INDEX IF NOT EXISTS idx_stock_scores_symbol ON stock_scores(symbol);
CREATE INDEX IF NOT EXISTS idx_stock_scores_composite ON stock_scores(composite_score);

-- Additional tables that exist in the current system but need to be compatible
-- Company profile table (needs to be compatible with both loaders and current API)
CREATE TABLE IF NOT EXISTS company_profile (
    ticker VARCHAR(10) PRIMARY KEY,
    name TEXT,
    sector VARCHAR(100),
    industry VARCHAR(100),
    description TEXT,
    market_cap BIGINT,
    employees INTEGER,
    founded INTEGER,
    headquarters VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Annual balance sheet (for financial data)
CREATE TABLE IF NOT EXISTS annual_balance_sheet (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10),
    year INTEGER,
    total_assets BIGINT,
    total_liabilities BIGINT,
    total_debt BIGINT,
    revenue BIGINT,
    net_income BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ticker, year)
);

-- Market data table (for real-time market data from loader)
CREATE TABLE IF NOT EXISTS market_data (
    ticker VARCHAR(10) PRIMARY KEY,
    previous_close NUMERIC,
    regular_market_previous_close NUMERIC,
    open_price NUMERIC,
    regular_market_open NUMERIC,
    day_low NUMERIC,
    regular_market_day_low NUMERIC,
    day_high NUMERIC,
    regular_market_day_high NUMERIC,
    regular_market_price NUMERIC,
    current_price NUMERIC,
    post_market_price NUMERIC,
    post_market_change NUMERIC,
    post_market_change_pct NUMERIC,
    volume BIGINT,
    regular_market_volume BIGINT,
    average_volume BIGINT,
    avg_volume_10d BIGINT,
    avg_daily_volume_10d BIGINT,
    avg_daily_volume_3m BIGINT,
    bid_price NUMERIC,
    ask_price NUMERIC,
    bid_size INT,
    ask_size INT,
    market_state VARCHAR(20),
    fifty_two_week_low NUMERIC,
    fifty_two_week_high NUMERIC,
    fifty_two_week_range VARCHAR(50),
    fifty_two_week_low_change NUMERIC,
    fifty_two_week_low_change_pct NUMERIC,
    fifty_two_week_high_change NUMERIC,
    fifty_two_week_high_change_pct NUMERIC,
    fifty_two_week_change_pct NUMERIC,
    fifty_day_avg NUMERIC,
    two_hundred_day_avg NUMERIC,
    fifty_day_avg_change NUMERIC,
    fifty_day_avg_change_pct NUMERIC,
    two_hundred_day_avg_change NUMERIC,
    two_hundred_day_avg_change_pct NUMERIC,
    source_interval_sec INT,
    market_cap BIGINT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Stock news table (for news data)
CREATE TABLE IF NOT EXISTS stock_news (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    url TEXT,
    publish_time TIMESTAMP,
    provider VARCHAR(100),
    related_tickers JSONB,
    sentiment_score DECIMAL(3,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Earnings reports table (from load_earnings_data.py)
CREATE TABLE IF NOT EXISTS earnings_reports (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    company_name VARCHAR(200),
    report_date DATE,
    quarter INTEGER,
    fiscal_year INTEGER,
    estimated_eps DECIMAL(10,4),
    actual_eps DECIMAL(10,4),
    surprise_percent DECIMAL(8,4),
    estimated_revenue BIGINT,
    actual_revenue BIGINT,
    revenue_surprise_percent DECIMAL(8,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_year, quarter)
);

-- Stock scores table (from loadstockscores.py)
CREATE TABLE IF NOT EXISTS stock_scores (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    composite_score DECIMAL(8,4),
    momentum_score DECIMAL(8,4),
    value_score DECIMAL(8,4),
    quality_score DECIMAL(8,4),
    growth_score DECIMAL(8,4),
    volatility_score DECIMAL(8,4),
    sentiment_score DECIMAL(8,4),
    analyst_score DECIMAL(8,4),
    technical_score DECIMAL(8,4),
    financial_health_score DECIMAL(8,4),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol)
);

-- Key metrics table (for backwards compatibility with existing API)
CREATE TABLE IF NOT EXISTS key_metrics (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10),
    ticker VARCHAR(10), -- For compatibility with existing routes
    date DATE NOT NULL DEFAULT CURRENT_DATE,
    revenue DECIMAL(15,2),
    net_income DECIMAL(15,2),
    total_assets DECIMAL(15,2),
    total_liabilities DECIMAL(15,2),
    shareholders_equity DECIMAL(15,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ticker, date)
);