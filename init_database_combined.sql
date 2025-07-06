-- Combined Database Initialization Script
-- This script combines all database initialization schemas into a single comprehensive script
-- Created by combining: init.sql, create_scoring_tables.sql, create_health_status_table.sql, create_api_keys_table.sql

-- ================================
-- CORE TABLES (from init.sql)
-- ================================

-- Create stocks table if it doesn't exist
CREATE TABLE IF NOT EXISTS stocks (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    market VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create stock_symbols table (used by loadstocksymbols_test)
CREATE TABLE IF NOT EXISTS stock_symbols (
    symbol VARCHAR(50),
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

-- Create etf_symbols table (used by loadstocksymbols_test)
CREATE TABLE IF NOT EXISTS etf_symbols (
    symbol VARCHAR(50),
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

-- Create price_weekly table (used by loadpriceweekly)
CREATE TABLE IF NOT EXISTS price_weekly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(12,4),
    high DECIMAL(12,4),
    low DECIMAL(12,4),
    close DECIMAL(12,4),
    adj_close DECIMAL(12,4),
    volume BIGINT,
    dividends DECIMAL(10,4),
    stock_splits DECIMAL(10,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Create technicals_weekly table (used by loadtechnicalsweekly)
CREATE TABLE IF NOT EXISTS technicals_weekly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL,
    date DATE NOT NULL,
    
    -- Moving averages
    sma_20 DECIMAL(12,4),
    sma_50 DECIMAL(12,4),
    sma_200 DECIMAL(12,4),
    ema_12 DECIMAL(12,4),
    ema_26 DECIMAL(12,4),
    
    -- MACD
    macd DECIMAL(12,4),
    macd_signal DECIMAL(12,4),
    macd_histogram DECIMAL(12,4),
    
    -- RSI
    rsi_14 DECIMAL(8,4),
    
    -- Bollinger Bands
    bb_upper DECIMAL(12,4),
    bb_middle DECIMAL(12,4),
    bb_lower DECIMAL(12,4),
    
    -- Volume
    volume_sma_20 BIGINT,
    
    -- Pivot points
    pivot_high DECIMAL(12,4),
    pivot_low DECIMAL(12,4),
    
    -- Other indicators
    td_sequential INTEGER,
    td_combo INTEGER,
    marketwatch_signal VARCHAR(10),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Create last_updated table
CREATE TABLE IF NOT EXISTS last_updated (
    script_name VARCHAR(255) PRIMARY KEY,
    last_run TIMESTAMP WITH TIME ZONE
);

-- Create earnings and prices tables
CREATE TABLE IF NOT EXISTS earnings (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    fiscal_date_ending DATE,
    reported_eps DECIMAL(10,4),
    estimated_eps DECIMAL(10,4),
    surprise DECIMAL(10,4),
    surprise_percentage DECIMAL(8,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS prices (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    open_price DECIMAL(12,4),
    high_price DECIMAL(12,4),
    low_price DECIMAL(12,4),
    close_price DECIMAL(12,4),
    volume BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- ================================
-- API KEYS AND PORTFOLIO TABLES
-- ================================

-- Create user_api_keys table for storing encrypted API credentials
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

-- Create portfolio tables for storing imported data
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

-- Create trading_alerts table
CREATE TABLE IF NOT EXISTS trading_alerts (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    alert_type VARCHAR(50) NOT NULL, -- 'price_above', 'price_below', 'volume_surge', 'pattern'
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
-- COMPREHENSIVE SCORING SYSTEM
-- ================================

-- Enhanced stock symbols with sector/industry classification
CREATE TABLE IF NOT EXISTS stock_symbols_enhanced (
    symbol VARCHAR(10) PRIMARY KEY,
    company_name VARCHAR(255) NOT NULL,
    sector VARCHAR(100),
    industry VARCHAR(150),
    sub_industry VARCHAR(200),
    market_cap_tier VARCHAR(20), -- large_cap, mid_cap, small_cap, micro_cap
    exchange VARCHAR(10),
    currency VARCHAR(3) DEFAULT 'USD',
    country VARCHAR(50) DEFAULT 'US',
    is_active BOOLEAN DEFAULT TRUE,
    listing_date DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Market regime tracking for dynamic score weighting
CREATE TABLE IF NOT EXISTS market_regime (
    date DATE PRIMARY KEY,
    regime VARCHAR(20) NOT NULL, -- bull, bear, normal, transition
    confidence_score DECIMAL(5,2), -- 0-100 confidence in regime classification
    vix_level DECIMAL(6,2),
    yield_curve_slope DECIMAL(8,4),
    credit_spreads DECIMAL(8,4),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Master scoring table
CREATE TABLE IF NOT EXISTS stock_scores (
    symbol VARCHAR(10),
    date DATE,
    
    -- Primary Scores (0-100)
    quality_score DECIMAL(5,2),
    growth_score DECIMAL(5,2),
    value_score DECIMAL(5,2),
    momentum_score DECIMAL(5,2),
    sentiment_score DECIMAL(5,2),
    positioning_score DECIMAL(5,2),
    
    -- Composite Scores
    composite_score DECIMAL(5,2), -- Weighted average of all scores
    percentile_rank DECIMAL(5,2), -- Percentile rank vs universe
    sector_adjusted_score DECIMAL(5,2), -- Sector-neutral score
    
    -- Metadata
    market_regime VARCHAR(20), -- bull, bear, normal at time of calculation
    confidence_score DECIMAL(5,2), -- 0-100 confidence in score accuracy
    data_completeness DECIMAL(5,2), -- % of required data available
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

-- ================================
-- HEALTH MONITORING SYSTEM
-- ================================

-- Create comprehensive health_status table for database monitoring
CREATE TABLE IF NOT EXISTS health_status (
    table_name VARCHAR(255) PRIMARY KEY,
    status VARCHAR(50) NOT NULL DEFAULT 'unknown', -- 'healthy', 'stale', 'empty', 'error', 'missing', 'unknown'
    record_count BIGINT DEFAULT 0,
    missing_data_count BIGINT DEFAULT 0,
    last_updated TIMESTAMP WITH TIME ZONE,
    last_checked TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_stale BOOLEAN DEFAULT FALSE,
    error TEXT,
    table_category VARCHAR(100), -- 'symbols', 'prices', 'technicals', 'financials', 'company', 'earnings', 'sentiment', 'trading', 'other'
    critical_table BOOLEAN DEFAULT FALSE, -- Whether this table is critical for basic functionality
    expected_update_frequency INTERVAL DEFAULT '1 day', -- How often we expect updates
    size_bytes BIGINT DEFAULT 0,
    last_vacuum TIMESTAMP WITH TIME ZONE,
    last_analyze TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ================================
-- INDEXES FOR PERFORMANCE
-- ================================

-- Core table indexes
CREATE INDEX IF NOT EXISTS idx_stocks_symbol ON stocks(symbol);
CREATE INDEX IF NOT EXISTS idx_stock_symbols_symbol ON stock_symbols(symbol);
CREATE INDEX IF NOT EXISTS idx_etf_symbols_symbol ON etf_symbols(symbol);
CREATE INDEX IF NOT EXISTS idx_price_weekly_symbol_date ON price_weekly(symbol, date);
CREATE INDEX IF NOT EXISTS idx_technicals_weekly_symbol_date ON technicals_weekly(symbol, date);
CREATE INDEX IF NOT EXISTS idx_earnings_symbol ON earnings(symbol);
CREATE INDEX IF NOT EXISTS idx_prices_symbol_date ON prices(symbol, date);

-- API keys and portfolio indexes
CREATE INDEX IF NOT EXISTS idx_user_api_keys_user_id ON user_api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_user_api_keys_provider ON user_api_keys(provider);
CREATE INDEX IF NOT EXISTS idx_user_api_keys_active ON user_api_keys(is_active);
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_user_id ON portfolio_holdings(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_symbol ON portfolio_holdings(symbol);
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_broker ON portfolio_holdings(broker);
CREATE INDEX IF NOT EXISTS idx_portfolio_metadata_user_id ON portfolio_metadata(user_id);
CREATE INDEX IF NOT EXISTS idx_trading_alerts_user_id ON trading_alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_trading_alerts_symbol ON trading_alerts(symbol);
CREATE INDEX IF NOT EXISTS idx_trading_alerts_active ON trading_alerts(is_active);

-- Scoring system indexes
CREATE INDEX IF NOT EXISTS idx_stock_scores_symbol_date ON stock_scores(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_stock_scores_date_composite ON stock_scores(date DESC, composite_score DESC);
CREATE INDEX IF NOT EXISTS idx_market_regime_date ON market_regime(date DESC);

-- Health monitoring indexes
CREATE INDEX IF NOT EXISTS idx_health_status_status ON health_status(status);
CREATE INDEX IF NOT EXISTS idx_health_status_last_updated ON health_status(last_updated);
CREATE INDEX IF NOT EXISTS idx_health_status_category ON health_status(table_category);
CREATE INDEX IF NOT EXISTS idx_health_status_critical ON health_status(critical_table);
CREATE INDEX IF NOT EXISTS idx_health_status_stale ON health_status(is_stale);

-- ================================
-- HEALTH MONITORING SETUP
-- ================================

-- Create a function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_health_status_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to automatically update the updated_at field
DROP TRIGGER IF EXISTS trigger_health_status_updated_at ON health_status;
CREATE TRIGGER trigger_health_status_updated_at
    BEFORE UPDATE ON health_status
    FOR EACH ROW
    EXECUTE FUNCTION update_health_status_updated_at();

-- Insert all tables that should be monitored
INSERT INTO health_status (table_name, table_category, critical_table, expected_update_frequency) VALUES
-- Core Tables
('stock_symbols', 'symbols', true, '1 week'),
('etf_symbols', 'symbols', true, '1 week'),
('last_updated', 'tracking', true, '1 hour'),
('stocks', 'other', false, '1 day'),
('earnings', 'test', false, '1 day'),
('prices', 'test', false, '1 day'),

-- Price & Market Data Tables
('price_weekly', 'prices', true, '1 week'),
('technicals_weekly', 'technicals', true, '1 week'),

-- Portfolio & Trading Tables
('user_api_keys', 'trading', true, '1 hour'),
('portfolio_holdings', 'trading', true, '1 hour'),
('portfolio_metadata', 'trading', true, '1 hour'),
('trading_alerts', 'trading', false, '1 hour'),

-- Scoring System Tables
('stock_symbols_enhanced', 'scoring', false, '1 week'),
('market_regime', 'scoring', false, '1 day'),
('stock_scores', 'scoring', true, '1 day'),

-- System Health Monitoring
('health_status', 'system', true, '1 hour')
ON CONFLICT (table_name) DO NOTHING;

-- ================================
-- SAMPLE DATA
-- ================================

-- Insert some test data
INSERT INTO stocks (symbol, name, market) VALUES 
    ('AAPL', 'Apple Inc.', 'NASDAQ'),
    ('GOOGL', 'Alphabet Inc.', 'NASDAQ'),
    ('MSFT', 'Microsoft Corporation', 'NASDAQ')
ON CONFLICT (symbol) DO NOTHING;

-- ================================
-- COMPLETION MESSAGE
-- ================================

-- Record initialization in last_updated
INSERT INTO last_updated (script_name, last_run) VALUES 
    ('init_database_combined.sql', CURRENT_TIMESTAMP)
ON CONFLICT (script_name) DO UPDATE SET last_run = EXCLUDED.last_run;

-- Print confirmation
SELECT 'Combined database initialization completed successfully!' as status;