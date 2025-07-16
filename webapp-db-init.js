#!/usr/bin/env node
/**
 * ECS-based Webapp Database Initialization Script
 * Runs as an ECS task during deployment to initialize webapp database tables
 * Updated to use AWS SDK v3 for compatibility
 * Trigger v2: 2025-07-16 - Database diagnostic deployment phase
 */

const { Client } = require('pg');
const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');

// Configure AWS SDK
const secretsManager = new SecretsManagerClient({
    region: process.env.AWS_REGION || 'us-east-1'
});

// Configure logging - DB initialization trigger for deployment
const log = (level, message, ...args) => {
    const timestamp = new Date().toISOString();
    console.log(`${timestamp} - ${level.toUpperCase()} - ${message}`, ...args);
};

async function getDbCredentials() {
    log('info', 'Fetching database credentials from Secrets Manager');
    
    try {
        const secretArn = process.env.DB_SECRET_ARN;
        if (!secretArn) {
            throw new Error('DB_SECRET_ARN environment variable not set');
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
            ssl: { rejectUnauthorized: false }, // SSL required for RDS but allow self-signed certs
            // MASSIVELY INCREASED TIMEOUTS FOR CONNECTIVITY ISSUES
            connectionTimeoutMillis: 60000, // 60 seconds
            query_timeout: 120000, // 2 minutes
            statement_timeout: 120000, // 2 minutes
            idle_in_transaction_session_timeout: 60000, // 60 seconds
            keepAlive: true,
            keepAliveInitialDelayMillis: 10000, // 10 seconds
            // Additional connection resilience
            max: 1, // Single connection for init
            min: 0,
            acquireTimeoutMillis: 60000, // 60 seconds to acquire connection
            createTimeoutMillis: 60000, // 60 seconds to create connection
            destroyTimeoutMillis: 10000 // 10 seconds to destroy connection
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

async function ensureTableColumnsExist(client) {
    try {
        log('info', '🔍 Checking and adding missing columns to existing tables...');
        
        // Check if portfolio_metadata table exists and has last_sync column
        const portfolioMetadataCheck = await client.query(`
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'portfolio_metadata' 
            AND column_name = 'last_sync'
        `);
        
        if (portfolioMetadataCheck.rows.length === 0) {
            // Check if table exists at all
            const tableCheck = await client.query(`
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_name = 'portfolio_metadata'
            `);
            
            if (tableCheck.rows.length > 0) {
                log('info', '📝 Adding missing last_sync column to portfolio_metadata table');
                await client.query(`
                    ALTER TABLE portfolio_metadata 
                    ADD COLUMN IF NOT EXISTS last_sync TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                `);
            }
        }
        
        // Check if portfolio_holdings table exists and has last_sync column
        const portfolioHoldingsCheck = await client.query(`
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'portfolio_holdings' 
            AND column_name = 'last_sync'
        `);
        
        if (portfolioHoldingsCheck.rows.length === 0) {
            // Check if table exists at all
            const tableCheck = await client.query(`
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_name = 'portfolio_holdings'
            `);
            
            if (tableCheck.rows.length > 0) {
                log('info', '📝 Adding missing last_sync column to portfolio_holdings table');
                await client.query(`
                    ALTER TABLE portfolio_holdings 
                    ADD COLUMN IF NOT EXISTS last_sync TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                `);
            }
        }
        
        log('info', '✅ Table column validation completed');
        
    } catch (error) {
        log('error', '❌ Error ensuring table columns exist:', error.message);
        // Don't throw error here - we want to continue with schema creation
    }
}

async function checkTablesExist(client) {
    const result = await client.query(`
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        ORDER BY table_name;
    `);
    
    const existingTables = result.rows.map(row => row.table_name);
    const criticalTables = [
        'user_api_keys', 'portfolio_holdings', 'portfolio_metadata', 
        'watchlists', 'watchlist_items', 'trading_alerts', 'health_status',
        'stocks', 'prices', 'price_weekly', 'last_updated'
    ];
    
    return {
        existingTables,
        criticalTables,
        totalTables: existingTables.length,
        criticalTablesExist: criticalTables.filter(table => existingTables.includes(table))
    };
}

function getWebappDatabaseSchema() {
    return `
-- ================================
-- WEBAPP CORE TABLES
-- ================================

-- Note: stock_symbols table should be created by the main data loading scripts
-- We only create webapp-specific tables here

-- Create last_updated table
CREATE TABLE IF NOT EXISTS last_updated (
    script_name VARCHAR(255) PRIMARY KEY,
    last_run TIMESTAMP WITH TIME ZONE
);

-- ================================
-- USER AND API MANAGEMENT
-- ================================

-- Create API Keys table
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
    validation_status VARCHAR(50) DEFAULT 'PENDING',
    validation_message TEXT,
    validation_details JSONB,
    last_validated TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP
);

-- Create unique index to allow one active API key per user, provider, and account type
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_api_keys_active_unique 
ON user_api_keys (user_id, provider, is_sandbox) 
WHERE is_active = true;

-- ================================
-- PORTFOLIO MANAGEMENT
-- ================================

-- Create Portfolio Holdings table
CREATE TABLE IF NOT EXISTS portfolio_holdings (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    api_key_id INTEGER,
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

-- Create Portfolio Metadata table
CREATE TABLE IF NOT EXISTS portfolio_metadata (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    api_key_id INTEGER,
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

-- ================================
-- TRADING AND ALERTS
-- ================================

-- Create Trading Alerts table
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

-- Create Trading Strategies table
CREATE TABLE IF NOT EXISTS trading_strategies (
    id VARCHAR(255) PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    strategy_type VARCHAR(50) NOT NULL,
    configuration JSONB NOT NULL,
    provider VARCHAR(50) DEFAULT 'alpaca',
    is_active BOOLEAN DEFAULT false,
    status VARCHAR(50) DEFAULT 'registered',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create Strategy Executions table
CREATE TABLE IF NOT EXISTS strategy_executions (
    id VARCHAR(255) PRIMARY KEY,
    strategy_id VARCHAR(255) NOT NULL,
    execution_type VARCHAR(50) NOT NULL,
    signal_data JSONB,
    orders_placed JSONB,
    execution_result JSONB,
    error_message TEXT,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (strategy_id) REFERENCES trading_strategies(id) ON DELETE CASCADE
);

-- ================================
-- WATCHLISTS
-- ================================

-- Create Watchlists table
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

-- Create Watchlist Items table
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

-- ================================
-- INSTITUTIONAL TRADING SYSTEM
-- ================================

-- Trade Executions (from broker APIs)
CREATE TABLE IF NOT EXISTS trade_executions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    api_key_id INTEGER REFERENCES user_api_keys(id),
    broker VARCHAR(50) NOT NULL, -- 'alpaca', 'td_ameritrade', 'interactive_brokers'
    
    -- Trade Identification
    trade_id VARCHAR(100) NOT NULL, -- Broker's trade ID
    order_id VARCHAR(100), -- Original order ID
    
    -- Security Information
    symbol VARCHAR(20) NOT NULL,
    asset_class VARCHAR(20) NOT NULL DEFAULT 'equity', -- 'equity', 'option', 'crypto', 'forex'
    security_type VARCHAR(50) DEFAULT 'stock', -- 'stock', 'etf', 'call', 'put', etc.
    
    -- Execution Details
    side VARCHAR(10) NOT NULL, -- 'buy', 'sell', 'short', 'cover'
    quantity DECIMAL(15,6) NOT NULL,
    price DECIMAL(15,8) NOT NULL,
    commission DECIMAL(10,4) DEFAULT 0,
    fees DECIMAL(10,4) DEFAULT 0,
    
    -- Timing
    execution_time TIMESTAMP WITH TIME ZONE NOT NULL,
    settlement_date DATE,
    
    -- Market Data at Execution
    bid_price DECIMAL(15,8),
    ask_price DECIMAL(15,8),
    market_price DECIMAL(15,8),
    volume_at_execution BIGINT,
    
    -- Metadata
    venue VARCHAR(50), -- Exchange/venue
    order_type VARCHAR(20), -- 'market', 'limit', 'stop', etc.
    time_in_force VARCHAR(20), -- 'day', 'gtc', etc.
    
    -- Import tracking
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(broker, trade_id)
);

-- Create indexes for trade_executions
CREATE INDEX IF NOT EXISTS idx_trade_executions_user_id ON trade_executions(user_id);
CREATE INDEX IF NOT EXISTS idx_trade_executions_symbol ON trade_executions(symbol);
CREATE INDEX IF NOT EXISTS idx_trade_executions_execution_time ON trade_executions(execution_time);
CREATE INDEX IF NOT EXISTS idx_trade_executions_broker ON trade_executions(broker);

-- Reconstructed Positions from Executions
CREATE TABLE IF NOT EXISTS position_history (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    asset_class VARCHAR(20) NOT NULL DEFAULT 'equity',
    
    -- Position Timeline
    opened_at TIMESTAMP WITH TIME ZONE NOT NULL,
    closed_at TIMESTAMP WITH TIME ZONE,
    
    -- Position Details
    side VARCHAR(10) NOT NULL, -- 'long', 'short'
    total_quantity DECIMAL(15,6) NOT NULL,
    avg_entry_price DECIMAL(15,8) NOT NULL,
    avg_exit_price DECIMAL(15,8),
    
    -- Financial Results
    gross_pnl DECIMAL(15,4),
    net_pnl DECIMAL(15,4), -- After commissions/fees
    total_commissions DECIMAL(10,4),
    total_fees DECIMAL(10,4),
    
    -- Performance Metrics
    return_percentage DECIMAL(8,4),
    holding_period_days DECIMAL(8,2),
    max_adverse_excursion DECIMAL(8,4), -- MAE
    max_favorable_excursion DECIMAL(8,4), -- MFE
    
    -- Market Context
    entry_market_cap DECIMAL(20,2),
    sector VARCHAR(100),
    industry VARCHAR(150),
    
    -- Risk Metrics
    position_size_percentage DECIMAL(6,4), -- % of portfolio
    portfolio_beta DECIMAL(6,4),
    position_volatility DECIMAL(6,4),
    
    -- Status
    status VARCHAR(20) DEFAULT 'open', -- 'open', 'closed', 'partially_closed'
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for position_history
CREATE INDEX IF NOT EXISTS idx_position_history_user_id ON position_history(user_id);
CREATE INDEX IF NOT EXISTS idx_position_history_symbol ON position_history(symbol);
CREATE INDEX IF NOT EXISTS idx_position_history_opened_at ON position_history(opened_at);
CREATE INDEX IF NOT EXISTS idx_position_history_status ON position_history(status);

-- Advanced Trade Analytics
CREATE TABLE IF NOT EXISTS trade_analytics (
    id SERIAL PRIMARY KEY,
    position_id INTEGER REFERENCES position_history(id),
    user_id VARCHAR(255) NOT NULL,
    
    -- Entry Analysis
    entry_signal_quality DECIMAL(4,2), -- 0-100 score
    entry_timing_score DECIMAL(4,2), -- Relative to optimal entry
    entry_market_regime VARCHAR(50), -- 'trending', 'ranging', 'volatile', etc.
    entry_rsi DECIMAL(6,2),
    entry_relative_strength DECIMAL(8,4), -- vs sector/market
    
    -- Exit Analysis
    exit_signal_quality DECIMAL(4,2),
    exit_timing_score DECIMAL(4,2),
    exit_reason VARCHAR(100), -- 'stop_loss', 'take_profit', 'time_decay', etc.
    
    -- Risk Management
    initial_risk_amount DECIMAL(15,4),
    risk_reward_ratio DECIMAL(6,2),
    position_sizing_score DECIMAL(4,2), -- Kelly criterion based
    
    -- Performance Attribution
    market_return_during_trade DECIMAL(8,4), -- SPY return during trade
    sector_return_during_trade DECIMAL(8,4),
    alpha_generated DECIMAL(8,4), -- Return vs benchmark
    
    -- Behavioral Analysis
    emotional_state_score DECIMAL(4,2), -- Derived from trading patterns
    discipline_score DECIMAL(4,2), -- Adherence to rules
    cognitive_bias_flags JSONB, -- Array of detected biases
    
    -- Pattern Recognition
    trade_pattern_type VARCHAR(100), -- 'breakout', 'mean_reversion', etc.
    pattern_confidence DECIMAL(4,2), -- 0-100 confidence in pattern
    pattern_success_rate DECIMAL(4,2), -- Historical success rate
    
    -- Market Analysis
    market_volatility_regime VARCHAR(50),
    sector_momentum DECIMAL(8,4),
    correlation_to_market DECIMAL(6,4),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for trade_analytics
CREATE INDEX IF NOT EXISTS idx_trade_analytics_position_id ON trade_analytics(position_id);
CREATE INDEX IF NOT EXISTS idx_trade_analytics_user_id ON trade_analytics(user_id);

-- Performance Benchmarks (time-series data)
CREATE TABLE IF NOT EXISTS performance_benchmarks (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    benchmark_date DATE NOT NULL,
    
    -- Portfolio Performance
    portfolio_value DECIMAL(15,4),
    daily_return DECIMAL(8,4),
    cumulative_return DECIMAL(8,4),
    volatility DECIMAL(6,4),
    
    -- Risk Metrics
    sharpe_ratio DECIMAL(6,4),
    sortino_ratio DECIMAL(6,4),
    max_drawdown DECIMAL(6,4),
    beta DECIMAL(6,4),
    
    -- Benchmark Comparisons
    spy_return DECIMAL(8,4),
    sector_return DECIMAL(8,4),
    alpha DECIMAL(8,4),
    
    -- Trading Activity
    trades_count INTEGER DEFAULT 0,
    win_rate DECIMAL(4,2),
    avg_hold_days DECIMAL(6,2),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(user_id, benchmark_date)
);

-- Create indexes for performance_benchmarks
CREATE INDEX IF NOT EXISTS idx_performance_benchmarks_user_id ON performance_benchmarks(user_id);
CREATE INDEX IF NOT EXISTS idx_performance_benchmarks_date ON performance_benchmarks(benchmark_date);

-- Trade Import Tracking
CREATE TABLE IF NOT EXISTS trade_import_logs (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    broker VARCHAR(20) NOT NULL,
    import_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    trades_imported INTEGER DEFAULT 0,
    positions_processed INTEGER DEFAULT 0,
    date_range_start DATE,
    date_range_end DATE,
    status VARCHAR(20) DEFAULT 'completed', -- 'in_progress', 'completed', 'failed'
    error_message TEXT,
    
    -- Performance tracking
    execution_time_seconds DECIMAL(8,2),
    api_calls_made INTEGER DEFAULT 0,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for trade_import_logs
CREATE INDEX IF NOT EXISTS idx_trade_import_logs_user_id ON trade_import_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_trade_import_logs_broker ON trade_import_logs(broker);
CREATE INDEX IF NOT EXISTS idx_trade_import_logs_date ON trade_import_logs(import_date);

-- Broker API Configuration
CREATE TABLE IF NOT EXISTS broker_api_configs (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    broker VARCHAR(20) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_paper_trading BOOLEAN DEFAULT TRUE,
    
    -- Sync Configuration
    auto_sync_enabled BOOLEAN DEFAULT FALSE,
    sync_frequency_hours INTEGER DEFAULT 24,
    last_sync_date TIMESTAMP,
    last_sync_status VARCHAR(20), -- 'success', 'failed', 'in_progress'
    last_sync_error TEXT,
    
    -- Import Statistics
    total_trades_imported INTEGER DEFAULT 0,
    last_import_date TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(user_id, broker)
);

-- Create indexes for broker_api_configs
CREATE INDEX IF NOT EXISTS idx_broker_api_configs_user_id ON broker_api_configs(user_id);
CREATE INDEX IF NOT EXISTS idx_broker_api_configs_broker ON broker_api_configs(broker);

-- Trade Insights (AI-generated recommendations)
CREATE TABLE IF NOT EXISTS trade_insights (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    insight_type VARCHAR(50) NOT NULL, -- 'pattern', 'risk', 'timing', 'behavioral'
    
    -- Insight Details
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    severity VARCHAR(20) DEFAULT 'medium', -- 'low', 'medium', 'high', 'critical'
    confidence_score DECIMAL(4,2), -- 0-100 confidence
    
    -- Related Data
    related_positions INTEGER[], -- Array of position IDs
    related_symbols VARCHAR(10)[],
    time_period_start DATE,
    time_period_end DATE,
    
    -- Recommendations
    recommended_action VARCHAR(100),
    potential_impact_description TEXT,
    quantified_impact DECIMAL(8,4), -- Expected P&L impact
    
    -- Metadata
    is_read BOOLEAN DEFAULT FALSE,
    is_dismissed BOOLEAN DEFAULT FALSE,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for trade_insights
CREATE INDEX IF NOT EXISTS idx_trade_insights_user_id ON trade_insights(user_id);
CREATE INDEX IF NOT EXISTS idx_trade_insights_type ON trade_insights(insight_type);
CREATE INDEX IF NOT EXISTS idx_trade_insights_severity ON trade_insights(severity);

-- ================================
-- HEALTH AND MONITORING
-- ================================

-- Create Health Status table
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

-- Create Performance Metrics table for real-time monitoring
CREATE TABLE IF NOT EXISTS performance_metrics (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    uptime BIGINT NOT NULL,
    active_requests INTEGER NOT NULL DEFAULT 0,
    total_requests BIGINT NOT NULL DEFAULT 0,
    total_errors BIGINT NOT NULL DEFAULT 0,
    error_rate REAL NOT NULL DEFAULT 0,
    avg_response_time REAL NOT NULL DEFAULT 0,
    memory_used BIGINT NOT NULL DEFAULT 0,
    memory_total BIGINT NOT NULL DEFAULT 0,
    metrics_data JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance metrics
CREATE INDEX IF NOT EXISTS idx_performance_metrics_timestamp ON performance_metrics(timestamp);
CREATE INDEX IF NOT EXISTS idx_performance_metrics_error_rate ON performance_metrics(error_rate);
CREATE INDEX IF NOT EXISTS idx_performance_metrics_response_time ON performance_metrics(avg_response_time);

-- ================================
-- STOCK SYMBOL AND COMPANY DATA TABLES
-- ================================

-- Create stock_symbols table (if not exists)
CREATE TABLE IF NOT EXISTS stock_symbols (
    symbol VARCHAR(10) PRIMARY KEY,
    security_name VARCHAR(200),
    market_category VARCHAR(10),
    test_issue BOOLEAN DEFAULT FALSE,
    financial_status VARCHAR(10),
    round_lot_size INTEGER,
    exchange VARCHAR(10),
    nasdaq_symbol BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create company_profile table (from loadinfo.py schema)
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

-- Create leadership_team table
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

-- Create governance_scores table
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

-- Create market_data table
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
    regular_market_time_ms BIGINT,
    post_market_change_percent NUMERIC,
    post_market_change NUMERIC,
    post_market_price NUMERIC,
    post_market_time_ms BIGINT,
    pre_market_change_percent NUMERIC,
    pre_market_change NUMERIC,
    pre_market_price NUMERIC,
    pre_market_time_ms BIGINT,
    bid NUMERIC,
    ask NUMERIC,
    bid_size INT,
    ask_size INT,
    fifty_two_week_low NUMERIC,
    fifty_two_week_high NUMERIC,
    fifty_two_week_change NUMERIC,
    fifty_two_week_change_pct NUMERIC,
    fifty_day_avg NUMERIC,
    fifty_day_avg_change NUMERIC,
    fifty_day_avg_change_pct NUMERIC,
    two_hundred_day_avg NUMERIC,
    two_hundred_day_avg_change NUMERIC,
    two_hundred_day_avg_change_pct NUMERIC,
    source_interval_sec INT,
    market_cap BIGINT
);

-- Create key_metrics table
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

-- Create analyst_estimates table
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
-- BASIC PRICE DATA TABLES
-- ================================

-- Create prices table
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

-- Create price_weekly table
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

-- ================================
-- INDEXES FOR PERFORMANCE
-- ================================

-- User API Keys indexes
CREATE INDEX IF NOT EXISTS idx_user_api_keys_user_id ON user_api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_user_api_keys_provider ON user_api_keys(provider);
CREATE INDEX IF NOT EXISTS idx_user_api_keys_active ON user_api_keys(is_active);

-- Portfolio Holdings indexes - optimized for performance
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_user_id ON portfolio_holdings(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_symbol ON portfolio_holdings(symbol);
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_broker ON portfolio_holdings(broker);
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_user_api_key ON portfolio_holdings(user_id, api_key_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_user_symbol ON portfolio_holdings(user_id, symbol);
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_market_value ON portfolio_holdings(market_value DESC);
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_updated_at ON portfolio_holdings(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_user_active ON portfolio_holdings(user_id, api_key_id, updated_at DESC) WHERE quantity > 0;

-- Portfolio Metadata indexes - optimized for performance
CREATE INDEX IF NOT EXISTS idx_portfolio_metadata_user_id ON portfolio_metadata(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_metadata_user_api_key ON portfolio_metadata(user_id, api_key_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_metadata_last_sync ON portfolio_metadata(last_sync DESC);

-- User API Keys indexes - optimized for portfolio queries
CREATE INDEX IF NOT EXISTS idx_user_api_keys_user_active ON user_api_keys(user_id, is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_user_api_keys_sandbox ON user_api_keys(user_id, is_sandbox, is_active) WHERE is_active = true;

-- Trading Alerts indexes
CREATE INDEX IF NOT EXISTS idx_trading_alerts_user_id ON trading_alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_trading_alerts_symbol ON trading_alerts(symbol);
CREATE INDEX IF NOT EXISTS idx_trading_alerts_active ON trading_alerts(is_active);

-- Watchlists indexes
CREATE INDEX IF NOT EXISTS idx_watchlists_user_id ON watchlists(user_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_items_watchlist_id ON watchlist_items(watchlist_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_items_symbol ON watchlist_items(symbol);

-- Health Status indexes
CREATE INDEX IF NOT EXISTS idx_health_status_status ON health_status(status);
CREATE INDEX IF NOT EXISTS idx_health_status_last_updated ON health_status(last_updated);
CREATE INDEX IF NOT EXISTS idx_health_status_category ON health_status(table_category);
CREATE INDEX IF NOT EXISTS idx_health_status_critical ON health_status(critical_table);

-- Price data indexes
CREATE INDEX IF NOT EXISTS idx_prices_symbol ON prices(symbol);
CREATE INDEX IF NOT EXISTS idx_prices_date ON prices(date);
CREATE INDEX IF NOT EXISTS idx_price_weekly_symbol ON price_weekly(symbol);
CREATE INDEX IF NOT EXISTS idx_price_weekly_date ON price_weekly(date);

-- Stock symbol and company data indexes
CREATE INDEX IF NOT EXISTS idx_stock_symbols_symbol ON stock_symbols(symbol);
CREATE INDEX IF NOT EXISTS idx_stock_symbols_exchange ON stock_symbols(exchange);
CREATE INDEX IF NOT EXISTS idx_stock_symbols_market_category ON stock_symbols(market_category);

-- Company profile indexes
CREATE INDEX IF NOT EXISTS idx_company_profile_ticker ON company_profile(ticker);
CREATE INDEX IF NOT EXISTS idx_company_profile_sector ON company_profile(sector);
CREATE INDEX IF NOT EXISTS idx_company_profile_industry ON company_profile(industry);
CREATE INDEX IF NOT EXISTS idx_company_profile_exchange ON company_profile(exchange);

-- Leadership team indexes
CREATE INDEX IF NOT EXISTS idx_leadership_team_ticker ON leadership_team(ticker);
CREATE INDEX IF NOT EXISTS idx_leadership_team_title ON leadership_team(title);

-- Market data indexes
CREATE INDEX IF NOT EXISTS idx_market_data_ticker ON market_data(ticker);
CREATE INDEX IF NOT EXISTS idx_market_data_market_cap ON market_data(market_cap);

-- Key metrics indexes
CREATE INDEX IF NOT EXISTS idx_key_metrics_ticker ON key_metrics(ticker);
CREATE INDEX IF NOT EXISTS idx_key_metrics_pe ON key_metrics(trailing_pe);
CREATE INDEX IF NOT EXISTS idx_key_metrics_market_cap ON key_metrics(enterprise_value);

-- Analyst estimates indexes
CREATE INDEX IF NOT EXISTS idx_analyst_estimates_ticker ON analyst_estimates(ticker);
CREATE INDEX IF NOT EXISTS idx_analyst_estimates_recommendation ON analyst_estimates(recommendation_key);

-- ================================
-- INITIALIZE HEALTH STATUS
-- ================================

-- Insert health status records for critical tables
INSERT INTO health_status (table_name, table_category, critical_table, expected_update_frequency) VALUES
('user_api_keys', 'webapp', true, '1 hour'),
('portfolio_holdings', 'webapp', true, '1 hour'),
('portfolio_metadata', 'webapp', true, '1 hour'),
('trading_alerts', 'webapp', false, '1 hour'),
('watchlists', 'webapp', false, '1 hour'),
('watchlist_items', 'webapp', false, '1 hour'),
('trade_executions', 'trading', true, '1 hour'),
('position_history', 'trading', true, '1 hour'),
('trade_analytics', 'trading', false, '1 hour'),
('performance_benchmarks', 'trading', false, '1 day'),
('trade_import_logs', 'trading', false, '1 day'),
('broker_api_configs', 'trading', false, '1 day'),
('trade_insights', 'trading', false, '1 hour'),
('stock_symbols', 'market_data', true, '1 day'),
('company_profile', 'market_data', true, '1 week'),
('leadership_team', 'market_data', false, '1 week'),
('governance_scores', 'market_data', false, '1 week'),
('market_data', 'market_data', true, '1 day'),
('key_metrics', 'market_data', true, '1 day'),
('analyst_estimates', 'market_data', false, '1 day'),
('prices', 'market_data', true, '1 day'),
('price_weekly', 'market_data', true, '1 week'),
('last_updated', 'system', true, '1 hour'),
('health_status', 'system', true, '1 hour')
ON CONFLICT (table_name) DO NOTHING;
`;
}

async function connectWithRetry(dbConfig, maxRetries = 3) {
    // Try different connection configurations - prioritize RDS public subnet configs
    const connectionConfigs = [
        { 
            ...dbConfig, 
            ssl: false,
            connectionTimeoutMillis: 20000 
        }, // No SSL - RDS public subnet standard
        { 
            ...dbConfig, 
            ssl: false,
            connectionTimeoutMillis: 30000,
            keepAlive: true
        }, // No SSL with keep-alive
        { 
            ...dbConfig, 
            ssl: { require: false, rejectUnauthorized: false },
            connectionTimeoutMillis: 25000
        }, // SSL optional fallback
    ];
    log('info', '🔧 Database Connection Diagnostics');
    log('info', `   Host: ${dbConfig.host}`);
    log('info', `   Port: ${dbConfig.port}`);
    log('info', `   Database: ${dbConfig.database}`);
    log('info', `   Username: ${dbConfig.user}`);
    log('info', `   SSL Required: ${dbConfig.ssl?.require || 'false'}`);
    log('info', `   SSL Reject Unauthorized: ${dbConfig.ssl?.rejectUnauthorized || 'false'}`);
    log('info', `   Connection Timeout: ${dbConfig.connectionTimeoutMillis}ms`);
    log('info', `   Max Retries: ${maxRetries}`);
    
    for (let configIndex = 0; configIndex < connectionConfigs.length; configIndex++) {
        const currentConfig = connectionConfigs[configIndex];
        log('info', `🔄 Trying connection config ${configIndex + 1}/${connectionConfigs.length}`);
        log('info', `   SSL Mode: ${JSON.stringify(currentConfig.ssl)}`);
        
        // Create client with current configuration
        const client = new Client({
            ...currentConfig,
            connectionTimeoutMillis: 30000, // 30 seconds - conservative
            query_timeout: 30000, // 30 seconds for queries
            statement_timeout: 30000 // 30 seconds for statements
        });
        
        // Add client event listeners for debugging
        client.on('connect', () => {
            log('info', '🔗 Client connected to database');
        });
        
        client.on('error', (err) => {
            log('error', `🔌 Client error: ${err.message}`);
            log('error', `   Error code: ${err.code}`);
            log('error', `   Error severity: ${err.severity}`);
            log('error', `   Error detail: ${err.detail}`);
            log('error', `   Error hint: ${err.hint}`);
        });
        
        client.on('end', () => {
            log('info', '🔌 Client disconnected from database');
        });
        
        try {
            log('info', `🔗 Attempting database connection to ${dbConfig.host}:${dbConfig.port}...`);
            log('info', `   Using SSL: ${JSON.stringify(dbConfig.ssl)}`);
            
            const startTime = Date.now();
            await client.connect();
            const connectTime = Date.now() - startTime;
            
            log('info', `✅ Database connection successful in ${connectTime}ms`);
            
            // Test the connection with comprehensive query
            log('info', '🧪 Testing database connectivity...');
            const testStart = Date.now();
            const testResult = await client.query(`
                SELECT 
                    current_database() as database_name,
                    current_user as connected_user,
                    inet_server_addr() as server_address,
                    inet_server_port() as server_port,
                    version() as postgresql_version,
                    current_timestamp as connection_time
            `);
            const testTime = Date.now() - testStart;
            
            log('info', `✅ Database connectivity test passed in ${testTime}ms`);
            log('info', `   Database: ${testResult.rows[0].database_name}`);
            log('info', `   Connected as: ${testResult.rows[0].connected_user}`);
            log('info', `   Server: ${testResult.rows[0].server_address}:${testResult.rows[0].server_port}`);
            log('info', `   PostgreSQL: ${testResult.rows[0].postgresql_version.split(' ')[0]}`);
            
            return client;
        } catch (error) {
            const connectTime = Date.now() - startTime;
            log('error', `❌ Connection attempt ${attempt} failed after ${connectTime}ms`);
            log('error', `   Error: ${error.message}`);
            log('error', `   Error code: ${error.code}`);
            log('error', `   Error errno: ${error.errno}`);
            log('error', `   Error syscall: ${error.syscall}`);
            log('error', `   Error address: ${error.address}`);
            log('error', `   Error port: ${error.port}`);
            
            // Enhanced error analysis
            if (error.code === 'ECONNREFUSED') {
                log('error', '🚨 ECONNREFUSED: Database server is not accepting connections');
                log('error', '   Possible causes:');
                log('error', '   1. Database server is down');
                log('error', '   2. Security group blocking port 5432');
                log('error', '   3. Database not listening on expected port');
                log('error', '   4. Network ACL blocking connection');
            } else if (error.code === 'ECONNRESET') {
                log('error', '🚨 ECONNRESET: Connection was reset by database server');
                log('error', '   Possible causes:');
                log('error', '   1. SSL/TLS handshake failure');
                log('error', '   2. Database rejecting connection');
                log('error', '   3. Network firewall dropping connection');
            } else if (error.code === 'ENOTFOUND') {
                log('error', '🚨 ENOTFOUND: DNS resolution failed');
                log('error', '   Possible causes:');
                log('error', '   1. Incorrect database hostname');
                log('error', '   2. DNS resolution issues');
                log('error', '   3. Network connectivity problems');
            } else if (error.code === 'ETIMEDOUT') {
                log('error', '🚨 ETIMEDOUT: Connection attempt timed out');
                log('error', '   Possible causes:');
                log('error', '   1. Security group not allowing inbound connections');
                log('error', '   2. Database server overloaded');
                log('error', '   3. Network routing issues');
            } else if (error.message.includes('password authentication failed')) {
                log('error', '🚨 AUTHENTICATION FAILED: Wrong username or password');
                log('error', '   Possible causes:');
                log('error', '   1. Incorrect credentials in Secrets Manager');
                log('error', '   2. Database user does not exist');
                log('error', '   3. Database user lacks necessary permissions');
            } else if (error.message.includes('SSL')) {
                log('error', '🚨 SSL ERROR: SSL/TLS connection failed');
                log('error', '   Possible causes:');
                log('error', '   1. Database not configured for SSL');
                log('error', '   2. Certificate validation issues');
                log('error', '   3. SSL protocol mismatch');
            }
            
            try {
                await client.end();
                log('info', '🔌 Client connection closed after error');
            } catch (closeError) {
                log('error', `⚠️ Error closing client: ${closeError.message}`);
            }
            
            if (configIndex === connectionConfigs.length - 1) {
                log('error', `🚫 All ${connectionConfigs.length} connection configurations failed`);
                throw new Error(`Failed to connect with any configuration. Last error: ${error.message}`);
            }
            
            // Brief wait before trying next configuration
            log('info', `⏳ Waiting 2 seconds before trying next configuration...`);
            await new Promise(resolve => setTimeout(resolve, 2000));
        }
    }
}

async function testNetworkConnectivity(host, port) {
    log('info', '🌐 Enhanced Network Connectivity Test');
    log('info', `   Target: ${host}:${port}`);
    
    try {
        // 1. DNS resolution test with comprehensive output
        log('info', '🔍 Step 1: DNS Resolution Test');
        const dns = require('dns').promises;
        const addresses = await dns.lookup(host, { all: true });
        
        if (Array.isArray(addresses)) {
            log('info', `✅ DNS resolution successful: ${host} has ${addresses.length} addresses`);
            addresses.forEach((addr, index) => {
                log('info', `   Address ${index + 1}: ${addr.address} (${addr.family === 4 ? 'IPv4' : 'IPv6'})`);
            });
        } else {
            log('info', `✅ DNS resolution successful: ${host} -> ${addresses.address}`);
        }
        
        // 2. Test network route information
        log('info', '🔍 Step 2: Network Environment Check');
        const os = require('os');
        const networkInterfaces = os.networkInterfaces();
        
        log('info', '   Local Network Interfaces:');
        Object.keys(networkInterfaces).forEach(name => {
            const interfaces = networkInterfaces[name];
            interfaces.forEach(iface => {
                if (!iface.internal) {
                    log('info', `     ${name}: ${iface.address} (${iface.family})`);
                }
            });
        });
        
        // 3. TCP connection test with enhanced diagnostics
        log('info', '🔍 Step 3: TCP Connection Test');
        const net = require('net');
        
        return new Promise((resolve, reject) => {
            const socket = new net.Socket();
            const startTime = Date.now();
            
            const timeout = setTimeout(() => {
                const elapsed = Date.now() - startTime;
                socket.destroy();
                log('error', `❌ TCP connection timeout after ${elapsed}ms`);
                log('error', '   Possible causes:');
                log('error', '   1. Security group blocking outbound connections');
                log('error', '   2. Database security group not allowing inbound from this subnet');
                log('error', '   3. Network ACL blocking the connection');
                log('error', '   4. Database is in different VPC/subnet');
                log('error', '   5. Route table configuration issue');
                reject(new Error(`Network timeout: Cannot reach ${host}:${port} after ${elapsed}ms`));
            }, 15000); // 15 second timeout
            
            socket.connect(port, host, () => {
                const elapsed = Date.now() - startTime;
                clearTimeout(timeout);
                socket.destroy();
                log('info', `✅ TCP connection successful in ${elapsed}ms`);
                log('info', `   Local address: ${socket.localAddress}:${socket.localPort}`);
                log('info', `   Remote address: ${socket.remoteAddress}:${socket.remotePort}`);
                resolve(true);
            });
            
            socket.on('error', (error) => {
                const elapsed = Date.now() - startTime;
                clearTimeout(timeout);
                socket.destroy();
                
                log('error', `❌ TCP connection failed after ${elapsed}ms`);
                log('error', `   Error: ${error.message}`);
                log('error', `   Error code: ${error.code}`);
                log('error', `   Error errno: ${error.errno}`);
                log('error', `   Error syscall: ${error.syscall}`);
                
                if (error.code === 'ECONNREFUSED') {
                    log('error', '🚨 ECONNREFUSED - Port is not accepting connections');
                    log('error', '   Likely causes:');
                    log('error', '   1. RDS instance is stopped or unavailable');
                    log('error', '   2. Database security group blocking inbound port 5432');
                    log('error', '   3. Database is in different subnet than expected');
                } else if (error.code === 'EHOSTUNREACH') {
                    log('error', '🚨 EHOSTUNREACH - Cannot route to host');
                    log('error', '   Likely causes:');
                    log('error', '   1. RDS instance is in different VPC');
                    log('error', '   2. Route table missing route to database subnet');
                    log('error', '   3. Network ACL blocking connection');
                } else if (error.code === 'ENETUNREACH') {
                    log('error', '🚨 ENETUNREACH - Network unreachable');
                    log('error', '   Likely causes:');
                    log('error', '   1. Subnet configuration issue');
                    log('error', '   2. Internet/NAT gateway configuration');
                    log('error', '   3. VPC peering or routing issue');
                }
                
                reject(new Error(`Network connectivity failed: ${error.message}`));
            });
            
            socket.on('timeout', () => {
                const elapsed = Date.now() - startTime;
                clearTimeout(timeout);
                socket.destroy();
                log('error', `❌ TCP connection timeout after ${elapsed}ms`);
                reject(new Error(`Socket timeout: Connection to ${host}:${port} timed out`));
            });
        });
    } catch (error) {
        log('error', `❌ Network connectivity test failed: ${error.message}`);
        if (error.code === 'ENOTFOUND') {
            log('error', '🚨 DNS resolution failed');
            log('error', '   Possible causes:');
            log('error', '   1. Incorrect database hostname');
            log('error', '   2. DNS server configuration issue');
            log('error', '   3. Network connectivity to DNS servers');
        }
        throw error;
    }
}

async function initializeWebappDatabase() {
    log('info', '🚀 Starting webapp database initialization v1.4 - TIMEOUT FIX');
    log('info', `Environment: ${process.env.ENVIRONMENT || 'unknown'}`);
    log('info', `AWS Region: ${process.env.AWS_REGION || 'unknown'}`);
    log('info', `DB Secret ARN: ${process.env.DB_SECRET_ARN ? 'set' : 'NOT SET'}`);
    
    let client;
    
    try {
        // Get database credentials
        const dbConfig = await getDbCredentials();
        log('info', `Target database: ${dbConfig.host}:${dbConfig.port} (database: ${dbConfig.database})`);
        
        // Test network connectivity first
        await testNetworkConnectivity(dbConfig.host, dbConfig.port);
        
        // Connect to database with retry logic
        client = await connectWithRetry(dbConfig, 3);
        
        // Check existing tables
        const beforeStatus = await checkTablesExist(client);
        log('info', `📊 Found ${beforeStatus.totalTables} existing tables`);
        log('info', `📋 Critical tables present: ${beforeStatus.criticalTablesExist.join(', ')}`);
        
        // Initialize webapp database schema in parts to isolate any issues
        log('info', '🔧 Creating webapp database schema...');
        
        // First, check and add missing columns to existing tables
        await ensureTableColumnsExist(client);
        
        // Split schema into parts for better error isolation
        const schemaSQL = getWebappDatabaseSchema();
        const schemaParts = schemaSQL.split(/(?=CREATE TABLE|CREATE INDEX|INSERT INTO)/);
        
        for (let i = 0; i < schemaParts.length; i++) {
            const part = schemaParts[i].trim();
            if (part && !part.startsWith('--') && part.length > 10) {
                try {
                    await executeSQL(client, part, `Schema part ${i + 1}`);
                } catch (error) {
                    log('error', `❌ Schema part ${i + 1} failed:`, error.message);
                    log('error', `Problematic SQL: ${part.substring(0, 200)}...`);
                    
                    // Check if this is a column missing error for index creation
                    if (error.code === '42703' && part.includes('CREATE INDEX')) {
                        log('warn', `⚠️ Skipping index creation due to missing column - this may be expected if table schema has changed`);
                        continue; // Skip this index creation and continue with other parts
                    }
                    
                    throw error;
                }
            }
        }
        
        // Test database connectivity with a simple query
        await executeSQL(client, `
            SELECT current_database() as db_name, 
                   current_user as db_user, 
                   inet_server_addr() as server_ip,
                   version() as db_version;
        `, 'Test database connectivity');
        
        // Update last_updated tracking
        await executeSQL(client, `
            INSERT INTO last_updated (script_name, last_run) 
            VALUES ('webapp_db_init_ecs', NOW())
            ON CONFLICT (script_name) 
            DO UPDATE SET last_run = EXCLUDED.last_run;
        `, 'Update last_updated tracking');
        
        // Verify tables after creation
        const afterStatus = await checkTablesExist(client);
        log('info', `✅ Database now has ${afterStatus.totalTables} tables`);
        log('info', `✅ Critical tables: ${afterStatus.criticalTablesExist.length}/${afterStatus.criticalTables.length}`);
        
        log('info', '🎉 Webapp database initialization completed successfully');
        return 0;
        
    } catch (error) {
        log('error', '❌ Webapp database initialization failed:', error.message);
        log('error', 'Full error details:', error);
        if (error.code) {
            log('error', `Error code: ${error.code}`);
        }
        if (error.stack) {
            log('error', 'Stack trace:', error.stack);
        }
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
    initializeWebappDatabase().then(exitCode => {
        process.exit(exitCode);
    }).catch(error => {
        log('error', 'Unhandled error:', error);
        process.exit(1);
    });
}

module.exports = { initializeWebappDatabase };
