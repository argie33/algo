-- Web App Database Initialization Script
-- Creates webapp-specific tables not covered by loader scripts
-- Loader scripts create market data tables and take precedence

-- ===============================================
-- USER MANAGEMENT TABLES
-- ===============================================

CREATE TABLE IF NOT EXISTS user_profiles (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100),
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    phone VARCHAR(20),
    country VARCHAR(50) DEFAULT 'US',
    timezone VARCHAR(50) DEFAULT 'America/New_York',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS user_api_keys (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    broker VARCHAR(50) NOT NULL, -- 'alpaca', 'td_ameritrade', etc.
    api_key_encrypted TEXT NOT NULL,
    api_secret_encrypted TEXT,
    environment VARCHAR(20) DEFAULT 'paper', -- 'paper' or 'live'
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP,
    UNIQUE(user_id, broker, environment)
);

CREATE TABLE IF NOT EXISTS user_dashboard_settings (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) UNIQUE NOT NULL,
    theme VARCHAR(20) DEFAULT 'light',
    default_watchlist_id INTEGER,
    dashboard_layout JSONB,
    chart_preferences JSONB,
    notification_settings JSONB,
    risk_tolerance VARCHAR(20) DEFAULT 'moderate', -- 'conservative', 'moderate', 'aggressive'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_2fa_secrets (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) UNIQUE NOT NULL,
    secret_encrypted TEXT NOT NULL,
    backup_codes_encrypted TEXT[],
    is_enabled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP
);

-- ===============================================
-- PORTFOLIO MANAGEMENT TABLES
-- ===============================================

CREATE TABLE IF NOT EXISTS portfolio_holdings (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    quantity DECIMAL(15,8) NOT NULL DEFAULT 0,
    avg_cost DECIMAL(15,4),
    current_price DECIMAL(15,4),
    market_value DECIMAL(15,2),
    unrealized_pnl DECIMAL(15,2),
    unrealized_pnl_percent DECIMAL(8,4),
    day_change DECIMAL(15,2),
    day_change_percent DECIMAL(8,4),
    broker VARCHAR(50) DEFAULT 'manual', -- 'alpaca', 'manual', etc.
    account_id VARCHAR(100),
    position_id VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_synced TIMESTAMP,
    UNIQUE(user_id, symbol, broker)
);

CREATE TABLE IF NOT EXISTS portfolio_transactions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    transaction_type VARCHAR(20) NOT NULL, -- 'buy', 'sell', 'dividend', 'split'
    quantity DECIMAL(15,8) NOT NULL,
    price DECIMAL(15,4) NOT NULL,
    total_amount DECIMAL(15,2) NOT NULL,
    fees DECIMAL(10,2) DEFAULT 0,
    broker VARCHAR(50) DEFAULT 'manual',
    broker_transaction_id VARCHAR(100),
    trade_date DATE NOT NULL,
    settlement_date DATE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS portfolio_performance (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    date DATE NOT NULL,
    total_value DECIMAL(15,2) NOT NULL,
    total_cost DECIMAL(15,2),
    cash_balance DECIMAL(15,2) DEFAULT 0,
    day_change DECIMAL(15,2),
    day_change_percent DECIMAL(8,4),
    total_return DECIMAL(15,2),
    total_return_percent DECIMAL(8,4),
    broker VARCHAR(50) DEFAULT 'combined',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, date, broker)
);

-- ===============================================
-- WATCHLIST MANAGEMENT TABLES
-- ===============================================

CREATE TABLE IF NOT EXISTS watchlists (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    is_default BOOLEAN DEFAULT FALSE,
    is_public BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, name)
);

CREATE TABLE IF NOT EXISTS watchlist_items (
    id SERIAL PRIMARY KEY,
    watchlist_id INTEGER NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    target_price DECIMAL(15,4),
    alert_enabled BOOLEAN DEFAULT FALSE,
    sort_order INTEGER DEFAULT 0,
    UNIQUE(watchlist_id, symbol)
);

CREATE TABLE IF NOT EXISTS watchlist_performance (
    id SERIAL PRIMARY KEY,
    watchlist_id INTEGER NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    total_value DECIMAL(15,2),
    day_change DECIMAL(15,2),
    day_change_percent DECIMAL(8,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(watchlist_id, date)
);

-- ===============================================
-- TRADING STRATEGY TABLES
-- ===============================================

CREATE TABLE IF NOT EXISTS trading_strategies (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    strategy_type VARCHAR(50), -- 'momentum', 'mean_reversion', 'custom'
    conditions JSONB NOT NULL,
    actions JSONB NOT NULL,
    risk_parameters JSONB,
    is_active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_executed TIMESTAMP,
    UNIQUE(user_id, name)
);

-- ===============================================
-- ALERT MANAGEMENT TABLES
-- ===============================================

CREATE TABLE IF NOT EXISTS price_alerts (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    alert_type VARCHAR(20) NOT NULL, -- 'above', 'below', 'change_percent'
    target_value DECIMAL(15,4) NOT NULL,
    current_value DECIMAL(15,4),
    is_triggered BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    triggered_at TIMESTAMP,
    message TEXT
);

CREATE TABLE IF NOT EXISTS risk_alerts (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    alert_type VARCHAR(50) NOT NULL, -- 'portfolio_loss', 'position_size', 'sector_concentration'
    threshold_value DECIMAL(15,4) NOT NULL,
    current_value DECIMAL(15,4),
    is_triggered BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    symbol VARCHAR(20), -- NULL for portfolio-level alerts
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    triggered_at TIMESTAMP,
    message TEXT
);

-- ===============================================
-- SCREENER TABLES
-- ===============================================

CREATE TABLE IF NOT EXISTS saved_screens (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    filters JSONB NOT NULL,
    sort_by VARCHAR(50),
    sort_direction VARCHAR(10) DEFAULT 'DESC',
    is_public BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, name)
);

-- ===============================================
-- RISK MANAGEMENT TABLES
-- ===============================================

CREATE TABLE IF NOT EXISTS user_risk_limits (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) UNIQUE NOT NULL,
    max_position_size_percent DECIMAL(5,2) DEFAULT 10.00, -- Max % of portfolio per position
    max_sector_allocation_percent DECIMAL(5,2) DEFAULT 25.00, -- Max % per sector
    max_daily_loss_percent DECIMAL(5,2) DEFAULT 5.00, -- Max daily loss %
    max_portfolio_var DECIMAL(5,2) DEFAULT 10.00, -- Max Value at Risk %
    stop_loss_percent DECIMAL(5,2) DEFAULT 10.00, -- Default stop loss %
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ===============================================
-- AUDIT AND ACTIVITY TABLES
-- ===============================================

CREATE TABLE IF NOT EXISTS user_activity_log (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    action VARCHAR(100) NOT NULL,
    details JSONB,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ===============================================
-- INDEXES FOR PERFORMANCE
-- ===============================================

-- User profile indexes
CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON user_profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_user_profiles_email ON user_profiles(email);

-- Portfolio indexes
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_user_id ON portfolio_holdings(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_symbol ON portfolio_holdings(symbol);
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_user_symbol ON portfolio_holdings(user_id, symbol);
CREATE INDEX IF NOT EXISTS idx_portfolio_transactions_user_id ON portfolio_transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_transactions_symbol ON portfolio_transactions(symbol);
CREATE INDEX IF NOT EXISTS idx_portfolio_transactions_date ON portfolio_transactions(trade_date);
CREATE INDEX IF NOT EXISTS idx_portfolio_performance_user_date ON portfolio_performance(user_id, date);

-- Watchlist indexes
CREATE INDEX IF NOT EXISTS idx_watchlists_user_id ON watchlists(user_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_items_watchlist_id ON watchlist_items(watchlist_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_items_symbol ON watchlist_items(symbol);

-- Alert indexes
CREATE INDEX IF NOT EXISTS idx_price_alerts_user_id ON price_alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_price_alerts_symbol ON price_alerts(symbol);
CREATE INDEX IF NOT EXISTS idx_price_alerts_active ON price_alerts(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_risk_alerts_user_id ON risk_alerts(user_id);

-- Strategy indexes
CREATE INDEX IF NOT EXISTS idx_trading_strategies_user_id ON trading_strategies(user_id);
CREATE INDEX IF NOT EXISTS idx_trading_strategies_active ON trading_strategies(is_active) WHERE is_active = TRUE;

-- Activity log indexes
CREATE INDEX IF NOT EXISTS idx_user_activity_log_user_id ON user_activity_log(user_id);
CREATE INDEX IF NOT EXISTS idx_user_activity_log_created_at ON user_activity_log(created_at);

-- ===============================================
-- UPDATE TRIGGERS
-- ===============================================

-- Update timestamps trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Add update triggers to relevant tables
CREATE TRIGGER update_user_profiles_updated_at BEFORE UPDATE ON user_profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_user_dashboard_settings_updated_at BEFORE UPDATE ON user_dashboard_settings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_portfolio_holdings_updated_at BEFORE UPDATE ON portfolio_holdings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_watchlists_updated_at BEFORE UPDATE ON watchlists
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_trading_strategies_updated_at BEFORE UPDATE ON trading_strategies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_saved_screens_updated_at BEFORE UPDATE ON saved_screens
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_user_risk_limits_updated_at BEFORE UPDATE ON user_risk_limits
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ===============================================
-- INITIAL DATA SETUP
-- ===============================================

-- Insert default risk limits for system-wide defaults (can be referenced by user_id = 'default')
INSERT INTO user_risk_limits (user_id, max_position_size_percent, max_sector_allocation_percent, max_daily_loss_percent, max_portfolio_var, stop_loss_percent)
VALUES ('default', 10.00, 25.00, 5.00, 10.00, 10.00)
ON CONFLICT (user_id) DO NOTHING;

-- Success message
DO $$
BEGIN
    RAISE NOTICE 'Webapp database initialization completed successfully!';
    RAISE NOTICE 'Created tables: user_profiles, user_api_keys, portfolio_holdings, portfolio_transactions, watchlists, trading_strategies, alerts, and more.';
    RAISE NOTICE 'Note: Market data tables are created by loader scripts and take precedence.';
END
$$;