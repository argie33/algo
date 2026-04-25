-- Reset local database to match loader table structures exactly
-- This drops all existing tables and recreates them with exact loader schemas

-- Drop existing tables to avoid conflicts
DROP TABLE IF EXISTS fundamental_metrics CASCADE;
DROP TABLE IF EXISTS price_daily CASCADE;
DROP TABLE IF EXISTS etf_price_daily CASCADE;
DROP TABLE IF EXISTS stock_symbols CASCADE;
DROP TABLE IF EXISTS etf_symbols CASCADE;
DROP TABLE IF EXISTS company_profile CASCADE;
DROP TABLE IF EXISTS annual_balance_sheet CASCADE;
DROP TABLE IF EXISTS key_metrics CASCADE;
DROP TABLE IF EXISTS last_updated CASCADE;
DROP TABLE IF EXISTS buy_sell_daily CASCADE;
DROP TABLE IF EXISTS buy_sell_weekly CASCADE;
DROP TABLE IF EXISTS buy_sell_monthly CASCADE;

-- Stock symbols table (exact match to loadstocksymbols.py)
CREATE TABLE stock_symbols (
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

-- ETF symbols table (exact match to loadstocksymbols.py)
CREATE TABLE etf_symbols (
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

-- Price daily table (exact match to loadpricedaily.py)
CREATE TABLE price_daily (
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

-- ETF price daily table (exact match to loadpricedaily.py)
CREATE TABLE etf_price_daily (
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


-- Last updated tracking table (from loaders)
CREATE TABLE last_updated (
    script_name   VARCHAR(255) PRIMARY KEY,
    last_run      TIMESTAMP WITH TIME ZONE
);

-- Company profile table (exact match to loadinfo.py structure)
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

-- Annual balance sheet (for financial data) - matches loadannualbalancesheet.py
CREATE TABLE annual_balance_sheet (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    fiscal_year INT NOT NULL,
    date DATE,
    total_assets DECIMAL(16,2),
    current_assets DECIMAL(16,2),
    total_liabilities DECIMAL(16,2),
    current_liabilities DECIMAL(16,2),
    stockholders_equity DECIMAL(16,2),
    cash_and_equivalents DECIMAL(16,2),
    accounts_receivable DECIMAL(16,2),
    inventory DECIMAL(16,2),
    accounts_payable DECIMAL(16,2),
    long_term_debt DECIMAL(16,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_year)
);

-- Quarterly balance sheet (for quarterly financial data)
CREATE TABLE quarterly_balance_sheet (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    fiscal_year INT NOT NULL,
    fiscal_quarter INT NOT NULL,
    date DATE,
    total_assets DECIMAL(16,2),
    current_assets DECIMAL(16,2),
    total_liabilities DECIMAL(16,2),
    current_liabilities DECIMAL(16,2),
    stockholders_equity DECIMAL(16,2),
    cash_and_equivalents DECIMAL(16,2),
    accounts_receivable DECIMAL(16,2),
    inventory DECIMAL(16,2),
    accounts_payable DECIMAL(16,2),
    long_term_debt DECIMAL(16,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_year, fiscal_quarter)
);

-- Annual income statement (for financial data) - matches loadannualincomestatement.py
CREATE TABLE annual_income_statement (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    fiscal_year INT NOT NULL,
    date DATE,
    revenue DECIMAL(16,2),
    cost_of_revenue DECIMAL(16,2),
    gross_profit DECIMAL(16,2),
    operating_expenses DECIMAL(16,2),
    operating_income DECIMAL(16,2),
    net_income DECIMAL(16,2),
    earnings_per_share DECIMAL(12,4),
    tax_expense DECIMAL(16,2),
    interest_expense DECIMAL(16,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_year)
);

-- Quarterly income statement (for quarterly financial data)
CREATE TABLE quarterly_income_statement (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    fiscal_year INT NOT NULL,
    fiscal_quarter INT NOT NULL,
    date DATE,
    revenue DECIMAL(16,2),
    cost_of_revenue DECIMAL(16,2),
    gross_profit DECIMAL(16,2),
    operating_expenses DECIMAL(16,2),
    operating_income DECIMAL(16,2),
    net_income DECIMAL(16,2),
    earnings_per_share DECIMAL(12,4),
    tax_expense DECIMAL(16,2),
    interest_expense DECIMAL(16,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_year, fiscal_quarter)
);

-- Annual cash flow (for cash flow data) - matches loadannualcashflow.py
CREATE TABLE annual_cash_flow (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    fiscal_year INT NOT NULL,
    date DATE,
    operating_cash_flow DECIMAL(16,2),
    investing_cash_flow DECIMAL(16,2),
    financing_cash_flow DECIMAL(16,2),
    capital_expenditures DECIMAL(16,2),
    free_cash_flow DECIMAL(16,2),
    dividends_paid DECIMAL(16,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_year)
);

-- Quarterly cash flow (for quarterly cash flow data) - matches loadquarterlycashflow.py
CREATE TABLE quarterly_cash_flow (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    fiscal_year INT NOT NULL,
    fiscal_quarter INT NOT NULL,
    date DATE,
    operating_cash_flow DECIMAL(16,2),
    investing_cash_flow DECIMAL(16,2),
    financing_cash_flow DECIMAL(16,2),
    capital_expenditures DECIMAL(16,2),
    free_cash_flow DECIMAL(16,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_year, fiscal_quarter)
);

-- Market data table (exact match to loadinfo.py)
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

-- Key metrics table (exact match to loadinfo.py)
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

-- Leadership team table (exact match to loadinfo.py)
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

-- Governance scores table (from loadinfo.py)
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

-- Analyst estimates table (from loadinfo.py)
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

-- Buy Sell tables (exact match to loadbuyselldaily.py, loadbuysellweekly.py, loadbuysellmonthly.py)
CREATE TABLE buy_sell_daily (
    id           SERIAL PRIMARY KEY,
    symbol       VARCHAR(20)    NOT NULL,
    timeframe    VARCHAR(10)    NOT NULL,
    date         DATE           NOT NULL,
    open         REAL,
    high         REAL,
    low          REAL,
    close        REAL,
    volume       BIGINT,
    signal       VARCHAR(10),
    buylevel     REAL,
    stoplevel    REAL,
    inposition   BOOLEAN,
    UNIQUE(symbol, timeframe, date)
);

CREATE TABLE buy_sell_weekly (
    id           SERIAL PRIMARY KEY,
    symbol       VARCHAR(20)    NOT NULL,
    timeframe    VARCHAR(10)    NOT NULL,
    date         DATE           NOT NULL,
    open         REAL,
    high         REAL,
    low          REAL,
    close        REAL,
    volume       BIGINT,
    signal       VARCHAR(10),
    buylevel     REAL,
    stoplevel    REAL,
    inposition   BOOLEAN,
    UNIQUE(symbol, timeframe, date)
);

CREATE TABLE buy_sell_monthly (
    id           SERIAL PRIMARY KEY,
    symbol       VARCHAR(20)    NOT NULL,
    timeframe    VARCHAR(10)    NOT NULL,
    date         DATE           NOT NULL,
    open         REAL,
    high         REAL,
    low          REAL,
    close        REAL,
    volume       BIGINT,
    signal       VARCHAR(10),
    buylevel     REAL,
    stoplevel    REAL,
    inposition   BOOLEAN,
    UNIQUE(symbol, timeframe, date)
);

-- Factor Metrics tables (from loadfactormetrics.py)
CREATE TABLE IF NOT EXISTS growth_metrics (
    symbol VARCHAR(50),
    date DATE,
    revenue_growth_pct NUMERIC,
    earnings_growth_pct NUMERIC,
    bookval_growth_pct NUMERIC,
    PRIMARY KEY (symbol, date)
);

CREATE TABLE IF NOT EXISTS momentum_metrics (
    symbol VARCHAR(50),
    date DATE,
    current_price NUMERIC,
    momentum_3m NUMERIC,
    momentum_6m NUMERIC,
    momentum_12m NUMERIC,
    price_vs_sma_50 NUMERIC,
    price_vs_sma_200 NUMERIC,
    price_vs_52w_high NUMERIC,
    PRIMARY KEY (symbol, date)
);

CREATE TABLE IF NOT EXISTS quality_metrics (
    symbol VARCHAR(50),
    date DATE,
    roe NUMERIC,
    roa NUMERIC,
    debt_to_equity NUMERIC,
    current_ratio NUMERIC,
    PRIMARY KEY (symbol, date)
);

-- Positioning Metrics table (from loaddailycompanydata.py)
CREATE TABLE IF NOT EXISTS positioning_metrics (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    date DATE,
    institutional_ownership_pct DECIMAL(8,6),
    institutional_holders_count INTEGER,
    insider_ownership_pct DECIMAL(8,6),
    short_ratio DECIMAL(8,2),
    short_interest_pct DECIMAL(8,6),
    short_percent_of_float DECIMAL(8,6),
    ad_rating DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(symbol, date)
);

-- Dashboard settings (for user preferences)
CREATE TABLE IF NOT EXISTS user_dashboard_settings (
    user_id VARCHAR(255) PRIMARY KEY,
    dashboard_config JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance (matching loaders)
CREATE INDEX IF NOT EXISTS idx_fundamental_metrics_symbol ON fundamental_metrics(symbol);
CREATE INDEX IF NOT EXISTS idx_fundamental_metrics_sector ON fundamental_metrics(sector);
CREATE INDEX IF NOT EXISTS idx_fundamental_metrics_industry ON fundamental_metrics(industry);
CREATE INDEX IF NOT EXISTS idx_fundamental_metrics_updated ON fundamental_metrics(updated_at);
CREATE INDEX IF NOT EXISTS idx_price_daily_symbol_date ON price_daily(symbol, date);
CREATE INDEX IF NOT EXISTS idx_etf_price_daily_symbol_date ON etf_price_daily(symbol, date);
CREATE INDEX IF NOT EXISTS idx_buy_sell_daily_symbol_date ON buy_sell_daily(symbol, date);
CREATE INDEX IF NOT EXISTS idx_buy_sell_weekly_symbol_date ON buy_sell_weekly(symbol, date);
CREATE INDEX IF NOT EXISTS idx_buy_sell_monthly_symbol_date ON buy_sell_monthly(symbol, date);
CREATE INDEX IF NOT EXISTS idx_growth_metrics_symbol_date ON growth_metrics(symbol, date);
CREATE INDEX IF NOT EXISTS idx_momentum_metrics_symbol_date ON momentum_metrics(symbol, date);
CREATE INDEX IF NOT EXISTS idx_quality_metrics_symbol_date ON quality_metrics(symbol, date);
CREATE INDEX IF NOT EXISTS idx_positioning_metrics_symbol_date ON positioning_metrics(symbol, date);
CREATE INDEX IF NOT EXISTS idx_annual_balance_sheet_symbol_fiscal_year ON annual_balance_sheet(symbol, fiscal_year);
CREATE INDEX IF NOT EXISTS idx_quarterly_balance_sheet_symbol_fiscal_year ON quarterly_balance_sheet(symbol, fiscal_year);
CREATE INDEX IF NOT EXISTS idx_annual_income_statement_symbol_fiscal_year ON annual_income_statement(symbol, fiscal_year);
CREATE INDEX IF NOT EXISTS idx_quarterly_income_statement_symbol_fiscal_year ON quarterly_income_statement(symbol, fiscal_year);
CREATE INDEX IF NOT EXISTS idx_annual_cash_flow_symbol_fiscal_year ON annual_cash_flow(symbol, fiscal_year);
CREATE INDEX IF NOT EXISTS idx_quarterly_cash_flow_symbol_fiscal_year ON quarterly_cash_flow(symbol, fiscal_year);