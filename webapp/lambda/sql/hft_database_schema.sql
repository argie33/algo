-- HFT Database Schema for High Frequency Trading System
-- This schema supports the HFT trading platform with strategies, positions, orders, and performance tracking

-- Drop existing tables if they exist (be careful in production!)
DROP TABLE IF EXISTS hft_performance_metrics CASCADE;
DROP TABLE IF EXISTS hft_orders CASCADE;
DROP TABLE IF EXISTS hft_positions CASCADE;
DROP TABLE IF EXISTS hft_strategies CASCADE;
DROP TABLE IF EXISTS hft_risk_events CASCADE;
DROP TABLE IF EXISTS hft_market_data CASCADE;

-- Create HFT Strategies table
CREATE TABLE hft_strategies (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(id),
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL CHECK (type IN ('scalping', 'momentum', 'arbitrage', 'mean_reversion', 'market_making')),
    symbols TEXT[] NOT NULL, -- Array of symbols this strategy trades
    parameters JSONB NOT NULL, -- Strategy-specific parameters
    risk_parameters JSONB NOT NULL, -- Risk management parameters
    enabled BOOLEAN DEFAULT false,
    paper_trading BOOLEAN DEFAULT true,
    max_position_size DECIMAL(15,8) DEFAULT 1000,
    max_daily_loss DECIMAL(15,2) DEFAULT 500,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deployed_at TIMESTAMP,
    last_signal_at TIMESTAMP
);

-- Create HFT Positions table
CREATE TABLE hft_positions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(id),
    strategy_id INTEGER NOT NULL REFERENCES hft_strategies(id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    position_type VARCHAR(10) NOT NULL CHECK (position_type IN ('LONG', 'SHORT')),
    quantity DECIMAL(15,8) NOT NULL,
    entry_price DECIMAL(15,8) NOT NULL,
    current_price DECIMAL(15,8),
    unrealized_pnl DECIMAL(15,2) DEFAULT 0,
    realized_pnl DECIMAL(15,2) DEFAULT 0,
    stop_loss DECIMAL(15,8),
    take_profit DECIMAL(15,8),
    opened_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP,
    status VARCHAR(20) DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'CLOSED', 'PARTIAL')),
    alpaca_position_id VARCHAR(255), -- External broker position ID
    metadata JSONB -- Additional position metadata
);

-- Create HFT Orders table
CREATE TABLE hft_orders (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(id),
    strategy_id INTEGER NOT NULL REFERENCES hft_strategies(id) ON DELETE CASCADE,
    position_id INTEGER REFERENCES hft_positions(id),
    symbol VARCHAR(20) NOT NULL,
    order_type VARCHAR(20) NOT NULL CHECK (order_type IN ('market', 'limit', 'stop', 'stop_limit')),
    side VARCHAR(10) NOT NULL CHECK (side IN ('BUY', 'SELL')),
    quantity DECIMAL(15,8) NOT NULL,
    price DECIMAL(15,8), -- NULL for market orders
    stop_price DECIMAL(15,8), -- For stop orders
    status VARCHAR(20) DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'SUBMITTED', 'FILLED', 'PARTIAL', 'CANCELLED', 'REJECTED')),
    time_in_force VARCHAR(10) DEFAULT 'IOC' CHECK (time_in_force IN ('IOC', 'GTC', 'DAY', 'FOK')),
    
    -- Execution details
    alpaca_order_id VARCHAR(255), -- External broker order ID
    execution_time_ms INTEGER, -- Execution latency in milliseconds
    filled_quantity DECIMAL(15,8) DEFAULT 0,
    avg_fill_price DECIMAL(15,8),
    commission DECIMAL(10,4) DEFAULT 0,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    submitted_at TIMESTAMP,
    filled_at TIMESTAMP,
    
    -- Additional data
    metadata JSONB -- Order metadata and execution details
);

-- Create HFT Performance Metrics table
CREATE TABLE hft_performance_metrics (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(id),
    strategy_id INTEGER NOT NULL REFERENCES hft_strategies(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    
    -- Trade statistics
    total_trades INTEGER DEFAULT 0,
    profitable_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    
    -- P&L metrics
    total_pnl DECIMAL(15,2) DEFAULT 0,
    realized_pnl DECIMAL(15,2) DEFAULT 0,
    unrealized_pnl DECIMAL(15,2) DEFAULT 0,
    commission_paid DECIMAL(10,4) DEFAULT 0,
    
    -- Risk metrics
    max_drawdown DECIMAL(15,2) DEFAULT 0,
    max_daily_loss DECIMAL(15,2) DEFAULT 0,
    var_95 DECIMAL(15,2), -- Value at Risk (95% confidence)
    sharpe_ratio DECIMAL(8,4),
    
    -- Performance metrics
    avg_execution_time_ms DECIMAL(8,2),
    min_execution_time_ms INTEGER,
    max_execution_time_ms INTEGER,
    win_rate DECIMAL(5,4), -- Percentage as decimal (0.0 to 1.0)
    profit_factor DECIMAL(8,4),
    
    -- Volume and activity
    total_volume DECIMAL(15,8) DEFAULT 0,
    avg_trade_size DECIMAL(15,8),
    max_position_size DECIMAL(15,8),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Ensure one record per strategy per day
    UNIQUE(strategy_id, date)
);

-- Create HFT Risk Events table for risk management tracking
CREATE TABLE hft_risk_events (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(id),
    strategy_id INTEGER REFERENCES hft_strategies(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL CHECK (event_type IN ('STOP_LOSS', 'TAKE_PROFIT', 'MAX_DRAWDOWN', 'DAILY_LOSS_LIMIT', 'POSITION_LIMIT', 'CIRCUIT_BREAKER')),
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    symbol VARCHAR(20),
    trigger_value DECIMAL(15,8),
    threshold_value DECIMAL(15,8),
    action_taken VARCHAR(100),
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    metadata JSONB
);

-- Create HFT Market Data table for historical data and backtesting
CREATE TABLE hft_market_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    price DECIMAL(15,8) NOT NULL,
    bid DECIMAL(15,8),
    ask DECIMAL(15,8),
    volume DECIMAL(15,8),
    spread DECIMAL(15,8),
    source VARCHAR(20) DEFAULT 'alpaca',
    latency_ms INTEGER, -- Data latency for HFT analysis
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Index for fast time-series queries
    UNIQUE(symbol, timestamp, source)
);

-- Create indexes for performance optimization
CREATE INDEX idx_hft_strategies_user_enabled ON hft_strategies(user_id, enabled);
CREATE INDEX idx_hft_strategies_symbols ON hft_strategies USING GIN(symbols);

CREATE INDEX idx_hft_positions_user_strategy ON hft_positions(user_id, strategy_id);
CREATE INDEX idx_hft_positions_symbol_status ON hft_positions(symbol, status);
CREATE INDEX idx_hft_positions_opened_at ON hft_positions(opened_at);

CREATE INDEX idx_hft_orders_user_strategy ON hft_orders(user_id, strategy_id);
CREATE INDEX idx_hft_orders_symbol_status ON hft_orders(symbol, status);
CREATE INDEX idx_hft_orders_created_at ON hft_orders(created_at);
CREATE INDEX idx_hft_orders_alpaca_id ON hft_orders(alpaca_order_id);

CREATE INDEX idx_hft_performance_strategy_date ON hft_performance_metrics(strategy_id, date);
CREATE INDEX idx_hft_performance_user_date ON hft_performance_metrics(user_id, date);

CREATE INDEX idx_hft_risk_events_user_created ON hft_risk_events(user_id, created_at);
CREATE INDEX idx_hft_risk_events_strategy_type ON hft_risk_events(strategy_id, event_type);

CREATE INDEX idx_hft_market_data_symbol_time ON hft_market_data(symbol, timestamp DESC);
CREATE INDEX idx_hft_market_data_created_at ON hft_market_data(created_at);

-- Create triggers for automatic timestamp updates
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_hft_strategies_updated_at 
    BEFORE UPDATE ON hft_strategies 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_hft_performance_updated_at 
    BEFORE UPDATE ON hft_performance_metrics 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create views for common queries
CREATE VIEW hft_active_positions AS
SELECT 
    p.*,
    s.name as strategy_name,
    s.type as strategy_type,
    (p.current_price - p.entry_price) * p.quantity * 
    CASE WHEN p.position_type = 'LONG' THEN 1 ELSE -1 END as unrealized_pnl_calc
FROM hft_positions p
JOIN hft_strategies s ON p.strategy_id = s.id
WHERE p.status = 'OPEN';

CREATE VIEW hft_daily_performance AS
SELECT 
    pm.*,
    s.name as strategy_name,
    s.type as strategy_type,
    CASE WHEN pm.total_trades > 0 
         THEN pm.profitable_trades::decimal / pm.total_trades 
         ELSE 0 END as win_rate_calc
FROM hft_performance_metrics pm
JOIN hft_strategies s ON pm.strategy_id = s.id
ORDER BY pm.date DESC, pm.total_pnl DESC;

-- Grant permissions (adjust user as needed)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO financial_app_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO financial_app_user;

-- Insert sample data for testing (optional)
-- This would be handled by the application, but here's an example:
/*
INSERT INTO hft_strategies (user_id, name, type, symbols, parameters, risk_parameters, enabled, paper_trading) 
VALUES (
    'test-user-1', 
    'BTC Scalping Strategy', 
    'scalping', 
    ARRAY['BTC/USD'], 
    '{"minSpread": 0.001, "maxSpread": 0.005, "volumeThreshold": 1000, "momentumPeriod": 5, "executionDelay": 100}',
    '{"positionSize": 0.1, "stopLoss": 0.02, "takeProfit": 0.01, "maxDailyLoss": 500}',
    false,
    true
);
*/

-- Add comments for documentation
COMMENT ON TABLE hft_strategies IS 'HFT trading strategies with configuration and risk parameters';
COMMENT ON TABLE hft_positions IS 'Active and historical HFT positions';
COMMENT ON TABLE hft_orders IS 'HFT order execution records with timing and fill details';
COMMENT ON TABLE hft_performance_metrics IS 'Daily performance metrics per strategy';
COMMENT ON TABLE hft_risk_events IS 'Risk management events and circuit breaker activations';
COMMENT ON TABLE hft_market_data IS 'Historical market data for backtesting and analysis';

-- Final verification query
SELECT 
    'HFT Database Schema Created Successfully' as status,
    COUNT(*) as tables_created
FROM information_schema.tables 
WHERE table_name LIKE 'hft_%' AND table_schema = 'public';