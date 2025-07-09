#!/usr/bin/env node
/**
 * ECS-based Webapp Database Initialization Script
 * Runs as an ECS task during deployment to initialize webapp database tables
 */

const { Client } = require('pg');
const AWS = require('aws-sdk');

// Configure AWS SDK
const secretsManager = new AWS.SecretsManager({
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
            throw new Error('DB_SECRET_ARN environment variable not set');
        }
        
        const response = await secretsManager.getSecretValue({ SecretId: secretArn }).promise();
        const secret = JSON.parse(response.SecretString);
        
        return {
            host: secret.host,
            port: parseInt(secret.port) || 5432,
            database: secret.dbname || 'postgres',
            user: secret.username,
            password: secret.password,
            ssl: {
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

-- Create stocks table
CREATE TABLE IF NOT EXISTS stocks (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    market VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP,
    UNIQUE(user_id, provider)
);

-- ================================
-- PORTFOLIO MANAGEMENT
-- ================================

-- Create Portfolio Holdings table
CREATE TABLE IF NOT EXISTS portfolio_holdings (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    quantity DECIMAL(15,4) NOT NULL,
    market_value DECIMAL(15,2),
    cost_basis DECIMAL(15,2),
    pnl DECIMAL(15,2),
    pnl_percent DECIMAL(8,4),
    weight DECIMAL(8,4),
    sector VARCHAR(100),
    current_price DECIMAL(12,4),
    average_entry_price DECIMAL(12,4),
    day_change DECIMAL(15,2),
    day_change_percent DECIMAL(8,4),
    exchange VARCHAR(20),
    broker VARCHAR(50),
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, symbol, broker)
);

-- Create Portfolio Metadata table
CREATE TABLE IF NOT EXISTS portfolio_metadata (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    broker VARCHAR(50) NOT NULL,
    total_value DECIMAL(15,2),
    total_cash DECIMAL(15,2),
    total_pnl DECIMAL(15,2),
    total_pnl_percent DECIMAL(8,4),
    positions_count INTEGER,
    account_status VARCHAR(50),
    environment VARCHAR(20),
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, broker)
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

-- Portfolio Holdings indexes
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_user_id ON portfolio_holdings(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_symbol ON portfolio_holdings(symbol);
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_broker ON portfolio_holdings(broker);

-- Portfolio Metadata indexes
CREATE INDEX IF NOT EXISTS idx_portfolio_metadata_user_id ON portfolio_metadata(user_id);

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
CREATE INDEX IF NOT EXISTS idx_stocks_symbol ON stocks(symbol);

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
('stocks', 'symbols', true, '1 week'),
('prices', 'market_data', true, '1 day'),
('price_weekly', 'market_data', true, '1 week'),
('last_updated', 'system', true, '1 hour'),
('health_status', 'system', true, '1 hour')
ON CONFLICT (table_name) DO NOTHING;
`;
}

async function initializeWebappDatabase() {
    log('info', '🚀 Starting webapp database initialization');
    
    let client;
    
    try {
        // Get database credentials
        const dbConfig = await getDbCredentials();
        
        // Connect to database
        log('info', `Connecting to database at ${dbConfig.host}:${dbConfig.port}`);
        client = new Client(dbConfig);
        await client.connect();
        log('info', '✅ Database connection successful');
        
        // Check existing tables
        const beforeStatus = await checkTablesExist(client);
        log('info', `📊 Found ${beforeStatus.totalTables} existing tables`);
        log('info', `📋 Critical tables present: ${beforeStatus.criticalTablesExist.join(', ')}`);
        
        // Initialize webapp database schema
        log('info', '🔧 Creating webapp database schema...');
        await executeSQL(client, getWebappDatabaseSchema(), 'Webapp database schema initialization');
        
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
        return 1;
    } finally {
        if (client) {
            await client.end();
            log('info', 'Database connection closed');
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