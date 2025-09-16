-- Comprehensive Database Schema Fix Script
-- This script addresses all identified missing columns and tables

-- First, add missing columns to existing tables

-- 1. Add sentiment column to stock_scores table
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'stock_scores' AND column_name = 'sentiment') THEN
        ALTER TABLE stock_scores ADD COLUMN sentiment DECIMAL(5,2) DEFAULT NULL;
    END IF;
END $$;

-- 2. Add var_1d column to portfolio_risk table (if it exists)
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'portfolio_risk') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_name = 'portfolio_risk' AND column_name = 'var_1d') THEN
            ALTER TABLE portfolio_risk ADD COLUMN var_1d DECIMAL(10,4) DEFAULT NULL;
        END IF;
    END IF;
END $$;

-- 3. Add transaction_id column to portfolio_transactions table (if it exists)
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'portfolio_transactions') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_name = 'portfolio_transactions' AND column_name = 'transaction_id') THEN
            ALTER TABLE portfolio_transactions ADD COLUMN transaction_id SERIAL PRIMARY KEY;
        END IF;
    END IF;
END $$;

-- 4. Add previous_close column to price_daily table
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'price_daily') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_name = 'price_daily' AND column_name = 'previous_close') THEN
            ALTER TABLE price_daily ADD COLUMN previous_close DECIMAL(12,4) DEFAULT NULL;
        END IF;
    END IF;
END $$;

-- 5. Add previous_close column to stocks table (for market movers)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'stocks' AND column_name = 'previous_close') THEN
        ALTER TABLE stocks ADD COLUMN previous_close DECIMAL(12,4) DEFAULT NULL;
    END IF;
END $$;

-- 6. Create market_indices table if it doesn't exist
CREATE TABLE IF NOT EXISTS market_indices (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    current_price DECIMAL(12,4),
    change_amount DECIMAL(12,4),
    change_percent DECIMAL(8,4),
    volume BIGINT,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 7. Add change_amount column to market_indices table if missing
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'market_indices') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_name = 'market_indices' AND column_name = 'change_amount') THEN
            ALTER TABLE market_indices ADD COLUMN change_amount DECIMAL(12,4) DEFAULT NULL;
        END IF;
    END IF;
END $$;

-- 8. Create annual_balance_sheet table
CREATE TABLE IF NOT EXISTS annual_balance_sheet (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    item_name VARCHAR(200) NOT NULL,
    value BIGINT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date, item_name)
);

-- 9. Create annual_income_statement table
CREATE TABLE IF NOT EXISTS annual_income_statement (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    item_name VARCHAR(200) NOT NULL,
    value BIGINT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date, item_name)
);

-- 10. Create portfolio_risk table if it doesn't exist
CREATE TABLE IF NOT EXISTS portfolio_risk (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    risk_score DECIMAL(5,2),
    beta DECIMAL(8,4),
    var_1d DECIMAL(10,4),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id)
);

-- Insert some sample data for market indices
INSERT INTO market_indices (symbol, name, current_price, change_amount, change_percent, volume)
VALUES 
    ('SPY', 'SPDR S&P 500 ETF Trust', 560.25, 2.45, 0.44, 89234567),
    ('QQQ', 'Invesco QQQ Trust', 495.80, -1.25, -0.25, 45123456),
    ('IWM', 'iShares Russell 2000 ETF', 225.40, 0.85, 0.38, 23456789),
    ('DIA', 'SPDR Dow Jones Industrial Average ETF', 420.15, 3.20, 0.77, 12345678)
ON CONFLICT (symbol) DO UPDATE SET
    current_price = EXCLUDED.current_price,
    change_amount = EXCLUDED.change_amount,
    change_percent = EXCLUDED.change_percent,
    volume = EXCLUDED.volume,
    last_updated = CURRENT_TIMESTAMP,
    updated_at = CURRENT_TIMESTAMP;

-- Insert sample data for annual financial statements (AAPL example)
INSERT INTO annual_balance_sheet (symbol, date, item_name, value)
VALUES 
    ('AAPL', '2023-09-30', 'Total Assets', 352755000000),
    ('AAPL', '2023-09-30', 'Total Liabilities', 290437000000),
    ('AAPL', '2023-09-30', 'Total Equity', 62318000000),
    ('AAPL', '2022-09-30', 'Total Assets', 352583000000),
    ('AAPL', '2022-09-30', 'Total Liabilities', 302083000000),
    ('AAPL', '2022-09-30', 'Total Equity', 50500000000)
ON CONFLICT (symbol, date, item_name) DO UPDATE SET
    value = EXCLUDED.value,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO annual_income_statement (symbol, date, item_name, value)
VALUES 
    ('AAPL', '2023-09-30', 'Total Revenue', 383285000000),
    ('AAPL', '2023-09-30', 'Net Income', 96995000000),
    ('AAPL', '2023-09-30', 'Operating Income', 114301000000),
    ('AAPL', '2022-09-30', 'Total Revenue', 394328000000),
    ('AAPL', '2022-09-30', 'Net Income', 99803000000),
    ('AAPL', '2022-09-30', 'Operating Income', 119437000000)
ON CONFLICT (symbol, date, item_name) DO UPDATE SET
    value = EXCLUDED.value,
    updated_at = CURRENT_TIMESTAMP;

-- Insert sample portfolio risk data for dev user
INSERT INTO portfolio_risk (user_id, risk_score, beta, var_1d)
VALUES ('dev-user-bypass', 7.5, 1.25, -2.34)
ON CONFLICT (user_id) DO UPDATE SET
    risk_score = EXCLUDED.risk_score,
    beta = EXCLUDED.beta,
    var_1d = EXCLUDED.var_1d,
    updated_at = CURRENT_TIMESTAMP;

-- Update stock_scores with sample sentiment data
UPDATE stock_scores SET sentiment = 
    CASE 
        WHEN composite_score > 7 THEN ROUND(random() * 20 + 70, 2)  -- Positive sentiment for high scores
        WHEN composite_score > 5 THEN ROUND(random() * 40 + 40, 2)  -- Neutral sentiment for medium scores  
        ELSE ROUND(random() * 40 + 20, 2)  -- Negative sentiment for low scores
    END
WHERE sentiment IS NULL;

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_annual_balance_sheet_symbol_date ON annual_balance_sheet(symbol, date);
CREATE INDEX IF NOT EXISTS idx_annual_income_statement_symbol_date ON annual_income_statement(symbol, date);
CREATE INDEX IF NOT EXISTS idx_market_indices_symbol ON market_indices(symbol);
CREATE INDEX IF NOT EXISTS idx_portfolio_risk_user_id ON portfolio_risk(user_id);

-- Update previous_close values for existing data
UPDATE stocks SET previous_close = 
    CASE 
        WHEN last_price IS NOT NULL AND change_percent IS NOT NULL 
        THEN ROUND(last_price / (1 + change_percent / 100), 4)
        ELSE last_price
    END
WHERE previous_close IS NULL AND last_price IS NOT NULL;

-- Add the fundamental_metrics table that's causing screener API errors
CREATE TABLE IF NOT EXISTS fundamental_metrics (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    pe_ratio DECIMAL(10,2),
    dividend_yield DECIMAL(5,2),
    profit_margin DECIMAL(5,2),
    debt_to_equity DECIMAL(10,2),
    roe DECIMAL(5,2),  -- Return on Equity
    roa DECIMAL(5,2),  -- Return on Assets
    current_ratio DECIMAL(10,2),
    quick_ratio DECIMAL(10,2),
    price_to_book DECIMAL(10,2),
    price_to_sales DECIMAL(10,2),
    revenue_growth DECIMAL(5,2),
    earnings_growth DECIMAL(5,2),
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, last_updated)
);

-- Create index on fundamental_metrics symbol
CREATE INDEX IF NOT EXISTS idx_fundamental_metrics_symbol ON fundamental_metrics(symbol);

-- Add the news table that's causing news API errors
CREATE TABLE IF NOT EXISTS news (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT,
    url TEXT,
    source VARCHAR(100),
    category VARCHAR(50),
    published_at TIMESTAMP,
    sentiment DECIMAL(3,2), -- sentiment score from -1 to 1
    symbols TEXT[], -- array of related stock symbols
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes on news table
CREATE INDEX IF NOT EXISTS idx_news_published_at ON news(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_symbols ON news USING GIN(symbols);
CREATE INDEX IF NOT EXISTS idx_news_category ON news(category);

-- Insert sample data into fundamental_metrics for existing stocks
INSERT INTO fundamental_metrics (symbol, pe_ratio, dividend_yield, profit_margin, debt_to_equity, roe, roa, current_ratio, quick_ratio, price_to_book, price_to_sales, revenue_growth, earnings_growth)
SELECT DISTINCT symbol,
    CASE WHEN random() < 0.5 THEN 15 + random() * 25 ELSE NULL END, -- pe_ratio between 15-40 or NULL
    CASE WHEN random() < 0.6 THEN random() * 5 ELSE NULL END, -- dividend_yield 0-5% or NULL
    CASE WHEN random() < 0.7 THEN 5 + random() * 20 ELSE NULL END, -- profit_margin 5-25% or NULL
    CASE WHEN random() < 0.8 THEN random() * 2 ELSE NULL END, -- debt_to_equity 0-2 or NULL
    CASE WHEN random() < 0.7 THEN 10 + random() * 20 ELSE NULL END, -- roe 10-30% or NULL
    CASE WHEN random() < 0.7 THEN 5 + random() * 15 ELSE NULL END, -- roa 5-20% or NULL
    CASE WHEN random() < 0.8 THEN 1 + random() * 2 ELSE NULL END, -- current_ratio 1-3 or NULL
    CASE WHEN random() < 0.8 THEN 0.5 + random() * 1.5 ELSE NULL END, -- quick_ratio 0.5-2 or NULL
    CASE WHEN random() < 0.8 THEN 1 + random() * 4 ELSE NULL END, -- price_to_book 1-5 or NULL
    CASE WHEN random() < 0.8 THEN 2 + random() * 8 ELSE NULL END, -- price_to_sales 2-10 or NULL
    CASE WHEN random() < 0.6 THEN -10 + random() * 30 ELSE NULL END, -- revenue_growth -10% to 20%
    CASE WHEN random() < 0.6 THEN -15 + random() * 40 ELSE NULL END -- earnings_growth -15% to 25%
FROM price_daily 
WHERE NOT EXISTS (SELECT 1 FROM fundamental_metrics WHERE fundamental_metrics.symbol = price_daily.symbol)
LIMIT 50; -- Add metrics for up to 50 stocks

-- Insert sample news data
INSERT INTO news (title, summary, url, source, category, published_at, sentiment, symbols) 
VALUES 
('Market Shows Strong Performance Amid Economic Uncertainty', 'Markets continued their upward trend despite ongoing economic challenges...', 'https://example.com/news1', 'Financial Times', 'market', NOW() - INTERVAL '2 hours', 0.3, ARRAY['SPY', 'QQQ']),
('Tech Stocks Rally on AI Innovation News', 'Major technology companies saw significant gains following announcements...', 'https://example.com/news2', 'Bloomberg', 'technology', NOW() - INTERVAL '4 hours', 0.6, ARRAY['AAPL', 'MSFT', 'GOOGL']),
('Federal Reserve Maintains Interest Rates', 'The Federal Reserve decided to keep interest rates unchanged...', 'https://example.com/news3', 'Reuters', 'economics', NOW() - INTERVAL '1 day', 0.1, ARRAY['SPY', 'TLT']),
('Energy Sector Sees Mixed Results', 'Oil and gas companies reported varied quarterly earnings...', 'https://example.com/news4', 'Wall Street Journal', 'energy', NOW() - INTERVAL '6 hours', -0.2, ARRAY['XOM', 'CVX']),
('Retail Earnings Beat Expectations', 'Several major retailers reported better than expected quarterly results...', 'https://example.com/news5', 'CNBC', 'retail', NOW() - INTERVAL '8 hours', 0.4, ARRAY['WMT', 'TGT']),
('Healthcare Stocks Rise on Drug Approval', 'Pharmaceutical companies gained after FDA approval announcements...', 'https://example.com/news6', 'Reuters', 'healthcare', NOW() - INTERVAL '10 hours', 0.5, ARRAY['JNJ', 'PFE']),
('Financial Sector Earnings Mixed', 'Banks reported varied quarterly results with some beating expectations...', 'https://example.com/news7', 'Bloomberg', 'finance', NOW() - INTERVAL '12 hours', 0.1, ARRAY['JPM', 'BAC']),
('Consumer Spending Shows Resilience', 'Retail sales data indicates continued consumer confidence...', 'https://example.com/news8', 'CNBC', 'consumer', NOW() - INTERVAL '14 hours', 0.3, ARRAY['WMT', 'AMZN']);

COMMIT;