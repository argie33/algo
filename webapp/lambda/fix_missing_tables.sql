-- Fix Missing Tables for Test Suite
-- This script adds all the missing tables that are causing test failures

-- 1. analyst_upgrade_downgrade table
CREATE TABLE IF NOT EXISTS analyst_upgrade_downgrade (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    analyst_name VARCHAR(255),
    firm_name VARCHAR(255),
    action VARCHAR(20) NOT NULL CHECK (action IN ('upgrade', 'downgrade', 'initiate', 'maintain', 'reiterate')),
    from_rating VARCHAR(50),
    to_rating VARCHAR(50),
    price_target DECIMAL(10,2),
    previous_price_target DECIMAL(10,2),
    announcement_date DATE NOT NULL DEFAULT CURRENT_DATE,
    published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source VARCHAR(255),
    confidence_level VARCHAR(20) DEFAULT 'medium',
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add sample data for analyst_upgrade_downgrade
INSERT INTO analyst_upgrade_downgrade (symbol, analyst_name, firm_name, action, from_rating, to_rating, price_target, announcement_date)
VALUES
    ('AAPL', 'John Smith', 'Goldman Sachs', 'upgrade', 'Hold', 'Buy', 195.00, CURRENT_DATE - INTERVAL '1 day'),
    ('AAPL', 'Jane Doe', 'Morgan Stanley', 'maintain', 'Buy', 'Buy', 200.00, CURRENT_DATE - INTERVAL '2 days'),
    ('MSFT', 'Bob Johnson', 'JP Morgan', 'upgrade', 'Neutral', 'Overweight', 450.00, CURRENT_DATE - INTERVAL '3 days'),
    ('GOOGL', 'Alice Brown', 'Credit Suisse', 'downgrade', 'Outperform', 'Neutral', 140.00, CURRENT_DATE - INTERVAL '1 week'),
    ('TSLA', 'Mike Wilson', 'Deutsche Bank', 'initiate', NULL, 'Buy', 280.00, CURRENT_DATE - INTERVAL '5 days')
ON CONFLICT DO NOTHING;

-- 2. earnings_estimates table
CREATE TABLE IF NOT EXISTS earnings_estimates (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    fiscal_year INTEGER NOT NULL,
    fiscal_quarter INTEGER CHECK (fiscal_quarter IN (1, 2, 3, 4)),
    estimate_type VARCHAR(20) NOT NULL DEFAULT 'consensus' CHECK (estimate_type IN ('consensus', 'high', 'low', 'individual')),
    earnings_per_share DECIMAL(8,4),
    revenue_estimate BIGINT,
    growth_estimate DECIMAL(6,2),
    analyst_count INTEGER DEFAULT 1,
    estimate_date DATE NOT NULL DEFAULT CURRENT_DATE,
    revision_date DATE,
    surprise_history JSONB,
    guidance JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_year, fiscal_quarter, estimate_type)
);

-- Add sample data for earnings_estimates
INSERT INTO earnings_estimates (symbol, fiscal_year, fiscal_quarter, estimate_type, earnings_per_share, revenue_estimate, growth_estimate, analyst_count)
VALUES
    ('AAPL', 2024, 4, 'consensus', 2.18, 119300000000, 2.1, 25),
    ('AAPL', 2024, 4, 'high', 2.25, 121000000000, 3.5, 25),
    ('AAPL', 2024, 4, 'low', 2.10, 117500000000, 0.5, 25),
    ('MSFT', 2024, 4, 'consensus', 2.95, 64500000000, 15.2, 22),
    ('MSFT', 2024, 4, 'high', 3.05, 66000000000, 18.0, 22),
    ('MSFT', 2024, 4, 'low', 2.85, 63000000000, 12.5, 22),
    ('GOOGL', 2024, 4, 'consensus', 1.55, 86250000000, 8.9, 20),
    ('TSLA', 2024, 4, 'consensus', 0.73, 25500000000, 22.5, 18)
ON CONFLICT (symbol, fiscal_year, fiscal_quarter, estimate_type) DO UPDATE SET
    earnings_per_share = EXCLUDED.earnings_per_share,
    revenue_estimate = EXCLUDED.revenue_estimate,
    growth_estimate = EXCLUDED.growth_estimate,
    analyst_count = EXCLUDED.analyst_count,
    updated_at = CURRENT_TIMESTAMP;

-- 3. news table (if missing)
CREATE TABLE IF NOT EXISTS news (
    id SERIAL PRIMARY KEY,
    headline VARCHAR(500) NOT NULL,
    summary TEXT,
    url VARCHAR(1000) UNIQUE,
    source VARCHAR(255),
    category VARCHAR(100),
    symbol VARCHAR(10),
    published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sentiment VARCHAR(20) DEFAULT 'neutral' CHECK (sentiment IN ('positive', 'negative', 'neutral')),
    relevance_score DECIMAL(4,3) DEFAULT 0.500,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add sample news data
INSERT INTO news (headline, summary, url, source, category, symbol, sentiment, relevance_score)
VALUES
    ('Apple Reports Strong Q4 Earnings', 'Apple Inc. reported better than expected quarterly results with strong iPhone sales.', 'https://example.com/apple-q4', 'Financial Times', 'earnings', 'AAPL', 'positive', 0.850),
    ('Microsoft Azure Growth Continues', 'Microsoft cloud services show continued strong growth in enterprise segment.', 'https://example.com/msft-azure', 'Reuters', 'business', 'MSFT', 'positive', 0.780),
    ('Tesla Production Update', 'Tesla provides update on production numbers and delivery targets for next quarter.', 'https://example.com/tesla-production', 'Bloomberg', 'business', 'TSLA', 'neutral', 0.650),
    ('Google AI Investment', 'Alphabet increases investment in artificial intelligence capabilities.', 'https://example.com/google-ai', 'TechCrunch', 'technology', 'GOOGL', 'positive', 0.720),
    ('Market Volatility Ahead', 'Analysts warn of potential market volatility due to economic indicators.', 'https://example.com/market-volatility', 'Wall Street Journal', 'market', NULL, 'negative', 0.600)
ON CONFLICT (url) DO NOTHING;

-- 4. stock_news table (if missing)
CREATE TABLE IF NOT EXISTS stock_news (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    headline VARCHAR(500) NOT NULL,
    summary TEXT,
    url VARCHAR(1000),
    source VARCHAR(255),
    published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sentiment VARCHAR(20) DEFAULT 'neutral',
    impact_score DECIMAL(4,3) DEFAULT 0.500,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add sample stock news data
INSERT INTO stock_news (symbol, headline, summary, url, source, sentiment, impact_score)
VALUES
    ('AAPL', 'Apple Stock Rating Upgraded by Analyst', 'Major investment firm upgrades Apple stock rating to Buy.', 'https://example.com/apple-upgrade', 'MarketWatch', 'positive', 0.750),
    ('MSFT', 'Microsoft Announces New Cloud Partnership', 'Strategic partnership expected to boost cloud revenue growth.', 'https://example.com/msft-partnership', 'CNBC', 'positive', 0.680),
    ('TSLA', 'Tesla Delivery Numbers Miss Estimates', 'Quarterly delivery numbers come in below analyst expectations.', 'https://example.com/tesla-delivery', 'Reuters', 'negative', 0.820),
    ('GOOGL', 'Alphabet Faces Regulatory Scrutiny', 'New regulatory investigations may impact business operations.', 'https://example.com/google-regulatory', 'Financial Times', 'negative', 0.750)
ON CONFLICT DO NOTHING;

-- 5. economic_events table (if missing)
CREATE TABLE IF NOT EXISTS economic_events (
    id SERIAL PRIMARY KEY,
    event_name VARCHAR(255) NOT NULL,
    event_date DATE NOT NULL,
    event_time TIME,
    importance VARCHAR(20) DEFAULT 'medium' CHECK (importance IN ('low', 'medium', 'high')),
    country VARCHAR(50) DEFAULT 'US',
    category VARCHAR(100),
    previous_value DECIMAL(15,4),
    forecast_value DECIMAL(15,4),
    actual_value DECIMAL(15,4),
    unit VARCHAR(50),
    description TEXT,
    source VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add sample economic events
INSERT INTO economic_events (event_name, event_date, importance, country, category, previous_value, forecast_value, description)
VALUES
    ('Federal Reserve Interest Rate Decision', CURRENT_DATE + INTERVAL '7 days', 'high', 'US', 'monetary_policy', 5.25, 5.25, 'Fed decides on federal funds rate'),
    ('Non-Farm Payrolls', CURRENT_DATE + INTERVAL '3 days', 'high', 'US', 'employment', 150000, 165000, 'Monthly employment change'),
    ('Consumer Price Index', CURRENT_DATE + INTERVAL '5 days', 'high', 'US', 'inflation', 3.2, 3.1, 'Monthly inflation measure'),
    ('GDP Growth Rate', CURRENT_DATE + INTERVAL '14 days', 'medium', 'US', 'growth', 2.1, 2.3, 'Quarterly GDP growth rate'),
    ('Unemployment Rate', CURRENT_DATE + INTERVAL '3 days', 'high', 'US', 'employment', 3.7, 3.6, 'Monthly unemployment rate')
ON CONFLICT DO NOTHING;

-- 6. Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_analyst_upgrade_downgrade_symbol ON analyst_upgrade_downgrade(symbol);
CREATE INDEX IF NOT EXISTS idx_analyst_upgrade_downgrade_date ON analyst_upgrade_downgrade(announcement_date DESC);
CREATE INDEX IF NOT EXISTS idx_earnings_estimates_symbol_year ON earnings_estimates(symbol, fiscal_year DESC);
CREATE INDEX IF NOT EXISTS idx_news_symbol ON news(symbol);
CREATE INDEX IF NOT EXISTS idx_news_published_at ON news(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_stock_news_symbol ON stock_news(symbol);
CREATE INDEX IF NOT EXISTS idx_economic_events_date ON economic_events(event_date);

-- 7. Fix existing sentiment_analysis table if needed
DO $$
BEGIN
    -- Add missing columns to sentiment_analysis if they don't exist
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'sentiment_analysis') THEN
        ALTER TABLE sentiment_analysis ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        ALTER TABLE sentiment_analysis ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
    END IF;
END $$;

COMMIT;