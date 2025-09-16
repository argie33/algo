-- Fix Additional Missing Database Columns Script
-- Based on test failures, adding missing columns found in various routes

-- 1. Add commission column to trade_executions table (te.commission)
DO $$ 
BEGIN
    -- First create trade_executions table if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'trade_executions') THEN
        CREATE TABLE trade_executions (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(100) NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            side VARCHAR(10) CHECK (side IN ('buy', 'sell')) DEFAULT 'buy',
            quantity INTEGER NOT NULL,
            price DECIMAL(12,4) NOT NULL,
            commission DECIMAL(10,4) DEFAULT 0,
            execution_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            order_id VARCHAR(100),
            execution_type VARCHAR(20) DEFAULT 'market',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX idx_trade_executions_user_id ON trade_executions(user_id);
        CREATE INDEX idx_trade_executions_symbol ON trade_executions(symbol);
        
        RAISE NOTICE 'Created trade_executions table with commission column';
    ELSE
        -- Add commission column if it doesn't exist
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_name = 'trade_executions' AND column_name = 'commission') THEN
            ALTER TABLE trade_executions ADD COLUMN commission DECIMAL(10,4) DEFAULT 0;
            RAISE NOTICE 'Added commission column to trade_executions table';
        ELSE
            RAISE NOTICE 'commission column already exists in trade_executions table';
        END IF;
    END IF;
END $$;

-- 2. Add close_price column to performance-related tables
DO $$ 
BEGIN
    -- Add close_price to portfolio_holdings table if missing
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'portfolio_holdings') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_name = 'portfolio_holdings' AND column_name = 'close_price') THEN
            ALTER TABLE portfolio_holdings ADD COLUMN close_price DECIMAL(12,4);
            RAISE NOTICE 'Added close_price column to portfolio_holdings table';
        END IF;
    END IF;
    
    -- Add close_price to position_history table if missing  
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'position_history') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_name = 'position_history' AND column_name = 'close_price') THEN
            ALTER TABLE position_history ADD COLUMN close_price DECIMAL(12,4);
            RAISE NOTICE 'Added close_price column to position_history table';
        END IF;
    END IF;
END $$;

-- 3. Add transaction_date column to portfolio transactions
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'portfolio_transactions') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_name = 'portfolio_transactions' AND column_name = 'transaction_date') THEN
            ALTER TABLE portfolio_transactions ADD COLUMN transaction_date DATE DEFAULT CURRENT_DATE;
            RAISE NOTICE 'Added transaction_date column to portfolio_transactions table';
        ELSE
            RAISE NOTICE 'transaction_date column already exists in portfolio_transactions table';
        END IF;
    END IF;
END $$;

-- 4. Create economic_indicators table with category column
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'economic_indicators') THEN
        CREATE TABLE economic_indicators (
            id SERIAL PRIMARY KEY,
            indicator_name VARCHAR(200) NOT NULL,
            category VARCHAR(100) NOT NULL,
            value DECIMAL(15,4),
            previous_value DECIMAL(15,4),
            unit VARCHAR(50),
            frequency VARCHAR(20), -- daily, weekly, monthly, quarterly, annually
            release_date DATE,
            next_release_date DATE,
            source VARCHAR(100),
            importance VARCHAR(20), -- high, medium, low
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(indicator_name, release_date)
        );
        
        CREATE INDEX idx_economic_indicators_category ON economic_indicators(category);
        CREATE INDEX idx_economic_indicators_release_date ON economic_indicators(release_date DESC);
        CREATE INDEX idx_economic_indicators_importance ON economic_indicators(importance);
        
        RAISE NOTICE 'Created economic_indicators table with category column';
    ELSE
        -- Add category column if it doesn't exist
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_name = 'economic_indicators' AND column_name = 'category') THEN
            ALTER TABLE economic_indicators ADD COLUMN category VARCHAR(100);
            RAISE NOTICE 'Added category column to economic_indicators table';
        ELSE
            RAISE NOTICE 'category column already exists in economic_indicators table';
        END IF;
    END IF;
END $$;

-- 5. Create trade_insights table
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'trade_insights') THEN
        CREATE TABLE trade_insights (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(100) NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            insight_type VARCHAR(50) NOT NULL, -- pattern, performance, risk, opportunity
            insight_text TEXT NOT NULL,
            confidence_score DECIMAL(3,2), -- 0.00 to 1.00
            relevance_score DECIMAL(3,2), -- 0.00 to 1.00
            tags TEXT[], -- array of insight tags
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP WITH TIME ZONE,
            is_active BOOLEAN DEFAULT true
        );
        
        CREATE INDEX idx_trade_insights_user_id ON trade_insights(user_id);
        CREATE INDEX idx_trade_insights_symbol ON trade_insights(symbol);
        CREATE INDEX idx_trade_insights_type ON trade_insights(insight_type);
        CREATE INDEX idx_trade_insights_active ON trade_insights(is_active, created_at DESC);
        
        RAISE NOTICE 'Created trade_insights table';
    ELSE
        RAISE NOTICE 'trade_insights table already exists';
    END IF;
END $$;

-- 6. Insert sample data to verify tables work

-- Sample trade executions data
INSERT INTO trade_executions (user_id, symbol, side, quantity, price, commission, execution_time)
VALUES 
    ('dev-user-bypass', 'AAPL', 'buy', 100, 180.50, 1.99, NOW() - INTERVAL '5 days'),
    ('dev-user-bypass', 'MSFT', 'buy', 50, 415.25, 2.49, NOW() - INTERVAL '3 days'),
    ('dev-user-bypass', 'GOOGL', 'sell', 25, 142.80, 1.49, NOW() - INTERVAL '1 day')
ON CONFLICT DO NOTHING;

-- Sample economic indicators data
INSERT INTO economic_indicators (indicator_name, category, value, previous_value, unit, frequency, release_date, source, importance)
VALUES 
    ('GDP Growth Rate', 'growth', 2.3, 2.1, 'percent', 'quarterly', CURRENT_DATE - INTERVAL '30 days', 'BEA', 'high'),
    ('Unemployment Rate', 'employment', 3.7, 3.8, 'percent', 'monthly', CURRENT_DATE - INTERVAL '7 days', 'BLS', 'high'),
    ('Consumer Price Index', 'inflation', 307.8, 307.3, 'index', 'monthly', CURRENT_DATE - INTERVAL '14 days', 'BLS', 'high'),
    ('Federal Funds Rate', 'monetary', 5.25, 5.00, 'percent', 'meeting', CURRENT_DATE - INTERVAL '45 days', 'Fed', 'high'),
    ('Consumer Confidence Index', 'sentiment', 102.5, 101.8, 'index', 'monthly', CURRENT_DATE - INTERVAL '5 days', 'Conference Board', 'medium')
ON CONFLICT (indicator_name, release_date) DO UPDATE SET
    value = EXCLUDED.value,
    previous_value = EXCLUDED.previous_value,
    updated_at = CURRENT_TIMESTAMP;

-- Sample trade insights data  
INSERT INTO trade_insights (user_id, symbol, insight_type, insight_text, confidence_score, relevance_score, tags)
VALUES 
    ('dev-user-bypass', 'AAPL', 'pattern', 'Stock showing strong upward momentum with increasing volume', 0.85, 0.92, ARRAY['momentum', 'volume', 'bullish']),
    ('dev-user-bypass', 'MSFT', 'performance', 'Outperforming sector average by 12% over last quarter', 0.78, 0.88, ARRAY['outperform', 'sector', 'quarterly']),
    ('dev-user-bypass', 'TSLA', 'risk', 'High volatility detected - consider position sizing', 0.91, 0.95, ARRAY['volatility', 'risk', 'position-sizing']),
    ('dev-user-bypass', 'GOOGL', 'opportunity', 'Potential bounce from support level at $140', 0.72, 0.81, ARRAY['support', 'bounce', 'technical'])
ON CONFLICT DO NOTHING;

-- Update existing data with new columns where appropriate

-- Update portfolio_holdings with sample close_price data
UPDATE portfolio_holdings 
SET close_price = ROUND(current_price * (0.95 + random() * 0.1), 2)
WHERE close_price IS NULL AND current_price IS NOT NULL;

-- Update position_history with sample close_price data
UPDATE position_history 
SET close_price = ROUND(avg_entry_price * (0.95 + random() * 0.1), 2)
WHERE close_price IS NULL AND avg_entry_price IS NOT NULL;

-- Update portfolio_transactions with transaction_date
UPDATE portfolio_transactions 
SET transaction_date = DATE(created_at)
WHERE transaction_date IS NULL;

COMMIT;

-- Verification queries
SELECT 'trade_executions' as table_name, 
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'trade_executions' AND column_name = 'commission') 
            THEN 'commission column EXISTS' 
            ELSE 'commission column MISSING' 
       END as commission_status;

SELECT 'economic_indicators' as table_name,
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'economic_indicators' AND column_name = 'category') 
            THEN 'category column EXISTS' 
            ELSE 'category column MISSING' 
       END as category_status;

SELECT 'trade_insights' as table_name,
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'trade_insights') 
            THEN 'table EXISTS' 
            ELSE 'table MISSING' 
       END as table_status;