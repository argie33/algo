-- Create Missing Database Tables for Real Site Functionality
-- This script creates all the missing tables that the site requires to function without mock data

-- Earnings Reports Table
CREATE TABLE IF NOT EXISTS earnings_reports (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    quarter INTEGER,
    fiscal_year INTEGER,
    report_date DATE,
    actual_eps DECIMAL(10,4),
    estimated_eps DECIMAL(10,4),
    revenue BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Analyst Upgrade/Downgrade Table
CREATE TABLE IF NOT EXISTS analyst_upgrade_downgrade (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    company_name VARCHAR(255),
    from_grade VARCHAR(50),
    to_grade VARCHAR(50),
    action VARCHAR(20),
    firm VARCHAR(100),
    date_updated DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Analyst Coverage Table
CREATE TABLE IF NOT EXISTS analyst_coverage (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    firm VARCHAR(100),
    rating VARCHAR(50),
    price_target DECIMAL(10,2),
    date_updated DATE,
    analyst_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Analyst Price Targets Table
CREATE TABLE IF NOT EXISTS analyst_price_targets (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    firm VARCHAR(100),
    price_target DECIMAL(10,2),
    date_updated DATE,
    action VARCHAR(20),
    previous_target DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Analyst Recommendations Table
CREATE TABLE IF NOT EXISTS analyst_recommendations (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    recommendation VARCHAR(50),
    analyst VARCHAR(100),
    rating VARCHAR(50),
    analyst_name VARCHAR(255),
    date_published DATE,
    price_target DECIMAL(10,2),
    track_record VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Research Reports Table
CREATE TABLE IF NOT EXISTS research_reports (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10),
    firm VARCHAR(100),
    title VARCHAR(500),
    rating VARCHAR(50),
    price_target DECIMAL(10,2),
    published_date DATE,
    analyst VARCHAR(255),
    summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Watchlist Performance Table
CREATE TABLE IF NOT EXISTS watchlist_performance (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    watchlist_id INTEGER,
    total_return VARCHAR(20),
    daily_return VARCHAR(20),
    weekly_return VARCHAR(20),
    monthly_return VARCHAR(20),
    best_performer VARCHAR(100),
    worst_performer VARCHAR(100),
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sentiment Analysis Table
CREATE TABLE IF NOT EXISTS sentiment_analysis (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    period VARCHAR(10),
    up_last7days INTEGER DEFAULT 0,
    up_last30days INTEGER DEFAULT 0,
    down_last30days INTEGER DEFAULT 0,
    sentiment_score DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_earnings_reports_symbol ON earnings_reports(symbol);
CREATE INDEX IF NOT EXISTS idx_analyst_upgrade_downgrade_symbol ON analyst_upgrade_downgrade(symbol);
CREATE INDEX IF NOT EXISTS idx_analyst_coverage_symbol ON analyst_coverage(symbol);
CREATE INDEX IF NOT EXISTS idx_analyst_price_targets_symbol ON analyst_price_targets(symbol);
CREATE INDEX IF NOT EXISTS idx_analyst_recommendations_symbol ON analyst_recommendations(symbol);
CREATE INDEX IF NOT EXISTS idx_research_reports_symbol ON research_reports(symbol);
CREATE INDEX IF NOT EXISTS idx_watchlist_performance_user ON watchlist_performance(user_id);
CREATE INDEX IF NOT EXISTS idx_sentiment_analysis_symbol ON sentiment_analysis(symbol);

-- Ensure the main data tables exist (these should be created by Python loaders)
-- But we'll create them here if they don't exist for local testing

CREATE TABLE IF NOT EXISTS stocks (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) UNIQUE NOT NULL,
    company_name VARCHAR(255),
    sector VARCHAR(100),
    industry VARCHAR(100),
    market_cap BIGINT,
    current_price DECIMAL(10,2),
    change_amount DECIMAL(10,2),
    change_percent DECIMAL(5,2),
    volume BIGINT,
    avg_volume BIGINT,
    pe_ratio DECIMAL(10,2),
    dividend_yield DECIMAL(5,2),
    week_52_high DECIMAL(10,2),
    week_52_low DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert some basic stock data if table is empty
INSERT INTO stocks (symbol, company_name, sector, industry, market_cap, current_price, change_amount, change_percent, volume)
SELECT 'AAPL', 'Apple Inc.', 'Technology', 'Consumer Electronics', 3000000000000, 175.50, 2.50, 1.45, 50000000
WHERE NOT EXISTS (SELECT 1 FROM stocks WHERE symbol = 'AAPL');

INSERT INTO stocks (symbol, company_name, sector, industry, market_cap, current_price, change_amount, change_percent, volume)
SELECT 'MSFT', 'Microsoft Corporation', 'Technology', 'Software', 2800000000000, 410.25, 5.75, 1.42, 25000000
WHERE NOT EXISTS (SELECT 1 FROM stocks WHERE symbol = 'MSFT');

INSERT INTO stocks (symbol, company_name, sector, industry, market_cap, current_price, change_amount, change_percent, volume)
SELECT 'META', 'Meta Platforms Inc.', 'Technology', 'Social Media', 800000000000, 325.80, -3.20, -0.97, 15000000
WHERE NOT EXISTS (SELECT 1 FROM stocks WHERE symbol = 'META');

COMMIT;
