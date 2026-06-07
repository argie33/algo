-- ════════════════════════════════════════════════════════════════════════════
-- DROP TABLES TO FORCE RECREATION WITH CORRECTED SCHEMA
-- ════════════════════════════════════════════════════════════════════════════
-- Drop tables that were modified to fix column names/schemas
DROP TABLE IF EXISTS data_loader_status CASCADE;

-- ════════════════════════════════════════════════════════════════════════════
-- CORE TABLES - Required for all systems
-- ════════════════════════════════════════════════════════════════════════════

-- Stock symbols and identifiers
CREATE TABLE IF NOT EXISTS stock_symbols (
    symbol VARCHAR(20) PRIMARY KEY,
    exchange VARCHAR(50),
    security_name VARCHAR(255),
    market_category VARCHAR(50),
    is_sp500 BOOLEAN DEFAULT FALSE,
    etf VARCHAR(5),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_stock_symbols_etf ON stock_symbols(etf);
CREATE INDEX IF NOT EXISTS idx_stock_symbols_active ON stock_symbols(active);

-- Daily OHLCV price data
CREATE TABLE IF NOT EXISTS price_daily (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date TEXT NOT NULL,
    open DECIMAL(12, 4),
    high DECIMAL(12, 4),
    low DECIMAL(12, 4),
    close DECIMAL(12, 4),
    volume BIGINT,
    adj_close DECIMAL(12, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_price_daily_unique ON price_daily(symbol, date);

-- Weekly price data
CREATE TABLE IF NOT EXISTS price_weekly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(12, 4),
    high DECIMAL(12, 4),
    low DECIMAL(12, 4),
    close DECIMAL(12, 4),
    volume BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_price_weekly_unique ON price_weekly(symbol, date);

-- Monthly price data
CREATE TABLE IF NOT EXISTS price_monthly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(12, 4),
    high DECIMAL(12, 4),
    low DECIMAL(12, 4),
    close DECIMAL(12, 4),
    volume BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_price_monthly_unique ON price_monthly(symbol, date);

-- ════════════════════════════════════════════════════════════════════════════
-- EARNINGS & FINANCIAL DATA
-- ════════════════════════════════════════════════════════════════════════════

-- Historical and forward-looking earnings data
CREATE TABLE IF NOT EXISTS earnings_estimates (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    quarter DATE,
    fiscal_quarter INTEGER,
    fiscal_year INTEGER,
    earnings_date DATE,
    estimated BOOLEAN,
    eps_actual DECIMAL(12, 4),
    revenue_actual DECIMAL(20, 2),
    eps_estimate DECIMAL(12, 4),
    revenue_estimate DECIMAL(20, 2),
    eps_surprise_pct DECIMAL(8, 2),
    revenue_surprise_pct DECIMAL(8, 2),
    eps_difference DECIMAL(12, 4),
    revenue_difference DECIMAL(20, 2),
    beat_miss_flag VARCHAR(20),
    surprise_percent DECIMAL(8, 2),
    estimate_revision_days INTEGER,
    estimate_revision_count INTEGER,
    fetched_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, quarter)
);

-- Earnings history (actual reported earnings + estimates)
CREATE TABLE IF NOT EXISTS earnings_history (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    quarter DATE,
    fiscal_quarter INTEGER,
    fiscal_year INTEGER,
    earnings_date DATE,
    estimated BOOLEAN,
    eps_actual DECIMAL(12, 4),
    revenue_actual DECIMAL(20, 2),
    eps_estimate DECIMAL(12, 4),
    revenue_estimate DECIMAL(20, 2),
    eps_surprise_pct DECIMAL(8, 2),
    revenue_surprise_pct DECIMAL(8, 2),
    eps_difference DECIMAL(12, 4),
    revenue_difference DECIMAL(20, 2),
    beat_miss_flag VARCHAR(20),
    surprise_percent DECIMAL(8, 2),
    estimate_revision_days INTEGER,
    estimate_revision_count INTEGER,
    fetched_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, quarter)
);

-- Earnings surprise (actual vs estimate EPS)
CREATE TABLE IF NOT EXISTS earnings_surprise (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    earnings_date DATE NOT NULL,
    eps_estimate DECIMAL(12, 4),
    eps_actual DECIMAL(12, 4),
    surprise_percent DECIMAL(8, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, earnings_date)
);

-- Earnings calendar (upcoming earnings announcements)
CREATE TABLE IF NOT EXISTS earnings_calendar (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    earnings_date DATE NOT NULL,
    announce_time VARCHAR(50),
    eps_estimate DECIMAL(12, 4),
    actual_eps DECIMAL(12, 4),
    revenue_estimate DECIMAL(20, 2),
    actual_revenue DECIMAL(20, 2),
    fiscal_period VARCHAR(20),
    company_name VARCHAR(255),
    status VARCHAR(50),
    surprise_pct DECIMAL(8, 2),
    fiscal_quarter INTEGER,
    fiscal_year INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, earnings_date)
);

-- ════════════════════════════════════════════════════════════════════════════
-- ANALYST DATA
-- ════════════════════════════════════════════════════════════════════════════

-- Analyst rating changes
CREATE TABLE IF NOT EXISTS analyst_upgrade_downgrade (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    action_date DATE,
    firm VARCHAR(100),
    old_rating VARCHAR(50),
    new_rating VARCHAR(50),
    action VARCHAR(20),
    company_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Analyst sentiment analysis (aggregated analyst recommendations)
CREATE TABLE IF NOT EXISTS analyst_sentiment_analysis (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    analyst_count INTEGER,
    bullish_count INTEGER,
    bearish_count INTEGER,
    neutral_count INTEGER,
    target_price DECIMAL(12, 2),
    current_price DECIMAL(12, 2),
    upside_downside_percent DECIMAL(8, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- ════════════════════════════════════════════════════════════════════════════
-- TECHNICAL INDICATORS
-- ════════════════════════════════════════════════════════════════════════════

-- Daily technical indicators
CREATE TABLE IF NOT EXISTS technical_data_daily (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    rsi DECIMAL(8, 4),
    rsi_14 DECIMAL(8, 4),
    macd DECIMAL(12, 4),
    macd_signal DECIMAL(12, 4),
    macd_hist DECIMAL(12, 4),
    macd_histogram DECIMAL(12, 4),
    mom DECIMAL(12, 4),
    roc DECIMAL(8, 4),
    roc_10d DECIMAL(8, 4),
    roc_20d DECIMAL(8, 4),
    roc_60d DECIMAL(8, 4),
    roc_120d DECIMAL(8, 4),
    roc_252d DECIMAL(8, 4),
    sma_20 DECIMAL(12, 4),
    sma_50 DECIMAL(12, 4),
    sma_150 DECIMAL(12, 4),
    sma_200 DECIMAL(12, 4),
    ema_12 DECIMAL(12, 4),
    ema_26 DECIMAL(12, 4),
    atr DECIMAL(12, 4),
    atr_14 DECIMAL(12, 4),
    bb_upper DECIMAL(12, 4),
    bb_middle DECIMAL(12, 4),
    bb_lower DECIMAL(12, 4),
    volume_ma_50 BIGINT,
    adx DECIMAL(8, 4),
    plus_di DECIMAL(8, 4),
    minus_di DECIMAL(8, 4),
    mansfield_rs DECIMAL(8, 4),
    price_data_age_days INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_technical_data_daily_unique ON technical_data_daily(symbol, date);

-- Weekly technical indicators
CREATE TABLE IF NOT EXISTS technical_data_weekly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    rsi DECIMAL(8, 4),
    macd DECIMAL(12, 4),
    macd_signal DECIMAL(12, 4),
    macd_hist DECIMAL(12, 4),
    sma_20 DECIMAL(12, 4),
    sma_50 DECIMAL(12, 4),
    sma_200 DECIMAL(12, 4),
    ema_12 DECIMAL(12, 4),
    ema_26 DECIMAL(12, 4),
    atr DECIMAL(12, 4),
    adx DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_technical_data_weekly_unique ON technical_data_weekly(symbol, date);

-- Monthly technical indicators
CREATE TABLE IF NOT EXISTS technical_data_monthly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    rsi DECIMAL(8, 4),
    macd DECIMAL(12, 4),
    macd_signal DECIMAL(12, 4),
    macd_hist DECIMAL(12, 4),
    sma_20 DECIMAL(12, 4),
    sma_50 DECIMAL(12, 4),
    sma_200 DECIMAL(12, 4),
    ema_12 DECIMAL(12, 4),
    ema_26 DECIMAL(12, 4),
    atr DECIMAL(12, 4),
    adx DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_technical_data_monthly_unique ON technical_data_monthly(symbol, date);

-- ════════════════════════════════════════════════════════════════════════════
-- TRADING SIGNALS
-- ════════════════════════════════════════════════════════════════════════════

-- Daily buy/sell signals
CREATE TABLE IF NOT EXISTS buy_sell_daily (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    timeframe VARCHAR(10) NOT NULL DEFAULT 'Daily',
    signal VARCHAR(20),
    signal_triggered_date DATE,
    signal_type VARCHAR(20),
    signal_strength DECIMAL(8, 4),
    entry_price DECIMAL(12, 4),
    buylevel DECIMAL(12, 4),
    stoplevel DECIMAL(12, 4),
    sell_level DECIMAL(12, 4),
    inposition BOOLEAN DEFAULT FALSE,
    initial_stop DECIMAL(12, 4),
    trailing_stop DECIMAL(12, 4),
    exit_trigger_1_price DECIMAL(12, 4),
    exit_trigger_2_price DECIMAL(12, 4),
    exit_trigger_3_price DECIMAL(12, 4),
    exit_trigger_4_price DECIMAL(12, 4),
    pivot_price DECIMAL(12, 4),
    buy_zone_start DECIMAL(12, 4),
    buy_zone_end DECIMAL(12, 4),
    profit_target_8pct DECIMAL(12, 4),
    profit_target_20pct DECIMAL(12, 4),
    profit_target_25pct DECIMAL(12, 4),
    open DECIMAL(12, 4),
    high DECIMAL(12, 4),
    low DECIMAL(12, 4),
    close DECIMAL(12, 4),
    volume BIGINT,
    avg_volume_50d BIGINT,
    volume_surge_pct DECIMAL(8, 4),
    rsi DECIMAL(8, 4),
    adx DECIMAL(8, 4),
    atr DECIMAL(12, 4),
    sma_50 DECIMAL(12, 4),
    sma_200 DECIMAL(12, 4),
    ema_21 DECIMAL(12, 4),
    pct_from_ema21 DECIMAL(8, 4),
    pct_from_sma50 DECIMAL(8, 4),
    mansfield_rs DECIMAL(8, 4),
    sata_score DECIMAL(8, 4),
    rs_rating INTEGER,
    base_type VARCHAR(50),
    base_length_days INTEGER,
    breakout_quality VARCHAR(10),
    risk_reward_ratio DECIMAL(8, 4),
    risk_pct DECIMAL(8, 4),
    entry_quality_score DECIMAL(8, 4),
    signal_quality_score DECIMAL(8, 4),
    position_size_recommendation DECIMAL(8, 4),
    current_gain_pct DECIMAL(8, 4),
    days_in_position INTEGER,
    stage_number INTEGER,
    stage_confidence DECIMAL(8, 4),
    substage VARCHAR(50),
    market_stage VARCHAR(50),
    reason VARCHAR(255),
    strength DECIMAL(8, 4),
    technical_data_age_days INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_buy_sell_daily_unique ON buy_sell_daily(symbol, timeframe, date);

-- Weekly buy/sell signals
CREATE TABLE IF NOT EXISTS buy_sell_weekly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    timeframe VARCHAR(10) NOT NULL DEFAULT 'Weekly',
    signal VARCHAR(20),
    signal_triggered_date DATE,
    signal_type VARCHAR(20),
    signal_strength DECIMAL(8, 4),
    entry_price DECIMAL(12, 4),
    buylevel DECIMAL(12, 4),
    stoplevel DECIMAL(12, 4),
    sell_level DECIMAL(12, 4),
    inposition BOOLEAN DEFAULT FALSE,
    initial_stop DECIMAL(12, 4),
    trailing_stop DECIMAL(12, 4),
    exit_trigger_1_price DECIMAL(12, 4),
    exit_trigger_2_price DECIMAL(12, 4),
    exit_trigger_3_price DECIMAL(12, 4),
    exit_trigger_4_price DECIMAL(12, 4),
    pivot_price DECIMAL(12, 4),
    buy_zone_start DECIMAL(12, 4),
    buy_zone_end DECIMAL(12, 4),
    profit_target_8pct DECIMAL(12, 4),
    profit_target_20pct DECIMAL(12, 4),
    profit_target_25pct DECIMAL(12, 4),
    open DECIMAL(12, 4),
    high DECIMAL(12, 4),
    low DECIMAL(12, 4),
    close DECIMAL(12, 4),
    volume BIGINT,
    avg_volume_50d BIGINT,
    volume_surge_pct DECIMAL(8, 4),
    rsi DECIMAL(8, 4),
    adx DECIMAL(8, 4),
    atr DECIMAL(12, 4),
    sma_50 DECIMAL(12, 4),
    sma_200 DECIMAL(12, 4),
    ema_21 DECIMAL(12, 4),
    pct_from_ema21 DECIMAL(8, 4),
    pct_from_sma50 DECIMAL(8, 4),
    mansfield_rs DECIMAL(8, 4),
    sata_score DECIMAL(8, 4),
    rs_rating INTEGER,
    base_type VARCHAR(50),
    base_length_days INTEGER,
    breakout_quality VARCHAR(10),
    risk_reward_ratio DECIMAL(8, 4),
    risk_pct DECIMAL(8, 4),
    entry_quality_score DECIMAL(8, 4),
    signal_quality_score DECIMAL(8, 4),
    position_size_recommendation DECIMAL(8, 4),
    current_gain_pct DECIMAL(8, 4),
    days_in_position INTEGER,
    stage_number INTEGER,
    stage_confidence DECIMAL(8, 4),
    substage VARCHAR(50),
    market_stage VARCHAR(50),
    reason VARCHAR(255),
    strength DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_buy_sell_weekly_unique ON buy_sell_weekly(symbol, timeframe, date);

-- Monthly buy/sell signals
CREATE TABLE IF NOT EXISTS buy_sell_monthly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    timeframe VARCHAR(10) NOT NULL DEFAULT 'Monthly',
    signal VARCHAR(20),
    signal_triggered_date DATE,
    signal_type VARCHAR(20),
    signal_strength DECIMAL(8, 4),
    entry_price DECIMAL(12, 4),
    buylevel DECIMAL(12, 4),
    stoplevel DECIMAL(12, 4),
    sell_level DECIMAL(12, 4),
    inposition BOOLEAN DEFAULT FALSE,
    initial_stop DECIMAL(12, 4),
    trailing_stop DECIMAL(12, 4),
    exit_trigger_1_price DECIMAL(12, 4),
    exit_trigger_2_price DECIMAL(12, 4),
    exit_trigger_3_price DECIMAL(12, 4),
    exit_trigger_4_price DECIMAL(12, 4),
    pivot_price DECIMAL(12, 4),
    buy_zone_start DECIMAL(12, 4),
    buy_zone_end DECIMAL(12, 4),
    profit_target_8pct DECIMAL(12, 4),
    profit_target_20pct DECIMAL(12, 4),
    profit_target_25pct DECIMAL(12, 4),
    open DECIMAL(12, 4),
    high DECIMAL(12, 4),
    low DECIMAL(12, 4),
    close DECIMAL(12, 4),
    volume BIGINT,
    avg_volume_50d BIGINT,
    volume_surge_pct DECIMAL(8, 4),
    rsi DECIMAL(8, 4),
    adx DECIMAL(8, 4),
    atr DECIMAL(12, 4),
    sma_50 DECIMAL(12, 4),
    sma_200 DECIMAL(12, 4),
    ema_21 DECIMAL(12, 4),
    pct_from_ema21 DECIMAL(8, 4),
    pct_from_sma50 DECIMAL(8, 4),
    mansfield_rs DECIMAL(8, 4),
    sata_score DECIMAL(8, 4),
    rs_rating INTEGER,
    base_type VARCHAR(50),
    base_length_days INTEGER,
    breakout_quality VARCHAR(10),
    risk_reward_ratio DECIMAL(8, 4),
    risk_pct DECIMAL(8, 4),
    entry_quality_score DECIMAL(8, 4),
    signal_quality_score DECIMAL(8, 4),
    position_size_recommendation DECIMAL(8, 4),
    current_gain_pct DECIMAL(8, 4),
    days_in_position INTEGER,
    stage_number INTEGER,
    stage_confidence DECIMAL(8, 4),
    substage VARCHAR(50),
    market_stage VARCHAR(50),
    reason VARCHAR(255),
    strength DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_buy_sell_monthly_unique ON buy_sell_monthly(symbol, timeframe, date);

-- ════════════════════════════════════════════════════════════════════════════
-- QUALITY METRICS
-- ════════════════════════════════════════════════════════════════════════════

-- Profitability and efficiency metrics
CREATE TABLE IF NOT EXISTS quality_metrics (
    symbol VARCHAR(20) PRIMARY KEY,
    operating_margin DECIMAL(8, 4),
    net_margin DECIMAL(8, 4),
    roe DECIMAL(8, 4),
    roa DECIMAL(8, 4),
    debt_to_equity DECIMAL(8, 4),
    current_ratio DECIMAL(8, 4),
    quick_ratio DECIMAL(8, 4),
    interest_coverage DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Growth metrics
CREATE TABLE IF NOT EXISTS growth_metrics (
    symbol VARCHAR(20) PRIMARY KEY,
    revenue_growth_5y DECIMAL(8, 4),
    revenue_growth_3y DECIMAL(8, 4),
    revenue_growth_1y DECIMAL(8, 4),
    eps_growth_5y DECIMAL(8, 4),
    eps_growth_3y DECIMAL(8, 4),
    eps_growth_1y DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Stability metrics
CREATE TABLE IF NOT EXISTS stability_metrics (
    symbol VARCHAR(20) PRIMARY KEY,
    volatility_30d DECIMAL(8, 4),
    volatility_60d DECIMAL(8, 4),
    volatility_252d DECIMAL(8, 4),
    beta DECIMAL(8, 4),
    debt_to_assets DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Value metrics
CREATE TABLE IF NOT EXISTS value_metrics (
    symbol VARCHAR(20) PRIMARY KEY,
    date DATE,
    market_cap BIGINT,
    pe_ratio DECIMAL(8, 4),
    pb_ratio DECIMAL(8, 4),
    ps_ratio DECIMAL(8, 4),
    peg_ratio DECIMAL(8, 4),
    dividend_yield DECIMAL(8, 4),
    fcf_yield DECIMAL(8, 4),
    held_percent_insiders DECIMAL(8, 4),
    held_percent_institutions DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Positioning metrics
CREATE TABLE IF NOT EXISTS positioning_metrics (
    symbol VARCHAR(20) PRIMARY KEY,
    institutional_ownership DECIMAL(8, 4),
    insider_ownership DECIMAL(8, 4),
    short_interest_percent DECIMAL(8, 4),
    shares_short_prior_month BIGINT,
    short_interest_trend VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- COMPOSITE SCORES
-- ════════════════════════════════════════════════════════════════════════════

-- Overall stock quality score
CREATE TABLE IF NOT EXISTS stock_scores (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL UNIQUE,
    composite_score DECIMAL(8, 2),
    quality_score DECIMAL(8, 2),
    growth_score DECIMAL(8, 2),
    stability_score DECIMAL(8, 2),
    value_score DECIMAL(8, 2),
    momentum_score DECIMAL(8, 2),
    positioning_score DECIMAL(8, 2),
    rs_percentile DECIMAL(8, 2),
    data_completeness DECIMAL(4, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- USER MANAGEMENT & SYSTEM TABLES
-- ════════════════════════════════════════════════════════════════════════════

-- User accounts and authentication
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100) UNIQUE,
    password_hash VARCHAR(255),
    role VARCHAR(20) NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Migration for existing deployments:
-- ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user'));

-- User dashboard settings and preferences
-- user_id is the Cognito sub (UUID string), not an integer FK to users
CREATE TABLE IF NOT EXISTS user_dashboard_settings (
    user_id VARCHAR(255) PRIMARY KEY,
    theme VARCHAR(20) DEFAULT 'dark',
    notifications BOOLEAN DEFAULT TRUE,
    preferences JSONB DEFAULT '{}',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User alerts for stock price changes
CREATE TABLE IF NOT EXISTS user_alerts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    alert_type VARCHAR(50),
    threshold DECIMAL(12, 4),
    triggered_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User API keys for integrations
CREATE TABLE IF NOT EXISTS user_api_keys (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    broker VARCHAR(50),
    api_key VARCHAR(500),
    api_secret VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP
);

-- Manual trades entered by users
CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100),
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10),
    quantity DECIMAL(12, 2),
    execution_price DECIMAL(12, 4),
    trade_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Manual portfolio positions
CREATE TABLE IF NOT EXISTS manual_positions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100),
    symbol VARCHAR(20) NOT NULL,
    quantity DECIMAL(12, 2),
    average_cost DECIMAL(12, 4),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Community feature signups
CREATE TABLE IF NOT EXISTS community_signups (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Contact form submissions
CREATE TABLE IF NOT EXISTS contact_submissions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255),
    email VARCHAR(255),
    subject VARCHAR(255),
    message TEXT,
    phone VARCHAR(20),
    status VARCHAR(20) DEFAULT 'new',
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Data loader run tracking for provenance
CREATE TABLE IF NOT EXISTS data_loader_runs (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(100),
    loader_name VARCHAR(255) NOT NULL,
    table_name VARCHAR(255),
    source_api VARCHAR(255),
    parameters JSONB,
    run_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    start_at TIMESTAMP,
    status VARCHAR(20) NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    records_loaded INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    error_message TEXT,
    duration_seconds DECIMAL(10, 2),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(loader_name, run_date)
);

-- ════════════════════════════════════════════════════════════════════════════
-- COMPANY & FUNDAMENTAL DATA
-- ════════════════════════════════════════════════════════════════════════════

-- Company profile and basic information
CREATE TABLE IF NOT EXISTS company_profile (
    ticker VARCHAR(20) PRIMARY KEY,
    symbol VARCHAR(20),
    short_name VARCHAR(255),
    long_name VARCHAR(255),
    display_name VARCHAR(255),
    sector VARCHAR(100),
    industry VARCHAR(100),
    exchange VARCHAR(50),
    website VARCHAR(255),
    employees BIGINT,
    currency_code VARCHAR(10),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Key financial metrics per company
CREATE TABLE IF NOT EXISTS key_metrics (
    ticker VARCHAR(20) PRIMARY KEY,
    symbol VARCHAR(20),
    market_cap BIGINT,
    held_percent_insiders DECIMAL(8, 4),
    held_percent_institutions DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insider transaction data
CREATE TABLE IF NOT EXISTS insider_transactions (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    insider_name VARCHAR(255),
    title VARCHAR(255),
    trade_type VARCHAR(20),
    shares BIGINT,
    trade_price DECIMAL(12, 4),
    trade_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Institutional ownership positioning
CREATE TABLE IF NOT EXISTS institutional_positioning (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE,
    shares_held BIGINT,
    percent_held DECIMAL(8, 4),
    change_from_prior BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- COMMODITY & MARKET DATA
-- ════════════════════════════════════════════════════════════════════════════

-- Commodity prices and data
CREATE TABLE IF NOT EXISTS commodity_prices (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    name VARCHAR(255),
    price DECIMAL(12, 4),
    date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Commodity price history
CREATE TABLE IF NOT EXISTS commodity_price_history (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE,
    open DECIMAL(12, 4),
    high DECIMAL(12, 4),
    low DECIMAL(12, 4),
    close DECIMAL(12, 4),
    volume BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Commodity categories and relationships
CREATE TABLE IF NOT EXISTS commodity_categories (
    id SERIAL PRIMARY KEY,
    category VARCHAR(100),
    symbols TEXT
);

-- COT (Commitments of Traders) data
CREATE TABLE IF NOT EXISTS cot_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE,
    commercial_long BIGINT,
    commercial_short BIGINT,
    non_commercial_long BIGINT,
    non_commercial_short BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Market distribution days
CREATE TABLE IF NOT EXISTS distribution_days (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE,
    distribution_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- General market data
CREATE TABLE IF NOT EXISTS market_data (
    id SERIAL PRIMARY KEY,
    metric_name VARCHAR(100),
    value DECIMAL(12, 4),
    date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- SENTIMENT & PSYCHOLOGICAL DATA
-- ════════════════════════════════════════════════════════════════════════════

-- AAII investor sentiment survey
CREATE TABLE IF NOT EXISTS aaii_sentiment (
    id SERIAL PRIMARY KEY,
    date DATE UNIQUE,
    bullish DECIMAL(8, 4),
    neutral DECIMAL(8, 4),
    bearish DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- NAAIM market strategists index
CREATE TABLE IF NOT EXISTS naaim (
    id SERIAL PRIMARY KEY,
    date DATE UNIQUE,
    naaim_number_mean DECIMAL(8, 4),
    bullish DECIMAL(8, 4),
    bearish DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Fear and Greed Index
CREATE TABLE IF NOT EXISTS fear_greed_index (
    id SERIAL PRIMARY KEY,
    date DATE UNIQUE,
    fear_greed_value DECIMAL(8, 4),
    fear_greed_label VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Market sentiment aggregates (puts/calls, VIX, broader sentiment scores)
CREATE TABLE IF NOT EXISTS market_sentiment (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    fear_greed_index DECIMAL(8, 4),
    put_call_ratio DECIMAL(8, 4),
    vix DECIMAL(8, 4),
    sentiment_score DECIMAL(8, 4),
    bullish_pct DECIMAL(8, 2),
    bearish_pct DECIMAL(8, 2),
    neutral_pct DECIMAL(8, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Social sentiment aggregates (Twitter, Reddit, StockTwits, etc.)
CREATE TABLE IF NOT EXISTS sentiment_social (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    twitter_sentiment_score DECIMAL(8, 4),
    twitter_mention_count INTEGER,
    reddit_sentiment_score DECIMAL(8, 4),
    reddit_mention_count INTEGER,
    stocktwits_sentiment_score DECIMAL(8, 4),
    stocktwits_mention_count INTEGER,
    overall_sentiment_score DECIMAL(8, 4),
    sentiment_trend VARCHAR(20),
    source_count INTEGER,
    sentiment_breakdown JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- NOTE: analyst_sentiment_analysis already defined above with full column set
-- (target_price, current_price, upside_downside_percent, total_analysts)
-- This duplicate definition removed to avoid confusion.

-- ════════════════════════════════════════════════════════════════════════════
-- OPTIONS DATA
-- ════════════════════════════════════════════════════════════════════════════

-- Options chains for stocks
CREATE TABLE IF NOT EXISTS options_chains (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    contract_symbol VARCHAR(50),
    option_type VARCHAR(10),
    expiration_date DATE,
    strike_price DECIMAL(12, 4),
    bid DECIMAL(12, 4),
    ask DECIMAL(12, 4),
    last_price DECIMAL(12, 4),
    volume BIGINT,
    open_interest BIGINT,
    data_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Options Greeks (Delta, Gamma, Theta, Vega, Rho)
CREATE TABLE IF NOT EXISTS options_greeks (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    contract_symbol VARCHAR(50),
    delta DECIMAL(8, 4),
    gamma DECIMAL(8, 4),
    theta DECIMAL(8, 4),
    vega DECIMAL(8, 4),
    rho DECIMAL(8, 4),
    data_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Implied volatility history
CREATE TABLE IF NOT EXISTS iv_history (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE,
    iv_30d DECIMAL(8, 4),
    iv_60d DECIMAL(8, 4),
    iv_180d DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- PORTFOLIO & HOLDINGS DATA
-- ════════════════════════════════════════════════════════════════════════════

-- Portfolio holdings for users
CREATE TABLE IF NOT EXISTS portfolio_holdings (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    quantity DECIMAL(12, 4),
    average_cost DECIMAL(12, 4),
    current_price DECIMAL(12, 4),
    market_value DECIMAL(15, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, symbol)
);

-- Portfolio performance metrics
CREATE TABLE IF NOT EXISTS portfolio_performance (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    date DATE,
    total_value DECIMAL(20, 2),
    total_gain_loss DECIMAL(20, 2),
    total_return_pct DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- ECONOMIC & MARKET INDEX DATA
-- ════════════════════════════════════════════════════════════════════════════

-- Economic calendar events (FRED release dates and upcoming data)
CREATE TABLE IF NOT EXISTS economic_calendar (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(100),
    event_date DATE NOT NULL,
    event_time TIME,
    event_name VARCHAR(255),
    category VARCHAR(100),
    country VARCHAR(50) DEFAULT 'US',
    importance VARCHAR(20),
    forecast_value DECIMAL(12, 4),
    actual_value DECIMAL(12, 4),
    previous_value DECIMAL(12, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_id, event_date)
);

-- Economic data time series
CREATE TABLE IF NOT EXISTS economic_data (
    id SERIAL PRIMARY KEY,
    series_id VARCHAR(50) NOT NULL,
    date DATE NOT NULL,
    value DECIMAL(12, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- Explicit unique index for ON CONFLICT support in loader
CREATE UNIQUE INDEX IF NOT EXISTS idx_economic_data_unique ON economic_data(series_id, date);
CREATE INDEX IF NOT EXISTS idx_economic_data_series_date ON economic_data(series_id, date DESC);

-- Index metrics (market breadth, etc.)
CREATE TABLE IF NOT EXISTS index_metrics (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE,
    closing_price DECIMAL(12, 4),
    momentum DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- SECTOR & INDUSTRY ANALYSIS
-- ════════════════════════════════════════════════════════════════════════════

-- Sector performance rankings
CREATE TABLE IF NOT EXISTS sector_ranking (
    id SERIAL PRIMARY KEY,
    sector_name VARCHAR(100),
    date DATE NOT NULL,
    current_rank INTEGER,
    momentum_score DECIMAL(8, 4),
    rank_1w_ago INTEGER,
    rank_4w_ago INTEGER,
    rank_12w_ago INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(sector_name, date)
);

-- Sector performance data
CREATE TABLE IF NOT EXISTS sector_performance (
    id SERIAL PRIMARY KEY,
    sector VARCHAR(100),
    date DATE,
    return_pct DECIMAL(8, 4),
    relative_strength DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(sector, date)
);

-- Industry rankings
CREATE TABLE IF NOT EXISTS industry_ranking (
    id SERIAL PRIMARY KEY,
    industry VARCHAR(100),
    date_recorded DATE,
    current_rank INTEGER,
    rank_1w_ago INTEGER,
    rank_4w_ago INTEGER,
    rank_12w_ago INTEGER,
    momentum_score DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Industry performance data
CREATE TABLE IF NOT EXISTS industry_performance (
    id SERIAL PRIMARY KEY,
    industry VARCHAR(100),
    date DATE,
    return_pct DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- SEASONALITY DATA
-- ════════════════════════════════════════════════════════════════════════════

-- Day of week seasonality — SPY-based market aggregate (no per-symbol rows)
CREATE TABLE IF NOT EXISTS seasonality_day_of_week (
    id SERIAL PRIMARY KEY,
    day VARCHAR(20),
    day_num INTEGER,
    avg_return DECIMAL(8, 4),
    win_rate DECIMAL(8, 4),
    days_counted INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='seasonality_day_of_week' AND column_name='day') THEN
        ALTER TABLE seasonality_day_of_week
            ADD COLUMN day VARCHAR(20),
            ADD COLUMN day_num INTEGER,
            ADD COLUMN avg_return DECIMAL(8,4),
            ADD COLUMN win_rate DECIMAL(8,4),
            ADD COLUMN days_counted INTEGER;
    END IF;
END $$;

-- Monthly seasonality patterns — SPY-based market aggregate (no per-symbol rows)
CREATE TABLE IF NOT EXISTS seasonality_monthly_stats (
    id SERIAL PRIMARY KEY,
    month INTEGER,
    month_name VARCHAR(20),
    avg_return DECIMAL(8, 4),
    best_return DECIMAL(8, 4),
    worst_return DECIMAL(8, 4),
    years_counted INTEGER,
    winning_years INTEGER,
    losing_years INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='seasonality_monthly_stats' AND column_name='month_name') THEN
        ALTER TABLE seasonality_monthly_stats
            ADD COLUMN month_name VARCHAR(20),
            ADD COLUMN avg_return DECIMAL(8,4),
            ADD COLUMN best_return DECIMAL(8,4),
            ADD COLUMN worst_return DECIMAL(8,4),
            ADD COLUMN years_counted INTEGER,
            ADD COLUMN winning_years INTEGER,
            ADD COLUMN losing_years INTEGER;
    END IF;
END $$;

-- ════════════════════════════════════════════════════════════════════════════
-- STRATEGY & ANALYSIS DATA
-- ════════════════════════════════════════════════════════════════════════════

-- Covered call opportunities
CREATE TABLE IF NOT EXISTS covered_call_opportunities (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    strike_price DECIMAL(12, 4),
    expiration_date DATE,
    annual_return_pct DECIMAL(8, 4),
    probability_profit DECIMAL(8, 4),
    data_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- EARNINGS & FINANCIAL FORECASTS
-- ════════════════════════════════════════════════════════════════════════════

-- Earnings estimate trends
CREATE TABLE IF NOT EXISTS earnings_estimate_trends (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    quarter DATE,
    fiscal_year INTEGER,
    period VARCHAR(20),
    current_estimate DECIMAL(12, 4),
    prior_estimate DECIMAL(12, 4),
    change_estimate DECIMAL(12, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Earnings estimate revisions
CREATE TABLE IF NOT EXISTS earnings_estimate_revisions (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    quarter DATE,
    fiscal_year INTEGER,
    revision_date DATE,
    estimate_before DECIMAL(12, 4),
    estimate_after DECIMAL(12, 4),
    revision_type VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- ALTERNATIVE METRICS
-- ════════════════════════════════════════════════════════════════════════════

-- Momentum metrics for stocks
CREATE TABLE IF NOT EXISTS momentum_metrics (
    symbol VARCHAR(20) PRIMARY KEY,
    momentum_1m DECIMAL(8, 4),
    momentum_3m DECIMAL(8, 4),
    momentum_6m DECIMAL(8, 4),
    momentum_12m DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Beta and volatility validation
CREATE TABLE IF NOT EXISTS beta_validation (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) UNIQUE,
    beta_yfinance DECIMAL(8, 4),
    beta_calculated DECIMAL(8, 4),
    validation_status VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- FINANCIAL STATEMENTS
-- ════════════════════════════════════════════════════════════════════════════

-- Annual income statements
CREATE TABLE IF NOT EXISTS annual_income_statement (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    fiscal_year INTEGER,
    revenue DECIMAL(20, 2),
    cost_of_revenue DECIMAL(20, 2),
    gross_profit DECIMAL(20, 2),
    operating_income DECIMAL(20, 2),
    net_income DECIMAL(20, 2),
    earnings_per_share DECIMAL(12, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_year)
);

-- Annual balance sheets
CREATE TABLE IF NOT EXISTS annual_balance_sheet (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    fiscal_year INTEGER,
    total_assets DECIMAL(20, 2),
    current_assets DECIMAL(20, 2),
    total_liabilities DECIMAL(20, 2),
    current_liabilities DECIMAL(20, 2),
    stockholders_equity DECIMAL(20, 2),
    inventory DECIMAL(20, 2),
    cash_and_equivalents DECIMAL(20, 2),
    accounts_receivable DECIMAL(20, 2),
    ppe_net DECIMAL(20, 2),
    goodwill DECIMAL(20, 2),
    long_term_debt DECIMAL(20, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_year)
);

-- Annual cash flows
CREATE TABLE IF NOT EXISTS annual_cash_flow (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    fiscal_year INTEGER,
    operating_cash_flow DECIMAL(20, 2),
    investing_cash_flow DECIMAL(20, 2),
    financing_cash_flow DECIMAL(20, 2),
    free_cash_flow DECIMAL(20, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_year)
);

-- Quarterly income statements
CREATE TABLE IF NOT EXISTS quarterly_income_statement (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    fiscal_year INTEGER,
    fiscal_quarter INTEGER,
    revenue DECIMAL(20, 2),
    net_income DECIMAL(20, 2),
    earnings_per_share DECIMAL(12, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_year, fiscal_quarter)
);

-- Quarterly balance sheets
CREATE TABLE IF NOT EXISTS quarterly_balance_sheet (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    fiscal_year INTEGER,
    fiscal_quarter INTEGER,
    total_assets DECIMAL(20, 2),
    current_assets DECIMAL(20, 2),
    total_liabilities DECIMAL(20, 2),
    current_liabilities DECIMAL(20, 2),
    stockholders_equity DECIMAL(20, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_year, fiscal_quarter)
);

-- Quarterly cash flows
CREATE TABLE IF NOT EXISTS quarterly_cash_flow (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    fiscal_year INTEGER,
    fiscal_quarter INTEGER,
    operating_cash_flow DECIMAL(20, 2),
    investing_cash_flow DECIMAL(20, 2),
    financing_cash_flow DECIMAL(20, 2),
    free_cash_flow DECIMAL(20, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_year, fiscal_quarter)
);

-- TTM (Trailing Twelve Months) income statement
CREATE TABLE IF NOT EXISTS ttm_income_statement (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    date DATE,
    item_name VARCHAR(255),
    value DECIMAL(20, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- TTM cash flow statement
CREATE TABLE IF NOT EXISTS ttm_cash_flow (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    date DATE,
    item_name VARCHAR(255),
    value DECIMAL(20, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- ════════════════════════════════════════════════════════════════════════════
-- ETF DATA
-- ════════════════════════════════════════════════════════════════════════════

-- ETF price data - Daily
CREATE TABLE IF NOT EXISTS etf_price_daily (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(12, 4),
    high DECIMAL(12, 4),
    low DECIMAL(12, 4),
    close DECIMAL(12, 4),
    volume BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- ETF price data - Weekly
CREATE TABLE IF NOT EXISTS etf_price_weekly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(12, 4),
    high DECIMAL(12, 4),
    low DECIMAL(12, 4),
    close DECIMAL(12, 4),
    volume BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- ETF price data - Monthly
CREATE TABLE IF NOT EXISTS etf_price_monthly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(12, 4),
    high DECIMAL(12, 4),
    low DECIMAL(12, 4),
    close DECIMAL(12, 4),
    volume BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- ETF buy/sell signals - Daily
CREATE TABLE IF NOT EXISTS buy_sell_daily_etf (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    signal VARCHAR(20),
    strength DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- ETF buy/sell signals - Weekly
CREATE TABLE IF NOT EXISTS buy_sell_weekly_etf (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    signal VARCHAR(20),
    strength DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- ETF buy/sell signals - Monthly
CREATE TABLE IF NOT EXISTS buy_sell_monthly_etf (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    signal VARCHAR(20),
    strength DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- ════════════════════════════════════════════════════════════════════════════
-- CALENDAR & NEWS
-- ════════════════════════════════════════════════════════════════════════════

-- Calendar events (earnings, dividends, etc)
CREATE TABLE IF NOT EXISTS calendar_events (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    event_type VARCHAR(50),
    event_date DATE,
    event_description VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- SWING TRADING ALGO SYSTEM
-- ════════════════════════════════════════════════════════════════════════════

-- Algo configuration (hot-reload enabled, no restart needed)
CREATE TABLE IF NOT EXISTS algo_config (
    id SERIAL PRIMARY KEY,
    key VARCHAR(100) NOT NULL UNIQUE,
    value TEXT,
    value_type VARCHAR(20),
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(100)
);

-- Market health daily (market breadth, distribution days, trend)
CREATE TABLE IF NOT EXISTS market_health_daily (
    id SERIAL PRIMARY KEY,
    date TEXT NOT NULL UNIQUE,
    spy_close DECIMAL(12, 4),
    market_trend VARCHAR(20),
    market_stage INTEGER,
    distribution_days_4w INTEGER,
    distribution_days_20d INTEGER,
    up_volume_percent DECIMAL(8, 2),
    advance_decline_ratio DECIMAL(10, 2),
    new_highs_count INTEGER,
    new_lows_count INTEGER,
    breadth_momentum_10d DECIMAL(8, 4),
    vix_level DECIMAL(8, 2),
    put_call_ratio DECIMAL(8, 4),
    yield_curve_slope DECIMAL(8, 4),
    fed_rate_environment VARCHAR(50),
    market_comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Trend template fields per symbol (52w highs/lows, MA slopes, stages)
CREATE TABLE IF NOT EXISTS trend_template_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    price_52w_high DECIMAL(12, 4),
    price_52w_low DECIMAL(12, 4),
    percent_from_52w_low DECIMAL(8, 2),
    percent_from_52w_high DECIMAL(8, 2),
    sma_50_slope DECIMAL(8, 4),
    sma_200_slope DECIMAL(8, 4),
    price_above_sma50 BOOLEAN,
    price_above_sma200 BOOLEAN,
    sma50_above_sma200 BOOLEAN,
    ma_spread_percent DECIMAL(8, 4),
    minervini_trend_score INTEGER,
    weinstein_stage INTEGER,
    trend_direction VARCHAR(20),
    consolidation_flag BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- CAN SLIM fundamentals per symbol
CREATE TABLE IF NOT EXISTS can_slim_metrics (
    symbol VARCHAR(20) PRIMARY KEY,
    eps_growth_current DECIMAL(8, 4),
    eps_growth_5y DECIMAL(8, 4),
    sales_growth_current DECIMAL(8, 4),
    profit_margin DECIMAL(8, 4),
    roe DECIMAL(8, 4),
    institutional_ownership_pct DECIMAL(8, 2),
    shares_float_millions INTEGER,
    new_product_catalyst TEXT,
    relative_price_strength DECIMAL(8, 4),
    can_slim_score INTEGER,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- VCP detection (Volatility Contraction Pattern)
CREATE TABLE IF NOT EXISTS vcp_patterns (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    atr_30d_avg DECIMAL(12, 4),
    atr_current DECIMAL(12, 4),
    atr_compression_pct DECIMAL(8, 2),
    range_30d_avg DECIMAL(12, 4),
    range_current DECIMAL(12, 4),
    vcp_strength INTEGER,
    breakout_volume_ratio DECIMAL(8, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Signal Quality Score composite ranking
CREATE TABLE IF NOT EXISTS signal_quality_scores (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    trend_template_score INTEGER,
    base_quality_score INTEGER,
    volume_confirmation_score INTEGER,
    distance_from_high_score INTEGER,
    institutional_ownership_score INTEGER,
    market_stage_score INTEGER,
    vcp_pattern_score INTEGER,
    distribution_days_score INTEGER,
    earnings_proximity_score INTEGER,
    composite_sqs INTEGER,
    rank_vs_all_signals INTEGER,
    buy_sell_daily_age_days INTEGER,
    technical_data_age_days INTEGER,
    trend_template_age_days INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);
CREATE INDEX IF NOT EXISTS idx_signal_quality_scores_symbol_date ON signal_quality_scores(symbol, date);

-- Data completeness score per symbol
CREATE TABLE IF NOT EXISTS data_completeness_scores (
    symbol VARCHAR(20) PRIMARY KEY,
    price_data_pct DECIMAL(8, 2),
    technical_data_pct DECIMAL(8, 2),
    earnings_data_pct DECIMAL(8, 2),
    analyst_coverage_pct DECIMAL(8, 2),
    institutional_data_pct DECIMAL(8, 2),
    composite_completeness_pct DECIMAL(8, 2),
    is_tradeable BOOLEAN,
    completeness_comment TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Theme and correlation tags
CREATE TABLE IF NOT EXISTS signal_themes (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    sector_theme VARCHAR(100),
    thematic_group VARCHAR(100),
    correlation_cluster VARCHAR(100),
    correlation_to_spy DECIMAL(8, 4),
    correlation_to_qqq DECIMAL(8, 4),
    correlation_to_iwm DECIMAL(8, 4),
    relative_strength_group VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Signals evaluated through filter pipeline
CREATE TABLE IF NOT EXISTS algo_signals_evaluated (
    id SERIAL PRIMARY KEY,
    signal_date DATE NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    source_table VARCHAR(50),
    source_timeframe VARCHAR(20),
    raw_signal VARCHAR(20),
    entry_price DECIMAL(12, 4),
    filter_tier_1_pass BOOLEAN,
    filter_tier_2_pass BOOLEAN,
    filter_tier_3_pass BOOLEAN,
    filter_tier_4_pass BOOLEAN,
    filter_tier_5_pass BOOLEAN,
    final_signal_quality_score INTEGER,
    final_risk_score DECIMAL(8, 2),
    evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    evaluation_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(signal_date, symbol, source_timeframe)
);

-- Trades executed by algo
CREATE TABLE IF NOT EXISTS algo_trades (
    id SERIAL PRIMARY KEY,
    trade_id VARCHAR(100) UNIQUE NOT NULL,
    idempotency_key VARCHAR(64),
    symbol VARCHAR(20) NOT NULL,
    signal_date DATE NOT NULL,
    trade_date DATE NOT NULL,
    entry_price DECIMAL(12, 4) NOT NULL,
    entry_time TIMESTAMP,
    entry_quantity INTEGER NOT NULL,
    entry_reason TEXT,
    position_size_pct DECIMAL(8, 2),
    stop_loss_price DECIMAL(12, 4),
    stop_loss_method VARCHAR(50),
    target_1_price DECIMAL(12, 4),
    target_1_r_multiple DECIMAL(8, 2),
    target_2_price DECIMAL(12, 4),
    target_2_r_multiple DECIMAL(8, 2),
    target_3_price DECIMAL(12, 4),
    target_3_r_multiple DECIMAL(8, 2),
    status VARCHAR(20),
    exit_date DATE,
    exit_time TIMESTAMP,
    exit_price DECIMAL(12, 4),
    exit_reason VARCHAR(100),
    exit_r_multiple DECIMAL(8, 2),
    profit_loss_dollars DECIMAL(12, 2),
    profit_loss_pct DECIMAL(8, 4),
    trade_duration_days INTEGER,
    execution_mode VARCHAR(20),
    alpaca_order_id VARCHAR(100),
    alpaca_trade_id VARCHAR(100),
    signal_quality_score INTEGER,
    trend_template_score DECIMAL(8, 4),
    swing_score DECIMAL(8, 4),
    swing_grade VARCHAR(20),
    base_type VARCHAR(50),
    base_quality VARCHAR(50),
    stage_phase INTEGER,
    sector VARCHAR(50),
    industry VARCHAR(100),
    rs_percentile DECIMAL(8, 4),
    market_exposure_at_entry DECIMAL(8, 4),
    exposure_tier_at_entry VARCHAR(30),
    stop_method VARCHAR(50),
    stop_reasoning TEXT,
    swing_components JSONB,
    advanced_components JSONB,
    bracket_order BOOLEAN DEFAULT FALSE,
    reentry_count INTEGER DEFAULT 0,
    prior_trade_id VARCHAR(100),
    partial_exits_log TEXT,
    partial_exit_count INTEGER DEFAULT 0,
    last_partial_exit_date DATE,
    mfe_pct DECIMAL(8, 4),
    mae_pct DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, signal_date, entry_price)
);

-- Active positions tracking
CREATE TABLE IF NOT EXISTS algo_positions (
    id SERIAL PRIMARY KEY,
    position_id VARCHAR(100) UNIQUE NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    quantity INTEGER NOT NULL,
    avg_entry_price DECIMAL(12, 4),
    current_price DECIMAL(12, 4),
    position_value DECIMAL(14, 2),
    unrealized_pnl DECIMAL(12, 2),
    unrealized_pnl_pct DECIMAL(8, 4),
    trade_ids VARCHAR(1000),
    trade_ids_arr TEXT[],
    status VARCHAR(20),
    stage_in_exit_plan VARCHAR(50),
    distribution_day_count INTEGER,
    profit_loss_dollars DECIMAL(12, 2),
    trade_duration_days INTEGER,
    days_since_entry INTEGER,
    target_levels_hit INTEGER DEFAULT 0,
    current_stop_price DECIMAL(12, 4),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add target level hit timestamp columns (Issue #17: idempotency for partial exits)
ALTER TABLE algo_positions
ADD COLUMN IF NOT EXISTS target_1_hit_time TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS target_2_hit_time TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS target_3_hit_time TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS cognito_sub VARCHAR(255);

-- Daily portfolio snapshots
CREATE TABLE IF NOT EXISTS algo_portfolio_snapshots (
    id SERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL UNIQUE,
    total_portfolio_value DECIMAL(14, 2),
    total_cash DECIMAL(14, 2),
    total_equity DECIMAL(14, 2),
    position_count INTEGER,
    largest_position_pct DECIMAL(8, 2),
    average_position_size_pct DECIMAL(8, 2),
    concentration_risk_pct DECIMAL(8, 2),
    realized_pnl_today DECIMAL(12, 2),
    unrealized_pnl_total DECIMAL(12, 2),
    unrealized_pnl_pct DECIMAL(8, 4),
    win_count_today INTEGER,
    loss_count_today INTEGER,
    daily_return_pct DECIMAL(8, 4),
    cumulative_return_pct DECIMAL(8, 4),
    max_drawdown_pct DECIMAL(8, 4),
    sharpe_ratio DECIMAL(8, 4),
    distribution_days_market INTEGER,
    market_health_status VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Audit log for all algo actions (compliance + debugging)
CREATE TABLE IF NOT EXISTS algo_audit_log (
    id SERIAL PRIMARY KEY,
    action_type VARCHAR(50) NOT NULL,
    symbol VARCHAR(20),
    action_date TIMESTAMP NOT NULL,
    details JSONB,
    actor VARCHAR(100),
    status VARCHAR(20),
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Daily algo performance metrics (computed from audit_log)
CREATE TABLE IF NOT EXISTS algo_metrics_daily (
    date DATE PRIMARY KEY,
    total_actions INTEGER,
    entries INTEGER,
    exits INTEGER,
    avg_signal_score DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Pyramid add tracking (for position scaling)
CREATE TABLE IF NOT EXISTS algo_trade_adds (
    id SERIAL PRIMARY KEY,
    trade_id VARCHAR(20) NOT NULL,
    add_number INTEGER NOT NULL,
    add_date DATE NOT NULL,
    add_price DECIMAL(15, 4) NOT NULL,
    add_quantity INTEGER NOT NULL,
    fraction_of_original DECIMAL(5, 4),
    r_multiple_at_add DECIMAL(5, 2),
    trigger_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(trade_id, add_number)
);

-- Data loader status monitoring
CREATE TABLE IF NOT EXISTS data_loader_status (
    table_name VARCHAR(80) PRIMARY KEY,
    frequency VARCHAR(20),
    role VARCHAR(80),
    latest_date DATE,
    age_days INTEGER,
    row_count BIGINT,
    stale_threshold_days INTEGER,
    status VARCHAR(20),
    last_updated TIMESTAMP,
    error_message TEXT,
    completion_pct DECIMAL(5, 2) DEFAULT 100.0,  -- ISSUE #2: Track symbol completion percentage
    symbol_count INTEGER,                        -- ISSUE #2: Expected number of symbols
    symbols_loaded INTEGER,                      -- ISSUE #2: Actual symbols successfully loaded
    execution_started TIMESTAMP,                 -- ISSUE #2: When loader started execution
    execution_completed TIMESTAMP                -- ISSUE #2: When loader finished execution (null if still running/crashed)
);

-- Data patrol audit log
CREATE TABLE IF NOT EXISTS data_patrol_log (
    id SERIAL PRIMARY KEY,
    patrol_run_id VARCHAR(100),
    check_name VARCHAR(100) NOT NULL,
    severity VARCHAR(20),
    target_table VARCHAR(80),
    message TEXT,
    details JSONB,
    status VARCHAR(20),
    patrol_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Data remediation log
CREATE TABLE IF NOT EXISTS data_remediation_log (
    id SERIAL PRIMARY KEY,
    remediation_date DATE NOT NULL,
    table_name VARCHAR(80) NOT NULL,
    fix_type VARCHAR(50),
    rows_affected INTEGER,
    status VARCHAR(20),
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Loader failure trend tracking (for chronic failure detection)
CREATE TABLE IF NOT EXISTS loader_failure_trend (
    id SERIAL PRIMARY KEY,
    loader_name VARCHAR(100) NOT NULL,
    tracking_date DATE NOT NULL,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    failure_rate_7day NUMERIC(5, 2),
    failure_rate_30day NUMERIC(5, 2),
    last_error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(loader_name, tracking_date)
);

CREATE INDEX IF NOT EXISTS idx_loader_failure_trend_date ON loader_failure_trend(loader_name, tracking_date DESC);

-- Market exposure daily snapshots
CREATE TABLE IF NOT EXISTS market_exposure_daily (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    market_exposure_pct DECIMAL(8, 4),
    long_exposure_pct DECIMAL(8, 4),
    short_exposure_pct DECIMAL(8, 4),
    exposure_tier VARCHAR(30),
    is_entry_allowed BOOLEAN,
    exposure_pct DECIMAL(8, 4),
    raw_score DECIMAL(8, 4),
    regime VARCHAR(50),
    distribution_days INTEGER,
    factors JSONB,
    halt_reasons TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date)
);

-- Notifications for UI
CREATE TABLE IF NOT EXISTS algo_notifications (
    id SERIAL PRIMARY KEY,
    kind VARCHAR(40) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    title VARCHAR(200) NOT NULL,
    message TEXT,
    symbol VARCHAR(20),
    details JSONB,
    seen BOOLEAN DEFAULT FALSE,
    seen_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Transaction Cost Analysis (TCA) - Execution quality tracking
CREATE TABLE IF NOT EXISTS algo_tca (
    tca_id SERIAL PRIMARY KEY,
    trade_id INTEGER REFERENCES algo_trades(id) ON DELETE CASCADE,
    symbol VARCHAR(10) NOT NULL,
    signal_date DATE NOT NULL,
    signal_price DECIMAL(12, 4) NOT NULL,
    fill_price DECIMAL(12, 4) NOT NULL,
    shares_requested INTEGER NOT NULL,
    shares_filled INTEGER NOT NULL,
    fill_rate_pct DECIMAL(6, 2),
    slippage_bps DECIMAL(10, 2),
    side VARCHAR(4) NOT NULL,
    execution_latency_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Live Performance Metrics - Daily aggregation for institutional comparison
CREATE TABLE IF NOT EXISTS algo_performance_daily (
    report_date DATE PRIMARY KEY,
    rolling_sharpe_252d NUMERIC(8, 4),
    rolling_sortino_252d NUMERIC(8, 4),
    calmar_ratio NUMERIC(8, 4),
    win_rate_50t NUMERIC(6, 2),
    avg_win_r_50t NUMERIC(6, 3),
    avg_loss_r_50t NUMERIC(6, 3),
    expectancy NUMERIC(6, 4),
    max_drawdown_pct NUMERIC(8, 2),
    live_vs_backtest_ratio NUMERIC(6, 4),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
-- Add new ratio columns to existing databases (idempotent)
ALTER TABLE algo_performance_daily ADD COLUMN IF NOT EXISTS rolling_sortino_252d NUMERIC(8, 4);
ALTER TABLE algo_performance_daily ADD COLUMN IF NOT EXISTS calmar_ratio NUMERIC(8, 4);

-- Portfolio Risk Metrics - Daily VaR, CVaR, concentration, beta
CREATE TABLE IF NOT EXISTS algo_risk_daily (
    report_date DATE PRIMARY KEY,
    var_pct_95 NUMERIC(8, 3),
    cvar_pct_95 NUMERIC(8, 3),
    stressed_var_pct NUMERIC(8, 3),
    portfolio_beta NUMERIC(6, 2),
    top_5_concentration NUMERIC(6, 2),
    status VARCHAR(20) DEFAULT 'ok',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Sector rotation signals
CREATE TABLE IF NOT EXISTS sector_rotation_signal (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    sector VARCHAR(50) NOT NULL,
    signal VARCHAR(20),
    strength DECIMAL(8, 4),
    rank INTEGER,
    details JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, sector)
);

-- Swing trader scores
CREATE TABLE IF NOT EXISTS swing_trader_scores (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    score DECIMAL(8, 4),
    grade VARCHAR(4),
    components JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Model Registry - Track deployed strategies and parameters
CREATE TABLE IF NOT EXISTS algo_model_registry (
    registry_id SERIAL PRIMARY KEY,
    strategy_name VARCHAR(100) NOT NULL,
    git_commit_hash VARCHAR(40) NOT NULL,
    param_snapshot JSONB NOT NULL,
    backtest_sharpe NUMERIC(8, 4),
    backtest_max_dd NUMERIC(8, 4),
    backtest_win_rate NUMERIC(6, 4),
    walk_forward_efficiency NUMERIC(6, 4),
    paper_sharpe NUMERIC(8, 4),
    paper_period_start DATE,
    paper_period_end DATE,
    deployed_at TIMESTAMPTZ,
    deployed_by VARCHAR(100),
    status VARCHAR(20) DEFAULT 'active',
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Configuration Audit Log - Track all parameter changes
CREATE TABLE IF NOT EXISTS algo_config_audit (
    audit_id SERIAL PRIMARY KEY,
    config_key VARCHAR(100) NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_by VARCHAR(100),
    change_reason TEXT,
    changed_at TIMESTAMPTZ DEFAULT now()
);

-- Champion/Challenger Results - A/B test results
CREATE TABLE IF NOT EXISTS algo_champion_challenger (
    trial_id SERIAL PRIMARY KEY,
    trial_date DATE NOT NULL,
    champion_registry_id INTEGER REFERENCES algo_model_registry(registry_id),
    challenger_registry_id INTEGER REFERENCES algo_model_registry(registry_id),
    champion_trades INTEGER,
    challenger_trades INTEGER,
    champion_pnl_pct NUMERIC(8, 2),
    challenger_pnl_pct NUMERIC(8, 2),
    t_statistic NUMERIC(8, 4),
    p_value NUMERIC(8, 6),
    winner VARCHAR(20),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Information Coefficient - Signal quality metric
CREATE TABLE IF NOT EXISTS algo_information_coefficient (
    ic_date DATE PRIMARY KEY,
    signal_name VARCHAR(100),
    lookback_days INTEGER,
    ic_pearson NUMERIC(8, 4),
    ic_spearman NUMERIC(8, 4),
    ic_interpretation VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ════════════════════════════════════════════════════════════════════════════
-- OPERATIONAL MONITORING & EXECUTION TRACKING (PHASE 1-4 INTEGRATION)
-- ════════════════════════════════════════════════════════════════════════════

-- Loader SLA Status - Data freshness monitoring per loader
CREATE TABLE IF NOT EXISTS loader_sla_status (
    id SERIAL PRIMARY KEY,
    loader_name VARCHAR(100) NOT NULL,
    table_name VARCHAR(80) NOT NULL,
    expected_frequency VARCHAR(20),
    max_age_hours INTEGER DEFAULT 24,
    latest_data_date DATE,
    row_count_today BIGINT,
    status VARCHAR(20) DEFAULT 'OK',
    alert_sent_at TIMESTAMP,
    last_check_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(loader_name, table_name)
);

-- Signal Trade Performance Attribution - Link trades to signals for win rate analysis
CREATE TABLE IF NOT EXISTS signal_trade_performance (
    id SERIAL PRIMARY KEY,
    trade_id INTEGER REFERENCES algo_trades(id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    signal_date DATE NOT NULL,
    entry_price DECIMAL(12, 4),
    base_type VARCHAR(50),
    sqs INTEGER,
    swing_score DECIMAL(8, 2),
    swing_grade VARCHAR(5),
    trend_score INTEGER,
    stage_at_entry VARCHAR(50),
    sector VARCHAR(100),
    rs_percentile INTEGER,
    market_exposure_at_entry DECIMAL(8, 2),
    exit_price DECIMAL(12, 4),
    exit_date DATE,
    hold_days INTEGER,
    realized_pnl DECIMAL(12, 2),
    realized_pnl_pct DECIMAL(8, 4),
    r_multiple DECIMAL(8, 2),
    win BOOLEAN,
    target_1_hit BOOLEAN DEFAULT FALSE,
    target_2_hit BOOLEAN DEFAULT FALSE,
    target_3_hit BOOLEAN DEFAULT FALSE,
    exit_by_stop BOOLEAN DEFAULT FALSE,
    exit_by_time BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(trade_id)
);

-- Filter Pipeline Rejection Log - Track why signals were rejected
CREATE TABLE IF NOT EXISTS filter_rejection_log (
    id SERIAL PRIMARY KEY,
    eval_date DATE NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    entry_price DECIMAL(12, 4),
    rejected_at_tier INTEGER,
    rejection_reason VARCHAR(300),
    tier_1_pass BOOLEAN,
    tier_2_pass BOOLEAN,
    tier_2_reason VARCHAR(200),
    tier_3_pass BOOLEAN,
    tier_3_reason VARCHAR(200),
    tier_4_pass BOOLEAN,
    tier_4_reason VARCHAR(200),
    tier_5_pass BOOLEAN,
    tier_5_reason VARCHAR(200),
    advanced_checks_reason VARCHAR(200),
    swing_score_min_reason VARCHAR(200),
    base_type VARCHAR(50),
    sqs INTEGER,
    buy_sell_daily_age_days INTEGER,
    technical_data_age_days INTEGER,
    trend_template_age_days INTEGER,
    max_data_age_days INTEGER,
    is_age_driven_rejection BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Order Execution Audit Trail - Track every order attempt, fill, rejection
CREATE TABLE IF NOT EXISTS order_execution_log (
    id SERIAL PRIMARY KEY,
    trade_id INTEGER REFERENCES algo_trades(id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    order_sequence_num INTEGER,
    order_timestamp TIMESTAMP,
    order_type VARCHAR(20),
    side VARCHAR(10),
    requested_shares INTEGER,
    requested_price DECIMAL(12, 4),
    order_status VARCHAR(50),
    filled_shares INTEGER,
    filled_price DECIMAL(12, 4),
    fill_rate_pct DECIMAL(6, 2),
    slippage_bps DECIMAL(10, 2),
    alpaca_order_id VARCHAR(100),
    rejection_reason VARCHAR(200),
    execution_latency_ms INTEGER,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- INDEXES for Performance
-- ════════════════════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_price_daily_symbol ON price_daily(symbol);
CREATE INDEX IF NOT EXISTS idx_price_daily_date ON price_daily(date);
CREATE INDEX IF NOT EXISTS idx_price_daily_symbol_date ON price_daily(symbol, date);

CREATE INDEX IF NOT EXISTS idx_technical_daily_symbol ON technical_data_daily(symbol);
CREATE INDEX IF NOT EXISTS idx_technical_daily_date ON technical_data_daily(date);

CREATE INDEX IF NOT EXISTS idx_buy_sell_daily_symbol ON buy_sell_daily(symbol);
CREATE INDEX IF NOT EXISTS idx_earnings_symbol ON earnings_estimates(symbol);
CREATE INDEX IF NOT EXISTS idx_analyst_symbol ON analyst_upgrade_downgrade(symbol);

-- Algo system indexes
CREATE INDEX IF NOT EXISTS idx_market_health_daily_date ON market_health_daily(date);
CREATE INDEX IF NOT EXISTS idx_trend_template_symbol ON trend_template_data(symbol);
CREATE INDEX IF NOT EXISTS idx_trend_template_date ON trend_template_data(date);
CREATE INDEX IF NOT EXISTS idx_trend_template_symbol_date ON trend_template_data(symbol, date);
CREATE INDEX IF NOT EXISTS idx_vcp_patterns_symbol_date ON vcp_patterns(symbol, date);
CREATE INDEX IF NOT EXISTS idx_signal_quality_symbol_date ON signal_quality_scores(symbol, date);
CREATE INDEX IF NOT EXISTS idx_algo_signals_evaluated_date ON algo_signals_evaluated(signal_date);
CREATE INDEX IF NOT EXISTS idx_algo_signals_evaluated_symbol ON algo_signals_evaluated(symbol);
CREATE INDEX IF NOT EXISTS idx_algo_trades_symbol ON algo_trades(symbol);
CREATE INDEX IF NOT EXISTS idx_algo_trades_status ON algo_trades(status);
CREATE INDEX IF NOT EXISTS idx_algo_positions_symbol ON algo_positions(symbol);
CREATE INDEX IF NOT EXISTS idx_algo_positions_status ON algo_positions(status);
CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_date ON algo_portfolio_snapshots(snapshot_date);
CREATE INDEX IF NOT EXISTS idx_audit_log_action_type ON algo_audit_log(action_type);
CREATE INDEX IF NOT EXISTS idx_audit_log_date ON algo_audit_log(action_date);

-- Indexes for TCA
CREATE INDEX IF NOT EXISTS idx_algo_tca_trade_id ON algo_tca(trade_id);
CREATE INDEX IF NOT EXISTS idx_algo_tca_symbol ON algo_tca(symbol);
CREATE INDEX IF NOT EXISTS idx_algo_tca_signal_date ON algo_tca(signal_date);

-- Indexes for Performance metrics
CREATE INDEX IF NOT EXISTS idx_algo_performance_daily_date ON algo_performance_daily(report_date);

-- Indexes for Risk metrics
CREATE INDEX IF NOT EXISTS idx_algo_risk_daily_date ON algo_risk_daily(report_date);

-- Indexes for Model Governance
CREATE INDEX IF NOT EXISTS idx_algo_model_registry_commit ON algo_model_registry(git_commit_hash);
CREATE INDEX IF NOT EXISTS idx_algo_model_registry_status ON algo_model_registry(status);
CREATE INDEX IF NOT EXISTS idx_algo_model_registry_deployed_at ON algo_model_registry(deployed_at);
CREATE INDEX IF NOT EXISTS idx_algo_config_audit_key ON algo_config_audit(config_key);
CREATE INDEX IF NOT EXISTS idx_algo_config_audit_date ON algo_config_audit(changed_at);
CREATE INDEX IF NOT EXISTS idx_algo_champion_challenger_date ON algo_champion_challenger(trial_date);
CREATE INDEX IF NOT EXISTS idx_algo_information_coefficient_date ON algo_information_coefficient(ic_date);

-- ════════════════════════════════════════════════════════════════════════════
-- BACKTEST & STRATEGY ANALYSIS TABLES
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS backtest_runs (
    run_id SERIAL PRIMARY KEY,
    run_name VARCHAR(200),
    run_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    strategy_name VARCHAR(200),
    start_date DATE,
    end_date DATE,
    initial_capital DECIMAL(15,2),
    final_value DECIMAL(15,2),
    total_return DECIMAL(8,4),
    annual_return DECIMAL(8,4),
    max_drawdown DECIMAL(8,4),
    sharpe_ratio DECIMAL(8,4),
    sortino_ratio DECIMAL(8,4),
    win_rate DECIMAL(8,4),
    profit_factor DECIMAL(8,4),
    num_trades INTEGER,
    num_winning_trades INTEGER,
    num_losing_trades INTEGER,
    avg_win DECIMAL(15,2),
    avg_loss DECIMAL(15,2),
    largest_win DECIMAL(15,2),
    largest_loss DECIMAL(15,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(run_name, run_timestamp)
);

CREATE TABLE IF NOT EXISTS backtest_trades (
    trade_id SERIAL PRIMARY KEY,
    run_id INTEGER REFERENCES backtest_runs(run_id),
    symbol VARCHAR(20),
    entry_date DATE,
    exit_date DATE,
    entry_price DECIMAL(12,4),
    exit_price DECIMAL(12,4),
    quantity DECIMAL(12,2),
    entry_value DECIMAL(15,2),
    exit_value DECIMAL(15,2),
    profit_loss DECIMAL(15,2),
    profit_loss_percent DECIMAL(8,4),
    trade_outcome VARCHAR(50),
    holding_days INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS safeguard_audit_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    symbol VARCHAR(20),
    safeguard_name VARCHAR(100),
    action VARCHAR(100),
    reason TEXT,
    details JSON,
    severity VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ════════════════════════════════════════════════════════════════════════════
-- ETF & MEAN REVERSION SIGNAL TABLES
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS etf_symbols (
    symbol VARCHAR(20) PRIMARY KEY,
    security_name VARCHAR(200),
    asset_class VARCHAR(100),
    expense_ratio DECIMAL(8,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ════════════════════════════════════════════════════════════════════════════
-- COMMODITY ANALYSIS TABLES
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS commodity_seasonality (
    symbol VARCHAR(20),
    month INTEGER,
    avg_return DECIMAL(8,4),
    win_rate DECIMAL(8,4),
    volatility DECIMAL(8,4),
    num_years INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(symbol, month)
);

CREATE TABLE IF NOT EXISTS commodity_correlations (
    symbol1 VARCHAR(20),
    symbol2 VARCHAR(20),
    correlation_30d DECIMAL(8,4),
    correlation_90d DECIMAL(8,4),
    correlation_1y DECIMAL(8,4),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(symbol1, symbol2)
);

CREATE TABLE IF NOT EXISTS commodity_technicals (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    date DATE,
    rsi DECIMAL(8,4),
    macd DECIMAL(12,4),
    macd_signal DECIMAL(12,4),
    sma_20 DECIMAL(12,4),
    sma_50 DECIMAL(12,4),
    sma_200 DECIMAL(12,4),
    bb_upper DECIMAL(12,4),
    bb_lower DECIMAL(12,4),
    atr DECIMAL(12,4),
    signal VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

CREATE TABLE IF NOT EXISTS commodity_macro_drivers (
    series_id VARCHAR(50),
    series_name VARCHAR(200),
    date DATE,
    value DECIMAL(15,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(series_id, date)
);

CREATE TABLE IF NOT EXISTS commodity_events (
    event_id SERIAL PRIMARY KEY,
    event_name VARCHAR(200),
    event_date DATE,
    event_type VARCHAR(100),
    description TEXT,
    impact VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for new tables
CREATE INDEX IF NOT EXISTS idx_trade_adds_trade_id ON algo_trade_adds(trade_id);
CREATE INDEX IF NOT EXISTS idx_data_patrol_log_date ON data_patrol_log(patrol_date);
CREATE INDEX IF NOT EXISTS idx_data_patrol_log_severity ON data_patrol_log(severity);
CREATE INDEX IF NOT EXISTS idx_data_remediation_log_date ON data_remediation_log(remediation_date);
CREATE INDEX IF NOT EXISTS idx_market_exposure_daily_date ON market_exposure_daily(date);
CREATE INDEX IF NOT EXISTS idx_notif_unseen ON algo_notifications(seen, created_at) WHERE seen = FALSE;
CREATE INDEX IF NOT EXISTS idx_notif_severity ON algo_notifications(severity);
CREATE INDEX IF NOT EXISTS idx_sector_rotation_date ON sector_rotation_signal(date);
CREATE INDEX IF NOT EXISTS idx_sector_rotation_sector ON sector_rotation_signal(sector);
CREATE INDEX IF NOT EXISTS idx_swing_scores_symbol_date ON swing_trader_scores(symbol, date);

-- Indexes for new operational tables
CREATE INDEX IF NOT EXISTS idx_loader_sla_status_check ON loader_sla_status(last_check_at);
CREATE INDEX IF NOT EXISTS idx_signal_perf_symbol_date ON signal_trade_performance(symbol, signal_date);
CREATE INDEX IF NOT EXISTS idx_signal_perf_base_type ON signal_trade_performance(base_type);
CREATE INDEX IF NOT EXISTS idx_signal_perf_win ON signal_trade_performance(win);
CREATE INDEX IF NOT EXISTS idx_rejection_eval_date ON filter_rejection_log(eval_date);
CREATE INDEX IF NOT EXISTS idx_rejection_tier ON filter_rejection_log(rejected_at_tier);
CREATE INDEX IF NOT EXISTS idx_rejection_symbol ON filter_rejection_log(symbol);
CREATE INDEX IF NOT EXISTS idx_order_trade_id ON order_execution_log(trade_id);
CREATE INDEX IF NOT EXISTS idx_order_status ON order_execution_log(order_status);
CREATE INDEX IF NOT EXISTS idx_order_timestamp ON order_execution_log(order_timestamp DESC);

-- Indexes for backtest and strategy tables
CREATE INDEX IF NOT EXISTS idx_backtest_runs_name ON backtest_runs(run_name);
CREATE INDEX IF NOT EXISTS idx_backtest_runs_timestamp ON backtest_runs(run_timestamp);
CREATE INDEX IF NOT EXISTS idx_backtest_trades_run_id ON backtest_trades(run_id);
CREATE INDEX IF NOT EXISTS idx_backtest_trades_symbol ON backtest_trades(symbol);
CREATE INDEX IF NOT EXISTS idx_safeguard_audit_log_symbol ON safeguard_audit_log(symbol);
CREATE INDEX IF NOT EXISTS idx_safeguard_audit_log_timestamp ON safeguard_audit_log(timestamp);

-- Indexes for sentiment tables
-- idx_market_sentiment_date removed (market_sentiment becomes a view, not a table)
CREATE INDEX IF NOT EXISTS idx_social_sentiment_symbol_date ON sentiment_social(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_social_sentiment_date ON sentiment_social(date DESC);

-- Indexes for commodity tables
CREATE INDEX IF NOT EXISTS idx_commodity_seasonality_symbol ON commodity_seasonality(symbol);
CREATE INDEX IF NOT EXISTS idx_commodity_technicals_symbol_date ON commodity_technicals(symbol, date);
CREATE INDEX IF NOT EXISTS idx_commodity_macro_drivers_series_date ON commodity_macro_drivers(series_id, date);
CREATE INDEX IF NOT EXISTS idx_commodity_events_date ON commodity_events(event_date);

-- ════════════════════════════════════════════════════════════════════════════
-- DERIVED VIEWS (API convenience — combine normalized tables)
-- ════════════════════════════════════════════════════════════════════════════

-- stock_fundamentals: join scores + profiles + fundamental metrics
-- Used by: /api/stocks/deep-value, /api/scores/stockscores
CREATE OR REPLACE VIEW stock_fundamentals AS
SELECT
    ss.symbol,
    COALESCE(cp.long_name, cp.short_name, ss.symbol) AS company_name,
    cp.sector,
    cp.industry,
    -- Scores
    sc.composite_score,
    sc.momentum_score,
    sc.quality_score,
    sc.value_score,
    sc.growth_score,
    sc.positioning_score,
    sc.stability_score,
    -- Current price
    pd.close AS current_price,
    -- Value metrics
    vm.pe_ratio AS trailing_pe,
    vm.pb_ratio AS price_to_book,
    vm.ps_ratio AS price_to_sales,
    vm.peg_ratio,
    vm.dividend_yield,
    -- Quality metrics
    qm.roe AS roe_pct,
    qm.roa AS roa_pct,
    qm.operating_margin AS op_margin_pct,
    qm.net_margin AS net_margin_pct,
    qm.debt_to_equity,
    qm.current_ratio,
    -- Growth metrics
    gm.revenue_growth_1y AS revenue_growth_yoy_pct,
    gm.eps_growth_1y AS eps_growth_yoy_pct,
    gm.revenue_growth_3y AS revenue_growth_3y_pct,
    gm.eps_growth_3y AS eps_growth_3y_pct,
    -- Stability
    stm.beta,
    -- Derived: margin of safety (simplified: discount from 52w high)
    CASE WHEN pd_52w.high_52w > 0
         THEN ROUND(((pd_52w.high_52w - pd.close) / pd_52w.high_52w * 100)::numeric, 2)
         ELSE NULL END AS margin_of_safety_pct,
    pd_52w.high_52w,
    pd_52w.low_52w,
    -- drop_from_52w_high_pct: same as margin_of_safety_pct, alternate name used by deep-value query
    CASE WHEN pd_52w.high_52w > 0
         THEN ROUND(((pd_52w.high_52w - pd.close) / pd_52w.high_52w * 100)::numeric, 2)
         ELSE NULL END AS drop_from_52w_high_pct,
    -- Columns not derivable from current loaders — NULL placeholders for API compatibility
    NULL::numeric AS forward_pe,
    NULL::numeric AS gross_margin_pct,
    NULL::numeric AS sector_median_pe,
    NULL::numeric AS market_median_pe,
    NULL::numeric AS discount_vs_sector_pe_pct,
    NULL::numeric AS discount_vs_market_pe_pct,
    NULL::numeric AS high_3y,
    NULL::numeric AS drop_from_3y_high_pct,
    NULL::numeric AS intrinsic_value_per_share,
    NULL::numeric AS fcf_growth_yoy_pct,
    NULL::numeric AS sustainable_growth_pct,
    NULL::numeric AS op_margin_trend_pp,
    NULL::numeric AS gross_margin_trend_pp,
    NULL::numeric AS roe_trend_pp,
    -- Generational score = composite_score (alias for UI compatibility)
    sc.composite_score AS generational_score
FROM stock_symbols ss
LEFT JOIN company_profile cp ON cp.ticker = ss.symbol
LEFT JOIN stock_scores sc ON sc.symbol = ss.symbol
LEFT JOIN value_metrics vm ON vm.symbol = ss.symbol
LEFT JOIN quality_metrics qm ON qm.symbol = ss.symbol
LEFT JOIN growth_metrics gm ON gm.symbol = ss.symbol
LEFT JOIN stability_metrics stm ON stm.symbol = ss.symbol
LEFT JOIN LATERAL (
    SELECT close FROM price_daily
    WHERE symbol = ss.symbol
    ORDER BY date DESC LIMIT 1
) pd ON true
LEFT JOIN LATERAL (
    SELECT MAX(high) AS high_52w, MIN(low) AS low_52w
    FROM price_daily
    WHERE symbol = ss.symbol AND date >= CURRENT_DATE - INTERVAL '252 days'
) pd_52w ON true
WHERE sc.composite_score IS NOT NULL;

-- sp500_list: placeholder — populated when SP500 data loader is added
-- For now, returns symbols with composite_score > 60 as a proxy
CREATE OR REPLACE VIEW sp500_list AS
SELECT symbol FROM stock_scores WHERE composite_score > 60;

-- market_sentiment: alias for fear_greed_index for API compatibility
CREATE OR REPLACE VIEW market_sentiment AS
SELECT
    date,
    fear_greed_value AS fear_greed_index,
    fear_greed_label AS label,
    NULL::numeric AS put_call_ratio,
    NULL::numeric AS vix,
    fear_greed_value AS sentiment_score
FROM fear_greed_index;

-- ════════════════════════════════════════════════════════════════════════════
-- BUY/SELL SIGNAL TABLE SCHEMA MIGRATIONS
-- The original buy_sell_daily/weekly/monthly tables had only 7 columns.
-- The loadbuyselldaily loader and Node.js API require ~50 columns.
-- These idempotent ALTERs add all missing columns and fix the UNIQUE constraint.
-- ════════════════════════════════════════════════════════════════════════════

-- ✅ CONSOLIDATED: buy_sell_daily/weekly/monthly columns now in CREATE TABLE

-- ✅ algo_trades: mfe_pct, mae_pct already in CREATE TABLE
-- ✅ technical_data_daily/weekly/monthly: close, ema_21 already in CREATE TABLE

-- ════════════════════════════════════════════════════════════════════════════
-- MISSING LOADER TARGET TABLES (required for market_data_batch + Step Functions)
-- ════════════════════════════════════════════════════════════════════════════

-- Market overview indices (loadmarket.py) — SPY/QQQ/IWM/VIX daily OHLCV
CREATE TABLE IF NOT EXISTS market_overview (
    id SERIAL PRIMARY KEY,
    index_name VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    close DECIMAL(12, 4),
    volume BIGINT,
    market_cap DECIMAL(15, 2),
    advance_decline_ratio DECIMAL(8, 4),
    vix DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(index_name, date)
);
CREATE INDEX IF NOT EXISTS idx_market_overview_index_date ON market_overview(index_name, date);
CREATE INDEX IF NOT EXISTS idx_market_overview_date ON market_overview(date);

-- Sector aggregate metrics (loadsectors.py) — one row per sector per day
CREATE TABLE IF NOT EXISTS sectors (
    id SERIAL PRIMARY KEY,
    sector_name VARCHAR(100) NOT NULL,
    metric_date DATE NOT NULL,
    performance_ytd DECIMAL(8, 4),
    performance_1y DECIMAL(8, 4),
    performance_3y DECIMAL(8, 4),
    pe_ratio DECIMAL(8, 4),
    dividend_yield DECIMAL(8, 4),
    market_cap DECIMAL(18, 2),
    stock_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(sector_name, metric_date)
);
CREATE INDEX IF NOT EXISTS idx_sectors_metric_date ON sectors(metric_date);

-- Factor metrics (loadfactormetrics.py) — price + derived ratios per symbol per day
-- Runs in Step Functions EOD pipeline; missing table blocks pipeline execution
CREATE TABLE IF NOT EXISTS factor_metrics (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    metric_date DATE NOT NULL,
    price DECIMAL(12, 4),
    volume BIGINT,
    momentum_3d DECIMAL(8, 4),
    volatility_20d DECIMAL(8, 4),
    pe_ratio DECIMAL(8, 4),
    pb_ratio DECIMAL(8, 4),
    dividend_yield DECIMAL(8, 4),
    debt_to_equity DECIMAL(8, 4),
    roe DECIMAL(8, 4),
    roa DECIMAL(8, 4),
    current_ratio DECIMAL(8, 4),
    quick_ratio DECIMAL(8, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, metric_date)
);
CREATE INDEX IF NOT EXISTS idx_factor_metrics_symbol_date ON factor_metrics(symbol, metric_date);
CREATE INDEX IF NOT EXISTS idx_factor_metrics_date ON factor_metrics(metric_date);

-- ════════════════════════════════════════════════════════════════════════════
-- BACKTEST RESULTS & HISTORICAL ANALYSIS
-- ════════════════════════════════════════════════════════════════════════════

-- Backtest results: historical performance data from strategy runs
CREATE TABLE IF NOT EXISTS backtest_results (
    id SERIAL PRIMARY KEY,
    backtest_id UUID UNIQUE DEFAULT gen_random_uuid(),
    strategy_name VARCHAR(100) NOT NULL,
    symbol VARCHAR(20),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    initial_capital DECIMAL(15, 2),
    final_capital DECIMAL(15, 2),
    total_return_pct DECIMAL(8, 4),
    annualized_return_pct DECIMAL(8, 4),
    max_drawdown_pct DECIMAL(8, 4),
    sharpe_ratio DECIMAL(8, 4),
    sortino_ratio DECIMAL(8, 4),
    win_rate_pct DECIMAL(8, 4),
    profit_factor DECIMAL(8, 4),
    total_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,
    avg_trade_return_pct DECIMAL(8, 4),
    best_trade_pct DECIMAL(8, 4),
    worst_trade_pct DECIMAL(8, 4),
    avg_holding_days DECIMAL(8, 2),
    parameters JSONB,
    equity_curve JSONB,
    trade_log JSONB,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Backtest trade details
CREATE TABLE IF NOT EXISTS backtest_trades (
    id SERIAL PRIMARY KEY,
    backtest_id UUID REFERENCES backtest_results(backtest_id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    trade_date DATE NOT NULL,
    entry_price DECIMAL(12, 4) NOT NULL,
    entry_quantity INTEGER NOT NULL,
    exit_date DATE,
    exit_price DECIMAL(12, 4),
    profit_loss_dollars DECIMAL(15, 2),
    profit_loss_pct DECIMAL(8, 4),
    holding_days INTEGER,
    exit_reason VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for backtest queries
CREATE INDEX IF NOT EXISTS idx_backtest_results_strategy ON backtest_results(strategy_name);
CREATE INDEX IF NOT EXISTS idx_backtest_results_date ON backtest_results(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_backtest_trades_backtest_id ON backtest_trades(backtest_id);
CREATE INDEX IF NOT EXISTS idx_backtest_trades_symbol ON backtest_trades(symbol);

-- Relative performance (loadrelativeperformance.py) — OHLCV per symbol for RS calculation
CREATE TABLE IF NOT EXISTS relative_performance (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(12, 4),
    high DECIMAL(12, 4),
    low DECIMAL(12, 4),
    close DECIMAL(12, 4),
    volume BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);
CREATE INDEX IF NOT EXISTS idx_relative_performance_symbol_date ON relative_performance(symbol, date);
CREATE INDEX IF NOT EXISTS idx_relative_performance_date ON relative_performance(date);

-- Market sentiment aggregates by symbol/market
CREATE TABLE IF NOT EXISTS sentiment (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    sentiment_score DECIMAL(8, 4),
    sentiment_label VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol)
);
CREATE INDEX IF NOT EXISTS idx_sentiment_symbol ON sentiment(symbol);

-- ════════════════════════════════════════════════════════════════════════════
-- LOADER TRACKING & MONITORING
-- ════════════════════════════════════════════════════════════════════════════

-- Loader execution metrics (loader_metrics.py)
CREATE TABLE IF NOT EXISTS loader_execution_metrics (
    id SERIAL PRIMARY KEY,
    loader_name VARCHAR(100) NOT NULL,
    execution_date TIMESTAMP,
    rows_inserted INTEGER,
    rows_updated INTEGER,
    rows_deleted INTEGER,
    duration_seconds DECIMAL(8, 2),
    success BOOLEAN,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(loader_name, execution_date)
);
CREATE INDEX IF NOT EXISTS idx_loader_metrics_loader_name ON loader_execution_metrics(loader_name);
CREATE INDEX IF NOT EXISTS idx_loader_metrics_execution_date ON loader_execution_metrics(execution_date);

-- Loader execution history (loader_sla_tracker.py)
CREATE TABLE IF NOT EXISTS loader_execution_history (
    id SERIAL PRIMARY KEY,
    loader_name VARCHAR(100) NOT NULL,
    execution_start TIMESTAMP,
    execution_end TIMESTAMP,
    status VARCHAR(20),
    rows_processed INTEGER,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_loader_history_loader_name ON loader_execution_history(loader_name);
CREATE INDEX IF NOT EXISTS idx_loader_history_execution_start ON loader_execution_history(execution_start);

-- Loader SLA status tracking
CREATE TABLE IF NOT EXISTS loader_sla_status (
    id SERIAL PRIMARY KEY,
    loader_name VARCHAR(100) NOT NULL,
    last_success_time TIMESTAMP,
    last_failure_time TIMESTAMP,
    consecutive_failures INTEGER DEFAULT 0,
    status VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(loader_name)
);
CREATE INDEX IF NOT EXISTS idx_loader_sla_status_loader_name ON loader_sla_status(loader_name);

-- Last updated timestamps (loadaaiidata.py, loadfeargreed.py, loadnaaim.py)
CREATE TABLE IF NOT EXISTS last_updated (
    id SERIAL PRIMARY KEY,
    script_name VARCHAR(100) NOT NULL UNIQUE,
    last_run TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_last_updated_script_name ON last_updated(script_name);

-- Price data for intermediate calculations (industry ranking, window calculations)
CREATE TABLE IF NOT EXISTS price_window (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    period_type VARCHAR(20),
    window_start DATE,
    window_end DATE,
    price_change DECIMAL(8, 4),
    volume_avg BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date, period_type)
);

-- ════════════════════════════════════════════════════════════════════════════
-- PERFORMANCE INDEXES (2026-05-15) — After Phase 1 Data Integrity
-- ════════════════════════════════════════════════════════════════════════════
-- Critical for orchestrator phases 2-7 execution speed

-- PRICE DATA INDEXES — Most expensive queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_daily_symbol_date
ON price_daily (symbol, date)
WHERE close IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_daily_symbol_desc
ON price_daily (symbol, date DESC)
WHERE close > 0;

-- WEEKLY/MONTHLY PRICE INDEXES — Essential for aggregation queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_weekly_symbol_date
ON price_weekly (symbol, date)
WHERE close IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_monthly_symbol_date
ON price_monthly (symbol, date)
WHERE close IS NOT NULL;

-- WEEKLY/MONTHLY TECHNICAL DATA INDEXES — For technical analysis aggregations
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_technical_data_weekly_symbol_date
ON technical_data_weekly (symbol, date)
WHERE sma_20 IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_technical_data_monthly_symbol_date
ON technical_data_monthly (symbol, date)
WHERE sma_20 IS NOT NULL;

-- TECHNICAL DATA INDEXES — Technical indicator queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_technical_data_daily_date
ON technical_data_daily (date)
WHERE sma_20 IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_technical_data_daily_symbol_date
ON technical_data_daily (symbol, date)
WHERE rsi IS NOT NULL;

-- BUY/SELL SIGNAL INDEXES — Phase 2 signal generation, Phase 5 exit
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_buy_sell_daily_date
ON buy_sell_daily (date)
WHERE buy_signal IS NOT NULL OR sell_signal IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_buy_sell_daily_symbol_date
ON buy_sell_daily (symbol, date)
WHERE buy_signal IS NOT NULL;

-- STOCK SCORES INDEXES — Entry qualification filtering
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_stock_scores_updated_at
ON stock_scores (updated_at DESC)
WHERE growth_score IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_stock_scores_symbol
ON stock_scores (symbol)
WHERE composite_score >= 0;

-- POSITION TRACKING INDEXES — Phase 3-7 position lifecycle
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_algo_positions_status
ON algo_positions (status)
WHERE status IN ('open', 'pending_exit');

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_algo_positions_symbol_status
ON algo_positions (symbol, status, entry_date DESC)
WHERE status = 'open';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_algo_positions_exit_conditions
ON algo_positions (status, created_at)
WHERE status = 'open' AND exit_reason IS NULL;

-- TRADE EXECUTION INDEXES — Trade history and reconciliation
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_algo_trades_status_date
ON algo_trades (status, trade_date DESC)
WHERE status IN ('filled', 'pending', 'failed');

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_algo_trades_position_id
ON algo_trades (position_id)
WHERE position_id IS NOT NULL;

-- RISK TRACKING INDEXES — VaR/concentration monitoring
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_algo_risk_daily_date
ON algo_risk_daily (report_date DESC)
WHERE report_date IS NOT NULL;

-- MARKET EXPOSURE INDEXES — Regime detection
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_market_exposure_daily_date
ON market_exposure_daily (date DESC)
WHERE exposure_tier IS NOT NULL;

-- PORTFOLIO SNAPSHOT INDEXES — Drawdown and performance calculations
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_algo_portfolio_snapshots_date
ON algo_portfolio_snapshots (snapshot_date DESC)
WHERE total_portfolio_value > 0;

-- AUDIT & MONITORING INDEXES
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_algo_audit_log_action_date
ON algo_audit_log (action_date DESC, action_type)
WHERE action_date >= NOW() - INTERVAL '30 days';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_data_patrol_log_severity
ON data_patrol_log (severity, created_at DESC)
WHERE severity IN ('error', 'critical');

-- LOADER SLA TRACKING INDEXES
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_loader_sla_tracker_date_status
ON loader_sla_tracker (start_time DESC, status)
WHERE start_time >= NOW() - INTERVAL '7 days';

-- ECONOMIC DATA INDEXES — Credit spreads, yield curve
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_economic_data_series_date
ON economic_data (series_id, date DESC)
WHERE series_id IN ('BAMLH0A0HYM2', 'T10Y2Y', 'FEDFUNDS', 'UNRATE')
  AND value IS NOT NULL;

-- ════════════════════════════════════════════════════════════════════════════
-- SCHEMA MIGRATIONS — Ensure live tables have all required columns
-- ════════════════════════════════════════════════════════════════════════════
ALTER TABLE backtest_trades ADD COLUMN IF NOT EXISTS quantity DECIMAL(12,2);
ALTER TABLE backtest_trades ADD COLUMN IF NOT EXISTS profit_loss_percent DECIMAL(8,4);

-- ════════════════════════════════════════════════════════════════════════════
-- FEATURE FLAGS — Control system behavior without code changes
-- ════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS feature_flags (
    flag_name VARCHAR(100) PRIMARY KEY,
    flag_type VARCHAR(50) NOT NULL,
    value TEXT,
    description TEXT,
    metadata JSONB DEFAULT '{}',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_feature_flags_type ON feature_flags (flag_type);

-- ════════════════════════════════════════════════════════════════════════════
-- LOADER WATERMARKS — Track incremental load progress per symbol
-- ════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS loader_watermarks (
    loader VARCHAR(100) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    granularity VARCHAR(20) NOT NULL DEFAULT 'symbol',
    watermark TEXT,
    rows_loaded INTEGER DEFAULT 0,
    last_run_at TIMESTAMPTZ,
    last_success_at TIMESTAMPTZ,
    error_count INTEGER DEFAULT 0,
    last_error TEXT,
    UNIQUE (loader, symbol, granularity)
);

-- ════════════════════════════════════════════════════════════════════════════
-- SCHEMA FIXES — Missing columns referenced by active code
-- ════════════════════════════════════════════════════════════════════════════

-- market_exposure_daily: add missing columns used by algo_market_exposure.py
ALTER TABLE market_exposure_daily ADD COLUMN IF NOT EXISTS long_exposure_pct DECIMAL(8, 4);
ALTER TABLE market_exposure_daily ADD COLUMN IF NOT EXISTS short_exposure_pct DECIMAL(8, 4);
ALTER TABLE market_exposure_daily ADD COLUMN IF NOT EXISTS is_entry_allowed BOOLEAN;
ALTER TABLE market_exposure_daily ADD COLUMN IF NOT EXISTS exposure_tier VARCHAR(50);
-- Widen column if it was previously created as VARCHAR(20) (too short for 'tier_1_strong_uptrend')
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'market_exposure_daily' AND column_name = 'exposure_tier'
        AND character_maximum_length < 50
    ) THEN
        ALTER TABLE market_exposure_daily ALTER COLUMN exposure_tier TYPE VARCHAR(50);
    END IF;
END $$;

-- sector_ranking: add missing historical rank columns used by sector rotation
ALTER TABLE sector_ranking ADD COLUMN IF NOT EXISTS rank_1w_ago INTEGER;
ALTER TABLE sector_ranking ADD COLUMN IF NOT EXISTS rank_4w_ago INTEGER;
ALTER TABLE sector_ranking ADD COLUMN IF NOT EXISTS rank_12w_ago INTEGER;

-- algo_positions: add missing columns referenced in index definitions
ALTER TABLE algo_positions ADD COLUMN IF NOT EXISTS entry_date DATE;
ALTER TABLE algo_positions ADD COLUMN IF NOT EXISTS exit_reason VARCHAR(100);

-- ════════════════════════════════════════════════════════════════════════════
-- NEW TABLES — Finance optimization system
-- ════════════════════════════════════════════════════════════════════════════

-- Component-level signal attribution (Information Coefficient per component)
CREATE TABLE IF NOT EXISTS algo_component_attribution (
    id SERIAL PRIMARY KEY,
    report_date DATE NOT NULL,
    component VARCHAR(50) NOT NULL,          -- setup_quality, trend_quality, momentum_rs, etc.
    ic_value DECIMAL(8,4),                   -- Information Coefficient (Pearson r vs realized P&L)
    ic_pvalue DECIMAL(8,4),                  -- Statistical significance
    sample_size INTEGER,                     -- Number of trades in window
    lookback_trades INTEGER,                 -- How many closed trades were analyzed
    avg_component_score DECIMAL(8,4),        -- Average component score in sample
    avg_realized_pnl DECIMAL(8,4),           -- Average realized P&L in sample
    regime VARCHAR(50),                      -- Market regime when measured
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(report_date, component)
);
CREATE INDEX IF NOT EXISTS idx_component_attribution_date ON algo_component_attribution(report_date DESC);
CREATE INDEX IF NOT EXISTS idx_component_attribution_component ON algo_component_attribution(component);

-- Historical record of weight changes (audit trail)
CREATE TABLE IF NOT EXISTS algo_weight_history (
    id SERIAL PRIMARY KEY,
    change_date DATE NOT NULL,
    component VARCHAR(50) NOT NULL,
    old_weight INTEGER,                      -- Previous weight (0-100)
    new_weight INTEGER,                      -- New weight (0-100)
    reason VARCHAR(200),                     -- 'ic_optimization', 'regime_shift', 'manual', etc.
    ic_value DECIMAL(8,4),                   -- IC that drove the optimization
    blending_factor DECIMAL(8,4),            -- Alpha used for smooth blending
    regime VARCHAR(50),                      -- Regime at time of change
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_weight_history_date ON algo_weight_history(change_date DESC);
CREATE INDEX IF NOT EXISTS idx_weight_history_component ON algo_weight_history(component);

-- Earnings metrics for earnings alpha scoring
CREATE TABLE IF NOT EXISTS earnings_metrics (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    report_date DATE NOT NULL,
    eps_surprise_pct DECIMAL(8,4),           -- (actual - consensus) / consensus
    revenue_surprise_pct DECIMAL(8,4),
    eps_beat_count_4q INTEGER,               -- # of last 4 quarters beaten
    eps_beat_rate_pct DECIMAL(8,4),          -- % of last 4 quarters beaten
    historical_beat_magnitude_avg DECIMAL(8,4), -- Average magnitude of beats
    guidance_raised BOOLEAN,                 -- Was guidance raised?
    guidance_beat_pct DECIMAL(8,4),          -- Beat guidance by how much?
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, report_date)
);
CREATE INDEX IF NOT EXISTS idx_earnings_metrics_symbol_date ON earnings_metrics(symbol, report_date DESC);
CREATE INDEX IF NOT EXISTS idx_earnings_metrics_date ON earnings_metrics(report_date DESC);

-- ════════════════════════════════════════════════════════════════════════════
-- SCHEMA MIGRATIONS - Add missing columns to existing tables
-- ════════════════════════════════════════════════════════════════════════════

-- Add updated_at column to analyst_sentiment_analysis if missing
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'analyst_sentiment_analysis' AND column_name = 'updated_at') THEN
        ALTER TABLE analyst_sentiment_analysis ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
    END IF;
END $$;

-- Add missing columns to annual_balance_sheet
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'annual_balance_sheet' AND column_name = 'current_liabilities') THEN
        ALTER TABLE annual_balance_sheet ADD COLUMN current_liabilities DECIMAL(20, 2);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'annual_balance_sheet' AND column_name = 'inventory') THEN
        ALTER TABLE annual_balance_sheet ADD COLUMN inventory DECIMAL(20, 2);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'annual_balance_sheet' AND column_name = 'cash_and_equivalents') THEN
        ALTER TABLE annual_balance_sheet ADD COLUMN cash_and_equivalents DECIMAL(20, 2);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'annual_balance_sheet' AND column_name = 'accounts_receivable') THEN
        ALTER TABLE annual_balance_sheet ADD COLUMN accounts_receivable DECIMAL(20, 2);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'annual_balance_sheet' AND column_name = 'ppe_net') THEN
        ALTER TABLE annual_balance_sheet ADD COLUMN ppe_net DECIMAL(20, 2);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'annual_balance_sheet' AND column_name = 'goodwill') THEN
        ALTER TABLE annual_balance_sheet ADD COLUMN goodwill DECIMAL(20, 2);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'annual_balance_sheet' AND column_name = 'long_term_debt') THEN
        ALTER TABLE annual_balance_sheet ADD COLUMN long_term_debt DECIMAL(20, 2);
    END IF;
END $$;

-- Add missing columns to quarterly_balance_sheet
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'quarterly_balance_sheet' AND column_name = 'current_assets') THEN
        ALTER TABLE quarterly_balance_sheet ADD COLUMN current_assets DECIMAL(20, 2);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'quarterly_balance_sheet' AND column_name = 'current_liabilities') THEN
        ALTER TABLE quarterly_balance_sheet ADD COLUMN current_liabilities DECIMAL(20, 2);
    END IF;
END $$;

-- Add missing columns to quarterly_cash_flow
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'quarterly_cash_flow' AND column_name = 'investing_cash_flow') THEN
        ALTER TABLE quarterly_cash_flow ADD COLUMN investing_cash_flow DECIMAL(20, 2);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'quarterly_cash_flow' AND column_name = 'financing_cash_flow') THEN
        ALTER TABLE quarterly_cash_flow ADD COLUMN financing_cash_flow DECIMAL(20, 2);
    END IF;
END $$;

-- ════════════════════════════════════════════════════════════════════════════
-- ENHANCED AUDIT LOGGING FOR REAL MONEY TRADING
-- ════════════════════════════════════════════════════════════════════════════

-- Position sizing audit: track all multipliers and cascade effect
CREATE TABLE IF NOT EXISTS algo_position_sizing_audit (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    signal_date DATE NOT NULL,
    entry_price DECIMAL(15, 4) NOT NULL,
    stop_loss_price DECIMAL(15, 4) NOT NULL,
    base_shares INTEGER NOT NULL,
    final_shares INTEGER NOT NULL,
    position_size_pct DECIMAL(8, 4) NOT NULL,
    cascade_multiplier DECIMAL(10, 4) NOT NULL DEFAULT 1.0,
    multipliers_json TEXT,
    reasons_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_position_sizing_symbol_date
    ON algo_position_sizing_audit(symbol, signal_date DESC);
CREATE INDEX IF NOT EXISTS idx_position_sizing_created_at
    ON algo_position_sizing_audit(created_at DESC);

-- Stop loss calculation audit: why was each stop chosen
CREATE TABLE IF NOT EXISTS algo_stop_loss_audit (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    signal_date DATE NOT NULL,
    entry_price DECIMAL(15, 4) NOT NULL,
    stop_loss_price DECIMAL(15, 4) NOT NULL,
    distance_pct DECIMAL(8, 4) NOT NULL,
    stop_method VARCHAR(50) NOT NULL,
    stop_reasoning TEXT,
    candidates_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_stop_loss_symbol_date
    ON algo_stop_loss_audit(symbol, signal_date DESC);
CREATE INDEX IF NOT EXISTS idx_stop_loss_created_at
    ON algo_stop_loss_audit(created_at DESC);

-- Exit rules distribution: track which exits fire most
CREATE TABLE IF NOT EXISTS algo_exit_rules_distribution (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    position_id VARCHAR(50),
    exit_rule VARCHAR(50) NOT NULL,
    exit_reason TEXT,
    entry_price DECIMAL(15, 4),
    exit_price DECIMAL(15, 4),
    pnl_dollars DECIMAL(15, 2),
    pnl_pct DECIMAL(8, 2),
    r_multiple DECIMAL(8, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_exit_rules_created_at
    ON algo_exit_rules_distribution(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_exit_rules_exit_rule
    ON algo_exit_rules_distribution(exit_rule, created_at DESC);

-- ════════════════════════════════════════════════════════════════════════════
-- FOREIGN KEY CONSTRAINTS FOR DATA INTEGRITY
-- ════════════════════════════════════════════════════════════════════════════

-- Add foreign key: algo_trades.symbol → stock_symbols.symbol
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_algo_trades_symbol' 
        AND table_name = 'algo_trades'
    ) THEN
        ALTER TABLE algo_trades
        ADD CONSTRAINT fk_algo_trades_symbol
        FOREIGN KEY (symbol) REFERENCES stock_symbols(symbol)
        ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
END $$;

-- Add foreign key: algo_positions.symbol → stock_symbols.symbol
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_algo_positions_symbol' 
        AND table_name = 'algo_positions'
    ) THEN
        ALTER TABLE algo_positions
        ADD CONSTRAINT fk_algo_positions_symbol
        FOREIGN KEY (symbol) REFERENCES stock_symbols(symbol)
        ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
END $$;

-- price_daily, technical_data_daily, buy_sell_daily intentionally contain
-- ETF and index symbols (^GSPC, SPY, etc.) that are NOT in stock_symbols.
-- FK constraints on these tables would break market-health and ETF price loaders.
-- Drop any previously-added FKs on these tables (idempotent - no-op if missing).
ALTER TABLE buy_sell_daily DROP CONSTRAINT IF EXISTS fk_buy_sell_daily_symbol;
ALTER TABLE technical_data_daily DROP CONSTRAINT IF EXISTS fk_technical_data_daily_symbol;
ALTER TABLE price_daily DROP CONSTRAINT IF EXISTS fk_price_daily_symbol;

-- Add foreign key: earnings_estimates.symbol → stock_symbols.symbol
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_earnings_estimates_symbol'
        AND table_name = 'earnings_estimates'
    ) THEN
        ALTER TABLE earnings_estimates
        ADD CONSTRAINT fk_earnings_estimates_symbol
        FOREIGN KEY (symbol) REFERENCES stock_symbols(symbol)
        ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
END $$;

-- ════════════════════════════════════════════════════════════════════════════
-- RUNTIME CONFIGURATION & AUDIT (Issue #20)
-- ════════════════════════════════════════════════════════════════════════════
-- ════════════════════════════════════════════════════════════════════════════
-- SCHEMA EVOLUTION: Add columns missing from production database
-- (CREATE TABLE IF NOT EXISTS does not add new columns to existing tables)
-- ════════════════════════════════════════════════════════════════════════════

-- technical_data_daily: indicator columns added 2026-05-30
ALTER TABLE technical_data_daily ADD COLUMN IF NOT EXISTS rsi_14 DECIMAL(8, 4);
ALTER TABLE technical_data_daily ADD COLUMN IF NOT EXISTS macd_histogram DECIMAL(12, 4);
ALTER TABLE technical_data_daily ADD COLUMN IF NOT EXISTS sma_150 DECIMAL(12, 4);
ALTER TABLE technical_data_daily ADD COLUMN IF NOT EXISTS atr_14 DECIMAL(12, 4);
ALTER TABLE technical_data_daily ADD COLUMN IF NOT EXISTS bb_upper DECIMAL(12, 4);
ALTER TABLE technical_data_daily ADD COLUMN IF NOT EXISTS bb_middle DECIMAL(12, 4);
ALTER TABLE technical_data_daily ADD COLUMN IF NOT EXISTS bb_lower DECIMAL(12, 4);
ALTER TABLE technical_data_daily ADD COLUMN IF NOT EXISTS volume_ma_50 BIGINT;

-- company_profile: add market_cap so routes can use it instead of unpopulated key_metrics
ALTER TABLE company_profile ADD COLUMN IF NOT EXISTS market_cap BIGINT;

-- economic_calendar: live table may have been created from an older schema with
-- different column names. Add all required columns idempotently.
ALTER TABLE economic_calendar ADD COLUMN IF NOT EXISTS event_id VARCHAR(100);
ALTER TABLE economic_calendar ADD COLUMN IF NOT EXISTS event_date DATE;
ALTER TABLE economic_calendar ADD COLUMN IF NOT EXISTS event_time TIME;
ALTER TABLE economic_calendar ADD COLUMN IF NOT EXISTS event_name VARCHAR(255);
ALTER TABLE economic_calendar ADD COLUMN IF NOT EXISTS category VARCHAR(100);
ALTER TABLE economic_calendar ADD COLUMN IF NOT EXISTS country VARCHAR(50) DEFAULT 'US';
ALTER TABLE economic_calendar ADD COLUMN IF NOT EXISTS importance VARCHAR(20);
ALTER TABLE economic_calendar ADD COLUMN IF NOT EXISTS forecast_value DECIMAL(12, 4);
ALTER TABLE economic_calendar ADD COLUMN IF NOT EXISTS actual_value DECIMAL(12, 4);
ALTER TABLE economic_calendar ADD COLUMN IF NOT EXISTS previous_value DECIMAL(12, 4);
ALTER TABLE economic_calendar ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
-- UNIQUE index required for ON CONFLICT (event_id, event_date) in load_economic_calendar.py
-- DROP first in case it was created without event_date being populated
DROP INDEX IF EXISTS idx_economic_calendar_event;
CREATE UNIQUE INDEX IF NOT EXISTS idx_economic_calendar_event ON economic_calendar(event_id, event_date);

-- value_metrics: add updated_at so OptimalLoader watermark works (watermark_field = "updated_at")
ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- quality_metrics, growth_metrics, stability_metrics, positioning_metrics:
-- add updated_at for watermark consistency across metric tables
ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE stability_metrics ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE positioning_metrics ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Note: INSERT/UPDATE requires dedicated service role with audit logging

-- ============================================================
-- Seed algo_config defaults (idempotent, ON CONFLICT DO NOTHING)
-- Mirrors AlgoConfig._DEFAULTS in algo/algo_config.py
-- ============================================================
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('base_risk_pct', '0.75', 'float', 'Base portfolio risk per trade', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('max_position_size_pct', '8.0', 'float', 'Maximum single position size', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('max_positions', '12', 'int', 'Maximum concurrent positions', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('max_concentration_pct', '50.0', 'float', 'Max concentration in top position', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('halt_drawdown_pct', '20.0', 'float', 'Portfolio drawdown pct to halt trading', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('risk_reduction_at_minus_5', '0.75', 'float', 'Risk pct at -5 pct drawdown', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('risk_reduction_at_minus_10', '0.5', 'float', 'Risk pct at -10 pct drawdown', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('risk_reduction_at_minus_15', '0.25', 'float', 'Risk pct at -15 pct drawdown', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('risk_reduction_at_minus_20', '0.0', 'float', 'Risk pct at -20 pct drawdown halt', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('min_completeness_score', '70', 'int', 'Minimum data completeness pct', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('min_stock_price', '5.0', 'float', 'Minimum stock price dollars', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('min_signal_quality_score', '60', 'int', 'Minimum SQS 0-100', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('min_volume_ma_50d', '300000', 'int', 'Minimum 50-day avg volume', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('min_avg_daily_dollar_volume', '500000', 'float', 'Minimum daily dollar volume', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('require_stock_stage_2', 'true', 'bool', 'Require Stage 2 trend template', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('max_stop_distance_pct', '12.0', 'float', 'Max stop distance pct from entry', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('max_positions_per_sector', '5', 'int', 'Max concurrent positions in one sector', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('max_positions_per_industry', '3', 'int', 'Max concurrent positions in one industry', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('min_swing_score', '55.0', 'float', 'Min swing trader score to enter', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('min_swing_grade', '', 'string', 'Min swing grade override', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('max_total_invested_pct', '95.0', 'float', 'Max pct of portfolio in open positions', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('max_distribution_days', '4', 'int', 'Max market distribution days', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('require_stage_2_market', 'false', 'bool', 'Require market Stage 2 at Tier 2', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('vix_max_threshold', '35.0', 'float', 'VIX level to halt trading', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('vix_caution_threshold', '25.0', 'float', 'VIX level to reduce positions', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('vix_caution_risk_reduction', '0.75', 'float', 'Risk multiplier when VIX caution', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('require_sma50_above_sma200', 'true', 'bool', 'Price and MA alignment', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('min_percent_from_52w_low', '30.0', 'float', 'Min pct from 52w low', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('max_percent_from_52w_high', '25.0', 'float', 'Max pct from 52w high', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('min_trend_template_score', '6', 'int', 'Min Minervini score 0-8', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('max_signal_age_days', '3', 'int', 'Reject BUY signals older than N days', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('min_close_quality_pct', '60.0', 'float', 'Close must be in upper N pct of range', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('min_breakout_volume_ratio', '1.25', 'float', 'Volume must be N x 50-day average', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('require_weekly_stage_2', 'true', 'bool', 'Require weekly chart Stage 2', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('min_rs_line_slope_days', '10', 'int', 'Days for RS line slope check', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('max_rs_pct_from_60d_high', '15.0', 'float', 'Max pct RS-line below 60d high', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('rs_slope_gate_enabled', 'false', 'bool', 'Hard-gate T3 on RS line trending up', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('volume_decay_gate_enabled', 'false', 'bool', 'Hard-gate T3 on volume decay into breakout', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('require_target_pullback', 'false', 'bool', 'Require pullback before partial profit exits', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('t1_target_r_multiple', '1.5', 'float', 'Tier 1 profit target R-mult', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('t2_target_r_multiple', '3.0', 'float', 'Tier 2 profit target R-mult', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('t3_target_r_multiple', '4.0', 'float', 'Tier 3 profit target R-mult', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('imported_position_default_stop_loss_pct', '5.0', 'float', 'Default stop loss pct for imported positions', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('imported_position_default_target_1_pct', '5.0', 'float', 'Default target 1 pct for imported positions', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('imported_position_default_target_2_pct', '10.0', 'float', 'Default target 2 pct for imported positions', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('imported_position_default_target_3_pct', '15.0', 'float', 'Default target 3 pct for imported positions', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('min_hold_days', '1', 'int', 'Minimum days to hold', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('max_hold_days', '20', 'int', 'Max days to hold position', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('exit_on_distribution_day', 'true', 'bool', 'Exit on market distribution', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('exit_on_rs_line_break_50dma', 'true', 'bool', 'Exit when RS line breaks 50-DMA', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('exit_on_td_sequential', 'true', 'bool', 'Exit on TD Sequential exhaustion', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('use_chandelier_trail', 'true', 'bool', 'Use chandelier ATR trailing stop', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('switch_to_21ema_after_days', '10', 'int', 'Days before switching chandelier to 21-EMA', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('eight_week_rule_threshold_pct', '20.0', 'float', 'ONeill 8-week hold threshold pct', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('eight_week_rule_window_days', '21', 'int', 'Days to check for 20pct plus gain', 'schema-seed') ON CONFLICT (key) DO NOTHING;

-- ISSUES #8-23 Configuration: Data Freshness, Completeness, and Pipeline Coordination
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('phase1_coverage_min_pct', '75', 'int', 'Min symbol coverage % for halt (Issue #8)', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('phase1_coverage_optimal_pct', '95', 'int', 'Optimal symbol coverage % for data quality (Issue #2)', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('phase1_halt_stale_days_threshold', '2', 'int', 'Days before data considered stale for halt (Issue #10)', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('data_loader_status_cache_ttl_sec', '60', 'int', 'Cache TTL for data_loader_status in seconds (Issue #22)', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('failsafe_grace_period_minutes', '150', 'int', 'Grace period for failsafe loader completion in minutes (Issue #4)', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('failsafe_trigger_poll_timeout_sec', '150', 'int', 'Timeout for failsafe task launch verification (Issue #13)', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('heartbeat_hung_timeout_minutes', '3', 'int', 'Minutes of stale heartbeat to detect hung loader (Issue #3)', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('circuit_breaker_threshold_eod_sec', '180', 'int', 'Circuit breaker timeout for EOD pipeline in seconds (Issue #20)', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('circuit_breaker_threshold_morning_sec', '480', 'int', 'Circuit breaker timeout for morning pipeline in seconds (Issue #20)', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('data_age_max_days', '2', 'int', 'Max age of source data before filtering in Phase 5 (Issue #15)', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('hung_task_cleanup_enabled', 'true', 'bool', 'Enable explicit cleanup of hung ECS tasks (Issue #23)', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('pipeline_overlap_warning_enabled', 'true', 'bool', 'Warn if morning/EOD pipelines overlap (Issue #11)', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('signal_quality_scores_required_morning_prep', 'false', 'bool', 'Require signal_quality_scores in morning pipeline (Issue #17)', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_low_volume_threshold', '100000', 'int', 'Min volume for data patrol (Issue #16)', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_price_minimum_dollars', '1.0', 'float', 'Min price for patrol validation (Issue #16)', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('chandelier_atr_mult', '3.0', 'float', 'ATR multiplier for chandelier stop', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('move_be_at_r', '1.0', 'float', 'R-multiple to trigger breakeven stop raise', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('pyramid_enabled', 'true', 'bool', 'Enable multi-entry pyramiding', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('pyramid_split_pct', '50,33,17', 'string', 'Entry size split pct', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('pyramid_add_1_gain_pct', '2.0', 'float', 'Gain pct to trigger Add 1', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('pyramid_add_2_gain_pct', '3.0', 'float', 'Additional gain pct to trigger Add 2', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('re_engage_recovery_pct', '8.0', 'float', 'Pct recovery from peak to resume trading', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('re_engage_min_days', '5', 'int', 'Min days after halt before re-engagement', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('require_ftd_to_re_engage', 'true', 'bool', 'Require Follow-Through Day signal', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('max_daily_loss_pct', '2.0', 'float', 'Max daily loss pct before halt', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('max_consecutive_losses', '3', 'int', 'Max consecutive losing trades', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('min_win_rate_pct', '40.0', 'float', 'Min win rate pct to trade', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('max_total_risk_pct', '4.0', 'float', 'Max total open risk pct', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('max_weekly_loss_pct', '5.0', 'float', 'Max weekly loss pct before halt', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('max_data_staleness_days', '3', 'int', 'Max data age in days', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('daily_profit_cap_pct', '2.0', 'float', 'Daily profit cap pct', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('sector_drawdown_halt_pct', '-12.0', 'float', 'Sector drawdown pct to halt trading', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('position_halt_flag_count', '2', 'int', 'Flags to propose early exit', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('max_reentries_per_name', '2', 'int', 'Max times to re-enter same symbol', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('min_days_before_reentry_same_symbol', '5', 'int', 'Days to wait before re-entering symbol', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('halt_entries_before_major_release_minutes', '60', 'int', 'Halt entries N minutes before major release', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('earnings_blackout_days_before', '7', 'int', 'Days before earnings to block entries', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('earnings_blackout_days_after', '3', 'int', 'Days after earnings to block entries', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('min_price_history_days', '200', 'int', 'Min trading days of price history', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('min_daily_volume_shares', '500000', 'int', 'Minimum daily volume shares', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('max_spread_pct', '0.5', 'float', 'Maximum bid-ask spread pct', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('min_market_cap_millions', '300.0', 'float', 'Minimum market cap millions', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('min_float_millions', '50.0', 'float', 'Minimum float shares millions', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('max_short_interest_pct', '30.0', 'float', 'Maximum short interest pct', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('block_days_before_earnings', '5', 'int', 'Block entries N days before earnings', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('max_extension_above_50ma_pct', '15.0', 'float', 'Max extension above 50-DMA pct', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('strong_sector_top_n', '5', 'int', 'Top N sectors count as strong', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('swing_weight_setup', '25', 'int', 'Swing score setup quality weight pct', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('swing_weight_trend', '20', 'int', 'Swing score trend quality weight pct', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('swing_weight_momentum', '20', 'int', 'Swing score momentum RS weight pct', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('swing_weight_volume', '12', 'int', 'Swing score volume weight pct', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('swing_weight_fundamentals', '10', 'int', 'Swing score fundamentals weight pct', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('swing_weight_sector', '8', 'int', 'Swing score sector industry weight pct', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('swing_weight_multi_timeframe', '5', 'int', 'Swing score multi-timeframe weight pct', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('swing_min_trend_score', '5', 'int', 'Swing score minimum Minervini trend score 0-8', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('swing_min_industry_rank', '100', 'int', 'Swing score industry rank threshold', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('swing_days_to_earnings_block', '5', 'int', 'Swing score block entries N days to earnings', 'schema-seed') ON CONFLICT (key) DO NOTHING;

-- Data patrol thresholds (configurable at runtime via algo_config)
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_staleness_price_daily', '7', 'int', 'Max days for price_daily staleness', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_staleness_technical_daily', '7', 'int', 'Max days for technical_data_daily staleness', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_staleness_buy_sell_daily', '7', 'int', 'Max days for buy_sell_daily staleness', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_staleness_signal_quality_scores', '7', 'int', 'Max days for signal_quality_scores staleness', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_staleness_stock_scores', '14', 'int', 'Max days for stock_scores staleness', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_staleness_earnings_history', '120', 'int', 'Max days for earnings_history staleness', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_min_universe_pct', '75', 'int', 'Minimum universe coverage pct', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_min_coverage_ratio', '0.75', 'float', 'Minimum coverage ratio for data patrol', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_max_daily_move_pct', '50', 'int', 'Max daily move pct for sanity check', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_max_daily_move_count', '10', 'int', 'Max count of extreme daily moves', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_low_volume_threshold', '1000000', 'int', 'Low volume threshold shares', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_high_volume_threshold', '100000000', 'int', 'High volume threshold shares', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_new_low_volume_alert', '50', 'int', 'Count of new low volume items to alert', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_price_daily_14d_min', '40000', 'int', 'Min 14d price_daily rows for patrol', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_buy_sell_daily_14d_min', '800', 'int', 'Min 14d buy_sell_daily rows for patrol', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_coverage_ratio_min', '0.80', 'float', 'Min coverage ratio for patrol', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('failsafe_grace_period_minutes', '150', 'int', 'Grace period for data failsafe trigger minutes', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('signal_max_data_age_days', '2', 'int', 'Max data age for signal generation days', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('execution_mode', 'auto', 'string', 'paper or dry or review or auto', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('alpaca_paper_trading', 'false', 'bool', 'Use Alpaca paper account', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('max_trades_per_day', '5', 'int', 'Max new trades per day', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('default_portfolio_value', '100000.0', 'float', 'Bootstrap portfolio value when Alpaca unreachable', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('enable_algo', 'true', 'bool', 'Enable algo trading', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('enable_backtesting', 'false', 'bool', 'Enable backtest mode', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('verbose_logging', 'true', 'bool', 'Detailed logging', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('api_request_timeout_seconds', '5', 'int', 'HTTP request timeout seconds', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('db_connection_timeout_seconds', '15', 'int', 'Database connection timeout seconds', 'schema-seed') ON CONFLICT (key) DO NOTHING;

-- Data Patrol Configuration (parameterized thresholds - Issue 9)
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_staleness_price_daily', '7', 'int', 'Max days stale for price_daily before CRIT alert', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_staleness_technical_daily', '7', 'int', 'Max days stale for technical_data_daily before CRIT alert', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_staleness_buy_sell_daily', '7', 'int', 'Max days stale for buy_sell_daily before CRIT alert', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_staleness_signal_quality_scores', '7', 'int', 'Max days stale for signal_quality_scores before WARN alert', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_staleness_trend_data', '7', 'int', 'Max days stale for trend_template_data before CRIT alert', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_staleness_market_health', '7', 'int', 'Max days stale for market_health_daily before ERROR alert', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_staleness_sector_ranking', '10', 'int', 'Max days stale for sector_ranking before WARN alert', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_staleness_industry_ranking', '10', 'int', 'Max days stale for industry_ranking before WARN alert', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_staleness_insider_transactions', '14', 'int', 'Max days stale for insider_transactions before INFO alert', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_staleness_analyst_upgrades', '14', 'int', 'Max days stale for analyst_upgrade_downgrade before INFO alert', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_staleness_stock_scores', '14', 'int', 'Max days stale for stock_scores before WARN alert', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_staleness_aaii_sentiment', '14', 'int', 'Max days stale for aaii_sentiment before INFO alert', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_staleness_growth_metrics', '45', 'int', 'Max days stale for growth_metrics before INFO alert', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_staleness_earnings_history', '120', 'int', 'Max days stale for earnings_history before INFO alert', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_max_null_pct_threshold', '5', 'int', 'Max NULL % in price data before ERROR alert', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_new_zero_symbols_error', '30', 'int', 'New zero-volume symbols threshold for ERROR alert', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_new_zero_symbols_warn', '5', 'int', 'New zero-volume symbols threshold for WARN alert', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_identical_ohlc_threshold', '30', 'int', 'Identical OHLC count threshold for WARN alert', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_low_volume_threshold', '1000000', 'int', 'Low volume threshold (volume < this)', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_high_volume_threshold', '100000000', 'int', 'High volume threshold (volume > this)', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('patrol_new_low_volume_alert', '50', 'int', 'New low-volume symbols threshold for WARN alert', 'schema-seed') ON CONFLICT (key) DO NOTHING;

-- Phase 1 Freshness Configuration (parameterized halt thresholds - Issue #1)
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('phase1_halt_stale_days_threshold', '2', 'int', 'Days stale for HALT if failsafe fails (default 2 trading days)', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('failsafe_grace_period_minutes', '150', 'int', 'Grace period for async failsafe loader (default 150 min)', 'schema-seed') ON CONFLICT (key) DO NOTHING;
INSERT INTO algo_config (key, value, value_type, description, updated_by) VALUES ('phase1_coverage_min_pct', '75', 'int', 'Min symbol coverage % for data tables (Issue #9)', 'schema-seed') ON CONFLICT (key) DO NOTHING;
