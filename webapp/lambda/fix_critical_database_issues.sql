-- Fix Critical Database Issues Identified from Server Logs
-- This addresses the specific column and table missing errors causing API failures

BEGIN;

-- Fix 1: Add missing 'momentum' column for sector analysis
DO $$
BEGIN
    -- Check if sectors table exists and add momentum column
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'sectors') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name = 'sectors' AND column_name = 'momentum') THEN
            ALTER TABLE sectors ADD COLUMN momentum DECIMAL(10,4) DEFAULT NULL;
            RAISE NOTICE 'Added momentum column to sectors table';
        ELSE
            RAISE NOTICE 'momentum column already exists in sectors table';
        END IF;
    ELSE
        -- Create sectors table if it doesn't exist
        CREATE TABLE sectors (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL UNIQUE,
            performance DECIMAL(8,4),
            momentum DECIMAL(10,4),
            volume_change DECIMAL(10,4),
            market_cap BIGINT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        RAISE NOTICE 'Created sectors table with momentum column';

        -- Insert sample sector data
        INSERT INTO sectors (name, performance, momentum, volume_change, market_cap) VALUES
        ('Technology', 2.45, 1.25, 15.6, 12500000000),
        ('Healthcare', 1.83, 0.89, 8.2, 8900000000),
        ('Financial Services', 0.92, -0.34, -5.1, 15600000000),
        ('Consumer Cyclical', 1.67, 1.12, 12.4, 7800000000),
        ('Communication Services', 2.11, 0.76, 9.8, 6500000000),
        ('Industrials', 1.34, 0.45, 6.7, 5400000000),
        ('Consumer Defensive', 0.78, -0.12, 3.2, 4900000000),
        ('Energy', -0.56, -1.23, -18.7, 3200000000),
        ('Utilities', 0.34, -0.67, -2.1, 2800000000),
        ('Real Estate', 1.23, 0.23, 4.5, 2100000000),
        ('Materials', 0.89, 0.12, 7.9, 1900000000);
    END IF;
END $$;

-- Fix 2: Add missing 'close_price' column to price_daily table
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'price_daily') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name = 'price_daily' AND column_name = 'close_price') THEN
            ALTER TABLE price_daily ADD COLUMN close_price DECIMAL(12,4) DEFAULT NULL;
            RAISE NOTICE 'Added close_price column to price_daily table';

            -- Update close_price to match close column if close exists
            IF EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name = 'price_daily' AND column_name = 'close') THEN
                UPDATE price_daily SET close_price = close WHERE close_price IS NULL;
                RAISE NOTICE 'Updated close_price values from close column';
            END IF;
        ELSE
            RAISE NOTICE 'close_price column already exists in price_daily table';
        END IF;
    ELSE
        RAISE NOTICE 'price_daily table does not exist - this may need to be created first';
    END IF;
END $$;

-- Fix 3: Create missing 'risk_assessments' table
CREATE TABLE IF NOT EXISTS risk_assessments (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    portfolio_id VARCHAR(100),
    symbol VARCHAR(20),
    assessment_type VARCHAR(50) DEFAULT 'portfolio',
    risk_score DECIMAL(5,2),
    beta DECIMAL(8,4),
    volatility DECIMAL(8,4),
    var_1d DECIMAL(12,4),
    var_5d DECIMAL(12,4),
    max_drawdown DECIMAL(8,4),
    sharpe_ratio DECIMAL(8,4),
    assessment_date DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for risk_assessments table
CREATE INDEX IF NOT EXISTS idx_risk_assessments_user ON risk_assessments(user_id);
CREATE INDEX IF NOT EXISTS idx_risk_assessments_symbol ON risk_assessments(symbol);
CREATE INDEX IF NOT EXISTS idx_risk_assessments_date ON risk_assessments(assessment_date);

-- Insert sample risk assessment data
INSERT INTO risk_assessments (user_id, portfolio_id, symbol, assessment_type, risk_score, beta, volatility, var_1d, var_5d, max_drawdown, sharpe_ratio)
VALUES
    ('dev-user-bypass', 'default', 'AAPL', 'individual', 6.8, 1.12, 0.28, 0.023, 0.051, 0.15, 1.34),
    ('dev-user-bypass', 'default', 'MSFT', 'individual', 5.9, 0.98, 0.24, 0.019, 0.043, 0.12, 1.52),
    ('dev-user-bypass', 'default', 'GOOGL', 'individual', 7.2, 1.18, 0.32, 0.027, 0.058, 0.18, 1.28),
    ('dev-user-bypass', 'default', NULL, 'portfolio', 6.5, 1.08, 0.26, 0.021, 0.047, 0.14, 1.41)
ON CONFLICT DO NOTHING;

-- Fix 4: Add missing 'fees' column to trade_history table
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'trade_history') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name = 'trade_history' AND column_name = 'fees') THEN
            ALTER TABLE trade_history ADD COLUMN fees DECIMAL(10,4) DEFAULT 0.00;
            RAISE NOTICE 'Added fees column to trade_history table';
        ELSE
            RAISE NOTICE 'fees column already exists in trade_history table';
        END IF;
    ELSE
        -- Create trade_history table if it doesn't exist
        CREATE TABLE trade_history (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(100) NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            side VARCHAR(10) CHECK (side IN ('buy', 'sell')) DEFAULT 'buy',
            quantity INTEGER NOT NULL,
            price DECIMAL(12,4) NOT NULL,
            total_amount DECIMAL(15,4) NOT NULL,
            fees DECIMAL(10,4) DEFAULT 0.00,
            trade_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(20) DEFAULT 'executed',
            order_type VARCHAR(20) DEFAULT 'market',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        -- Create indexes for trade_history table
        CREATE INDEX IF NOT EXISTS idx_trade_history_user_id ON trade_history(user_id);
        CREATE INDEX IF NOT EXISTS idx_trade_history_symbol ON trade_history(symbol);
        CREATE INDEX IF NOT EXISTS idx_trade_history_trade_date ON trade_history(trade_date DESC);
        RAISE NOTICE 'Created trade_history table with fees column';

        -- Insert sample trade history data
        INSERT INTO trade_history (user_id, symbol, side, quantity, price, total_amount, fees, trade_date, status)
        VALUES
            ('dev-user-bypass', 'AAPL', 'buy', 100, 180.50, 18050.00, 5.00, NOW() - INTERVAL '5 days', 'executed'),
            ('dev-user-bypass', 'MSFT', 'buy', 50, 415.25, 20762.50, 7.50, NOW() - INTERVAL '3 days', 'executed'),
            ('dev-user-bypass', 'GOOGL', 'sell', 25, 142.80, 3570.00, 3.50, NOW() - INTERVAL '1 day', 'executed'),
            ('dev-user-bypass', 'TSLA', 'buy', 75, 225.30, 16897.50, 8.00, NOW() - INTERVAL '2 days', 'executed');
    END IF;
END $$;

-- Fix 5: Ensure proper market quotes table structure
DO $$
BEGIN
    -- Check if market_quotes or similar table exists for real-time quotes
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'market_quotes') THEN
        CREATE TABLE market_quotes (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            price DECIMAL(12,4) NOT NULL,
            close_price DECIMAL(12,4),
            open_price DECIMAL(12,4),
            high_price DECIMAL(12,4),
            low_price DECIMAL(12,4),
            volume BIGINT,
            change_amount DECIMAL(12,4),
            change_percent DECIMAL(8,4),
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            market_session VARCHAR(20) DEFAULT 'regular',
            UNIQUE(symbol, timestamp)
        );

        -- Create indexes for market_quotes table
        CREATE INDEX IF NOT EXISTS idx_market_quotes_symbol ON market_quotes(symbol);
        CREATE INDEX IF NOT EXISTS idx_market_quotes_timestamp ON market_quotes(timestamp DESC);
        RAISE NOTICE 'Created market_quotes table';

        -- Insert sample market quotes data
        INSERT INTO market_quotes (symbol, price, close_price, open_price, high_price, low_price, volume, change_amount, change_percent)
        VALUES
            ('AAPL', 185.23, 184.50, 183.75, 186.12, 182.95, 45234567, 0.73, 0.40),
            ('MSFT', 412.87, 411.25, 409.50, 414.33, 408.22, 28765432, 1.62, 0.39),
            ('GOOGL', 143.45, 142.80, 142.10, 144.85, 141.75, 32876543, 0.65, 0.46),
            ('TSLA', 227.91, 225.30, 224.85, 229.45, 223.12, 67543210, 2.61, 1.16),
            ('NVDA', 498.76, 495.20, 492.85, 501.23, 491.45, 41234567, 3.56, 0.72);
    END IF;
END $$;

COMMIT;

-- Verify the fixes
SELECT 'Database schema fixes completed' as status;

-- Check sectors table
SELECT 'sectors' as table_name,
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sectors' AND column_name = 'momentum')
            THEN 'momentum column EXISTS'
            ELSE 'momentum column MISSING'
       END as momentum_status;

-- Check price_daily table
SELECT 'price_daily' as table_name,
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'price_daily' AND column_name = 'close_price')
            THEN 'close_price column EXISTS'
            ELSE 'close_price column MISSING'
       END as close_price_status;

-- Check risk_assessments table
SELECT 'risk_assessments' as table_name,
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'risk_assessments')
            THEN 'table EXISTS'
            ELSE 'table MISSING'
       END as table_status;

-- Check trade_history table
SELECT 'trade_history' as table_name,
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'trade_history' AND column_name = 'fees')
            THEN 'fees column EXISTS'
            ELSE 'fees column MISSING'
       END as fees_status;