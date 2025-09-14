-- Fix Missing Database Columns Script
-- This script adds the specific missing columns that are causing test failures

-- 1. Add 'side' column to trade_history table (th.side)
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'trade_history') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_name = 'trade_history' AND column_name = 'side') THEN
            ALTER TABLE trade_history ADD COLUMN side VARCHAR(10) CHECK (side IN ('buy', 'sell')) DEFAULT 'buy';
            RAISE NOTICE 'Added side column to trade_history table';
        ELSE
            RAISE NOTICE 'side column already exists in trade_history table';
        END IF;
    ELSE
        RAISE NOTICE 'trade_history table does not exist, creating it';
        -- Create the trade_history table if it doesn't exist
        CREATE TABLE trade_history (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(100) NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            side VARCHAR(10) CHECK (side IN ('buy', 'sell')) DEFAULT 'buy',
            quantity INTEGER NOT NULL,
            price DECIMAL(12,4) NOT NULL,
            total_amount DECIMAL(15,4) NOT NULL,
            fees DECIMAL(10,4) DEFAULT 0,
            trade_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(20) DEFAULT 'executed',
            order_type VARCHAR(20) DEFAULT 'market',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Create indexes
        CREATE INDEX idx_trade_history_user_id ON trade_history(user_id);
        CREATE INDEX idx_trade_history_symbol ON trade_history(symbol);
        CREATE INDEX idx_trade_history_trade_date ON trade_history(trade_date DESC);
        
        RAISE NOTICE 'Created trade_history table with side column';
    END IF;
END $$;

-- 2. Add 'side' column to position_history table (ph.side)
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'position_history') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_name = 'position_history' AND column_name = 'side') THEN
            ALTER TABLE position_history ADD COLUMN side VARCHAR(10) CHECK (side IN ('long', 'short')) DEFAULT 'long';
            RAISE NOTICE 'Added side column to position_history table';
        ELSE
            RAISE NOTICE 'side column already exists in position_history table';
        END IF;
    ELSE
        RAISE NOTICE 'position_history table does not exist, creating it';
        -- Create the position_history table if it doesn't exist
        CREATE TABLE position_history (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(100) NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            side VARCHAR(10) CHECK (side IN ('long', 'short')) DEFAULT 'long',
            quantity INTEGER NOT NULL,
            avg_entry_price DECIMAL(12,4) NOT NULL,
            avg_exit_price DECIMAL(12,4),
            net_pnl DECIMAL(15,4),
            return_percentage DECIMAL(8,4),
            opened_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            closed_at TIMESTAMP WITH TIME ZONE,
            status VARCHAR(20) DEFAULT 'open',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Create indexes
        CREATE INDEX idx_position_history_user_id ON position_history(user_id);
        CREATE INDEX idx_position_history_symbol ON position_history(symbol);
        CREATE INDEX idx_position_history_status ON position_history(status);
        
        RAISE NOTICE 'Created position_history table with side column';
    END IF;
END $$;

-- 3. Add 'strategy_description' column to trading_strategies table
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'trading_strategies') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_name = 'trading_strategies' AND column_name = 'strategy_description') THEN
            ALTER TABLE trading_strategies ADD COLUMN strategy_description TEXT;
            RAISE NOTICE 'Added strategy_description column to trading_strategies table';
        ELSE
            RAISE NOTICE 'strategy_description column already exists in trading_strategies table';
        END IF;
    ELSE
        RAISE NOTICE 'trading_strategies table does not exist, creating it';
        -- Create the trading_strategies table if it doesn't exist
        CREATE TABLE trading_strategies (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(100) NOT NULL,
            strategy_name VARCHAR(200) NOT NULL,
            strategy_description TEXT,
            strategy_code TEXT,
            backtest_id VARCHAR(100),
            status VARCHAR(20) DEFAULT 'draft',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, strategy_name)
        );
        
        -- Create indexes
        CREATE INDEX idx_trading_strategies_user_id ON trading_strategies(user_id);
        CREATE INDEX idx_trading_strategies_status ON trading_strategies(status);
        
        RAISE NOTICE 'Created trading_strategies table with strategy_description column';
    END IF;
END $$;

-- 4. Insert sample data to ensure tables work correctly

-- Sample trade_history data
INSERT INTO trade_history (user_id, symbol, side, quantity, price, total_amount, fees, trade_date, status)
VALUES 
    ('dev-user-bypass', 'AAPL', 'buy', 100, 180.50, 18050.00, 5.00, NOW() - INTERVAL '5 days', 'executed'),
    ('dev-user-bypass', 'MSFT', 'buy', 50, 415.25, 20762.50, 7.50, NOW() - INTERVAL '3 days', 'executed'),
    ('dev-user-bypass', 'GOOGL', 'sell', 25, 142.80, 3570.00, 3.50, NOW() - INTERVAL '1 day', 'executed'),
    ('dev-user-bypass', 'TSLA', 'buy', 75, 225.30, 16897.50, 8.00, NOW() - INTERVAL '2 days', 'executed')
ON CONFLICT DO NOTHING;

-- Sample position_history data
INSERT INTO position_history (user_id, symbol, side, quantity, avg_entry_price, avg_exit_price, net_pnl, return_percentage, opened_at, closed_at, status)
VALUES 
    ('dev-user-bypass', 'AAPL', 'long', 100, 175.50, 185.25, 975.00, 5.56, NOW() - INTERVAL '10 days', NOW() - INTERVAL '2 days', 'closed'),
    ('dev-user-bypass', 'MSFT', 'long', 50, 410.00, NULL, NULL, NULL, NOW() - INTERVAL '5 days', NULL, 'open'),
    ('dev-user-bypass', 'NVDA', 'long', 25, 480.75, 495.30, 363.75, 3.03, NOW() - INTERVAL '15 days', NOW() - INTERVAL '3 days', 'closed'),
    ('dev-user-bypass', 'TSLA', 'short', 30, 240.00, 220.50, 585.00, 8.13, NOW() - INTERVAL '8 days', NOW() - INTERVAL '1 day', 'closed')
ON CONFLICT DO NOTHING;

-- Sample trading_strategies data
INSERT INTO trading_strategies (user_id, strategy_name, strategy_description, strategy_code, backtest_id, status)
VALUES 
    ('dev-user-bypass', 'Mean Reversion Strategy', 'A strategy that identifies overbought and oversold conditions using RSI and moving averages', 'def strategy(): pass', 'bt_001', 'active'),
    ('dev-user-bypass', 'Momentum Breakout', 'Identifies stocks breaking out of consolidation patterns with high volume confirmation', 'def momentum_strategy(): pass', 'bt_002', 'testing'),
    ('dev-user-bypass', 'Value Investing', 'Long-term strategy focusing on undervalued stocks with strong fundamentals', 'def value_strategy(): pass', 'bt_003', 'draft')
ON CONFLICT (user_id, strategy_name) DO UPDATE SET
    strategy_description = EXCLUDED.strategy_description,
    strategy_code = EXCLUDED.strategy_code,
    backtest_id = EXCLUDED.backtest_id,
    status = EXCLUDED.status,
    updated_at = CURRENT_TIMESTAMP;

-- 5. Update existing records with default values if needed

-- Update trade_history records that have NULL side values
UPDATE trade_history SET side = 'buy' WHERE side IS NULL;

-- Update position_history records that have NULL side values
UPDATE position_history SET side = 'long' WHERE side IS NULL;

-- Update trading_strategies records that have NULL strategy_description
UPDATE trading_strategies 
SET strategy_description = 'Strategy description not provided'
WHERE strategy_description IS NULL OR strategy_description = '';

COMMIT;

-- Final verification
SELECT 'trade_history' as table_name, 
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'trade_history' AND column_name = 'side') 
            THEN 'side column EXISTS' 
            ELSE 'side column MISSING' 
       END as side_column_status;

SELECT 'position_history' as table_name,
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'position_history' AND column_name = 'side') 
            THEN 'side column EXISTS' 
            ELSE 'side column MISSING' 
       END as side_column_status;

SELECT 'trading_strategies' as table_name,
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'trading_strategies' AND column_name = 'strategy_description') 
            THEN 'strategy_description column EXISTS' 
            ELSE 'strategy_description column MISSING' 
       END as description_column_status;