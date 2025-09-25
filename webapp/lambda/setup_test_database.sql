-- Test Database Setup Script
-- This creates both core tables (from Python loaders) and webapp tables for testing
-- Production uses Python loaders for core tables, webapp only creates webapp-specific tables

-- ========================================
-- CORE DATA TABLES (from Python loaders)
-- ========================================

-- Core stock symbols table (from loadstocksymbols.py)
CREATE TABLE IF NOT EXISTS stock_symbols (
    symbol VARCHAR(10) PRIMARY KEY,
    security_name VARCHAR(255),
    exchange VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Company profile table (from loadinfo.py)
CREATE TABLE IF NOT EXISTS company_profile (
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
    full_exchange_name VARCHAR(100),
    exchange_timezone_name VARCHAR(100),
    exchange_timezone_short_name VARCHAR(20),
    exchange_data_delayed_by_sec INT,
    post_market_time_ms BIGINT,
    regular_market_time_ms BIGINT
);

-- Market data table (from loadinfo.py)
CREATE TABLE IF NOT EXISTS market_data (
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

-- Key metrics table (from loadinfo.py)
CREATE TABLE IF NOT EXISTS key_metrics (
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

-- Analyst estimates table (from loadinfo.py)
CREATE TABLE IF NOT EXISTS analyst_estimates (
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

-- Leadership team table (from loadinfo.py)
CREATE TABLE IF NOT EXISTS leadership_team (
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

-- Governance scores table (from loadinfo.py)
CREATE TABLE IF NOT EXISTS governance_scores (
    ticker VARCHAR(10) PRIMARY KEY REFERENCES company_profile(ticker),
    audit_risk INT,
    board_risk INT,
    compensation_risk INT,
    shareholder_rights_risk INT,
    overall_risk INT,
    governance_epoch_ms BIGINT,
    comp_data_as_of_ms BIGINT
);

-- Price daily table (from loadpricedaily.py)
CREATE TABLE IF NOT EXISTS price_daily (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    close DOUBLE PRECISION,
    adj_close DOUBLE PRECISION,
    volume BIGINT,
    dividends DOUBLE PRECISION,
    splits DOUBLE PRECISION,
    fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Earnings history table (from loadearningshistory.py)
CREATE TABLE IF NOT EXISTS earnings_history (
    symbol VARCHAR(20) NOT NULL,
    quarter DATE NOT NULL,
    eps_actual NUMERIC,
    eps_estimate NUMERIC,
    eps_difference NUMERIC,
    surprise_percent NUMERIC,
    fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, quarter)
);

-- Buy sell daily table (from loadbuyselldaily.py)
CREATE TABLE IF NOT EXISTS buy_sell_daily (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume BIGINT,
    signal VARCHAR(10),
    buylevel REAL,
    stoplevel REAL,
    inposition BOOLEAN,
    UNIQUE(symbol, timeframe, date)
);

-- Buy sell weekly table (from loadbuysellweekly.py)
CREATE TABLE IF NOT EXISTS buy_sell_weekly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume BIGINT,
    signal VARCHAR(10),
    buylevel REAL,
    stoplevel REAL,
    inposition BOOLEAN,
    UNIQUE(symbol, timeframe, date)
);

-- Buy sell monthly table (from loadbuysellmonthly.py)
CREATE TABLE IF NOT EXISTS buy_sell_monthly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume BIGINT,
    signal VARCHAR(10),
    buylevel REAL,
    stoplevel REAL,
    inposition BOOLEAN,
    UNIQUE(symbol, timeframe, date)
);

-- Swing trading signals table
CREATE TABLE IF NOT EXISTS swing_trading_signals (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    signal VARCHAR(20),
    entry_price DECIMAL(10,2),
    target_price DECIMAL(10,2),
    stop_loss DECIMAL(10,2),
    date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Technical data daily table
CREATE TABLE IF NOT EXISTS technical_data_daily (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    rsi_14 DECIMAL(5,2),
    sma_20 DECIMAL(10,2),
    sma_50 DECIMAL(10,2),
    sma_200 DECIMAL(10,2),
    price_vs_sma_200 DECIMAL(5,2),
    volume BIGINT,
    price DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Sentiment analysis table
CREATE TABLE IF NOT EXISTS sentiment_analysis (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    sentiment_score DECIMAL(3,2),
    news_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Profitability metrics table
CREATE TABLE IF NOT EXISTS profitability_metrics (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    roe DECIMAL(5,2),
    roa DECIMAL(5,2),
    trailing_pe DECIMAL(8,2),
    revenue_growth_1y DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Comprehensive scores table for scoring routes
CREATE TABLE IF NOT EXISTS comprehensive_scores (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    quality_score DECIMAL(3,2),
    growth_score DECIMAL(3,2),
    value_score DECIMAL(3,2),
    momentum_score DECIMAL(3,2),
    sentiment_score DECIMAL(3,2),
    positioning_score DECIMAL(3,2),
    composite_score DECIMAL(3,2),
    calculation_date DATE NOT NULL,
    data_quality INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, calculation_date)
);

-- Financial statements tables (from Python loaders) - key-value format
CREATE TABLE IF NOT EXISTS annual_balance_sheet (
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    item_name TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY(symbol, date, item_name)
);

CREATE TABLE IF NOT EXISTS quarterly_balance_sheet (
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    item_name TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY(symbol, date, item_name)
);

CREATE TABLE IF NOT EXISTS annual_income_statement (
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    item_name TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY(symbol, date, item_name)
);

CREATE TABLE IF NOT EXISTS quarterly_income_statement (
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    item_name TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY(symbol, date, item_name)
);

CREATE TABLE IF NOT EXISTS annual_cash_flow (
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    item_name TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY(symbol, date, item_name)
);

CREATE TABLE IF NOT EXISTS quarterly_cash_flow (
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    item_name TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY(symbol, date, item_name)
);

CREATE TABLE IF NOT EXISTS ttm_income_statement (
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    item_name TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY(symbol, date, item_name)
);

CREATE TABLE IF NOT EXISTS ttm_cash_flow (
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    item_name TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY(symbol, date, item_name)
);

-- ========================================
-- WEBAPP-SPECIFIC TABLES ONLY
-- ========================================

-- User watchlist functionality
CREATE TABLE IF NOT EXISTS watchlists (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    is_default BOOLEAN DEFAULT FALSE,
    is_public BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS watchlist_items (
    id SERIAL PRIMARY KEY,
    watchlist_id INTEGER REFERENCES watchlists(id) ON DELETE CASCADE,
    symbol VARCHAR(10) NOT NULL,
    notes TEXT,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(watchlist_id, symbol)
);

-- User portfolio tracking
CREATE TABLE IF NOT EXISTS portfolio_holdings (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    quantity DECIMAL(15,6),
    avg_price DECIMAL(10,2),
    current_price DECIMAL(10,2),
    market_value DECIMAL(15,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, symbol)
);

CREATE TABLE IF NOT EXISTS portfolio_performance (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    date DATE NOT NULL,
    total_value DECIMAL(15,2),
    daily_return DECIMAL(10,4),
    total_return DECIMAL(10,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, date)
);

-- Paper trading orders
CREATE TABLE IF NOT EXISTS orders_paper (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    side VARCHAR(10) NOT NULL, -- 'buy' or 'sell'
    quantity DECIMAL(15,6) NOT NULL,
    type VARCHAR(20) NOT NULL, -- 'market', 'limit', 'stop_limit'
    price DECIMAL(10,2),
    stop_price DECIMAL(10,2),
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    filled_at TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_stock_symbols_exchange ON stock_symbols(exchange);
CREATE INDEX IF NOT EXISTS idx_company_profile_sector ON company_profile(sector);
-- CREATE INDEX IF NOT EXISTS idx_company_profile_exchange ON company_profile(exchange); -- column doesn't exist
CREATE INDEX IF NOT EXISTS idx_market_data_market_cap ON market_data(market_cap);
CREATE INDEX IF NOT EXISTS idx_buy_sell_daily_symbol_date ON buy_sell_daily(symbol, date);
CREATE INDEX IF NOT EXISTS idx_buy_sell_weekly_symbol_date ON buy_sell_weekly(symbol, date);
CREATE INDEX IF NOT EXISTS idx_buy_sell_monthly_symbol_date ON buy_sell_monthly(symbol, date);
CREATE INDEX IF NOT EXISTS idx_technical_daily_symbol_date ON technical_data_daily(symbol, date);
CREATE INDEX IF NOT EXISTS idx_price_daily_symbol_date ON price_daily(symbol, date);
CREATE INDEX IF NOT EXISTS idx_sentiment_symbol_date ON sentiment_analysis(symbol, date);
CREATE INDEX IF NOT EXISTS idx_earnings_history_symbol_date ON earnings_history(symbol, quarter);
CREATE INDEX IF NOT EXISTS idx_annual_balance_sheet_symbol ON annual_balance_sheet(symbol);
CREATE INDEX IF NOT EXISTS idx_annual_balance_sheet_item ON annual_balance_sheet(item_name);
CREATE INDEX IF NOT EXISTS idx_quarterly_balance_sheet_symbol ON quarterly_balance_sheet(symbol);
CREATE INDEX IF NOT EXISTS idx_quarterly_balance_sheet_item ON quarterly_balance_sheet(item_name);
CREATE INDEX IF NOT EXISTS idx_annual_income_statement_symbol ON annual_income_statement(symbol);
CREATE INDEX IF NOT EXISTS idx_annual_income_statement_item ON annual_income_statement(item_name);
CREATE INDEX IF NOT EXISTS idx_quarterly_income_statement_symbol ON quarterly_income_statement(symbol);
CREATE INDEX IF NOT EXISTS idx_quarterly_income_statement_item ON quarterly_income_statement(item_name);
CREATE INDEX IF NOT EXISTS idx_annual_cash_flow_symbol ON annual_cash_flow(symbol);
CREATE INDEX IF NOT EXISTS idx_quarterly_cash_flow_symbol ON quarterly_cash_flow(symbol);
CREATE INDEX IF NOT EXISTS idx_ttm_income_statement_symbol ON ttm_income_statement(symbol);
CREATE INDEX IF NOT EXISTS idx_ttm_cash_flow_symbol ON ttm_cash_flow(symbol);
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_user ON portfolio_holdings(user_id);
CREATE INDEX IF NOT EXISTS idx_watchlists_user ON watchlists(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_user ON orders_paper(user_id);

-- Insert test data for core Python loader tables to make routes work
INSERT INTO company_profile (ticker, short_name, long_name, sector, industry, exchange, website_url, business_summary, employee_count) VALUES
('AAPL', 'Apple Inc.', 'Apple Inc.', 'Technology', 'Consumer Electronics', 'NASDAQ', 'https://www.apple.com', 'Technology company', 154000),
('MSFT', 'Microsoft Corp.', 'Microsoft Corporation', 'Technology', 'Software', 'NASDAQ', 'https://www.microsoft.com', 'Software company', 221000),
('GOOGL', 'Alphabet Inc.', 'Alphabet Inc.', 'Technology', 'Internet Content & Information', 'NASDAQ', 'https://www.google.com', 'Search and advertising', 182000),
('TSLA', 'Tesla Inc.', 'Tesla, Inc.', 'Consumer Cyclical', 'Auto Manufacturers', 'NASDAQ', 'https://www.tesla.com', 'Electric vehicles', 140000),
('AMZN', 'Amazon.com Inc.', 'Amazon.com, Inc.', 'Consumer Cyclical', 'Internet Retail', 'NASDAQ', 'https://www.amazon.com', 'E-commerce and cloud', 1500000)
ON CONFLICT (ticker) DO NOTHING;

INSERT INTO market_data (ticker, previous_close, current_price, volume, market_cap, fifty_two_week_low, fifty_two_week_high) VALUES
('AAPL', 175.50, 180.25, 52000000, 2800000000000, 130.00, 200.00),
('MSFT', 420.75, 425.30, 28000000, 3100000000000, 310.00, 450.00),
('GOOGL', 135.80, 138.45, 31000000, 1700000000000, 120.00, 160.00),
('TSLA', 250.30, 255.75, 67000000, 800000000000, 150.00, 420.00),
('AMZN', 145.20, 148.90, 35000000, 1500000000000, 120.00, 180.00)
ON CONFLICT (ticker) DO NOTHING;

INSERT INTO key_metrics (ticker, trailing_pe, forward_pe, price_to_book, profit_margin_pct, return_on_equity_pct, return_on_assets_pct, market_cap, enterprise_value) VALUES
('AAPL', 28.5, 25.2, 4.2, 0.26, 0.35, 0.18, 2800000000000, 2750000000000),
('MSFT', 32.1, 28.8, 5.1, 0.31, 0.42, 0.15, 3100000000000, 3050000000000),
('GOOGL', 22.3, 20.1, 3.8, 0.21, 0.28, 0.12, 1700000000000, 1680000000000),
('TSLA', 45.2, 38.5, 8.9, 0.08, 0.18, 0.09, 800000000000, 780000000000),
('AMZN', 38.7, 35.2, 6.2, 0.05, 0.12, 0.06, 1500000000000, 1480000000000)
ON CONFLICT (ticker) DO NOTHING;

INSERT INTO price_daily (symbol, date, open, high, low, close, adj_close, volume) VALUES
('AAPL', '2024-01-01', 175.00, 180.50, 174.20, 180.25, 180.25, 52000000),
('MSFT', '2024-01-01', 420.00, 425.80, 418.90, 425.30, 425.30, 28000000),
('GOOGL', '2024-01-01', 135.20, 139.00, 134.80, 138.45, 138.45, 31000000),
('TSLA', '2024-01-01', 248.50, 256.20, 247.80, 255.75, 255.75, 67000000),
('AMZN', '2024-01-01', 144.80, 149.20, 143.90, 148.90, 148.90, 35000000)
ON CONFLICT (symbol, date) DO NOTHING;

INSERT INTO earnings_history (symbol, quarter, eps_actual, eps_estimate, eps_difference, surprise_percent) VALUES
('AAPL', '2024-01-15', 2.18, 2.10, 0.08, 3.81),
('MSFT', '2024-01-20', 2.93, 2.87, 0.06, 2.09),
('GOOGL', '2024-01-25', 1.64, 1.59, 0.05, 3.14),
('TSLA', '2024-01-30', 0.71, 0.73, -0.02, -2.74),
('AMZN', '2024-02-05', 1.00, 0.80, 0.20, 25.00)
ON CONFLICT (symbol, quarter) DO NOTHING;

-- Insert webapp test data
INSERT INTO watchlists (user_id, name) VALUES
('test-user-123', 'My Watchlist'),
('test-user-456', 'Tech Stocks')
ON CONFLICT DO NOTHING;

INSERT INTO portfolio_holdings (user_id, symbol, quantity, average_cost, current_price) VALUES
('test-user-123', 'AAPL', 10.0, 150.00, 175.50),
('test-user-123', 'MSFT', 5.0, 300.00, 420.75)
ON CONFLICT (user_id, symbol) DO NOTHING;

COMMIT;