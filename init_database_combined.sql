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

-- Create stock_symbols table (used by loadstocksymbols_test and pricedaily)
-- This table must be populated with symbols for pricedaily to work properly
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

-- Create technical_data_daily table (required by TechnicalAnalysis webapp)
CREATE TABLE IF NOT EXISTS technical_data_daily (
    symbol VARCHAR(50) NOT NULL,
    date TIMESTAMP NOT NULL,
    open DECIMAL(12,4),
    high DECIMAL(12,4),
    low DECIMAL(12,4),
    close DECIMAL(12,4),
    volume BIGINT,
    rsi DECIMAL(8,4),
    macd DECIMAL(12,6),
    macd_signal DECIMAL(12,6),
    macd_histogram DECIMAL(12,6),
    sma_20 DECIMAL(12,4),
    sma_50 DECIMAL(12,4),
    ema_12 DECIMAL(12,4),
    ema_26 DECIMAL(12,4),
    bollinger_upper DECIMAL(12,4),
    bollinger_lower DECIMAL(12,4),
    bollinger_middle DECIMAL(12,4),
    stochastic_k DECIMAL(8,4),
    stochastic_d DECIMAL(8,4),
    williams_r DECIMAL(8,4),
    cci DECIMAL(8,4),
    adx DECIMAL(8,4),
    atr DECIMAL(12,4),
    obv BIGINT,
    mfi DECIMAL(8,4),
    roc DECIMAL(8,4),
    momentum DECIMAL(8,4),
    ad BIGINT,
    cmf DECIMAL(8,4),
    td_sequential DECIMAL(8,4),
    td_combo DECIMAL(8,4),
    marketwatch DECIMAL(8,4),
    dm DECIMAL(8,4),
    pivot_high DECIMAL(12,4),
    pivot_low DECIMAL(12,4),
    pivot_high_triggered BOOLEAN DEFAULT FALSE,
    pivot_low_triggered BOOLEAN DEFAULT FALSE,
    UNIQUE(symbol, date)
);

-- Create technical_data_weekly table (required by TechnicalAnalysis webapp)
CREATE TABLE IF NOT EXISTS technical_data_weekly (
    symbol VARCHAR(50) NOT NULL,
    date TIMESTAMP NOT NULL,
    open DECIMAL(12,4),
    high DECIMAL(12,4),
    low DECIMAL(12,4),
    close DECIMAL(12,4),
    volume BIGINT,
    rsi DECIMAL(8,4),
    macd DECIMAL(12,6),
    macd_signal DECIMAL(12,6),
    macd_histogram DECIMAL(12,6),
    sma_20 DECIMAL(12,4),
    sma_50 DECIMAL(12,4),
    ema_12 DECIMAL(12,4),
    ema_26 DECIMAL(12,4),
    bollinger_upper DECIMAL(12,4),
    bollinger_lower DECIMAL(12,4),
    bollinger_middle DECIMAL(12,4),
    stochastic_k DECIMAL(8,4),
    stochastic_d DECIMAL(8,4),
    williams_r DECIMAL(8,4),
    cci DECIMAL(8,4),
    adx DECIMAL(8,4),
    atr DECIMAL(12,4),
    obv BIGINT,
    mfi DECIMAL(8,4),
    roc DECIMAL(8,4),
    momentum DECIMAL(8,4),
    ad BIGINT,
    cmf DECIMAL(8,4),
    td_sequential DECIMAL(8,4),
    td_combo DECIMAL(8,4),
    marketwatch DECIMAL(8,4),
    dm DECIMAL(8,4),
    pivot_high DECIMAL(12,4),
    pivot_low DECIMAL(12,4),
    pivot_high_triggered BOOLEAN DEFAULT FALSE,
    pivot_low_triggered BOOLEAN DEFAULT FALSE,
    UNIQUE(symbol, date)
);

-- Create technical_data_monthly table (required by TechnicalAnalysis webapp)
CREATE TABLE IF NOT EXISTS technical_data_monthly (
    symbol VARCHAR(50) NOT NULL,
    date TIMESTAMP NOT NULL,
    open DECIMAL(12,4),
    high DECIMAL(12,4),
    low DECIMAL(12,4),
    close DECIMAL(12,4),
    volume BIGINT,
    rsi DECIMAL(8,4),
    macd DECIMAL(12,6),
    macd_signal DECIMAL(12,6),
    macd_histogram DECIMAL(12,6),
    sma_20 DECIMAL(12,4),
    sma_50 DECIMAL(12,4),
    ema_12 DECIMAL(12,4),
    ema_26 DECIMAL(12,4),
    bollinger_upper DECIMAL(12,4),
    bollinger_lower DECIMAL(12,4),
    bollinger_middle DECIMAL(12,4),
    stochastic_k DECIMAL(8,4),
    stochastic_d DECIMAL(8,4),
    williams_r DECIMAL(8,4),
    cci DECIMAL(8,4),
    adx DECIMAL(8,4),
    atr DECIMAL(12,4),
    obv BIGINT,
    mfi DECIMAL(8,4),
    roc DECIMAL(8,4),
    momentum DECIMAL(8,4),
    ad BIGINT,
    cmf DECIMAL(8,4),
    td_sequential DECIMAL(8,4),
    td_combo DECIMAL(8,4),
    marketwatch DECIMAL(8,4),
    dm DECIMAL(8,4),
    pivot_high DECIMAL(12,4),
    pivot_low DECIMAL(12,4),
    pivot_high_triggered BOOLEAN DEFAULT FALSE,
    pivot_low_triggered BOOLEAN DEFAULT FALSE,
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

-- Create economic calendar table for upcoming events
CREATE TABLE IF NOT EXISTS economic_calendar (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(50) UNIQUE,
    event_name VARCHAR(255) NOT NULL,
    country VARCHAR(10) DEFAULT 'US',
    category VARCHAR(100), -- 'monetary_policy', 'employment', 'inflation', 'gdp', 'housing', 'manufacturing', 'consumer'
    importance VARCHAR(20) NOT NULL, -- 'Low', 'Medium', 'High', 'Critical'
    currency VARCHAR(3) DEFAULT 'USD',
    event_date DATE NOT NULL,
    event_time TIME,
    timezone VARCHAR(50) DEFAULT 'America/New_York',
    actual_value VARCHAR(100),
    forecast_value VARCHAR(100),
    previous_value VARCHAR(100),
    unit VARCHAR(50), -- '%', 'K', 'M', 'B', 'Index', 'Points'
    frequency VARCHAR(20), -- 'Monthly', 'Quarterly', 'Yearly', 'Weekly'
    source VARCHAR(100), -- 'BLS', 'Fed', 'Commerce', 'Treasury', etc.
    description TEXT,
    impact_analysis TEXT,
    is_revised BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
CREATE INDEX IF NOT EXISTS idx_technical_data_daily_symbol_date ON technical_data_daily(symbol, date);
CREATE INDEX IF NOT EXISTS idx_technical_data_weekly_symbol_date ON technical_data_weekly(symbol, date);
CREATE INDEX IF NOT EXISTS idx_technical_data_monthly_symbol_date ON technical_data_monthly(symbol, date);
CREATE INDEX IF NOT EXISTS idx_earnings_symbol ON earnings(symbol);
CREATE INDEX IF NOT EXISTS idx_prices_symbol_date ON prices(symbol, date);
CREATE INDEX IF NOT EXISTS idx_economic_calendar_event_date ON economic_calendar(event_date);
CREATE INDEX IF NOT EXISTS idx_economic_calendar_importance ON economic_calendar(importance);
CREATE INDEX IF NOT EXISTS idx_economic_calendar_category ON economic_calendar(category);
CREATE INDEX IF NOT EXISTS idx_economic_calendar_country ON economic_calendar(country);

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
DO $$ 
BEGIN
    DROP TRIGGER IF EXISTS trigger_health_status_updated_at ON health_status;
    
    CREATE TRIGGER trigger_health_status_updated_at
        BEFORE UPDATE ON health_status
        FOR EACH ROW
        EXECUTE FUNCTION update_health_status_updated_at();
EXCEPTION
    WHEN duplicate_object THEN
        -- Trigger already exists, ignore
        NULL;
END $$;

-- Insert all tables that should be monitored
INSERT INTO health_status (table_name, table_category, critical_table, expected_update_frequency) VALUES
-- Core Tables
('stock_symbols', 'symbols', true, '1 week'),
('etf_symbols', 'symbols', true, '1 week'),
('last_updated', 'tracking', true, '1 hour'),
('stocks', 'other', false, '1 day'),
('earnings', 'test', false, '1 day'),
('prices', 'test', false, '1 day'),
('economic_calendar', 'economic', true, '1 day'),

-- Price & Market Data Tables
('price_weekly', 'prices', true, '1 week'),
('technicals_weekly', 'technicals', true, '1 week'),
('technical_data_daily', 'technicals', true, '1 day'),
('technical_data_weekly', 'technicals', true, '1 week'),
('technical_data_monthly', 'technicals', true, '1 month'),

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
('health_status', 'system', true, '1 hour'),

-- Pattern Recognition Tables
('pattern_types', 'patterns', true, '1 week'),
('detected_patterns', 'patterns', true, '1 hour'),
('pattern_performance', 'patterns', false, '1 day'),
('pattern_ml_models', 'patterns', false, '1 week'),
('pattern_scan_config', 'patterns', true, '1 day'),
('pattern_alerts', 'patterns', true, '1 hour'),
('pattern_features', 'patterns', false, '1 hour')
ON CONFLICT (table_name) DO NOTHING;

-- ================================
-- PATTERN RECOGNITION TABLES
-- ================================

-- Pattern types and their configurations
CREATE TABLE IF NOT EXISTS pattern_types (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    category VARCHAR(50) NOT NULL, -- 'candlestick', 'classical', 'harmonic', 'elliott_wave', 'ml_based'
    description TEXT,
    min_bars INTEGER NOT NULL DEFAULT 5,
    max_bars INTEGER NOT NULL DEFAULT 100,
    reliability_score DECIMAL(3,2) DEFAULT 0.75,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Detected patterns with enhanced ML scoring
CREATE TABLE IF NOT EXISTS detected_patterns (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    pattern_type_id INTEGER REFERENCES pattern_types(id),
    timeframe VARCHAR(10) NOT NULL, -- '1d', '1h', '4h', '1w', '1m'
    detection_date TIMESTAMP NOT NULL,
    start_date TIMESTAMP NOT NULL,
    end_date TIMESTAMP,
    confidence_score DECIMAL(5,4) NOT NULL, -- 0.0000 to 1.0000
    ml_confidence DECIMAL(5,4), -- ML model confidence
    traditional_confidence DECIMAL(5,4), -- Traditional TA confidence
    signal_strength VARCHAR(20), -- 'weak', 'moderate', 'strong', 'very_strong'
    direction VARCHAR(10), -- 'bullish', 'bearish', 'neutral'
    target_price DECIMAL(12,4),
    stop_loss DECIMAL(12,4),
    risk_reward_ratio DECIMAL(6,2),
    pattern_data JSONB, -- Store pattern-specific metrics
    key_levels JSONB, -- Support/resistance levels
    volume_confirmation BOOLEAN DEFAULT false,
    momentum_confirmation BOOLEAN DEFAULT false,
    status VARCHAR(20) DEFAULT 'active', -- 'active', 'triggered', 'invalidated', 'expired'
    outcome VARCHAR(20), -- 'success', 'failure', 'partial', 'pending'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Pattern performance tracking for ML training
CREATE TABLE IF NOT EXISTS pattern_performance (
    id SERIAL PRIMARY KEY,
    detected_pattern_id INTEGER REFERENCES detected_patterns(id),
    evaluation_date TIMESTAMP NOT NULL,
    price_at_detection DECIMAL(12,4) NOT NULL,
    price_at_evaluation DECIMAL(12,4) NOT NULL,
    percentage_change DECIMAL(8,4) NOT NULL,
    target_hit BOOLEAN DEFAULT false,
    stop_loss_hit BOOLEAN DEFAULT false,
    max_favorable_excursion DECIMAL(8,4),
    max_adverse_excursion DECIMAL(8,4),
    time_to_target INTEGER, -- days
    accuracy_score DECIMAL(5,4), -- How accurate the prediction was
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ML model metadata and performance
CREATE TABLE IF NOT EXISTS pattern_ml_models (
    id SERIAL PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL UNIQUE,
    model_type VARCHAR(50) NOT NULL, -- 'cnn', 'lstm', 'transformer', 'ensemble'
    version VARCHAR(20) NOT NULL,
    training_date TIMESTAMP NOT NULL,
    accuracy DECIMAL(5,4),
    precision_score DECIMAL(5,4),
    recall_score DECIMAL(5,4),
    f1_score DECIMAL(5,4),
    model_path TEXT, -- S3 path or local path
    feature_set JSONB, -- Features used in training
    hyperparameters JSONB,
    training_data_size INTEGER,
    validation_data_size INTEGER,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Real-time pattern scanning configuration
CREATE TABLE IF NOT EXISTS pattern_scan_config (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    pattern_type_id INTEGER REFERENCES pattern_types(id),
    timeframe VARCHAR(10) NOT NULL,
    is_enabled BOOLEAN DEFAULT true,
    min_confidence DECIMAL(3,2) DEFAULT 0.70,
    last_scan TIMESTAMP,
    scan_interval INTEGER DEFAULT 3600, -- seconds
    alert_enabled BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, pattern_type_id, timeframe)
);

-- Pattern alerts and notifications
CREATE TABLE IF NOT EXISTS pattern_alerts (
    id SERIAL PRIMARY KEY,
    detected_pattern_id INTEGER REFERENCES detected_patterns(id),
    alert_type VARCHAR(50) NOT NULL, -- 'new_pattern', 'target_hit', 'stop_loss_hit', 'pattern_invalidated'
    message TEXT NOT NULL,
    is_sent BOOLEAN DEFAULT false,
    sent_at TIMESTAMP,
    priority VARCHAR(20) DEFAULT 'medium', -- 'low', 'medium', 'high', 'critical'
    recipients JSONB, -- Array of notification targets
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Pattern feature cache for ML models
CREATE TABLE IF NOT EXISTS pattern_features (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    calculation_date TIMESTAMP NOT NULL,
    features JSONB NOT NULL, -- All calculated features for ML
    price_data JSONB, -- OHLCV data used
    technical_indicators JSONB, -- RSI, MACD, etc.
    volume_features JSONB, -- Volume-based features
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, timeframe, calculation_date)
);

-- ================================
-- PATTERN RECOGNITION INDEXES
-- ================================

-- Performance indexes for pattern detection
CREATE INDEX IF NOT EXISTS idx_detected_patterns_symbol_timeframe ON detected_patterns(symbol, timeframe);
CREATE INDEX IF NOT EXISTS idx_detected_patterns_type_confidence ON detected_patterns(pattern_type_id, confidence_score);
CREATE INDEX IF NOT EXISTS idx_detected_patterns_detection_date ON detected_patterns(detection_date);
CREATE INDEX IF NOT EXISTS idx_detected_patterns_status ON detected_patterns(status);
CREATE INDEX IF NOT EXISTS idx_pattern_performance_evaluation_date ON pattern_performance(evaluation_date);
CREATE INDEX IF NOT EXISTS idx_pattern_scan_config_symbol ON pattern_scan_config(symbol);
CREATE INDEX IF NOT EXISTS idx_pattern_features_symbol_timeframe ON pattern_features(symbol, timeframe);
CREATE INDEX IF NOT EXISTS idx_pattern_alerts_sent ON pattern_alerts(is_sent, created_at);

-- JSONB indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_detected_patterns_pattern_data ON detected_patterns USING GIN (pattern_data);
CREATE INDEX IF NOT EXISTS idx_pattern_features_features ON pattern_features USING GIN (features);

-- ================================
-- PATTERN RECOGNITION TRIGGERS
-- ================================

-- Update timestamp trigger
CREATE OR REPLACE FUNCTION update_pattern_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply trigger to detected_patterns
DROP TRIGGER IF EXISTS update_detected_patterns_timestamp ON detected_patterns;
CREATE TRIGGER update_detected_patterns_timestamp
    BEFORE UPDATE ON detected_patterns
    FOR EACH ROW EXECUTE FUNCTION update_pattern_timestamp();

-- ================================
-- SAMPLE DATA
-- ================================

-- Insert some test data
INSERT INTO stocks (symbol, name, market) VALUES 
    ('AAPL', 'Apple Inc.', 'NASDAQ'),
    ('GOOGL', 'Alphabet Inc.', 'NASDAQ'),
    ('MSFT', 'Microsoft Corporation', 'NASDAQ')
ON CONFLICT (symbol) DO NOTHING;

-- Insert pattern types
INSERT INTO pattern_types (name, category, description, min_bars, max_bars, reliability_score) VALUES 
    -- Candlestick Patterns
    ('Doji', 'candlestick', 'Indecision pattern with equal open and close', 1, 1, 0.65),
    ('Hammer', 'candlestick', 'Bullish reversal pattern with long lower shadow', 1, 1, 0.72),
    ('Hanging Man', 'candlestick', 'Bearish reversal pattern with long lower shadow', 1, 1, 0.68),
    ('Shooting Star', 'candlestick', 'Bearish reversal pattern with long upper shadow', 1, 1, 0.70),
    ('Engulfing Bullish', 'candlestick', 'Bullish reversal with larger white body engulfing previous black', 2, 2, 0.75),
    ('Engulfing Bearish', 'candlestick', 'Bearish reversal with larger black body engulfing previous white', 2, 2, 0.75),
    ('Morning Star', 'candlestick', 'Three-candle bullish reversal pattern', 3, 3, 0.78),
    ('Evening Star', 'candlestick', 'Three-candle bearish reversal pattern', 3, 3, 0.78),
    ('Three White Soldiers', 'candlestick', 'Strong bullish continuation pattern', 3, 3, 0.80),
    ('Three Black Crows', 'candlestick', 'Strong bearish continuation pattern', 3, 3, 0.80),
    
    -- Classical Chart Patterns
    ('Head and Shoulders', 'classical', 'Bearish reversal pattern with three peaks', 15, 50, 0.82),
    ('Inverse Head and Shoulders', 'classical', 'Bullish reversal pattern with three troughs', 15, 50, 0.82),
    ('Double Top', 'classical', 'Bearish reversal pattern with two peaks at similar levels', 10, 40, 0.76),
    ('Double Bottom', 'classical', 'Bullish reversal pattern with two troughs at similar levels', 10, 40, 0.76),
    ('Triple Top', 'classical', 'Strong bearish reversal with three peaks', 15, 60, 0.85),
    ('Triple Bottom', 'classical', 'Strong bullish reversal with three troughs', 15, 60, 0.85),
    ('Ascending Triangle', 'classical', 'Bullish continuation pattern with horizontal resistance', 8, 30, 0.73),
    ('Descending Triangle', 'classical', 'Bearish continuation pattern with horizontal support', 8, 30, 0.73),
    ('Symmetrical Triangle', 'classical', 'Continuation pattern with converging trendlines', 8, 30, 0.68),
    ('Rising Wedge', 'classical', 'Bearish pattern with upward sloping converging lines', 8, 25, 0.71),
    ('Falling Wedge', 'classical', 'Bullish pattern with downward sloping converging lines', 8, 25, 0.71),
    ('Cup and Handle', 'classical', 'Bullish continuation pattern resembling a cup', 20, 100, 0.79),
    ('Flag Bull', 'classical', 'Bullish continuation pattern after strong move up', 5, 15, 0.74),
    ('Flag Bear', 'classical', 'Bearish continuation pattern after strong move down', 5, 15, 0.74),
    ('Pennant Bull', 'classical', 'Bullish continuation with small symmetrical triangle', 5, 15, 0.72),
    ('Pennant Bear', 'classical', 'Bearish continuation with small symmetrical triangle', 5, 15, 0.72),
    
    -- Harmonic Patterns
    ('Gartley Bullish', 'harmonic', 'Bullish harmonic pattern with specific Fibonacci ratios', 10, 30, 0.81),
    ('Gartley Bearish', 'harmonic', 'Bearish harmonic pattern with specific Fibonacci ratios', 10, 30, 0.81),
    ('Butterfly Bullish', 'harmonic', 'Bullish butterfly pattern with 127.2% and 161.8% extensions', 10, 30, 0.83),
    ('Butterfly Bearish', 'harmonic', 'Bearish butterfly pattern with 127.2% and 161.8% extensions', 10, 30, 0.83),
    ('Bat Bullish', 'harmonic', 'Bullish bat pattern with 88.6% retracement', 10, 30, 0.79),
    ('Bat Bearish', 'harmonic', 'Bearish bat pattern with 88.6% retracement', 10, 30, 0.79),
    ('Crab Bullish', 'harmonic', 'Bullish crab pattern with 161.8% extension', 10, 30, 0.85),
    ('Crab Bearish', 'harmonic', 'Bearish crab pattern with 161.8% extension', 10, 30, 0.85),
    
    -- Elliott Wave Patterns
    ('Elliott Wave 5', 'elliott_wave', 'Five-wave impulse pattern', 20, 100, 0.77),
    ('Elliott Wave ABC', 'elliott_wave', 'Three-wave corrective pattern', 15, 80, 0.74),
    
    -- ML-Based Patterns
    ('ML Trend Reversal', 'ml_based', 'AI-detected trend reversal pattern', 5, 50, 0.88),
    ('ML Breakout', 'ml_based', 'AI-detected breakout pattern', 5, 30, 0.85),
    ('ML Continuation', 'ml_based', 'AI-detected continuation pattern', 5, 25, 0.82),
    ('ML Volume Anomaly', 'ml_based', 'AI-detected unusual volume pattern', 3, 20, 0.79)
ON CONFLICT (name) DO NOTHING;

-- ================================
-- COMPLETION MESSAGE
-- ================================

-- Record initialization in last_updated
INSERT INTO last_updated (script_name, last_run) VALUES 
    ('init_database_combined.sql', CURRENT_TIMESTAMP)
ON CONFLICT (script_name) DO UPDATE SET last_run = EXCLUDED.last_run;

-- Print confirmation
SELECT 'Combined database initialization completed successfully!' as status;