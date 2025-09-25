-- Fix portfolio_transactions table with total_amount column
-- This script creates the missing portfolio_transactions table with all required columns

-- Create portfolio_transactions table if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'portfolio_transactions') THEN
        CREATE TABLE portfolio_transactions (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(100) NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            transaction_type VARCHAR(20) NOT NULL CHECK (transaction_type IN ('buy', 'sell', 'deposit', 'withdrawal')),
            quantity DECIMAL(15,8) NOT NULL DEFAULT 0,
            price DECIMAL(12,4) NOT NULL DEFAULT 0,
            total_amount DECIMAL(15,4) NOT NULL,
            fees DECIMAL(10,4) DEFAULT 0,
            transaction_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            notes TEXT,
            broker VARCHAR(100) DEFAULT 'paper',
            status VARCHAR(20) DEFAULT 'completed',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            executed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        -- Create indexes for performance
        CREATE INDEX idx_portfolio_transactions_user_id ON portfolio_transactions(user_id);
        CREATE INDEX idx_portfolio_transactions_symbol ON portfolio_transactions(symbol);
        CREATE INDEX idx_portfolio_transactions_type ON portfolio_transactions(transaction_type);
        CREATE INDEX idx_portfolio_transactions_date ON portfolio_transactions(transaction_date DESC);

        RAISE NOTICE 'Created portfolio_transactions table with total_amount column';
    ELSE
        RAISE NOTICE 'portfolio_transactions table already exists';

        -- Check if total_amount column exists, add it if missing
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name = 'portfolio_transactions' AND column_name = 'total_amount') THEN
            ALTER TABLE portfolio_transactions ADD COLUMN total_amount DECIMAL(15,4) NOT NULL DEFAULT 0;
            RAISE NOTICE 'Added total_amount column to portfolio_transactions table';
        ELSE
            RAISE NOTICE 'total_amount column already exists in portfolio_transactions table';
        END IF;
    END IF;
END $$;

-- Insert sample test data for portfolio_transactions
INSERT INTO portfolio_transactions (user_id, symbol, transaction_type, quantity, price, total_amount, fees, transaction_date, notes, broker, status)
VALUES
    ('dev-user-bypass', 'AAPL', 'buy', 100.00000000, 180.50, 18050.00, 5.00, NOW() - INTERVAL '10 days', 'Initial purchase', 'paper', 'completed'),
    ('dev-user-bypass', 'MSFT', 'buy', 50.00000000, 415.25, 20762.50, 7.50, NOW() - INTERVAL '8 days', 'Microsoft purchase', 'paper', 'completed'),
    ('dev-user-bypass', 'GOOGL', 'buy', 25.00000000, 142.80, 3570.00, 3.50, NOW() - INTERVAL '5 days', 'Google purchase', 'paper', 'completed'),
    ('dev-user-bypass', 'GOOGL', 'sell', 10.00000000, 145.20, 1452.00, 2.00, NOW() - INTERVAL '2 days', 'Partial Google sale', 'paper', 'completed'),
    ('dev-user-bypass', 'TSLA', 'buy', 75.00000000, 225.30, 16897.50, 8.00, NOW() - INTERVAL '3 days', 'Tesla purchase', 'paper', 'completed')
ON CONFLICT DO NOTHING;

-- Verify the table was created properly
SELECT 'portfolio_transactions' as table_name,
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'portfolio_transactions' AND column_name = 'total_amount')
            THEN 'total_amount column EXISTS'
            ELSE 'total_amount column MISSING'
       END as total_amount_status;

COMMIT;