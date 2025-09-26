-- Database Setup Script for Webapp-Specific Tables Only
-- Python loaders create their own tables in AWS
-- This script only creates webapp-specific tables for local development

-- Grant schema permissions (commented out for local testing)
-- DO $$
-- BEGIN
--    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'stocks') THEN
--       GRANT ALL ON SCHEMA public TO stocks;
--       GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO stocks;
--       GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO stocks;
--       ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO stocks;
--       ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO stocks;
--    END IF;
-- END
-- $$;

-- ========================================
-- WEBAPP-SPECIFIC TABLES ONLY
-- ========================================

-- User watchlist functionality
CREATE TABLE IF NOT EXISTS watchlists (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    is_default BOOLEAN DEFAULT FALSE,
    is_public BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS watchlist_items (
    id SERIAL PRIMARY KEY,
    watchlist_id INTEGER REFERENCES watchlists(id) ON DELETE CASCADE,
    symbol VARCHAR(10) NOT NULL,
    notes TEXT,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(watchlist_id, symbol)
);

-- User portfolio tracking
CREATE TABLE IF NOT EXISTS portfolio_holdings (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    quantity DECIMAL(15,6),
    average_cost DECIMAL(10,2),
    current_price DECIMAL(10,2),
    market_value DECIMAL(15,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, symbol)
);

CREATE TABLE IF NOT EXISTS portfolio_performance (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    date DATE NOT NULL,
    total_value DECIMAL(15,2),
    daily_return DECIMAL(10,4),
    total_return DECIMAL(10,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, date)
);

-- Real trading orders (live trading)
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    side VARCHAR(10) NOT NULL, -- 'buy' or 'sell'
    quantity DECIMAL(15,6) NOT NULL,
    order_type VARCHAR(20) NOT NULL, -- 'market', 'limit', 'stop', 'stop_limit'
    limit_price DECIMAL(10,2),
    stop_price DECIMAL(10,2),
    time_in_force VARCHAR(10) DEFAULT 'day', -- 'day', 'gtc', 'ioc', 'fok'
    status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'filled', 'cancelled', 'partial', 'rejected'
    filled_quantity DECIMAL(15,6) DEFAULT 0,
    average_price DECIMAL(10,4),
    broker VARCHAR(50),
    broker_order_id VARCHAR(100),
    notes TEXT,
    extended_hours BOOLEAN DEFAULT false,
    all_or_none BOOLEAN DEFAULT false,
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    filled_at TIMESTAMP,
    cancelled_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Paper trading orders
CREATE TABLE IF NOT EXISTS orders_paper (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    side VARCHAR(10) NOT NULL, -- 'buy' or 'sell'
    quantity DECIMAL(15,6) NOT NULL,
    type VARCHAR(20) NOT NULL, -- 'market', 'limit', 'stop_limit'
    price DECIMAL(10,2),
    stop_price DECIMAL(10,2),
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    filled_at TIMESTAMP
);

-- User alert system
CREATE TABLE IF NOT EXISTS user_alerts (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,
    condition_type VARCHAR(20) NOT NULL,
    threshold_value DECIMAL(10,4),
    message TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    triggered_at TIMESTAMP
);

-- Signal alerts for users
CREATE TABLE IF NOT EXISTS signal_alerts (
    alert_id VARCHAR(100) PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    signal_type VARCHAR(10) DEFAULT 'BUY',
    min_strength DECIMAL(3,2) DEFAULT 0.7,
    notification_method VARCHAR(20) DEFAULT 'email',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'active'
);

-- User-specific trading settings
CREATE TABLE IF NOT EXISTS user_settings (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL UNIQUE,
    trading_mode VARCHAR(20) DEFAULT 'paper', -- 'paper' or 'live'
    risk_tolerance VARCHAR(20) DEFAULT 'moderate', -- 'conservative', 'moderate', 'aggressive'
    default_position_size DECIMAL(10,2) DEFAULT 1000.00,
    max_portfolio_risk DECIMAL(5,2) DEFAULT 2.0, -- percentage
    enable_notifications BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Trading session logs
CREATE TABLE IF NOT EXISTS trading_sessions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    session_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    session_end TIMESTAMP,
    total_trades INTEGER DEFAULT 0,
    profit_loss DECIMAL(15,2) DEFAULT 0,
    session_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User backtesting results
CREATE TABLE IF NOT EXISTS backtest_results (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    strategy_name VARCHAR(100) NOT NULL,
    symbol VARCHAR(10),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    total_return DECIMAL(10,4),
    sharpe_ratio DECIMAL(10,4),
    max_drawdown DECIMAL(10,4),
    total_trades INTEGER,
    win_rate DECIMAL(5,2),
    parameters JSONB,
    results_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for webapp tables (after all tables are created)
CREATE INDEX IF NOT EXISTS idx_watchlists_user ON watchlists(user_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_items_watchlist ON watchlist_items(watchlist_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_user ON portfolio_holdings(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_performance_user_date ON portfolio_performance(user_id, date);
CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);
CREATE INDEX IF NOT EXISTS idx_orders_paper_user ON orders_paper(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_paper_status ON orders_paper(status);
CREATE INDEX IF NOT EXISTS idx_user_alerts_user ON user_alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_user_alerts_active ON user_alerts(is_active);
CREATE INDEX IF NOT EXISTS idx_signal_alerts_active ON signal_alerts(is_active);
CREATE INDEX IF NOT EXISTS idx_trading_sessions_user ON trading_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_backtest_results_user ON backtest_results(user_id);

-- ========================================
-- SCORING AND ANALYSIS TABLES
-- ========================================

-- Comprehensive stock scoring table
CREATE TABLE IF NOT EXISTS comprehensive_scores (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    quality_score DECIMAL(3,2),
    growth_score DECIMAL(3,2),
    value_score DECIMAL(3,2),
    momentum_score DECIMAL(3,2),
    sentiment_score DECIMAL(3,2),
    positioning_score DECIMAL(3,2),
    composite_score DECIMAL(3,2),
    calculation_date DATE NOT NULL,
    data_quality INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, calculation_date)
);

CREATE INDEX IF NOT EXISTS idx_comprehensive_scores_symbol ON comprehensive_scores(symbol);
CREATE INDEX IF NOT EXISTS idx_comprehensive_scores_updated_at ON comprehensive_scores(updated_at);
CREATE INDEX IF NOT EXISTS idx_comprehensive_scores_composite ON comprehensive_scores(composite_score);