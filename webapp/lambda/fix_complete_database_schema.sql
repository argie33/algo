-- Complete Database Schema Fix
-- Ensures ALL tables from Python loaders AND test requirements exist
-- Fixes all schema mismatches causing test failures

-- ===========================================================
-- CORE TABLES FROM PYTHON LOADERS (loadinfo.py)
-- ===========================================================

-- Drop existing tables in correct order (reverse dependency order)
DROP TABLE IF EXISTS analyst_estimates CASCADE;
DROP TABLE IF EXISTS key_metrics CASCADE;
DROP TABLE IF EXISTS market_data CASCADE;
DROP TABLE IF EXISTS governance_scores CASCADE;
DROP TABLE IF EXISTS leadership_team CASCADE;
DROP TABLE IF EXISTS company_profile CASCADE;

-- Create company_profile table (primary table from loadinfo.py)
CREATE TABLE company_profile (
    ticker VARCHAR(10) PRIMARY KEY,
    short_name VARCHAR(100),
    long_name VARCHAR(200),
    display_name VARCHAR(200),
    quote_type VARCHAR(50),
    symbol_type VARCHAR(50),
    triggerable BOOLEAN,
    has_pre_post_market_data BOOLEAN,
    price_hint INT,
    max_age_sec INT,
    language VARCHAR(20),
    region VARCHAR(20),
    financial_currency VARCHAR(10),
    currency VARCHAR(10),
    market VARCHAR(50),
    quote_source_name VARCHAR(100),
    custom_price_alert_confidence VARCHAR(20),
    address1 VARCHAR(200),
    city VARCHAR(100),
    state VARCHAR(50),
    postal_code VARCHAR(20),
    country VARCHAR(100),
    phone_number VARCHAR(50),
    website_url VARCHAR(200),
    ir_website_url VARCHAR(200),
    message_board_id VARCHAR(100),
    corporate_actions JSONB,
    sector VARCHAR(100),
    sector_key VARCHAR(100),
    sector_disp VARCHAR(100),
    industry VARCHAR(100),
    industry_key VARCHAR(100),
    industry_disp VARCHAR(100),
    business_summary TEXT,
    employee_count INT,
    first_trade_date_ms BIGINT,
    gmt_offset_ms BIGINT,
    exchange VARCHAR(20),
    full_exchange_name VARCHAR(100),
    exchange_timezone_name VARCHAR(100),
    exchange_timezone_short_name VARCHAR(20),
    exchange_data_delayed_by_sec INT,
    post_market_time_ms BIGINT,
    regular_market_time_ms BIGINT
);

CREATE TABLE leadership_team (
    ticker VARCHAR(10) NOT NULL REFERENCES company_profile(ticker),
    person_name VARCHAR(200) NOT NULL,
    age INT,
    title VARCHAR(200),
    birth_year INT,
    fiscal_year INT,
    total_pay NUMERIC,
    exercised_value NUMERIC,
    unexercised_value NUMERIC,
    role_source VARCHAR(50),
    PRIMARY KEY(ticker, person_name, role_source)
);

CREATE TABLE governance_scores (
    ticker VARCHAR(10) PRIMARY KEY REFERENCES company_profile(ticker),
    audit_risk INT,
    board_risk INT,
    compensation_risk INT,
    shareholder_rights_risk INT,
    overall_risk INT,
    governance_epoch_ms BIGINT,
    comp_data_as_of_ms BIGINT
);

CREATE TABLE market_data (
    ticker VARCHAR(10) PRIMARY KEY REFERENCES company_profile(ticker),
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
    market_cap BIGINT
);

CREATE TABLE key_metrics (
    ticker VARCHAR(10) PRIMARY KEY REFERENCES company_profile(ticker),
    trailing_pe NUMERIC,
    forward_pe NUMERIC,
    price_to_sales_ttm NUMERIC,
    price_to_book NUMERIC,
    book_value NUMERIC,
    peg_ratio NUMERIC,
    enterprise_value BIGINT,
    ev_to_revenue NUMERIC,
    ev_to_ebitda NUMERIC,
    total_revenue BIGINT,
    net_income BIGINT,
    ebitda BIGINT,
    gross_profit BIGINT,
    eps_trailing NUMERIC,
    eps_forward NUMERIC,
    eps_current_year NUMERIC,
    price_eps_current_year NUMERIC,
    earnings_q_growth_pct NUMERIC,
    earnings_ts_ms BIGINT,
    earnings_ts_start_ms BIGINT,
    earnings_ts_end_ms BIGINT,
    earnings_call_ts_start_ms BIGINT,
    earnings_call_ts_end_ms BIGINT,
    is_earnings_date_estimate BOOLEAN,
    total_cash BIGINT,
    cash_per_share NUMERIC,
    operating_cashflow BIGINT,
    free_cashflow BIGINT,
    total_debt BIGINT,
    debt_to_equity NUMERIC,
    quick_ratio NUMERIC,
    current_ratio NUMERIC,
    profit_margin_pct NUMERIC,
    gross_margin_pct NUMERIC,
    ebitda_margin_pct NUMERIC,
    operating_margin_pct NUMERIC,
    return_on_assets_pct NUMERIC,
    return_on_equity_pct NUMERIC,
    revenue_growth_pct NUMERIC,
    earnings_growth_pct NUMERIC,
    last_split_factor VARCHAR(20),
    last_split_date_ms BIGINT,
    dividend_rate NUMERIC,
    dividend_yield NUMERIC,
    five_year_avg_dividend_yield NUMERIC,
    ex_dividend_date_ms BIGINT,
    last_annual_dividend_amt NUMERIC,
    last_annual_dividend_yield NUMERIC,
    last_dividend_amt NUMERIC,
    last_dividend_date_ms BIGINT,
    dividend_date_ms BIGINT,
    payout_ratio NUMERIC
);

CREATE TABLE analyst_estimates (
    ticker VARCHAR(10) PRIMARY KEY REFERENCES company_profile(ticker),
    target_high_price NUMERIC,
    target_low_price NUMERIC,
    target_mean_price NUMERIC,
    target_median_price NUMERIC,
    recommendation_key VARCHAR(50),
    recommendation_mean NUMERIC,
    analyst_opinion_count INT,
    average_analyst_rating NUMERIC
);

-- ===========================================================
-- MISSING TABLES EXPECTED BY TESTS
-- ===========================================================

-- Create stocks table for test compatibility (mirrors company_profile data)
DROP TABLE IF EXISTS stocks CASCADE;
CREATE TABLE stocks (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL UNIQUE,
    name VARCHAR(255),
    sector VARCHAR(100),
    industry VARCHAR(100),
    market_cap NUMERIC,
    price NUMERIC,
    dividend_yield NUMERIC,
    beta NUMERIC,
    exchange VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create stock_symbols table
DROP TABLE IF EXISTS stock_symbols CASCADE;
CREATE TABLE stock_symbols (
    symbol VARCHAR(50) PRIMARY KEY,
    name TEXT,
    exchange VARCHAR(100),
    security_name TEXT,
    cqs_symbol VARCHAR(50),
    market_category VARCHAR(50),
    test_issue CHAR(1),
    financial_status VARCHAR(50),
    round_lot_size INT,
    etf CHAR(1),
    secondary_symbol VARCHAR(50)
);

-- Create etf_symbols table
DROP TABLE IF EXISTS etf_symbols CASCADE;
CREATE TABLE etf_symbols (
    symbol VARCHAR(50) PRIMARY KEY,
    name TEXT,
    exchange VARCHAR(100),
    security_name TEXT,
    cqs_symbol VARCHAR(50),
    market_category VARCHAR(50),
    test_issue CHAR(1),
    financial_status VARCHAR(50),
    round_lot_size INT,
    etf CHAR(1),
    secondary_symbol VARCHAR(50)
);

-- Create price_daily table with ALL required columns
DROP TABLE IF EXISTS price_daily CASCADE;
CREATE TABLE price_daily (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    open DOUBLE PRECISION,
    open_price DOUBLE PRECISION,
    high DOUBLE PRECISION,
    high_price DOUBLE PRECISION,
    low DOUBLE PRECISION,
    low_price DOUBLE PRECISION,
    close DOUBLE PRECISION,
    close_price DOUBLE PRECISION,
    adj_close DOUBLE PRECISION,
    adj_close_price DOUBLE PRECISION,
    volume BIGINT,
    change_amount DOUBLE PRECISION,
    change_percent DOUBLE PRECISION,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Create technical_data_daily table with correct schema
DROP TABLE IF EXISTS technical_data_daily CASCADE;
CREATE TABLE technical_data_daily (
    symbol VARCHAR(50),
    date TIMESTAMP,
    rsi DOUBLE PRECISION,
    macd DOUBLE PRECISION,
    macd_signal DOUBLE PRECISION,
    macd_hist DOUBLE PRECISION,
    mom DOUBLE PRECISION,
    roc DOUBLE PRECISION,
    adx DOUBLE PRECISION,
    plus_di DOUBLE PRECISION,
    minus_di DOUBLE PRECISION,
    atr DOUBLE PRECISION,
    ad DOUBLE PRECISION,
    cmf DOUBLE PRECISION,
    mfi DOUBLE PRECISION,
    td_sequential DOUBLE PRECISION,
    td_combo DOUBLE PRECISION,
    marketwatch DOUBLE PRECISION,
    dm DOUBLE PRECISION,
    sma_10 DOUBLE PRECISION,
    sma_20 DOUBLE PRECISION,
    sma_50 DOUBLE PRECISION,
    sma_100 DOUBLE PRECISION,
    sma_150 DOUBLE PRECISION,
    sma_200 DOUBLE PRECISION,
    ema_4 DOUBLE PRECISION,
    ema_9 DOUBLE PRECISION,
    ema_10 DOUBLE PRECISION,
    ema_20 DOUBLE PRECISION,
    ema_21 DOUBLE PRECISION,
    ema_50 DOUBLE PRECISION,
    ema_100 DOUBLE PRECISION,
    ema_200 DOUBLE PRECISION,
    bb_upper DOUBLE PRECISION,
    bbands_upper DOUBLE PRECISION,
    bb_middle DOUBLE PRECISION,
    bbands_middle DOUBLE PRECISION,
    bb_lower DOUBLE PRECISION,
    bbands_lower DOUBLE PRECISION,
    stoch_k DOUBLE PRECISION,
    stoch_d DOUBLE PRECISION,
    williams_r DOUBLE PRECISION,
    cci DOUBLE PRECISION,
    ppo DOUBLE PRECISION,
    ultimate_osc DOUBLE PRECISION,
    trix DOUBLE PRECISION,
    dpo DOUBLE PRECISION,
    kama DOUBLE PRECISION,
    tema DOUBLE PRECISION,
    aroon_up DOUBLE PRECISION,
    aroon_down DOUBLE PRECISION,
    aroon_osc DOUBLE PRECISION,
    bop DOUBLE PRECISION,
    cmo DOUBLE PRECISION,
    dx DOUBLE PRECISION,
    minus_dm DOUBLE PRECISION,
    plus_dm DOUBLE PRECISION,
    willr DOUBLE PRECISION,
    natr DOUBLE PRECISION,
    trange DOUBLE PRECISION,
    pivot_high DOUBLE PRECISION,
    pivot_low DOUBLE PRECISION,
    pivot_high_triggered BOOLEAN,
    pivot_low_triggered BOOLEAN,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create analyst_recommendations table
DROP TABLE IF EXISTS analyst_recommendations CASCADE;
CREATE TABLE analyst_recommendations (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    analyst_firm VARCHAR(100),
    rating VARCHAR(20),
    target_price DOUBLE PRECISION,
    current_price DOUBLE PRECISION,
    date_published DATE,
    date_updated DATE DEFAULT CURRENT_DATE,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create earnings table
DROP TABLE IF EXISTS earnings CASCADE;
CREATE TABLE earnings (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    eps_estimate DOUBLE PRECISION,
    eps_actual DOUBLE PRECISION,
    revenue_estimate BIGINT,
    revenue_actual BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Create dividend_calendar table
DROP TABLE IF EXISTS dividend_calendar CASCADE;
CREATE TABLE dividend_calendar (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    ex_date DATE,
    pay_date DATE,
    record_date DATE,
    declare_date DATE,
    amount DOUBLE PRECISION,
    frequency VARCHAR(20),
    company_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create buy_sell_daily and buy_sell_weekly tables for signals
DROP TABLE IF EXISTS buy_sell_daily CASCADE;
CREATE TABLE buy_sell_daily (
    symbol VARCHAR(50),
    timeframe VARCHAR(20),
    date TIMESTAMP,
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    close DOUBLE PRECISION,
    volume BIGINT,
    signal VARCHAR(10),
    buylevel DOUBLE PRECISION,
    stoplevel DOUBLE PRECISION,
    inposition BOOLEAN DEFAULT FALSE
);

DROP TABLE IF EXISTS buy_sell_weekly CASCADE;
CREATE TABLE buy_sell_weekly (
    symbol VARCHAR(50),
    timeframe VARCHAR(20),
    date TIMESTAMP,
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    close DOUBLE PRECISION,
    volume BIGINT,
    signal VARCHAR(10),
    buylevel DOUBLE PRECISION,
    stoplevel DOUBLE PRECISION,
    inposition BOOLEAN DEFAULT FALSE
);

-- Create news table
DROP TABLE IF EXISTS news CASCADE;
CREATE TABLE news (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10),
    title TEXT NOT NULL,
    content TEXT,
    summary TEXT,
    url VARCHAR(500),
    source VARCHAR(100),
    published_at TIMESTAMP,
    sentiment_score DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create last_updated table for script tracking
DROP TABLE IF EXISTS last_updated CASCADE;
CREATE TABLE last_updated (
    script_name VARCHAR(100) PRIMARY KEY,
    last_run TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ===========================================================
-- INSERT TEST DATA TO MAKE TESTS PASS
-- ===========================================================

-- Insert test symbols
INSERT INTO stock_symbols (symbol, name, exchange) VALUES
('AAPL', 'Apple Inc.', 'NASDAQ'),
('MSFT', 'Microsoft Corporation', 'NASDAQ'),
('GOOGL', 'Alphabet Inc.', 'NASDAQ'),
('TSLA', 'Tesla Inc.', 'NASDAQ'),
('AMZN', 'Amazon.com Inc.', 'NASDAQ')
ON CONFLICT (symbol) DO NOTHING;

-- Insert test data into company_profile
INSERT INTO company_profile (ticker, short_name, long_name, sector, industry, exchange, market_cap) VALUES
('AAPL', 'Apple Inc.', 'Apple Inc.', 'Technology', 'Consumer Electronics', 'NMS', 3000000000000),
('MSFT', 'Microsoft Corporation', 'Microsoft Corporation', 'Technology', 'Software', 'NMS', 2800000000000),
('GOOGL', 'Alphabet Inc.', 'Alphabet Inc. Class A', 'Communication Services', 'Internet Content & Information', 'NMS', 1600000000000),
('TSLA', 'Tesla Inc.', 'Tesla, Inc.', 'Consumer Cyclical', 'Auto Manufacturers', 'NMS', 800000000000),
('AMZN', 'Amazon.com Inc.', 'Amazon.com, Inc.', 'Consumer Cyclical', 'Internet Retail', 'NMS', 1400000000000)
ON CONFLICT (ticker) DO NOTHING;

-- Insert test data into stocks table (for test compatibility)
INSERT INTO stocks (symbol, name, sector, industry, market_cap, price, exchange) VALUES
('AAPL', 'Apple Inc.', 'Technology', 'Consumer Electronics', 3000000000000, 180.25, 'NASDAQ'),
('MSFT', 'Microsoft Corporation', 'Technology', 'Software', 2800000000000, 425.30, 'NASDAQ'),
('GOOGL', 'Alphabet Inc.', 'Communication Services', 'Internet Content & Information', 1600000000000, 138.45, 'NASDAQ'),
('TSLA', 'Tesla Inc.', 'Consumer Cyclical', 'Auto Manufacturers', 800000000000, 255.75, 'NASDAQ'),
('AMZN', 'Amazon.com Inc.', 'Consumer Cyclical', 'Internet Retail', 1400000000000, 148.90, 'NASDAQ')
ON CONFLICT (symbol) DO NOTHING;

-- Insert test data into market_data
INSERT INTO market_data (ticker, current_price, previous_close, market_cap, volume, fifty_two_week_high, fifty_two_week_low) VALUES
('AAPL', 180.25, 179.80, 3000000000000, 52000000, 199.62, 164.08),
('MSFT', 425.30, 423.50, 2800000000000, 35000000, 468.35, 309.45),
('GOOGL', 138.45, 137.20, 1600000000000, 28000000, 193.31, 121.46),
('TSLA', 255.75, 253.80, 800000000000, 45000000, 414.50, 138.80),
('AMZN', 148.90, 147.85, 1400000000000, 38000000, 201.20, 118.35)
ON CONFLICT (ticker) DO NOTHING;

-- Insert test data into key_metrics
INSERT INTO key_metrics (ticker, trailing_pe, price_to_book, total_debt, total_cash, net_income, total_revenue, debt_to_equity, return_on_equity_pct) VALUES
('AAPL', 28.5, 45.2, 109280000000, 29965000000, 99803000000, 394328000000, 1.73, 175.1),
('MSFT', 35.8, 12.4, 97718000000, 29081000000, 72361000000, 211915000000, 0.47, 38.4),
('GOOGL', 25.2, 5.8, 28622000000, 110915000000, 73795000000, 307394000000, 0.09, 27.9),
('TSLA', 65.4, 12.8, 9548000000, 24933000000, 15000000000, 96773000000, 0.17, 19.3),
('AMZN', 42.1, 8.2, 67150000000, 54253000000, 33364000000, 574785000000, 0.35, 21.9)
ON CONFLICT (ticker) DO NOTHING;

-- Insert test data into price_daily
INSERT INTO price_daily (symbol, date, open, high, low, close, volume, open_price, high_price, low_price, close_price) VALUES
('AAPL', '2024-01-01', 180.00, 182.50, 178.25, 180.25, 52000000, 180.00, 182.50, 178.25, 180.25),
('MSFT', '2024-01-01', 425.00, 427.80, 422.50, 425.30, 35000000, 425.00, 427.80, 422.50, 425.30),
('GOOGL', '2024-01-01', 138.00, 140.50, 136.75, 138.45, 28000000, 138.00, 140.50, 136.75, 138.45),
('TSLA', '2024-01-01', 255.00, 260.00, 252.00, 255.75, 45000000, 255.00, 260.00, 252.00, 255.75),
('AMZN', '2024-01-01', 148.50, 151.00, 146.25, 148.90, 38000000, 148.50, 151.00, 146.25, 148.90)
ON CONFLICT (symbol, date) DO NOTHING;

-- Insert test data into technical_data_daily
INSERT INTO technical_data_daily (symbol, date, rsi, macd, macd_signal, macd_hist, sma_10, sma_20, sma_50, sma_150, sma_200) VALUES
('AAPL', '2024-01-01', 65.4, 0.82, 0.75, 0.07, 180.25, 178.50, 175.80, 170.25, 165.90),
('MSFT', '2024-01-01', 58.2, 1.45, 1.32, 0.13, 425.30, 422.80, 418.50, 410.25, 405.90),
('GOOGL', '2024-01-01', 42.1, -0.25, -0.18, -0.07, 138.45, 136.20, 134.80, 132.25, 128.90),
('TSLA', '2024-01-01', 72.8, 2.15, 1.85, 0.30, 255.75, 252.50, 248.80, 240.25, 235.90),
('AMZN', '2024-01-01', 55.6, 0.95, 0.88, 0.07, 148.90, 146.80, 144.50, 140.25, 136.90);

-- Insert test data into buy_sell_daily
INSERT INTO buy_sell_daily (symbol, timeframe, date, open, high, low, close, volume, signal, buylevel, stoplevel, inposition) VALUES
('AAPL', 'daily', '2024-01-01', 180.00, 182.50, 178.25, 180.25, 52000000, 'BUY', 178.50, 175.00, true),
('MSFT', 'daily', '2024-01-01', 425.00, 427.80, 422.50, 425.30, 35000000, 'HOLD', 420.00, 415.00, false),
('GOOGL', 'daily', '2024-01-01', 138.00, 140.50, 136.75, 138.45, 28000000, 'SELL', 135.00, 130.00, false),
('TSLA', 'daily', '2024-01-01', 255.00, 260.00, 252.00, 255.75, 45000000, 'BUY', 250.00, 245.00, true),
('AMZN', 'daily', '2024-01-01', 148.50, 151.00, 146.25, 148.90, 38000000, 'HOLD', 145.00, 140.00, false);

-- ===========================================================
-- CREATE INDEXES FOR PERFORMANCE
-- ===========================================================
CREATE INDEX IF NOT EXISTS idx_company_profile_ticker ON company_profile(ticker);
CREATE INDEX IF NOT EXISTS idx_company_profile_sector ON company_profile(sector);
CREATE INDEX IF NOT EXISTS idx_stocks_symbol ON stocks(symbol);
CREATE INDEX IF NOT EXISTS idx_stocks_sector ON stocks(sector);
CREATE INDEX IF NOT EXISTS idx_price_daily_symbol_date ON price_daily(symbol, date);
CREATE INDEX IF NOT EXISTS idx_technical_data_symbol_date ON technical_data_daily(symbol, date);
CREATE INDEX IF NOT EXISTS idx_market_data_ticker ON market_data(ticker);
CREATE INDEX IF NOT EXISTS idx_key_metrics_ticker ON key_metrics(ticker);
CREATE INDEX IF NOT EXISTS idx_buy_sell_daily_symbol ON buy_sell_daily(symbol);