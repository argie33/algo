-- Fix Portfolio and Order Management Tables
-- Consolidate duplicate functionality and create proper data flow

-- Create portfolio transactions table
CREATE TABLE IF NOT EXISTS portfolio_transactions (
    transaction_id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    transaction_type VARCHAR(20) NOT NULL,
    quantity DECIMAL(15,4) NOT NULL,
    price DECIMAL(15,4) NOT NULL,
    total_amount DECIMAL(15,4) NOT NULL,
    commission DECIMAL(10,4) DEFAULT 0.00,
    transaction_date TIMESTAMP NOT NULL,
    settlement_date TIMESTAMP,
    notes TEXT,
    user_id VARCHAR(50) NOT NULL,
    broker VARCHAR(50) DEFAULT 'manual',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create portfolio holdings table (calculated from transactions)
CREATE TABLE IF NOT EXISTS portfolio_holdings (
    holding_id SERIAL PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    quantity DECIMAL(15,4) NOT NULL,
    average_cost DECIMAL(15,4) NOT NULL,
    current_price DECIMAL(15,4) DEFAULT 0,
    market_value DECIMAL(15,4) DEFAULT 0,
    unrealized_pnl DECIMAL(15,4) DEFAULT 0,
    unrealized_pnl_percent DECIMAL(10,4) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, symbol)
);

-- Insert test transaction data
INSERT INTO portfolio_transactions (symbol, transaction_type, quantity, price, total_amount, commission, transaction_date, settlement_date, notes, user_id, broker) VALUES
('AAPL', 'BUY', 100.00, 150.00, 15000.00, 7.50, '2024-01-01', '2024-01-03', 'Initial AAPL purchase', 'default_user', 'manual'),
('MSFT', 'BUY', 50.00, 400.00, 20000.00, 5.00, '2024-01-02', '2024-01-04', 'MSFT position', 'default_user', 'manual'),
('GOOGL', 'BUY', 50.00, 160.00, 8000.00, 4.00, '2024-01-03', '2024-01-05', 'GOOGL initial purchase', 'default_user', 'manual'),
('GOOGL', 'SELL', 25.00, 140.00, 3500.00, 3.50, '2024-01-05', '2024-01-07', 'Partial GOOGL sale', 'default_user', 'manual'),
('TSLA', 'BUY', 30.00, 250.00, 7500.00, 4.00, '2024-01-10', '2024-01-12', 'Tesla investment', 'default_user', 'manual'),
('AMZN', 'DIVIDEND', 10.00, 3.50, 35.00, 0.00, '2024-01-15', '2024-01-15', 'Quarterly dividend', 'default_user', 'manual')
ON CONFLICT DO NOTHING;

-- Calculate and insert portfolio holdings from transactions
INSERT INTO portfolio_holdings (user_id, symbol, quantity, average_cost, current_price, market_value, unrealized_pnl, unrealized_pnl_percent)
SELECT
    user_id,
    symbol,
    SUM(CASE
        WHEN transaction_type = 'BUY' THEN quantity
        WHEN transaction_type = 'SELL' THEN -quantity
        ELSE 0
    END) as total_quantity,
    CASE
        WHEN SUM(CASE WHEN transaction_type = 'BUY' THEN quantity ELSE 0 END) > 0 THEN
            SUM(CASE WHEN transaction_type = 'BUY' THEN total_amount ELSE 0 END) /
            SUM(CASE WHEN transaction_type = 'BUY' THEN quantity ELSE 0 END)
        ELSE 0
    END as avg_cost,
    CASE symbol
        WHEN 'AAPL' THEN 175.50
        WHEN 'MSFT' THEN 420.75
        WHEN 'GOOGL' THEN 143.50
        WHEN 'TSLA' THEN 285.00
        WHEN 'AMZN' THEN 148.90
        ELSE 100.00
    END as current_price,
    0 as market_value,
    0 as unrealized_pnl,
    0 as unrealized_pnl_percent
FROM portfolio_transactions
WHERE user_id = 'default_user' AND transaction_type IN ('BUY', 'SELL')
GROUP BY user_id, symbol
HAVING SUM(CASE
    WHEN transaction_type = 'BUY' THEN quantity
    WHEN transaction_type = 'SELL' THEN -quantity
    ELSE 0
END) > 0
ON CONFLICT (user_id, symbol) DO UPDATE SET
    quantity = EXCLUDED.quantity,
    average_cost = EXCLUDED.average_cost,
    current_price = EXCLUDED.current_price,
    updated_at = CURRENT_TIMESTAMP;

-- Update market values and PnL
UPDATE portfolio_holdings SET
    market_value = quantity * current_price,
    unrealized_pnl = (current_price - average_cost) * quantity,
    unrealized_pnl_percent = CASE
        WHEN average_cost > 0 THEN ((current_price - average_cost) / average_cost) * 100
        ELSE 0
    END,
    updated_at = CURRENT_TIMESTAMP
WHERE user_id = 'default_user';

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_portfolio_transactions_user ON portfolio_transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_transactions_symbol ON portfolio_transactions(symbol);
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_user ON portfolio_holdings(user_id);