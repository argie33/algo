#!/usr/bin/env node
/**
 * Comprehensive Database Initialization Script
 * Creates ALL tables referenced in the codebase to fix missing table issues
 * Updated to include scoring tables, trading tables, analytics, and more
 */

const { Client } = require('pg');
const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');

// Configure AWS SDK
const secretsManager = new SecretsManagerClient({
    region: process.env.AWS_REGION || 'us-east-1'
});

// Configure logging
const log = (level, message, ...args) => {
    const timestamp = new Date().toISOString();
    console.log(`${timestamp} - ${level.toUpperCase()} - ${message}`, ...args);
};

async function getDbCredentials() {
    log('info', 'Fetching database credentials from Secrets Manager');
    
    try {
        const secretArn = process.env.DB_SECRET_ARN;
        if (!secretArn) {
            // Local development fallback
            return {
                host: process.env.DB_HOST || 'localhost',
                port: parseInt(process.env.DB_PORT) || 5432,
                database: process.env.DB_NAME || 'postgres',
                user: process.env.DB_USER || 'postgres',
                password: process.env.DB_PASSWORD || 'postgres',
                connectionTimeoutMillis: 30000
            };
        }
        
        const command = new GetSecretValueCommand({ SecretId: secretArn });
        const response = await secretsManager.send(command);
        const secret = JSON.parse(response.SecretString);
        
        return {
            host: secret.host,
            port: parseInt(secret.port) || 5432,
            database: secret.dbname || 'postgres',
            user: secret.username,
            password: secret.password,
            ssl: {
                require: true,
                rejectUnauthorized: false
            },
            connectionTimeoutMillis: 30000
        };
    } catch (error) {
        log('error', 'Failed to get database credentials:', error.message);
        throw error;
    }
}

async function executeSQL(client, sql, description) {
    try {
        log('info', `Executing: ${description}`);
        await client.query(sql);
        log('info', `✅ ${description} completed`);
    } catch (error) {
        log('error', `❌ ${description} failed:`, error.message);
        throw error;
    }
}

function getComprehensiveSchema() {
    return `
-- ================================
-- CORE REFERENCE TABLES  
-- ================================

-- Create last_updated table
CREATE TABLE IF NOT EXISTS last_updated (
    script_name VARCHAR(255) PRIMARY KEY,
    last_run TIMESTAMP WITH TIME ZONE
);

-- Enhanced stock symbols table
CREATE TABLE IF NOT EXISTS stock_symbols (
    symbol VARCHAR(10) PRIMARY KEY,
    security_name VARCHAR(200),
    market_category VARCHAR(10),
    test_issue BOOLEAN DEFAULT FALSE,
    financial_status VARCHAR(10),
    round_lot_size INTEGER,
    exchange VARCHAR(10),
    nasdaq_symbol BOOLEAN DEFAULT FALSE,
    sector VARCHAR(100),
    industry VARCHAR(150),
    market_cap_tier VARCHAR(20),
    currency VARCHAR(3) DEFAULT 'USD',
    country VARCHAR(50) DEFAULT 'US',
    is_active BOOLEAN DEFAULT TRUE,
    listing_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Alternative enhanced symbols table (for scoring system)
CREATE TABLE IF NOT EXISTS stock_symbols_enhanced (
    symbol VARCHAR(10) PRIMARY KEY,
    company_name VARCHAR(255) NOT NULL,
    sector VARCHAR(100),
    industry VARCHAR(150),
    sub_industry VARCHAR(200),
    market_cap_tier VARCHAR(20),
    exchange VARCHAR(10),
    currency VARCHAR(3) DEFAULT 'USD',
    country VARCHAR(50) DEFAULT 'US',
    is_active BOOLEAN DEFAULT TRUE,
    listing_date DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Symbols table (alternative name used in some routes)
CREATE TABLE IF NOT EXISTS symbols (
    symbol VARCHAR(10) PRIMARY KEY,
    name VARCHAR(200),
    sector VARCHAR(100),
    industry VARCHAR(150),
    exchange VARCHAR(10),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Basic stocks table
CREATE TABLE IF NOT EXISTS stocks (
    symbol VARCHAR(10) PRIMARY KEY,
    company_name VARCHAR(255),
    sector VARCHAR(100),
    industry VARCHAR(150),
    exchange VARCHAR(10),
    market_cap BIGINT,
    shares_outstanding BIGINT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ================================
-- PRICE DATA TABLES
-- ================================

-- Main prices table
CREATE TABLE IF NOT EXISTS prices (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    open_price DECIMAL(12,4),
    high_price DECIMAL(12,4),
    low_price DECIMAL(12,4),
    close_price DECIMAL(12,4),
    volume BIGINT,
    adjusted_close DECIMAL(12,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Daily price data
CREATE TABLE IF NOT EXISTS price_daily (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    open_price DECIMAL(12,4),
    high_price DECIMAL(12,4),
    low_price DECIMAL(12,4),
    close_price DECIMAL(12,4),
    volume BIGINT,
    adjusted_close DECIMAL(12,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Latest daily prices
CREATE TABLE IF NOT EXISTS latest_price_daily (
    symbol VARCHAR(10) PRIMARY KEY,
    date DATE NOT NULL,
    open_price DECIMAL(12,4),
    high_price DECIMAL(12,4),
    low_price DECIMAL(12,4),
    close_price DECIMAL(12,4),
    volume BIGINT,
    adjusted_close DECIMAL(12,4),
    change_amount DECIMAL(12,4),
    change_percent DECIMAL(8,4),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Weekly price data
CREATE TABLE IF NOT EXISTS price_weekly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    open_price DECIMAL(12,4),
    high_price DECIMAL(12,4),
    low_price DECIMAL(12,4),
    close_price DECIMAL(12,4),
    volume BIGINT,
    adjusted_close DECIMAL(12,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Monthly price data
CREATE TABLE IF NOT EXISTS price_monthly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    open_price DECIMAL(12,4),
    high_price DECIMAL(12,4),
    low_price DECIMAL(12,4),
    close_price DECIMAL(12,4),
    volume BIGINT,
    adjusted_close DECIMAL(12,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Generic price data table
CREATE TABLE IF NOT EXISTS price_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    price_type VARCHAR(20) NOT NULL, -- 'daily', 'weekly', 'monthly'
    open_price DECIMAL(12,4),
    high_price DECIMAL(12,4),
    low_price DECIMAL(12,4),
    close_price DECIMAL(12,4),
    volume BIGINT,
    adjusted_close DECIMAL(12,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date, price_type)
);

-- Stock data (generic)
CREATE TABLE IF NOT EXISTS stock_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    data_type VARCHAR(50) NOT NULL,
    value DECIMAL(15,4),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date, data_type)
);

-- ================================
-- TECHNICAL ANALYSIS TABLES
-- ================================

-- Technical data daily
CREATE TABLE IF NOT EXISTS technical_data_daily (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    rsi_14 DECIMAL(6,2),
    macd DECIMAL(8,4),
    macd_signal DECIMAL(8,4),
    macd_histogram DECIMAL(8,4),
    bb_upper DECIMAL(12,4),
    bb_middle DECIMAL(12,4),
    bb_lower DECIMAL(12,4),
    ma_20 DECIMAL(12,4),
    ma_50 DECIMAL(12,4),
    ma_200 DECIMAL(12,4),
    volume_ma_20 BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Alternative name for technical data
CREATE TABLE IF NOT EXISTS technicals_daily (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    rsi_14 DECIMAL(6,2),
    macd DECIMAL(8,4),
    bb_upper DECIMAL(12,4),
    bb_lower DECIMAL(12,4),
    ma_50 DECIMAL(12,4),
    ma_200 DECIMAL(12,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Technical indicators
CREATE TABLE IF NOT EXISTS technical_indicators (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    indicator_name VARCHAR(50) NOT NULL,
    value DECIMAL(15,4),
    signal VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date, indicator_name)
);

-- ================================
-- TRADING SIGNALS AND STRATEGIES
-- ================================

-- Buy/sell signals daily
CREATE TABLE IF NOT EXISTS buy_sell_daily (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    signal VARCHAR(10) NOT NULL, -- 'BUY', 'SELL', 'HOLD'
    strategy VARCHAR(50) NOT NULL,
    confidence DECIMAL(5,2),
    price DECIMAL(12,4),
    volume BIGINT,
    reasoning TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date, strategy)
);

-- Buy/sell signals weekly
CREATE TABLE IF NOT EXISTS buy_sell_weekly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    signal VARCHAR(10) NOT NULL,
    strategy VARCHAR(50) NOT NULL,
    confidence DECIMAL(5,2),
    price DECIMAL(12,4),
    reasoning TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date, strategy)
);

-- Buy/sell signals monthly
CREATE TABLE IF NOT EXISTS buy_sell_monthly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    signal VARCHAR(10) NOT NULL,
    strategy VARCHAR(50) NOT NULL,
    confidence DECIMAL(5,2),
    price DECIMAL(12,4),
    reasoning TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date, strategy)
);

-- Swing trader signals
CREATE TABLE IF NOT EXISTS swing_trader (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    signal VARCHAR(10) NOT NULL,
    entry_price DECIMAL(12,4),
    stop_loss DECIMAL(12,4),
    take_profit DECIMAL(12,4),
    risk_reward_ratio DECIMAL(6,2),
    confidence DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Latest signals
CREATE TABLE IF NOT EXISTS latest_signals (
    symbol VARCHAR(10) PRIMARY KEY,
    latest_signal VARCHAR(10),
    signal_date DATE,
    strategy VARCHAR(50),
    confidence DECIMAL(5,2),
    price DECIMAL(12,4),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Signal analytics
CREATE TABLE IF NOT EXISTS signal_analytics (
    id SERIAL PRIMARY KEY,
    strategy VARCHAR(50) NOT NULL,
    symbol VARCHAR(10),
    date_range_start DATE,
    date_range_end DATE,
    total_signals INTEGER,
    winning_signals INTEGER,
    losing_signals INTEGER,
    win_rate DECIMAL(5,2),
    avg_return DECIMAL(8,4),
    max_return DECIMAL(8,4),
    min_return DECIMAL(8,4),
    sharpe_ratio DECIMAL(8,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Ranked signals
CREATE TABLE IF NOT EXISTS ranked_signals (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    signal VARCHAR(10) NOT NULL,
    rank INTEGER,
    score DECIMAL(8,4),
    factors JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- ================================
-- USER TRADING SYSTEM
-- ================================

-- User API Keys (already in main schema but ensuring it's here)
CREATE TABLE IF NOT EXISTS user_api_keys (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    provider VARCHAR(50) NOT NULL,
    encrypted_api_key TEXT NOT NULL,
    key_iv VARCHAR(32) NOT NULL,
    key_auth_tag VARCHAR(32) NOT NULL,
    encrypted_api_secret TEXT,
    secret_iv VARCHAR(32),
    secret_auth_tag VARCHAR(32),
    user_salt VARCHAR(32) NOT NULL,
    is_sandbox BOOLEAN DEFAULT true,
    is_active BOOLEAN DEFAULT true,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP,
    UNIQUE(user_id, provider)
);

-- Trading orders
CREATE TABLE IF NOT EXISTS trading_orders (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    api_key_id INTEGER REFERENCES user_api_keys(id),
    symbol VARCHAR(10) NOT NULL,
    order_type VARCHAR(20) NOT NULL, -- 'market', 'limit', 'stop'
    side VARCHAR(10) NOT NULL, -- 'buy', 'sell'
    quantity DECIMAL(15,6) NOT NULL,
    price DECIMAL(12,4),
    stop_price DECIMAL(12,4),
    time_in_force VARCHAR(20) DEFAULT 'day',
    status VARCHAR(20) DEFAULT 'pending',
    order_id VARCHAR(100), -- Broker order ID
    filled_quantity DECIMAL(15,6) DEFAULT 0,
    filled_price DECIMAL(12,4),
    commission DECIMAL(10,4) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User strategies
CREATE TABLE IF NOT EXISTS user_strategies (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    strategy_name VARCHAR(100) NOT NULL,
    strategy_type VARCHAR(50) NOT NULL,
    parameters JSONB NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, strategy_name)
);

-- Backtest results
CREATE TABLE IF NOT EXISTS backtest_results (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    strategy_id INTEGER REFERENCES user_strategies(id),
    symbol VARCHAR(10),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    initial_capital DECIMAL(15,2),
    final_capital DECIMAL(15,2),
    total_return DECIMAL(8,4),
    annualized_return DECIMAL(8,4),
    sharpe_ratio DECIMAL(8,4),
    max_drawdown DECIMAL(8,4),
    total_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,
    win_rate DECIMAL(5,2),
    avg_trade_return DECIMAL(8,4),
    results_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ================================
-- PORTFOLIO MANAGEMENT
-- ================================

-- Portfolio Holdings
CREATE TABLE IF NOT EXISTS portfolio_holdings (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    api_key_id INTEGER REFERENCES user_api_keys(id),
    symbol VARCHAR(10) NOT NULL,
    quantity DECIMAL(15,4) NOT NULL,
    avg_cost DECIMAL(12,4),
    current_price DECIMAL(12,4),
    market_value DECIMAL(15,2),
    cost_basis DECIMAL(15,2),
    unrealized_pl DECIMAL(15,2),
    unrealized_plpc DECIMAL(8,4),
    day_change DECIMAL(15,2),
    day_change_percent DECIMAL(8,4),
    sector VARCHAR(100),
    exchange VARCHAR(20),
    broker VARCHAR(50),
    account_type VARCHAR(20) DEFAULT 'paper',
    last_sync TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, api_key_id, symbol)
);

-- Portfolio Metadata
CREATE TABLE IF NOT EXISTS portfolio_metadata (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    api_key_id INTEGER REFERENCES user_api_keys(id),
    total_equity DECIMAL(15,2),
    total_market_value DECIMAL(15,2),
    total_unrealized_pl DECIMAL(15,2),
    total_unrealized_plpc DECIMAL(8,4),
    account_type VARCHAR(20) DEFAULT 'paper',
    broker VARCHAR(50),
    account_status VARCHAR(50),
    last_sync TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, api_key_id)
);

-- Portfolio Data Refresh Requests (for tracking portfolio data refresh operations)
CREATE TABLE IF NOT EXISTS portfolio_data_refresh_requests (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    symbols JSONB NOT NULL,
    status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'in_progress', 'completed', 'failed'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    UNIQUE(user_id)
);

-- Portfolios table (for risk management)
CREATE TABLE IF NOT EXISTS portfolios (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    total_value DECIMAL(15,2),
    cash_balance DECIMAL(15,2),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, name)
);

-- ================================
-- WATCHLISTS AND ALERTS
-- ================================

-- Watchlists
CREATE TABLE IF NOT EXISTS watchlists (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    color VARCHAR(7) DEFAULT '#1976d2',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, name)
);

-- Watchlist Items
CREATE TABLE IF NOT EXISTS watchlist_items (
    id SERIAL PRIMARY KEY,
    watchlist_id INTEGER NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
    symbol VARCHAR(10) NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    alert_price DECIMAL(12,4),
    alert_type VARCHAR(20) CHECK (alert_type IN ('above', 'below', 'change_percent')),
    alert_value DECIMAL(12,4),
    position_order INTEGER DEFAULT 0,
    UNIQUE(watchlist_id, symbol)
);

-- Trading Alerts
CREATE TABLE IF NOT EXISTS trading_alerts (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,
    target_value DECIMAL(12,4),
    current_value DECIMAL(12,4),
    condition_met BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    message TEXT,
    triggered_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Watchlist alerts (from init_alerts.sql)
CREATE TABLE IF NOT EXISTS watchlist_alerts (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,
    condition VARCHAR(20) NOT NULL,
    target_value DECIMAL(15,4) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    expiry_date TIMESTAMP NULL,
    message TEXT NULL,
    trigger_count INTEGER DEFAULT 0,
    last_triggered TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Alert notifications
CREATE TABLE IF NOT EXISTS alert_notifications (
    id SERIAL PRIMARY KEY,
    alert_id INTEGER NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,
    trigger_value DECIMAL(15,4) NOT NULL,
    market_data JSONB NOT NULL,
    is_read BOOLEAN DEFAULT false,
    read_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ================================
-- SCREENING AND SAVED SEARCHES
-- ================================

-- Saved screens
CREATE TABLE IF NOT EXISTS saved_screens (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    criteria JSONB NOT NULL,
    is_public BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, name)
);

-- ================================
-- EARNINGS AND FUNDAMENTALS
-- ================================

-- Earnings history
CREATE TABLE IF NOT EXISTS earnings_history (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    fiscal_date_ending DATE NOT NULL,
    reported_date DATE,
    period_type VARCHAR(20) NOT NULL, -- 'quarterly', 'annual'
    reported_eps DECIMAL(10,4),
    estimated_eps DECIMAL(10,4),
    surprise DECIMAL(10,4),
    surprise_percentage DECIMAL(8,4),
    revenue DECIMAL(20,2),
    estimated_revenue DECIMAL(20,2),
    revenue_surprise_percentage DECIMAL(8,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_date_ending, period_type)
);

-- Earnings estimates
CREATE TABLE IF NOT EXISTS earnings_estimates (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    period_ending DATE NOT NULL,
    period_type VARCHAR(20) NOT NULL,
    estimate_date DATE NOT NULL,
    estimated_eps DECIMAL(10,4),
    estimated_revenue DECIMAL(20,2),
    analyst_count INTEGER,
    high_estimate DECIMAL(10,4),
    low_estimate DECIMAL(10,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, period_ending, period_type, estimate_date)
);

-- Earnings metrics
CREATE TABLE IF NOT EXISTS earnings_metrics (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    eps_ttm DECIMAL(10,4),
    eps_growth_yoy DECIMAL(8,4),
    eps_growth_qoq DECIMAL(8,4),
    pe_ratio DECIMAL(8,4),
    peg_ratio DECIMAL(8,4),
    earnings_yield DECIMAL(8,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Revenue estimates
CREATE TABLE IF NOT EXISTS revenue_estimates (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    period_ending DATE NOT NULL,
    period_type VARCHAR(20) NOT NULL,
    estimate_date DATE NOT NULL,
    estimated_revenue DECIMAL(20,2),
    analyst_count INTEGER,
    high_estimate DECIMAL(20,2),
    low_estimate DECIMAL(20,2),
    growth_estimate DECIMAL(8,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, period_ending, period_type, estimate_date)
);

-- EPS revisions
CREATE TABLE IF NOT EXISTS eps_revisions (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    period_ending DATE NOT NULL,
    revision_date DATE NOT NULL,
    analyst_firm VARCHAR(100),
    old_estimate DECIMAL(10,4),
    new_estimate DECIMAL(10,4),
    revision_amount DECIMAL(10,4),
    revision_type VARCHAR(20), -- 'upgrade', 'downgrade', 'maintain'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- EPS trend
CREATE TABLE IF NOT EXISTS eps_trend (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    current_qtr_estimate DECIMAL(10,4),
    next_qtr_estimate DECIMAL(10,4),
    current_year_estimate DECIMAL(10,4),
    next_year_estimate DECIMAL(10,4),
    revisions_7d INTEGER,
    revisions_30d INTEGER,
    revisions_90d INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Growth estimates
CREATE TABLE IF NOT EXISTS growth_estimates (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    current_qtr_growth DECIMAL(8,4),
    next_qtr_growth DECIMAL(8,4),
    current_year_growth DECIMAL(8,4),
    next_year_growth DECIMAL(8,4),
    next_5_years_growth DECIMAL(8,4),
    past_5_years_growth DECIMAL(8,4),
    peg_ratio DECIMAL(8,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- ================================
-- FINANCIAL STATEMENTS
-- ================================

-- Annual balance sheet
CREATE TABLE IF NOT EXISTS annual_balance_sheet (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    fiscal_date_ending DATE NOT NULL,
    total_assets DECIMAL(20,2),
    total_current_assets DECIMAL(20,2),
    cash_and_equivalents DECIMAL(20,2),
    inventory DECIMAL(20,2),
    total_non_current_assets DECIMAL(20,2),
    property_plant_equipment DECIMAL(20,2),
    total_liabilities DECIMAL(20,2),
    total_current_liabilities DECIMAL(20,2),
    total_non_current_liabilities DECIMAL(20,2),
    total_shareholder_equity DECIMAL(20,2),
    retained_earnings DECIMAL(20,2),
    common_stock DECIMAL(20,2),
    treasury_stock DECIMAL(20,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_date_ending)
);

-- Annual income statement
CREATE TABLE IF NOT EXISTS annual_income_statement (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    fiscal_date_ending DATE NOT NULL,
    total_revenue DECIMAL(20,2),
    gross_profit DECIMAL(20,2),
    operating_income DECIMAL(20,2),
    operating_expenses DECIMAL(20,2),
    research_development DECIMAL(20,2),
    ebitda DECIMAL(20,2),
    net_income DECIMAL(20,2),
    basic_shares_outstanding DECIMAL(20,2),
    diluted_shares_outstanding DECIMAL(20,2),
    basic_eps DECIMAL(10,4),
    diluted_eps DECIMAL(10,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_date_ending)
);

-- Annual cash flow
CREATE TABLE IF NOT EXISTS annual_cash_flow (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    fiscal_date_ending DATE NOT NULL,
    operating_cash_flow DECIMAL(20,2),
    payments_for_operating_activities DECIMAL(20,2),
    proceeds_from_operating_activities DECIMAL(20,2),
    change_in_operating_liabilities DECIMAL(20,2),
    change_in_operating_assets DECIMAL(20,2),
    depreciation_depletion_amortization DECIMAL(20,2),
    capital_expenditures DECIMAL(20,2),
    change_in_inventory DECIMAL(20,2),
    change_in_accounts_receivable DECIMAL(20,2),
    change_in_net_income DECIMAL(20,2),
    cash_flow_from_investment DECIMAL(20,2),
    cash_flow_from_financing DECIMAL(20,2),
    proceeds_from_repayments_short_term_debt DECIMAL(20,2),
    payments_for_repurchase_of_common_stock DECIMAL(20,2),
    payments_for_repurchase_of_equity DECIMAL(20,2),
    payments_for_repurchase_of_preferred_stock DECIMAL(20,2),
    dividend_payout DECIMAL(20,2),
    dividend_payout_common_stock DECIMAL(20,2),
    dividend_payout_preferred_stock DECIMAL(20,2),
    proceeds_from_issuance_of_common_stock DECIMAL(20,2),
    proceeds_from_issuance_of_long_term_debt_and_capital_securities_net DECIMAL(20,2),
    proceeds_from_issuance_of_preferred_stock DECIMAL(20,2),
    proceeds_from_repurchase_of_equity DECIMAL(20,2),
    proceeds_from_sale_of_treasury_stock DECIMAL(20,2),
    change_in_cash_and_cash_equivalents DECIMAL(20,2),
    change_in_exchange_rate DECIMAL(20,2),
    net_income DECIMAL(20,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_date_ending)
);

-- ================================
-- ANALYST DATA
-- ================================

-- Analyst upgrade/downgrade
CREATE TABLE IF NOT EXISTS analyst_upgrade_downgrade (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    firm VARCHAR(100) NOT NULL,
    to_grade VARCHAR(50),
    from_grade VARCHAR(50),
    action VARCHAR(20), -- 'Upgrade', 'Downgrade', 'Initiate', 'Reiterate'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Analyst recommendations
CREATE TABLE IF NOT EXISTS analyst_recommendations (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    firm VARCHAR(100) NOT NULL,
    analyst_name VARCHAR(100),
    rating VARCHAR(50) NOT NULL,
    price_target DECIMAL(10,4),
    rating_change VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ================================
-- MARKET DATA AND SENTIMENT
-- ================================

-- Market data (generic)
CREATE TABLE IF NOT EXISTS market_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10),
    date DATE NOT NULL,
    data_type VARCHAR(50) NOT NULL,
    value DECIMAL(15,4),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date, data_type)
);

-- Fear & Greed Index
CREATE TABLE IF NOT EXISTS fear_greed (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    value INTEGER NOT NULL,
    classification VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date)
);

-- Alternative fear greed table name
CREATE TABLE IF NOT EXISTS fear_greed_index (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    value INTEGER NOT NULL,
    classification VARCHAR(20),
    momentum_value INTEGER,
    market_volatility_value INTEGER,
    junk_bond_demand_value INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date)
);

-- NAAIM exposure index
CREATE TABLE IF NOT EXISTS naaim (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    mean_exposure DECIMAL(6,2),
    median_exposure DECIMAL(6,2),
    std_dev DECIMAL(6,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date)
);

-- AAII sentiment
CREATE TABLE IF NOT EXISTS aaii_sentiment (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    bullish_pct DECIMAL(5,2),
    neutral_pct DECIMAL(5,2),
    bearish_pct DECIMAL(5,2),
    bull_bear_spread DECIMAL(6,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date)
);

-- ================================
-- ECONOMIC DATA
-- ================================

-- Economic data
CREATE TABLE IF NOT EXISTS economic_data (
    id SERIAL PRIMARY KEY,
    indicator_code VARCHAR(50) NOT NULL,
    date DATE NOT NULL,
    value DECIMAL(15,4),
    units VARCHAR(50),
    frequency VARCHAR(20),
    seasonal_adjustment VARCHAR(50),
    last_updated TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(indicator_code, date)
);

-- Economic indicators
CREATE TABLE IF NOT EXISTS economic_indicators (
    id SERIAL PRIMARY KEY,
    indicator_name VARCHAR(100) NOT NULL,
    indicator_code VARCHAR(50) NOT NULL,
    category VARCHAR(50),
    description TEXT,
    units VARCHAR(50),
    frequency VARCHAR(20),
    source VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(indicator_code)
);

-- Economic calendar
CREATE TABLE IF NOT EXISTS economic_calendar (
    id SERIAL PRIMARY KEY,
    event_date DATE NOT NULL,
    event_time TIME,
    country VARCHAR(5) NOT NULL,
    event_name VARCHAR(200) NOT NULL,
    importance VARCHAR(20), -- 'Low', 'Medium', 'High'
    actual_value VARCHAR(50),
    forecast_value VARCHAR(50),
    previous_value VARCHAR(50),
    currency VARCHAR(3),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ================================
-- NEWS AND SENTIMENT
-- ================================

-- News articles
CREATE TABLE IF NOT EXISTS news_articles (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10),
    title VARCHAR(500) NOT NULL,
    summary TEXT,
    url VARCHAR(1000),
    published_date TIMESTAMP NOT NULL,
    source VARCHAR(100),
    sentiment_score DECIMAL(6,4), -- -1 to 1
    relevance_score DECIMAL(5,2), -- 0 to 100
    category VARCHAR(50),
    tickers_mentioned TEXT[], -- Array of ticker symbols
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ================================
-- PATTERN RECOGNITION
-- ================================

-- Detected patterns
CREATE TABLE IF NOT EXISTS detected_patterns (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    pattern_type VARCHAR(50) NOT NULL,
    confidence DECIMAL(5,2),
    timeframe VARCHAR(20), -- '1D', '1W', '1M'
    breakout_target DECIMAL(12,4),
    stop_loss DECIMAL(12,4),
    risk_reward_ratio DECIMAL(6,2),
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Pattern types
CREATE TABLE IF NOT EXISTS pattern_types (
    id SERIAL PRIMARY KEY,
    pattern_name VARCHAR(50) UNIQUE NOT NULL,
    category VARCHAR(30) NOT NULL, -- 'reversal', 'continuation', 'consolidation'
    description TEXT,
    bullish BOOLEAN,
    avg_success_rate DECIMAL(5,2),
    avg_target_move DECIMAL(6,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Pattern performance
CREATE TABLE IF NOT EXISTS pattern_performance (
    id SERIAL PRIMARY KEY,
    pattern_id INTEGER REFERENCES detected_patterns(id),
    evaluation_date DATE NOT NULL,
    outcome VARCHAR(20), -- 'success', 'failure', 'partial'
    target_hit BOOLEAN,
    stop_loss_hit BOOLEAN,
    max_favorable_move DECIMAL(6,2),
    max_adverse_move DECIMAL(6,2),
    holding_period_days INTEGER,
    final_return DECIMAL(8,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Pattern detections (alternative table name)
CREATE TABLE IF NOT EXISTS pattern_detections (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    pattern_name VARCHAR(50) NOT NULL,
    confidence DECIMAL(5,2),
    details JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date, pattern_name)
);

-- ================================
-- SCORING SYSTEM TABLES
-- ================================

-- Quality metrics
CREATE TABLE IF NOT EXISTS quality_metrics (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    earnings_quality_score DECIMAL(5,2),
    balance_sheet_score DECIMAL(5,2),
    cash_flow_quality_score DECIMAL(5,2),
    debt_quality_score DECIMAL(5,2),
    management_effectiveness_score DECIMAL(5,2),
    composite_quality_score DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Comprehensive scores
CREATE TABLE IF NOT EXISTS comprehensive_scores (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    quality_score DECIMAL(5,2),
    value_score DECIMAL(5,2),
    growth_score DECIMAL(5,2),
    momentum_score DECIMAL(5,2),
    sentiment_score DECIMAL(5,2),
    technical_score DECIMAL(5,2),
    composite_score DECIMAL(5,2),
    percentile_rank DECIMAL(5,2),
    sector VARCHAR(100),
    market_cap_tier VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Momentum metrics
CREATE TABLE IF NOT EXISTS momentum_metrics (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    price_momentum_1m DECIMAL(8,4),
    price_momentum_3m DECIMAL(8,4),
    price_momentum_6m DECIMAL(8,4),
    price_momentum_12m DECIMAL(8,4),
    earnings_momentum DECIMAL(8,4),
    estimate_revisions DECIMAL(8,4),
    relative_strength DECIMAL(8,4),
    composite_momentum_score DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Positioning metrics
CREATE TABLE IF NOT EXISTS positioning_metrics (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    institutional_ownership_pct DECIMAL(8,4),
    insider_ownership_pct DECIMAL(8,4),
    short_interest_pct DECIMAL(8,4),
    institutional_buying DECIMAL(8,4),
    days_to_cover DECIMAL(6,2),
    composite_positioning_score DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Social sentiment analysis
CREATE TABLE IF NOT EXISTS social_sentiment_analysis (
    symbol VARCHAR(10),
    date DATE,
    reddit_mention_count INTEGER,
    reddit_sentiment_score DECIMAL(6,4),
    search_volume_index INTEGER,
    news_article_count INTEGER,
    news_sentiment_score DECIMAL(6,4),
    composite_social_sentiment_score DECIMAL(5,2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- Technical indicators (from scoring system)
CREATE TABLE IF NOT EXISTS technical_indicators_scoring (
    symbol VARCHAR(10),
    date DATE,
    rsi_14 DECIMAL(6,2),
    macd_signal DECIMAL(8,6),
    price_vs_ma50 DECIMAL(8,4),
    price_vs_ma200 DECIMAL(8,4),
    composite_technical_score DECIMAL(5,2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- Profitability metrics
CREATE TABLE IF NOT EXISTS profitability_metrics (
    symbol VARCHAR(10),
    date DATE,
    return_on_equity DECIMAL(8,4),
    return_on_assets DECIMAL(8,4),
    return_on_invested_capital DECIMAL(8,4),
    net_profit_margin DECIMAL(8,4),
    gross_margin DECIMAL(8,4),
    operating_margin DECIMAL(8,4),
    composite_profitability_score DECIMAL(5,2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- Balance sheet metrics
CREATE TABLE IF NOT EXISTS balance_sheet_metrics (
    symbol VARCHAR(10),
    date DATE,
    debt_to_equity DECIMAL(8,4),
    current_ratio DECIMAL(8,4),
    quick_ratio DECIMAL(8,4),
    interest_coverage DECIMAL(8,4),
    piotroski_f_score INTEGER,
    altman_z_score DECIMAL(8,4),
    composite_balance_sheet_score DECIMAL(5,2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- Valuation metrics
CREATE TABLE IF NOT EXISTS valuation_metrics (
    symbol VARCHAR(10),
    date DATE,
    pe_ratio DECIMAL(8,4),
    pb_ratio DECIMAL(8,4),
    ps_ratio DECIMAL(8,4),
    peg_ratio DECIMAL(8,4),
    ev_ebitda DECIMAL(8,4),
    ev_sales DECIMAL(8,4),
    dcf_value DECIMAL(12,4),
    margin_of_safety DECIMAL(8,4),
    composite_value_score DECIMAL(5,2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- Growth metrics
CREATE TABLE IF NOT EXISTS growth_metrics (
    symbol VARCHAR(10),
    date DATE,
    revenue_growth_1yr DECIMAL(8,4),
    revenue_growth_3yr DECIMAL(8,4),
    eps_growth_1yr DECIMAL(8,4),
    eps_growth_3yr DECIMAL(8,4),
    sustainable_growth_rate DECIMAL(8,4),
    composite_growth_score DECIMAL(5,2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- Market regime
CREATE TABLE IF NOT EXISTS market_regime (
    date DATE PRIMARY KEY,
    regime VARCHAR(20) NOT NULL,
    confidence_score DECIMAL(5,2),
    vix_level DECIMAL(6,2),
    yield_curve_slope DECIMAL(8,4),
    credit_spreads DECIMAL(8,4),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Stock scores (master scoring table)
CREATE TABLE IF NOT EXISTS stock_scores (
    symbol VARCHAR(10),
    date DATE,
    quality_score DECIMAL(5,2),
    growth_score DECIMAL(5,2),
    value_score DECIMAL(5,2),
    momentum_score DECIMAL(5,2),
    sentiment_score DECIMAL(5,2),
    positioning_score DECIMAL(5,2),
    composite_score DECIMAL(5,2),
    percentile_rank DECIMAL(5,2),
    sector_adjusted_score DECIMAL(5,2),
    market_regime VARCHAR(20),
    confidence_score DECIMAL(5,2),
    data_completeness DECIMAL(5,2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- Score performance tracking
CREATE TABLE IF NOT EXISTS score_performance_tracking (
    symbol VARCHAR(10),
    score_date DATE,
    evaluation_date DATE,
    forward_return_1m DECIMAL(8,4),
    forward_return_3m DECIMAL(8,4),
    forward_return_6m DECIMAL(8,4),
    forward_return_12m DECIMAL(8,4),
    original_composite_score DECIMAL(5,2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, score_date, evaluation_date)
);

-- ================================
-- RISK MANAGEMENT
-- ================================

-- Risk limits
CREATE TABLE IF NOT EXISTS risk_limits (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    portfolio_id INTEGER REFERENCES portfolios(id),
    limit_type VARCHAR(50) NOT NULL, -- 'position_size', 'sector_exposure', 'var'
    limit_value DECIMAL(15,4) NOT NULL,
    current_value DECIMAL(15,4),
    warning_threshold DECIMAL(15,4),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Market risk indicators
CREATE TABLE IF NOT EXISTS market_risk_indicators (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    vix DECIMAL(6,2),
    term_structure_slope DECIMAL(8,4),
    credit_spreads DECIMAL(8,4),
    correlation_breakdown BOOLEAN,
    risk_regime VARCHAR(20), -- 'low', 'medium', 'high', 'crisis'
    systemic_risk_score DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date)
);

-- Portfolio risk metrics
CREATE TABLE IF NOT EXISTS portfolio_risk_metrics (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    portfolio_id INTEGER REFERENCES portfolios(id),
    date DATE NOT NULL,
    var_1_day DECIMAL(15,4), -- Value at Risk 1-day 95%
    var_1_week DECIMAL(15,4),
    expected_shortfall DECIMAL(15,4),
    beta DECIMAL(6,4),
    tracking_error DECIMAL(6,4),
    sharpe_ratio DECIMAL(8,4),
    sortino_ratio DECIMAL(8,4),
    max_drawdown DECIMAL(6,4),
    concentration_risk DECIMAL(5,2),
    sector_concentration JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, portfolio_id, date)
);

-- ================================
-- SECTOR ANALYSIS
-- ================================

-- Sector summary
CREATE TABLE IF NOT EXISTS sector_summary (
    id SERIAL PRIMARY KEY,
    sector VARCHAR(100) NOT NULL,
    date DATE NOT NULL,
    total_market_cap DECIMAL(20,2),
    avg_pe_ratio DECIMAL(8,4),
    avg_pb_ratio DECIMAL(8,4),
    avg_dividend_yield DECIMAL(6,4),
    performance_1d DECIMAL(8,4),
    performance_1w DECIMAL(8,4),
    performance_1m DECIMAL(8,4),
    performance_3m DECIMAL(8,4),
    performance_ytd DECIMAL(8,4),
    momentum_score DECIMAL(5,2),
    relative_strength DECIMAL(8,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(sector, date)
);

-- ================================
-- USER PREFERENCE TABLES
-- ================================

-- User notification preferences (enhanced)
CREATE TABLE IF NOT EXISTS user_notification_preferences (
    user_id VARCHAR(255) PRIMARY KEY,
    email_notifications BOOLEAN DEFAULT TRUE,
    push_notifications BOOLEAN DEFAULT TRUE,
    price_alerts BOOLEAN DEFAULT TRUE,
    portfolio_updates BOOLEAN DEFAULT TRUE,
    market_news BOOLEAN DEFAULT FALSE,
    weekly_reports BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User theme preferences (enhanced)
CREATE TABLE IF NOT EXISTS user_theme_preferences (
    user_id VARCHAR(255) PRIMARY KEY,
    dark_mode BOOLEAN DEFAULT FALSE,
    primary_color VARCHAR(20) DEFAULT '#1976d2',
    chart_style VARCHAR(20) DEFAULT 'candlestick',
    layout VARCHAR(20) DEFAULT 'standard',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ================================
-- COMPANY PROFILE TABLES (from webapp-db-init.js)
-- ================================

-- Company profile
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
    exchange VARCHAR(20),
    full_exchange_name VARCHAR(100),
    exchange_timezone_name VARCHAR(100),
    exchange_timezone_short_name VARCHAR(20),
    exchange_data_delayed_by_sec INT,
    post_market_time_ms BIGINT,
    regular_market_time_ms BIGINT
);

-- Leadership team
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

-- Governance scores
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

-- Key metrics
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
    profit_margins NUMERIC,
    gross_margins NUMERIC,
    operating_margins NUMERIC,
    return_on_assets NUMERIC,
    return_on_equity NUMERIC,
    revenue_ttm BIGINT,
    revenue_per_share NUMERIC,
    quarterly_revenue_growth NUMERIC,
    gross_profit_ttm BIGINT,
    ebitda BIGINT,
    net_income_to_common_ttm BIGINT,
    diluted_eps NUMERIC,
    quarterly_earnings_growth NUMERIC,
    total_cash BIGINT,
    total_cash_per_share NUMERIC,
    total_debt BIGINT,
    debt_to_equity NUMERIC,
    current_ratio NUMERIC,
    book_value_per_share NUMERIC,
    operating_cash_flow_ttm BIGINT,
    levered_free_cash_flow_ttm BIGINT,
    shares_outstanding BIGINT,
    float_shares BIGINT,
    shares_short BIGINT,
    shares_short_prior_month BIGINT,
    short_ratio NUMERIC,
    short_percent_of_float NUMERIC,
    shares_short_prior_month_date_ms BIGINT,
    date_short_interest_ms BIGINT,
    shares_percent_held_by_insiders NUMERIC,
    shares_percent_held_by_institutions NUMERIC,
    forward_annual_dividend_rate NUMERIC,
    forward_annual_dividend_yield NUMERIC,
    trailing_annual_dividend_rate NUMERIC,
    trailing_annual_dividend_yield NUMERIC,
    five_year_avg_dividend_yield NUMERIC,
    last_annual_dividend_amt NUMERIC,
    last_annual_dividend_yield NUMERIC,
    last_dividend_amt NUMERIC,
    last_dividend_date_ms BIGINT,
    dividend_date_ms BIGINT,
    payout_ratio NUMERIC
);

-- Analyst estimates (company profile related)
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

-- ================================
-- HEALTH AND MONITORING
-- ================================

-- Health Status
CREATE TABLE IF NOT EXISTS health_status (
    table_name VARCHAR(255) PRIMARY KEY,
    status VARCHAR(50) NOT NULL DEFAULT 'unknown',
    record_count BIGINT DEFAULT 0,
    missing_data_count BIGINT DEFAULT 0,
    last_updated TIMESTAMP WITH TIME ZONE,
    last_checked TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_stale BOOLEAN DEFAULT FALSE,
    error TEXT,
    table_category VARCHAR(100),
    critical_table BOOLEAN DEFAULT FALSE,
    expected_update_frequency INTERVAL DEFAULT '1 day',
    size_bytes BIGINT DEFAULT 0,
    last_vacuum TIMESTAMP WITH TIME ZONE,
    last_analyze TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ================================
-- INDEXES FOR PERFORMANCE
-- ================================

-- User API Keys indexes
CREATE INDEX IF NOT EXISTS idx_user_api_keys_user_id ON user_api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_user_api_keys_provider ON user_api_keys(provider);
CREATE INDEX IF NOT EXISTS idx_user_api_keys_active ON user_api_keys(is_active);

-- Price data indexes
CREATE INDEX IF NOT EXISTS idx_prices_symbol ON prices(symbol);
CREATE INDEX IF NOT EXISTS idx_prices_date ON prices(date);
CREATE INDEX IF NOT EXISTS idx_price_daily_symbol_date ON price_daily(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_latest_price_daily_symbol ON latest_price_daily(symbol);
CREATE INDEX IF NOT EXISTS idx_price_weekly_symbol_date ON price_weekly(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_price_monthly_symbol_date ON price_monthly(symbol, date DESC);

-- Trading signals indexes
CREATE INDEX IF NOT EXISTS idx_buy_sell_daily_symbol_date ON buy_sell_daily(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_buy_sell_weekly_symbol_date ON buy_sell_weekly(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_buy_sell_monthly_symbol_date ON buy_sell_monthly(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_latest_signals_symbol ON latest_signals(symbol);

-- Technical analysis indexes
CREATE INDEX IF NOT EXISTS idx_technical_data_daily_symbol_date ON technical_data_daily(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_technicals_daily_symbol_date ON technicals_daily(symbol, date DESC);

-- Portfolio indexes
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_user_id ON portfolio_holdings(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_symbol ON portfolio_holdings(symbol);
CREATE INDEX IF NOT EXISTS idx_portfolio_metadata_user_id ON portfolio_metadata(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_data_refresh_requests_user_id ON portfolio_data_refresh_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_data_refresh_requests_status ON portfolio_data_refresh_requests(status);

-- Watchlist indexes
CREATE INDEX IF NOT EXISTS idx_watchlists_user_id ON watchlists(user_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_items_watchlist_id ON watchlist_items(watchlist_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_alerts_user_id ON watchlist_alerts(user_id);

-- Earnings indexes
CREATE INDEX IF NOT EXISTS idx_earnings_history_symbol_date ON earnings_history(symbol, fiscal_date_ending DESC);
CREATE INDEX IF NOT EXISTS idx_earnings_estimates_symbol_date ON earnings_estimates(symbol, period_ending DESC);

-- News indexes
CREATE INDEX IF NOT EXISTS idx_news_articles_symbol_date ON news_articles(symbol, published_date DESC);
CREATE INDEX IF NOT EXISTS idx_news_articles_published_date ON news_articles(published_date DESC);

-- Market data indexes
CREATE INDEX IF NOT EXISTS idx_market_data_symbol_date ON market_data(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_economic_data_indicator_date ON economic_data(indicator_code, date DESC);

-- Scoring system indexes
CREATE INDEX IF NOT EXISTS idx_stock_scores_symbol_date ON stock_scores(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_comprehensive_scores_symbol_date ON comprehensive_scores(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_quality_metrics_symbol_date ON quality_metrics(symbol, date DESC);

-- Pattern indexes
CREATE INDEX IF NOT EXISTS idx_detected_patterns_symbol_date ON detected_patterns(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_pattern_detections_symbol_date ON pattern_detections(symbol, date DESC);

-- Risk indexes
CREATE INDEX IF NOT EXISTS idx_portfolio_risk_metrics_user_date ON portfolio_risk_metrics(user_id, date DESC);

-- Company profile indexes
CREATE INDEX IF NOT EXISTS idx_company_profile_ticker ON company_profile(ticker);
CREATE INDEX IF NOT EXISTS idx_company_profile_sector ON company_profile(sector);
CREATE INDEX IF NOT EXISTS idx_company_profile_industry ON company_profile(industry);

-- Health status indexes
CREATE INDEX IF NOT EXISTS idx_health_status_status ON health_status(status);
CREATE INDEX IF NOT EXISTS idx_health_status_critical ON health_status(critical_table);

-- Stock symbols indexes
CREATE INDEX IF NOT EXISTS idx_stock_symbols_symbol ON stock_symbols(symbol);
CREATE INDEX IF NOT EXISTS idx_stock_symbols_sector ON stock_symbols(sector);
CREATE INDEX IF NOT EXISTS idx_symbols_symbol ON symbols(symbol);
CREATE INDEX IF NOT EXISTS idx_stocks_symbol ON stocks(symbol);

-- ================================
-- UPDATE TRIGGERS
-- ================================

-- Function for updating timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language plpgsql;

-- Triggers for updated_at columns
DROP TRIGGER IF EXISTS update_stock_symbols_updated_at ON stock_symbols;
CREATE TRIGGER update_stock_symbols_updated_at
    BEFORE UPDATE ON stock_symbols
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_user_api_keys_updated_at ON user_api_keys;
CREATE TRIGGER update_user_api_keys_updated_at
    BEFORE UPDATE ON user_api_keys
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_portfolio_holdings_updated_at ON portfolio_holdings;
CREATE TRIGGER update_portfolio_holdings_updated_at
    BEFORE UPDATE ON portfolio_holdings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_portfolio_metadata_updated_at ON portfolio_metadata;
CREATE TRIGGER update_portfolio_metadata_updated_at
    BEFORE UPDATE ON portfolio_metadata
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_watchlists_updated_at ON watchlists;
CREATE TRIGGER update_watchlists_updated_at
    BEFORE UPDATE ON watchlists
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_watchlist_alerts_updated_at ON watchlist_alerts;
CREATE TRIGGER update_watchlist_alerts_updated_at
    BEFORE UPDATE ON watchlist_alerts
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_user_notification_preferences_updated_at ON user_notification_preferences;
CREATE TRIGGER update_user_notification_preferences_updated_at
    BEFORE UPDATE ON user_notification_preferences
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_user_theme_preferences_updated_at ON user_theme_preferences;
CREATE TRIGGER update_user_theme_preferences_updated_at
    BEFORE UPDATE ON user_theme_preferences
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ================================
-- INITIALIZE HEALTH STATUS
-- ================================

-- Insert health status records for critical tables
INSERT INTO health_status (table_name, table_category, critical_table, expected_update_frequency) VALUES
('user_api_keys', 'webapp', true, '1 hour'),
('portfolio_holdings', 'webapp', true, '1 hour'),
('portfolio_metadata', 'webapp', true, '1 hour'),
('portfolio_data_refresh_requests', 'webapp', false, '1 hour'),
('trading_alerts', 'webapp', false, '1 hour'),
('watchlists', 'webapp', false, '1 hour'),
('watchlist_items', 'webapp', false, '1 hour'),
('stock_symbols', 'market_data', true, '1 day'),
('prices', 'market_data', true, '1 day'),
('price_daily', 'market_data', true, '1 day'),
('latest_price_daily', 'market_data', true, '1 hour'),
('technical_data_daily', 'technical', true, '1 day'),
('buy_sell_daily', 'signals', true, '1 day'),
('earnings_history', 'fundamentals', true, '1 week'),
('news_articles', 'news', false, '1 hour'),
('market_data', 'market_data', true, '1 day'),
('economic_data', 'economic', true, '1 day'),
('comprehensive_scores', 'scoring', true, '1 day'),
('stock_scores', 'scoring', true, '1 day'),
('detected_patterns', 'patterns', false, '1 day'),
('company_profile', 'company', true, '1 week'),
('health_status', 'system', true, '1 hour'),
('last_updated', 'system', true, '1 hour')
ON CONFLICT (table_name) DO NOTHING;
`;
}

async function initializeComprehensiveDatabase() {
    log('info', '🚀 Starting comprehensive database initialization v2.0');
    log('info', `Environment: ${process.env.ENVIRONMENT || 'unknown'}`);
    log('info', `AWS Region: ${process.env.AWS_REGION || 'unknown'}`);
    log('info', `DB Secret ARN: ${process.env.DB_SECRET_ARN ? 'set' : 'NOT SET'}`);
    
    let client;
    
    try {
        // Get database credentials
        const dbConfig = await getDbCredentials();
        
        // Connect to database
        log('info', `Connecting to database at ${dbConfig.host}:${dbConfig.port} (database: ${dbConfig.database})`);
        client = new Client(dbConfig);
        await client.connect();
        log('info', '✅ Database connection successful');
        
        // Create comprehensive database schema
        log('info', '🔧 Creating comprehensive database schema...');
        await executeSQL(client, getComprehensiveSchema(), 'Comprehensive database schema initialization');
        
        // Test database connectivity
        const testResult = await client.query(`
            SELECT current_database() as db_name, 
                   current_user as db_user, 
                   COUNT(*) FILTER (WHERE table_schema = 'public') as table_count
            FROM information_schema.tables;
        `);
        
        log('info', `✅ Database test: ${testResult.rows[0].table_count} tables created`);
        
        // Update last_updated tracking
        await executeSQL(client, `
            INSERT INTO last_updated (script_name, last_run) 
            VALUES ('comprehensive_db_init', NOW())
            ON CONFLICT (script_name) 
            DO UPDATE SET last_run = EXCLUDED.last_run;
        `, 'Update last_updated tracking');
        
        log('info', '🎉 Comprehensive database initialization completed successfully');
        return 0;
        
    } catch (error) {
        log('error', '❌ Comprehensive database initialization failed:', error.message);
        log('error', 'Full error details:', error);
        return 1;
    } finally {
        if (client) {
            try {
                await client.end();
                log('info', 'Database connection closed');
            } catch (closeError) {
                log('error', 'Error closing database connection:', closeError.message);
            }
        }
    }
}

// Run initialization if this script is executed directly
if (require.main === module) {
    initializeComprehensiveDatabase().then(exitCode => {
        process.exit(exitCode);
    }).catch(error => {
        log('error', 'Unhandled error:', error);
        process.exit(1);
    });
}

module.exports = { initializeComprehensiveDatabase };