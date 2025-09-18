-- Create trades table for trading functionality
CREATE TABLE IF NOT EXISTS trades (
    trade_id VARCHAR(255) PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('buy', 'sell')),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    type VARCHAR(20) NOT NULL DEFAULT 'market',
    limit_price DECIMAL(10,4),
    stop_price DECIMAL(10,4),
    time_in_force VARCHAR(10) DEFAULT 'day',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    executed_at TIMESTAMP,
    average_fill_price DECIMAL(10,4),
    filled_quantity INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_trades_user_id ON trades(user_id);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_created_at ON trades(created_at);

-- Insert sample test data
INSERT INTO trades (trade_id, user_id, symbol, side, quantity, type, status, created_at) VALUES
('test-trade-1', 'test-user', 'AAPL', 'buy', 100, 'market', 'filled', NOW() - INTERVAL '1 day'),
('test-trade-2', 'test-user', 'MSFT', 'sell', 50, 'limit', 'pending', NOW() - INTERVAL '2 hours'),
('test-trade-3', 'test-user', 'TSLA', 'buy', 25, 'market', 'filled', NOW() - INTERVAL '1 week')
ON CONFLICT (trade_id) DO NOTHING;