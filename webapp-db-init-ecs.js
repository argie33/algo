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