-- Fix Critical Missing Database Columns for Test Failures
-- This script addresses the specific columns causing test failures

-- 1. Add close_price to price_daily table (tests expect close_price but table has 'close')
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'price_daily') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name = 'price_daily' AND column_name = 'close_price') THEN
            ALTER TABLE price_daily ADD COLUMN close_price DOUBLE PRECISION;
            -- Copy data from existing 'close' column
            UPDATE price_daily SET close_price = close WHERE close_price IS NULL;
            RAISE NOTICE 'Added close_price column to price_daily table and copied data from close column';
        ELSE
            RAISE NOTICE 'close_price column already exists in price_daily table';
        END IF;
    ELSE
        RAISE NOTICE 'price_daily table does not exist';
    END IF;
END $$;

-- 2. Create portfolio_performance table if it doesn't exist (needed for daily_pnl_percent)
CREATE TABLE IF NOT EXISTS portfolio_performance (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    total_value DECIMAL(15,2) DEFAULT 0,
    total_pnl DECIMAL(15,2) DEFAULT 0,
    total_pnl_percent DECIMAL(8,4) DEFAULT 0,
    daily_pnl DECIMAL(15,2) DEFAULT 0,
    daily_pnl_percent DECIMAL(8,4) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Add daily_pnl_percent column if table exists but column is missing
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'portfolio_performance') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name = 'portfolio_performance' AND column_name = 'daily_pnl_percent') THEN
            ALTER TABLE portfolio_performance ADD COLUMN daily_pnl_percent DECIMAL(8,4) DEFAULT 0;
            -- Calculate daily_pnl_percent as (daily_pnl/total_value)*100
            UPDATE portfolio_performance
            SET daily_pnl_percent = CASE
                WHEN total_value > 0 THEN (daily_pnl/total_value)*100
                ELSE 0
            END
            WHERE daily_pnl_percent = 0 OR daily_pnl_percent IS NULL;
            RAISE NOTICE 'Added daily_pnl_percent column to portfolio_performance table';
        ELSE
            RAISE NOTICE 'daily_pnl_percent column already exists in portfolio_performance table';
        END IF;
    END IF;
END $$;

-- 4. Add change_percent to price_daily if missing (some tests expect this)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'price_daily') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name = 'price_daily' AND column_name = 'change_percent') THEN
            ALTER TABLE price_daily ADD COLUMN change_percent DECIMAL(8,4);
            RAISE NOTICE 'Added change_percent column to price_daily table';
        ELSE
            RAISE NOTICE 'change_percent column already exists in price_daily table';
        END IF;
    END IF;
END $$;

-- 5. Insert sample data for testing
INSERT INTO portfolio_performance (user_id, total_value, total_pnl, total_pnl_percent, daily_pnl, daily_pnl_percent)
VALUES
    ('dev-user-bypass', 100000.00, 5000.00, 5.00, 250.00, 0.25),
    ('dev-user-bypass', 105250.00, 5250.00, 5.26, 250.00, 0.24),
    ('dev-user-bypass', 104800.00, 4800.00, 4.78, -450.00, -0.43),
    ('test-user', 50000.00, 2000.00, 4.00, 100.00, 0.20),
    ('test-user', 50100.00, 2100.00, 4.19, 100.00, 0.20)
ON CONFLICT DO NOTHING;

-- 6. Add sample price data with close_price
INSERT INTO price_daily (symbol, date, open, high, low, close, close_price, adj_close, volume, change_percent)
VALUES
    ('AAPL', CURRENT_DATE - INTERVAL '1 day', 180.00, 182.50, 179.00, 181.25, 181.25, 181.25, 50000000, 0.69),
    ('AAPL', CURRENT_DATE - INTERVAL '2 days', 178.50, 180.75, 177.25, 180.00, 180.00, 180.00, 48000000, 0.84),
    ('MSFT', CURRENT_DATE - INTERVAL '1 day', 415.00, 418.75, 412.50, 417.50, 417.50, 417.50, 25000000, 0.60),
    ('MSFT', CURRENT_DATE - INTERVAL '2 days', 413.25, 416.00, 411.75, 415.00, 415.00, 415.00, 23000000, 0.42),
    ('GOOGL', CURRENT_DATE - INTERVAL '1 day', 140.00, 143.25, 139.50, 142.75, 142.75, 142.75, 30000000, 1.96),
    ('GOOGL', CURRENT_DATE - INTERVAL '2 days', 138.50, 141.00, 137.75, 140.00, 140.00, 140.00, 28000000, 1.08)
ON CONFLICT DO NOTHING;

-- 7. Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_price_daily_symbol_date ON price_daily(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_price_daily_close_price ON price_daily(close_price) WHERE close_price IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_portfolio_performance_user_date ON portfolio_performance(user_id, created_at DESC);

-- 8. Create missing sentiment_analysis table if needed
CREATE TABLE IF NOT EXISTS sentiment_analysis (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL DEFAULT CURRENT_DATE,
    sentiment_score DECIMAL(3,2) DEFAULT 0.00,
    news_count INTEGER DEFAULT 0,
    positive_count INTEGER DEFAULT 0,
    negative_count INTEGER DEFAULT 0,
    neutral_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

-- Add sample sentiment data
INSERT INTO sentiment_analysis (symbol, sentiment_score, news_count, positive_count, negative_count, neutral_count)
VALUES
    ('AAPL', 0.65, 25, 15, 5, 5),
    ('MSFT', 0.72, 18, 12, 3, 3),
    ('GOOGL', 0.58, 22, 12, 6, 4),
    ('TSLA', 0.45, 35, 15, 12, 8),
    ('NVDA', 0.78, 20, 16, 2, 2)
ON CONFLICT (symbol, date) DO NOTHING;

COMMIT;

-- Verification queries
SELECT 'price_daily close_price check' as check_name,
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'price_daily' AND column_name = 'close_price')
            THEN 'EXISTS' ELSE 'MISSING' END as status;

SELECT 'portfolio_performance daily_pnl_percent check' as check_name,
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'portfolio_performance' AND column_name = 'daily_pnl_percent')
            THEN 'EXISTS' ELSE 'MISSING' END as status;

SELECT 'sentiment_analysis table check' as check_name,
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'sentiment_analysis')
            THEN 'EXISTS' ELSE 'MISSING' END as status;