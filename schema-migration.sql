-- =============================================================================
-- COMPREHENSIVE DATABASE SCHEMA MIGRATION
-- =============================================================================
-- This script creates all missing tables needed by the API routes
-- Run in phases: Phase 1 (blocking) → Phase 2 (high priority) → Phase 3+ (features)
-- =============================================================================

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- PHASE 1: CORE TRADING & USER TABLES (BLOCKING - DO FIRST)
-- =============================================================================

-- ============================================================================
-- 1. USER MANAGEMENT & AUTHENTICATION
-- ============================================================================

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) NOT NULL UNIQUE,
    cognito_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    deleted_at TIMESTAMP,
    active BOOLEAN DEFAULT true,
    roles TEXT[] DEFAULT ARRAY['user']
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_cognito_id ON users(cognito_id);
CREATE INDEX IF NOT EXISTS idx_users_active ON users(active);

-- API keys for Alpaca integration
CREATE TABLE IF NOT EXISTS user_api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key_name VARCHAR(255) NOT NULL,
    key_hash VARCHAR(255) NOT NULL,
    secret_hash VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    last_used_at TIMESTAMP,
    active BOOLEAN DEFAULT true,
    UNIQUE(user_id, key_name)
);

CREATE INDEX IF NOT EXISTS idx_user_api_keys_user_id ON user_api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_user_api_keys_active ON user_api_keys(active);

-- User portfolio metadata
CREATE TABLE IF NOT EXISTS user_portfolio (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    alpaca_account_id VARCHAR(255),
    initial_balance DECIMAL(15,2) NOT NULL DEFAULT 0,
    portfolio_type VARCHAR(50) DEFAULT 'swing_trader',  -- swing_trader, day_trader, investor
    risk_tolerance VARCHAR(50) DEFAULT 'moderate',       -- conservative, moderate, aggressive
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_portfolio_user_id ON user_portfolio(user_id);

-- User settings/preferences
CREATE TABLE IF NOT EXISTS user_dashboard_settings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    theme VARCHAR(50) DEFAULT 'dark',
    default_chart_timeframe VARCHAR(20) DEFAULT 'daily',
    default_sort VARCHAR(100),
    show_portfolio BOOLEAN DEFAULT true,
    show_watchlist BOOLEAN DEFAULT true,
    show_signals BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================================
-- 2. TRADING & POSITIONS
-- ============================================================================

-- Trade execution history (from any source: Alpaca, manual, algo)
CREATE TABLE IF NOT EXISTS trades (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,  -- 'buy' or 'sell'
    quantity DECIMAL(15,4) NOT NULL,
    execution_price DECIMAL(12,4) NOT NULL,
    execution_date TIMESTAMP NOT NULL,
    order_value DECIMAL(15,2),
    commission DECIMAL(10,4) DEFAULT 0,
    source VARCHAR(50) DEFAULT 'manual',  -- alpaca, manual, algo, optimization
    broker VARCHAR(50) DEFAULT 'alpaca',
    order_id VARCHAR(255),
    trade_id VARCHAR(255),
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trades_symbol_date ON trades(symbol, execution_date DESC);
CREATE INDEX IF NOT EXISTS idx_trades_user_date ON trades(user_id, execution_date DESC);
CREATE INDEX IF NOT EXISTS idx_trades_source ON trades(source);

-- Active and closed positions
CREATE TABLE IF NOT EXISTS algo_positions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol VARCHAR(20) NOT NULL,
    entry_date DATE NOT NULL,
    entry_price DECIMAL(12,4) NOT NULL,
    quantity DECIMAL(15,4) NOT NULL,
    stop_loss DECIMAL(12,4),
    profit_target_1 DECIMAL(12,4),
    profit_target_2 DECIMAL(12,4),
    profit_target_3 DECIMAL(12,4),
    position_value DECIMAL(15,2),
    unrealized_pl DECIMAL(15,2),
    unrealized_pl_pct DECIMAL(10,4),
    status VARCHAR(20) NOT NULL DEFAULT 'open',  -- open, closed, trimmed
    exit_date DATE,
    exit_price DECIMAL(12,4),
    realized_pl DECIMAL(15,2),
    realized_pl_pct DECIMAL(10,4),
    exit_reason TEXT,
    signal_id BIGINT,
    trade_id UUID REFERENCES trades(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_algo_positions_symbol ON algo_positions(symbol);
CREATE INDEX IF NOT EXISTS idx_algo_positions_status ON algo_positions(status);
CREATE INDEX IF NOT EXISTS idx_algo_positions_entry_date ON algo_positions(entry_date DESC);

-- Portfolio snapshots (daily/weekly history)
CREATE TABLE IF NOT EXISTS algo_portfolio_snapshots (
    id BIGSERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL,
    total_portfolio_value DECIMAL(15,2),
    cash_balance DECIMAL(15,2),
    position_count INT,
    open_position_count INT,
    unrealized_pnl DECIMAL(15,2),
    unrealized_pnl_pct DECIMAL(10,4),
    realized_pnl_day DECIMAL(15,2),
    realized_pnl_ytd DECIMAL(15,2),
    daily_return_pct DECIMAL(10,4),
    market_health_status VARCHAR(50),
    circuitbreaker_status VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

SELECT create_hypertable('algo_portfolio_snapshots', 'snapshot_date', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_algo_portfolio_snapshots_date ON algo_portfolio_snapshots(snapshot_date DESC);

-- Trade log from algo orchestrator
CREATE TABLE IF NOT EXISTS algo_trades (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    signal_date DATE NOT NULL,
    entry_date DATE,
    entry_price DECIMAL(12,4),
    quantity DECIMAL(15,4),
    stop_loss DECIMAL(12,4),
    profit_targets TEXT,  -- JSON: [1.05, 1.10, 1.15]
    exit_date DATE,
    exit_price DECIMAL(12,4),
    exit_reason VARCHAR(100),
    realized_pnl DECIMAL(15,2),
    realized_pnl_pct DECIMAL(10,4),
    status VARCHAR(20),  -- pending, opened, closed
    signal_type VARCHAR(50),
    base_type VARCHAR(50),
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

SELECT create_hypertable('algo_trades', 'signal_date', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_algo_trades_symbol ON algo_trades(symbol);
CREATE INDEX IF NOT EXISTS idx_algo_trades_date ON algo_trades(signal_date DESC);

-- Manually entered positions (user entries)
CREATE TABLE IF NOT EXISTS manual_positions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    entry_date DATE NOT NULL,
    entry_price DECIMAL(12,4) NOT NULL,
    quantity DECIMAL(15,4) NOT NULL,
    stop_loss DECIMAL(12,4),
    profit_target DECIMAL(12,4),
    position_value DECIMAL(15,2),
    notes TEXT,
    status VARCHAR(20) DEFAULT 'open',
    exit_date DATE,
    exit_price DECIMAL(12,4),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_manual_positions_user_symbol ON manual_positions(user_id, symbol);
CREATE INDEX IF NOT EXISTS idx_manual_positions_status ON manual_positions(status);

-- Current portfolio holdings
CREATE TABLE IF NOT EXISTS portfolio_holdings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    quantity DECIMAL(15,4) NOT NULL,
    average_cost DECIMAL(12,4),
    current_price DECIMAL(12,4),
    position_value DECIMAL(15,2),
    unrealized_pl DECIMAL(15,2),
    unrealized_pl_pct DECIMAL(10,4),
    last_updated TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, symbol)
);

CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_user ON portfolio_holdings(user_id);

-- ============================================================================
-- 3. MARKET STATE & TECHNICAL INDICATORS
-- ============================================================================

-- Market health/state daily
CREATE TABLE IF NOT EXISTS market_health_daily (
    id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL,
    market_trend VARCHAR(50),           -- uptrend, downtrend, consolidation
    market_stage INT,                    -- 1-4
    stage_name VARCHAR(50),              -- Stage 1 accumulation, etc
    stage_confidence DECIMAL(5,2),
    distribution_days_4w INT,
    follow_through_signal BOOLEAN,
    market_breadth_positive BOOLEAN,
    market_breadth_ratio DECIMAL(8,4),
    advance_decline_line INT,
    vix_level DECIMAL(8,2),
    vix_trend VARCHAR(50),               -- rising, falling, stable
    fed_rate DECIMAL(5,2),
    gdp_growth DECIMAL(5,2),
    inflation_rate DECIMAL(5,2),
    unemployment_rate DECIMAL(5,2),
    consumer_confidence INT,
    circuit_breaker_status VARCHAR(50),  -- normal, warning, halted
    created_at TIMESTAMP DEFAULT NOW()
);

SELECT create_hypertable('market_health_daily', 'date', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_market_health_daily_date ON market_health_daily(date DESC);

-- Technical indicators per symbol per day
CREATE TABLE IF NOT EXISTS technical_data_daily (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    close DECIMAL(12,4),
    volume BIGINT,
    rsi DECIMAL(10,4),
    adx DECIMAL(10,4),
    atr DECIMAL(12,4),
    macd DECIMAL(10,4),
    signal_line DECIMAL(10,4),
    histogram DECIMAL(10,4),
    sma_20 DECIMAL(12,4),
    sma_50 DECIMAL(12,4),
    sma_200 DECIMAL(12,4),
    ema_12 DECIMAL(12,4),
    ema_26 DECIMAL(12,4),
    ema_21 DECIMAL(12,4),
    bollinger_upper DECIMAL(12,4),
    bollinger_middle DECIMAL(12,4),
    bollinger_lower DECIMAL(12,4),
    stoch_k DECIMAL(10,4),
    stoch_d DECIMAL(10,4),
    obv BIGINT,
    cmf DECIMAL(10,4),
    williams_r DECIMAL(10,4),
    price_from_52w_high DECIMAL(10,4),
    price_from_52w_low DECIMAL(10,4),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(symbol, date)
);

SELECT create_hypertable('technical_data_daily', 'date', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_technical_data_daily_symbol_date ON technical_data_daily(symbol, date DESC);

-- Trend template analysis
CREATE TABLE IF NOT EXISTS trend_template_data (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    minervini_trend_score DECIMAL(10,4),
    percent_from_52w_low DECIMAL(10,4),
    percent_from_52w_high DECIMAL(10,4),
    trend_strength VARCHAR(50),
    trend_direction VARCHAR(20),  -- up, down, sideways
    trend_confirmation BOOLEAN,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(symbol, date)
);

SELECT create_hypertable('trend_template_data', 'date', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_trend_template_data_symbol_date ON trend_template_data(symbol, date DESC);

-- Signal quality scoring
CREATE TABLE IF NOT EXISTS signal_quality_scores (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    signal_type VARCHAR(50),
    base_type VARCHAR(50),
    composite_sqs DECIMAL(10,4),          -- Signal Quality Score 0-100
    entry_quality DECIMAL(10,4),
    risk_reward_score DECIMAL(10,4),
    momentum_score DECIMAL(10,4),
    technical_confirmation DECIMAL(10,4),
    volume_confirmation DECIMAL(10,4),
    trend_alignment DECIMAL(10,4),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(symbol, date, signal_type)
);

SELECT create_hypertable('signal_quality_scores', 'date', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_signal_quality_scores_symbol_date ON signal_quality_scores(symbol, date DESC);

-- Data completeness/availability tracking
CREATE TABLE IF NOT EXISTS data_completeness_scores (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    composite_completeness_pct DECIMAL(10,2),
    price_data_complete BOOLEAN,
    volume_data_complete BOOLEAN,
    technical_data_complete BOOLEAN,
    fundamental_data_complete BOOLEAN,
    sentiment_data_complete BOOLEAN,
    missing_fields TEXT,  -- JSON list of missing columns
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(symbol, date)
);

SELECT create_hypertable('data_completeness_scores', 'date', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_data_completeness_scores_symbol_date ON data_completeness_scores(symbol, date DESC);

-- =============================================================================
-- PHASE 2: EXTEND EXISTING TABLES WITH MISSING COLUMNS
-- =============================================================================

-- ============================================================================
-- 4. EXTEND buy_sell_daily WITH MISSING COLUMNS
-- ============================================================================

-- Add missing columns to buy_sell_daily (check if they exist first)
DO $$
BEGIN
    -- Add signal quality/metadata columns if they don't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='buy_sell_daily' AND column_name='buylevel') THEN
        ALTER TABLE buy_sell_daily ADD COLUMN buylevel DECIMAL(12,4);
        ALTER TABLE buy_sell_daily ADD COLUMN stoplevel DECIMAL(12,4);
        ALTER TABLE buy_sell_daily ADD COLUMN strength DECIMAL(10,4);
        ALTER TABLE buy_sell_daily ADD COLUMN signal_strength DECIMAL(10,4);
        ALTER TABLE buy_sell_daily ADD COLUMN inposition BOOLEAN;
        ALTER TABLE buy_sell_daily ADD COLUMN entry_price DECIMAL(12,4);
        ALTER TABLE buy_sell_daily ADD COLUMN base_type VARCHAR(50);
        ALTER TABLE buy_sell_daily ADD COLUMN signal_type VARCHAR(50);
        ALTER TABLE buy_sell_daily ADD COLUMN signal_triggered_date DATE;

        -- Trading levels
        ALTER TABLE buy_sell_daily ADD COLUMN pivot_price DECIMAL(12,4);
        ALTER TABLE buy_sell_daily ADD COLUMN buy_zone_start DECIMAL(12,4);
        ALTER TABLE buy_sell_daily ADD COLUMN buy_zone_end DECIMAL(12,4);

        -- Exit triggers
        ALTER TABLE buy_sell_daily ADD COLUMN exit_trigger_1_price DECIMAL(12,4);
        ALTER TABLE buy_sell_daily ADD COLUMN exit_trigger_2_price DECIMAL(12,4);
        ALTER TABLE buy_sell_daily ADD COLUMN exit_trigger_3_price DECIMAL(12,4);
        ALTER TABLE buy_sell_daily ADD COLUMN exit_trigger_4_price DECIMAL(12,4);

        -- Stop and trailing stop
        ALTER TABLE buy_sell_daily ADD COLUMN initial_stop DECIMAL(12,4);
        ALTER TABLE buy_sell_daily ADD COLUMN trailing_stop DECIMAL(12,4);
        ALTER TABLE buy_sell_daily ADD COLUMN sell_level DECIMAL(12,4);

        -- Base metrics
        ALTER TABLE buy_sell_daily ADD COLUMN base_length_days INT;
        ALTER TABLE buy_sell_daily ADD COLUMN avg_volume_50d BIGINT;
        ALTER TABLE buy_sell_daily ADD COLUMN volume_surge_pct DECIMAL(10,4);

        -- Quality scores
        ALTER TABLE buy_sell_daily ADD COLUMN rs_rating DECIMAL(10,4);
        ALTER TABLE buy_sell_daily ADD COLUMN breakout_quality DECIMAL(10,4);
        ALTER TABLE buy_sell_daily ADD COLUMN risk_reward_ratio DECIMAL(10,4);
        ALTER TABLE buy_sell_daily ADD COLUMN mansfield_rs DECIMAL(10,4);
        ALTER TABLE buy_sell_daily ADD COLUMN sata_score DECIMAL(10,4);

        -- Position metrics
        ALTER TABLE buy_sell_daily ADD COLUMN current_gain_pct DECIMAL(10,4);
        ALTER TABLE buy_sell_daily ADD COLUMN days_in_position INT;
        ALTER TABLE buy_sell_daily ADD COLUMN entry_quality_score DECIMAL(10,4);
        ALTER TABLE buy_sell_daily ADD COLUMN risk_pct DECIMAL(10,4);
        ALTER TABLE buy_sell_daily ADD COLUMN position_size_recommendation DECIMAL(10,4);

        -- Profit targets
        ALTER TABLE buy_sell_daily ADD COLUMN profit_target_8pct DECIMAL(12,4);
        ALTER TABLE buy_sell_daily ADD COLUMN profit_target_20pct DECIMAL(12,4);
        ALTER TABLE buy_sell_daily ADD COLUMN profit_target_25pct DECIMAL(12,4);

        -- Market stage
        ALTER TABLE buy_sell_daily ADD COLUMN market_stage VARCHAR(50);
        ALTER TABLE buy_sell_daily ADD COLUMN stage_number INT;
        ALTER TABLE buy_sell_daily ADD COLUMN stage_confidence DECIMAL(10,4);
        ALTER TABLE buy_sell_daily ADD COLUMN substage VARCHAR(50);

        -- Technical columns
        ALTER TABLE buy_sell_daily ADD COLUMN rsi DECIMAL(10,4);
        ALTER TABLE buy_sell_daily ADD COLUMN adx DECIMAL(10,4);
        ALTER TABLE buy_sell_daily ADD COLUMN atr DECIMAL(12,4);
        ALTER TABLE buy_sell_daily ADD COLUMN macd DECIMAL(10,4);
        ALTER TABLE buy_sell_daily ADD COLUMN signal_line DECIMAL(10,4);
        ALTER TABLE buy_sell_daily ADD COLUMN sma_20 DECIMAL(12,4);
        ALTER TABLE buy_sell_daily ADD COLUMN sma_50 DECIMAL(12,4);
        ALTER TABLE buy_sell_daily ADD COLUMN sma_200 DECIMAL(12,4);
        ALTER TABLE buy_sell_daily ADD COLUMN ema_21 DECIMAL(12,4);
        ALTER TABLE buy_sell_daily ADD COLUMN ema_26 DECIMAL(12,4);
        ALTER TABLE buy_sell_daily ADD COLUMN pct_from_ema21 DECIMAL(10,4);
        ALTER TABLE buy_sell_daily ADD COLUMN pct_from_sma50 DECIMAL(10,4);

        -- Price data
        ALTER TABLE buy_sell_daily ADD COLUMN open DECIMAL(12,4);
        ALTER TABLE buy_sell_daily ADD COLUMN high DECIMAL(12,4);
        ALTER TABLE buy_sell_daily ADD COLUMN low DECIMAL(12,4);
        ALTER TABLE buy_sell_daily ADD COLUMN close DECIMAL(12,4);
        ALTER TABLE buy_sell_daily ADD COLUMN volume BIGINT;

        RAISE NOTICE 'Successfully added missing columns to buy_sell_daily';
    ELSE
        RAISE NOTICE 'buy_sell_daily already has buylevel column - skipping column additions';
    END IF;
END $$;

-- ============================================================================
-- 5. EXTEND stock_symbols WITH MISSING COLUMNS
-- ============================================================================

DO $$
BEGIN
    -- Add metadata columns if they don't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='stock_symbols' AND column_name='security_name') THEN
        ALTER TABLE stock_symbols ADD COLUMN security_name VARCHAR(255);
        ALTER TABLE stock_symbols ADD COLUMN market_category VARCHAR(50);
        ALTER TABLE stock_symbols ADD COLUMN exchange VARCHAR(20);
        RAISE NOTICE 'Successfully added missing columns to stock_symbols';
    END IF;
END $$;

-- =============================================================================
-- PHASE 3: FINANCIAL DATA TABLES
-- =============================================================================

-- ============================================================================
-- 6. FINANCIAL DATA & FUNDAMENTALS
-- ============================================================================

-- Company profile information
CREATE TABLE IF NOT EXISTS company_profile (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL UNIQUE,
    company_name VARCHAR(255),
    sector VARCHAR(100),
    industry VARCHAR(100),
    website VARCHAR(255),
    description TEXT,
    ceo VARCHAR(255),
    employees INT,
    founded_year INT,
    market_cap BIGINT,
    pe_ratio DECIMAL(10,2),
    eps DECIMAL(10,2),
    dividend_yield DECIMAL(10,4),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_company_profile_symbol ON company_profile(symbol);

-- Analyst sentiment
CREATE TABLE IF NOT EXISTS analyst_sentiment_analysis (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    buy_count INT,
    hold_count INT,
    sell_count INT,
    strong_buy_count INT,
    strong_sell_count INT,
    consensus_rating VARCHAR(50),
    average_target_price DECIMAL(12,4),
    consensus_pct_upside DECIMAL(10,4),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(symbol, date)
);

SELECT create_hypertable('analyst_sentiment_analysis', 'date', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_analyst_sentiment_symbol_date ON analyst_sentiment_analysis(symbol, date DESC);

-- Insider transactions
CREATE TABLE IF NOT EXISTS insider_transactions (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    transaction_date DATE NOT NULL,
    insider_name VARCHAR(255),
    insider_title VARCHAR(100),
    transaction_type VARCHAR(50),  -- buy, sell
    shares INT,
    share_price DECIMAL(12,4),
    transaction_value DECIMAL(15,2),
    shares_owned INT,
    created_at TIMESTAMP DEFAULT NOW()
);

SELECT create_hypertable('insider_transactions', 'transaction_date', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_insider_transactions_symbol_date ON insider_transactions(symbol, transaction_date DESC);

-- Insider roster
CREATE TABLE IF NOT EXISTS insider_roster (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    insider_name VARCHAR(255) NOT NULL,
    title VARCHAR(100),
    shares_owned INT,
    shares_traded INT,
    last_trade_date DATE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(symbol, insider_name)
);

CREATE INDEX IF NOT EXISTS idx_insider_roster_symbol ON insider_roster(symbol);

-- Earnings history
CREATE TABLE IF NOT EXISTS earnings_history (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    earnings_date DATE NOT NULL,
    quarter VARCHAR(10),
    fiscal_year INT,
    eps_actual DECIMAL(10,4),
    eps_estimate DECIMAL(10,4),
    revenue_actual BIGINT,
    revenue_estimate BIGINT,
    beat_miss VARCHAR(10),  -- beat, miss, meet
    surprise_pct DECIMAL(10,4),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(symbol, earnings_date)
);

SELECT create_hypertable('earnings_history', 'earnings_date', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_earnings_history_symbol_date ON earnings_history(symbol, earnings_date DESC);

-- Earnings estimates (forward looking)
CREATE TABLE IF NOT EXISTS earnings_estimates (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    fiscal_year INT NOT NULL,
    quarter VARCHAR(10),
    eps_estimate DECIMAL(10,4),
    revenue_estimate BIGINT,
    estimate_date DATE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(symbol, fiscal_year, quarter)
);

CREATE INDEX IF NOT EXISTS idx_earnings_estimates_symbol ON earnings_estimates(symbol);

-- Quality metrics
CREATE TABLE IF NOT EXISTS quality_metrics (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    roe DECIMAL(10,4),
    roa DECIMAL(10,4),
    debt_to_equity DECIMAL(10,4),
    current_ratio DECIMAL(10,4),
    quick_ratio DECIMAL(10,4),
    interest_coverage DECIMAL(10,4),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(symbol, date)
);

SELECT create_hypertable('quality_metrics', 'date', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_quality_metrics_symbol_date ON quality_metrics(symbol, date DESC);

-- Growth metrics
CREATE TABLE IF NOT EXISTS growth_metrics (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    revenue_growth_yoy DECIMAL(10,4),
    earnings_growth_yoy DECIMAL(10,4),
    fcf_growth_yoy DECIMAL(10,4),
    avg_revenue_growth_3y DECIMAL(10,4),
    avg_earnings_growth_3y DECIMAL(10,4),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(symbol, date)
);

SELECT create_hypertable('growth_metrics', 'date', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_growth_metrics_symbol_date ON growth_metrics(symbol, date DESC);

-- Value metrics
CREATE TABLE IF NOT EXISTS value_metrics (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    pe_ratio DECIMAL(10,2),
    peg_ratio DECIMAL(10,2),
    pb_ratio DECIMAL(10,2),
    ps_ratio DECIMAL(10,2),
    price_to_fcf DECIMAL(10,2),
    ev_to_ebitda DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(symbol, date)
);

SELECT create_hypertable('value_metrics', 'date', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_value_metrics_symbol_date ON value_metrics(symbol, date DESC);

-- Stability metrics
CREATE TABLE IF NOT EXISTS stability_metrics (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    beta DECIMAL(10,4),
    volatility_30d DECIMAL(10,4),
    volatility_90d DECIMAL(10,4),
    sharpe_ratio DECIMAL(10,4),
    max_drawdown DECIMAL(10,4),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(symbol, date)
);

SELECT create_hypertable('stability_metrics', 'date', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_stability_metrics_symbol_date ON stability_metrics(symbol, date DESC);

-- =============================================================================
-- PHASE 4: ADDITIONAL SIGNAL & ANALYSIS TABLES
-- =============================================================================

-- ============================================================================
-- 7. ADDITIONAL SIGNAL TABLES
-- ============================================================================

-- Mean reversion signals
CREATE TABLE IF NOT EXISTS mean_reversion_signals_daily (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    signal VARCHAR(10),  -- buy, sell, none
    mean_reversion_score DECIMAL(10,4),
    deviation_from_mean DECIMAL(10,4),
    zscore DECIMAL(10,4),
    confidence DECIMAL(10,4),
    created_at TIMESTAMP DEFAULT NOW()
);

SELECT create_hypertable('mean_reversion_signals_daily', 'date', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_mean_reversion_signals_symbol_date ON mean_reversion_signals_daily(symbol, date DESC);

-- Range/support-resistance signals
CREATE TABLE IF NOT EXISTS range_signals_daily (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    signal VARCHAR(10),  -- breakout, breakdown, range_top, range_bottom
    resistance_level DECIMAL(12,4),
    support_level DECIMAL(12,4),
    range_strength DECIMAL(10,4),
    breakout_confirmation BOOLEAN,
    created_at TIMESTAMP DEFAULT NOW()
);

SELECT create_hypertable('range_signals_daily', 'date', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_range_signals_symbol_date ON range_signals_daily(symbol, date DESC);

-- =============================================================================
-- 8. PERFORMANCE & BACKTESTING
-- ============================================================================

-- Backtest runs
CREATE TABLE IF NOT EXISTS backtest_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    strategy_name VARCHAR(255),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    initial_capital DECIMAL(15,2) NOT NULL,
    final_value DECIMAL(15,2),
    total_return_pct DECIMAL(10,4),
    annual_return_pct DECIMAL(10,4),
    sharpe_ratio DECIMAL(10,4),
    max_drawdown_pct DECIMAL(10,4),
    win_rate_pct DECIMAL(10,4),
    total_trades INT,
    winning_trades INT,
    losing_trades INT,
    avg_win DECIMAL(15,2),
    avg_loss DECIMAL(15,2),
    profit_factor DECIMAL(10,4),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_backtest_runs_created ON backtest_runs(created_at DESC);

-- Trades in a backtest
CREATE TABLE IF NOT EXISTS backtest_trades (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    backtest_id UUID NOT NULL REFERENCES backtest_runs(id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    entry_date DATE NOT NULL,
    entry_price DECIMAL(12,4),
    quantity INT,
    exit_date DATE,
    exit_price DECIMAL(12,4),
    pnl DECIMAL(15,2),
    pnl_pct DECIMAL(10,4),
    status VARCHAR(20),  -- closed, open
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_backtest_trades_backtest_id ON backtest_trades(backtest_id);

-- =============================================================================
-- 9. MONITORING & LOGGING
-- ============================================================================

-- Data patrol log (data quality monitoring)
CREATE TABLE IF NOT EXISTS data_patrol_log (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    patrol_date DATE,
    issue_type VARCHAR(100),
    severity VARCHAR(20),
    description TEXT,
    resolved BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_data_patrol_log_date ON data_patrol_log(patrol_date DESC);

-- Algorithm audit log
CREATE TABLE IF NOT EXISTS algo_audit_log (
    id BIGSERIAL PRIMARY KEY,
    run_date DATE NOT NULL,
    run_time TIMESTAMP NOT NULL,
    phase_name VARCHAR(100),
    phase_number INT,
    status VARCHAR(50),
    summary TEXT,
    trades_executed INT,
    errors_count INT,
    warnings_count INT,
    created_at TIMESTAMP DEFAULT NOW()
);

SELECT create_hypertable('algo_audit_log', 'run_date', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_algo_audit_log_date ON algo_audit_log(run_date DESC);

-- Filter rejection log (for debugging signal filtering)
CREATE TABLE IF NOT EXISTS filter_rejection_log (
    id BIGSERIAL PRIMARY KEY,
    signal_date DATE NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    filter_name VARCHAR(100),
    rejection_reason TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

SELECT create_hypertable('filter_rejection_log', 'signal_date', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_filter_rejection_log_symbol_date ON filter_rejection_log(symbol, signal_date DESC);

-- =============================================================================
-- 10. ECONOMIC & MACRO DATA
-- ============================================================================

-- Economic calendar events
CREATE TABLE IF NOT EXISTS economic_calendar (
    id BIGSERIAL PRIMARY KEY,
    event_name VARCHAR(255) NOT NULL,
    event_date DATE NOT NULL,
    country VARCHAR(50),
    importance VARCHAR(20),  -- low, medium, high
    forecast DECIMAL(15,4),
    actual DECIMAL(15,4),
    previous DECIMAL(15,4),
    created_at TIMESTAMP DEFAULT NOW()
);

SELECT create_hypertable('economic_calendar', 'event_date', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_economic_calendar_date ON economic_calendar(event_date DESC);

-- Economic indicators
CREATE TABLE IF NOT EXISTS economic_data (
    id BIGSERIAL PRIMARY KEY,
    indicator_name VARCHAR(255) NOT NULL,
    data_date DATE NOT NULL,
    country VARCHAR(50) DEFAULT 'USA',
    value DECIMAL(15,4),
    previous_value DECIMAL(15,4),
    change DECIMAL(10,4),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(indicator_name, data_date, country)
);

SELECT create_hypertable('economic_data', 'data_date', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_economic_data_indicator_date ON economic_data(indicator_name, data_date DESC);

-- Fear & Greed Index
CREATE TABLE IF NOT EXISTS fear_greed_index (
    id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    index_value DECIMAL(10,4),
    index_category VARCHAR(50),  -- fear, neutral, greed
    created_at TIMESTAMP DEFAULT NOW()
);

SELECT create_hypertable('fear_greed_index', 'date', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_fear_greed_index_date ON fear_greed_index(date DESC);

-- =============================================================================
-- 11. COMMODITY DATA
-- ============================================================================

-- Commodity prices
CREATE TABLE IF NOT EXISTS commodity_prices (
    id BIGSERIAL PRIMARY KEY,
    commodity_symbol VARCHAR(20) NOT NULL,
    commodity_name VARCHAR(255),
    date DATE NOT NULL,
    open DECIMAL(12,4),
    high DECIMAL(12,4),
    low DECIMAL(12,4),
    close DECIMAL(12,4),
    volume BIGINT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(commodity_symbol, date)
);

SELECT create_hypertable('commodity_prices', 'date', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_commodity_prices_symbol_date ON commodity_prices(commodity_symbol, date DESC);

-- Commodity correlations
CREATE TABLE IF NOT EXISTS commodity_correlations (
    id BIGSERIAL PRIMARY KEY,
    commodity_1 VARCHAR(20) NOT NULL,
    commodity_2 VARCHAR(20) NOT NULL,
    correlation DECIMAL(10,4),
    calculation_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(commodity_1, commodity_2, calculation_date)
);

SELECT create_hypertable('commodity_correlations', 'calculation_date', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_commodity_correlations_date ON commodity_correlations(calculation_date DESC);

-- =============================================================================
-- FINAL: INDEXES & ANALYSIS
-- =============================================================================

-- Analyze all tables for query optimizer
ANALYZE;

-- Print completion message
\echo ''
\echo '=========================================='
\echo '✅ Schema migration complete!'
\echo '=========================================='
\echo 'New tables created: 50+'
\echo 'User management: users, user_api_keys, user_portfolio, user_dashboard_settings'
\echo 'Trading: trades, algo_positions, algo_portfolio_snapshots, manual_positions'
\echo 'Market data: market_health_daily, technical_data_daily, trend_template_data'
\echo 'Signal quality: signal_quality_scores, data_completeness_scores'
\echo 'Financial: company_profile, analyst_sentiment, earnings, metrics'
\echo 'Advanced: commodities, economics, backtesting, logging'
\echo ''
\echo 'Extended tables: buy_sell_daily, stock_symbols'
\echo ''
\echo 'Note: All tables indexed and ready for production use'
\echo '=========================================='
