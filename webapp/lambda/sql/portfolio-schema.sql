-- Portfolio Database Schema
-- Creates tables for portfolio holdings, metadata, optimizations, and trading data

-- Portfolio Holdings Table
-- Stores current portfolio positions for each user
CREATE TABLE IF NOT EXISTS portfolio_holdings (
    holding_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    symbol VARCHAR(10) NOT NULL,
    quantity DECIMAL(15, 6) NOT NULL CHECK (quantity >= 0),
    avg_cost DECIMAL(10, 2) NOT NULL CHECK (avg_cost >= 0),
    current_price DECIMAL(10, 2),
    market_value DECIMAL(15, 2),
    unrealized_pl DECIMAL(15, 2),
    sector VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, symbol)
);

-- Portfolio Metadata Table
-- Stores account-level information and sync status
CREATE TABLE IF NOT EXISTS portfolio_metadata (
    metadata_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE UNIQUE,
    account_id VARCHAR(50),
    account_type VARCHAR(20) DEFAULT 'margin',
    total_equity DECIMAL(15, 2),
    buying_power DECIMAL(15, 2),
    cash DECIMAL(15, 2),
    day_trade_count INTEGER DEFAULT 0,
    last_sync_at TIMESTAMP,
    sync_status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Portfolio Optimizations Table
-- Stores optimization runs and their parameters
CREATE TABLE IF NOT EXISTS portfolio_optimizations (
    optimization_id UUID PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    optimization_type VARCHAR(50) NOT NULL,
    parameters JSONB,
    status VARCHAR(20) DEFAULT 'pending',
    results JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- Recommended Trades Table
-- Stores trade recommendations from optimization algorithms
CREATE TABLE IF NOT EXISTS recommended_trades (
    trade_id SERIAL PRIMARY KEY,
    optimization_id UUID REFERENCES portfolio_optimizations(optimization_id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    symbol VARCHAR(10) NOT NULL,
    action VARCHAR(10) NOT NULL CHECK (action IN ('BUY', 'SELL')),
    quantity DECIMAL(15, 6) NOT NULL,
    estimated_price DECIMAL(10, 2),
    rationale TEXT,
    priority VARCHAR(10) DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high')),
    status VARCHAR(20) DEFAULT 'pending',
    executed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Trading Orders Table
-- Stores actual trading orders and execution history
CREATE TABLE IF NOT EXISTS trading_orders (
    order_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    broker_order_id VARCHAR(100),
    symbol VARCHAR(10) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('BUY', 'SELL')),
    order_type VARCHAR(20) DEFAULT 'market',
    quantity DECIMAL(15, 6) NOT NULL,
    price DECIMAL(10, 2),
    filled_quantity DECIMAL(15, 6) DEFAULT 0,
    filled_price DECIMAL(10, 2),
    status VARCHAR(20) DEFAULT 'pending',
    time_in_force VARCHAR(10) DEFAULT 'day',
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    filled_at TIMESTAMP,
    cancelled_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Portfolio Performance History Table
-- Stores daily portfolio performance snapshots
CREATE TABLE IF NOT EXISTS portfolio_performance_history (
    history_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    date DATE NOT NULL,
    total_value DECIMAL(15, 2) NOT NULL,
    total_cost DECIMAL(15, 2) NOT NULL,
    unrealized_pl DECIMAL(15, 2) NOT NULL,
    realized_pl DECIMAL(15, 2) DEFAULT 0,
    cash_value DECIMAL(15, 2) DEFAULT 0,
    position_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, date)
);

-- Watchlist Table
-- Stores user stock watchlists
CREATE TABLE IF NOT EXISTS watchlist (
    watchlist_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    symbol VARCHAR(10) NOT NULL,
    notes TEXT,
    target_price DECIMAL(10, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, symbol)
);

-- Price Alerts Table
-- Stores user-defined price alerts
CREATE TABLE IF NOT EXISTS price_alerts (
    alert_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    symbol VARCHAR(10) NOT NULL,
    condition VARCHAR(20) NOT NULL CHECK (condition IN ('above', 'below', 'change_percent')),
    target_price DECIMAL(10, 2),
    change_percent DECIMAL(5, 2),
    alert_type VARCHAR(20) NOT NULL CHECK (alert_type IN ('email', 'sms', 'push')),
    is_active BOOLEAN DEFAULT true,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    triggered_at TIMESTAMP
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_user_id ON portfolio_holdings(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_symbol ON portfolio_holdings(symbol);
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_updated_at ON portfolio_holdings(updated_at);

CREATE INDEX IF NOT EXISTS idx_portfolio_metadata_user_id ON portfolio_metadata(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_metadata_sync_status ON portfolio_metadata(sync_status);

CREATE INDEX IF NOT EXISTS idx_portfolio_optimizations_user_id ON portfolio_optimizations(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_optimizations_created_at ON portfolio_optimizations(created_at);

CREATE INDEX IF NOT EXISTS idx_recommended_trades_user_id ON recommended_trades(user_id);
CREATE INDEX IF NOT EXISTS idx_recommended_trades_optimization_id ON recommended_trades(optimization_id);
CREATE INDEX IF NOT EXISTS idx_recommended_trades_status ON recommended_trades(status);

CREATE INDEX IF NOT EXISTS idx_trading_orders_user_id ON trading_orders(user_id);
CREATE INDEX IF NOT EXISTS idx_trading_orders_symbol ON trading_orders(symbol);
CREATE INDEX IF NOT EXISTS idx_trading_orders_status ON trading_orders(status);
CREATE INDEX IF NOT EXISTS idx_trading_orders_submitted_at ON trading_orders(submitted_at);

CREATE INDEX IF NOT EXISTS idx_portfolio_performance_user_id ON portfolio_performance_history(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_performance_date ON portfolio_performance_history(date);

CREATE INDEX IF NOT EXISTS idx_watchlist_user_id ON watchlist(user_id);
CREATE INDEX IF NOT EXISTS idx_price_alerts_user_id ON price_alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_price_alerts_symbol ON price_alerts(symbol);
CREATE INDEX IF NOT EXISTS idx_price_alerts_active ON price_alerts(is_active);

-- Add updated_at trigger function for automatic timestamp updates
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply updated_at triggers to relevant tables
CREATE TRIGGER update_portfolio_holdings_updated_at 
    BEFORE UPDATE ON portfolio_holdings 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_portfolio_metadata_updated_at 
    BEFORE UPDATE ON portfolio_metadata 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();