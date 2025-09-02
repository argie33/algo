-- Dummy data for local development testing
-- This script populates tables with test data to match AWS loader structure

-- Create tables (matching loader structures)
CREATE TABLE IF NOT EXISTS price_daily (
    id           SERIAL PRIMARY KEY,
    symbol       VARCHAR(10) NOT NULL,
    date         DATE         NOT NULL,
    open         DOUBLE PRECISION,
    high         DOUBLE PRECISION,
    low          DOUBLE PRECISION,
    close        DOUBLE PRECISION,
    adj_close    DOUBLE PRECISION,
    volume       BIGINT,
    dividends    DOUBLE PRECISION,
    stock_splits DOUBLE PRECISION,
    fetched_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

CREATE TABLE IF NOT EXISTS economic_data (
    series_id TEXT NOT NULL,
    date       DATE NOT NULL,
    value      DOUBLE PRECISION,
    title      TEXT,
    units      TEXT,
    frequency  TEXT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (series_id, date)
);

CREATE TABLE IF NOT EXISTS news (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10),
    headline TEXT NOT NULL,
    summary TEXT,
    url TEXT,
    published_at TIMESTAMP,
    sentiment DOUBLE PRECISION,
    relevance_score DOUBLE PRECISION,
    source VARCHAR(100),
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sentiment (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    sentiment_score DOUBLE PRECISION,
    positive_mentions INTEGER,
    negative_mentions INTEGER,
    neutral_mentions INTEGER,
    total_mentions INTEGER,
    source VARCHAR(50),
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date, source)
);

CREATE TABLE IF NOT EXISTS technicals_daily (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    rsi DOUBLE PRECISION,
    macd DOUBLE PRECISION,
    macd_signal DOUBLE PRECISION,
    macd_histogram DOUBLE PRECISION,
    sma_20 DOUBLE PRECISION,
    sma_50 DOUBLE PRECISION,
    sma_200 DOUBLE PRECISION,
    ema_12 DOUBLE PRECISION,
    ema_26 DOUBLE PRECISION,
    bollinger_upper DOUBLE PRECISION,
    bollinger_middle DOUBLE PRECISION,
    bollinger_lower DOUBLE PRECISION,
    stochastic_k DOUBLE PRECISION,
    stochastic_d DOUBLE PRECISION,
    williams_r DOUBLE PRECISION,
    atr DOUBLE PRECISION,
    adx DOUBLE PRECISION,
    cci DOUBLE PRECISION,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

CREATE TABLE IF NOT EXISTS analyst_recommendations (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    analyst_firm VARCHAR(100),
    rating VARCHAR(20),
    target_price DOUBLE PRECISION,
    current_price DOUBLE PRECISION,
    date_published DATE,
    date_updated DATE DEFAULT CURRENT_DATE,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS market_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    close_price DOUBLE PRECISION,
    market_cap BIGINT,
    volume BIGINT,
    sector VARCHAR(50),
    industry VARCHAR(100),
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

CREATE TABLE IF NOT EXISTS dividends (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    ex_date DATE NOT NULL,
    record_date DATE,
    payment_date DATE,
    amount DOUBLE PRECISION,
    yield_percent DOUBLE PRECISION,
    frequency VARCHAR(20),
    type VARCHAR(20),
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, ex_date)
);

CREATE TABLE IF NOT EXISTS stock_splits (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    ex_date DATE NOT NULL,
    declaration_date DATE,
    ratio VARCHAR(10),
    split_factor DOUBLE PRECISION,
    pre_split_price DOUBLE PRECISION,
    post_split_price DOUBLE PRECISION,
    reason TEXT,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, ex_date)
);

CREATE TABLE IF NOT EXISTS insider_transactions (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    insider_name VARCHAR(100),
    title VARCHAR(50),
    transaction_date DATE,
    transaction_type VARCHAR(30),
    shares INTEGER,
    price DOUBLE PRECISION,
    value DOUBLE PRECISION,
    ownership_type VARCHAR(20),
    remaining_shares INTEGER,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS portfolio_risk (
    id SERIAL PRIMARY KEY,
    portfolio_id VARCHAR(50),
    date DATE DEFAULT CURRENT_DATE,
    risk_score DOUBLE PRECISION,
    beta DOUBLE PRECISION,
    var_95 DOUBLE PRECISION,
    sharpe_ratio DOUBLE PRECISION,
    max_drawdown DOUBLE PRECISION,
    volatility DOUBLE PRECISION,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(portfolio_id, date)
);

-- Insert dummy data for testing

-- Price data for major stocks
INSERT INTO price_daily (symbol, date, open, high, low, close, adj_close, volume, dividends, stock_splits)
VALUES 
    ('AAPL', CURRENT_DATE, 185.50, 187.20, 184.80, 186.75, 186.75, 45000000, 0, 0),
    ('AAPL', CURRENT_DATE - INTERVAL '1 day', 183.20, 185.60, 182.90, 185.50, 185.50, 42000000, 0, 0),
    ('MSFT', CURRENT_DATE, 410.30, 412.80, 408.50, 411.25, 411.25, 22000000, 0, 0),
    ('MSFT', CURRENT_DATE - INTERVAL '1 day', 408.75, 410.40, 407.20, 410.30, 410.30, 21500000, 0, 0),
    ('GOOGL', CURRENT_DATE, 138.45, 139.80, 137.90, 139.20, 139.20, 18000000, 0, 0),
    ('TSLA', CURRENT_DATE, 248.60, 252.30, 247.10, 250.85, 250.85, 85000000, 0, 0),
    ('NVDA', CURRENT_DATE, 875.20, 882.50, 870.40, 878.90, 878.90, 35000000, 0, 0)
ON CONFLICT (symbol, date) DO NOTHING;

-- Economic data
INSERT INTO economic_data (series_id, date, value, title, units, frequency)
VALUES 
    ('GDPC1', CURRENT_DATE - INTERVAL '30 days', 27000.5, 'Real Gross Domestic Product', 'Billions of Chained 2012 Dollars', 'Quarterly'),
    ('UNRATE', CURRENT_DATE - INTERVAL '30 days', 3.7, 'Unemployment Rate', 'Percent', 'Monthly'),
    ('CPIAUCSL', CURRENT_DATE - INTERVAL '30 days', 307.8, 'Consumer Price Index for All Urban Consumers', 'Index 1982-1984=100', 'Monthly'),
    ('FEDFUNDS', CURRENT_DATE - INTERVAL '30 days', 5.25, 'Federal Funds Effective Rate', 'Percent', 'Monthly'),
    ('DGS10', CURRENT_DATE - INTERVAL '30 days', 4.35, '10-Year Treasury Constant Maturity Rate', 'Percent', 'Daily'),
    ('SP500', CURRENT_DATE - INTERVAL '30 days', 4750.2, 'S&P 500', 'Index', 'Daily')
ON CONFLICT (series_id, date) DO NOTHING;

-- News data
INSERT INTO news (symbol, headline, summary, url, published_at, sentiment, relevance_score, source)
VALUES 
    ('AAPL', 'Apple Reports Strong Q4 Earnings', 'Apple Inc. reported better than expected earnings for Q4 with revenue growth across all segments.', 'https://example.com/apple-earnings', CURRENT_TIMESTAMP - INTERVAL '2 hours', 0.8, 0.9, 'Reuters'),
    ('MSFT', 'Microsoft Cloud Revenue Surges', 'Microsoft Azure cloud services revenue increased 30% year-over-year in latest quarter.', 'https://example.com/msft-cloud', CURRENT_TIMESTAMP - INTERVAL '4 hours', 0.7, 0.85, 'Bloomberg'),
    ('TSLA', 'Tesla Delivers Record Number of Vehicles', 'Tesla delivered a record number of electric vehicles in Q4, beating analyst expectations.', 'https://example.com/tesla-deliveries', CURRENT_TIMESTAMP - INTERVAL '6 hours', 0.6, 0.8, 'CNBC')
ON CONFLICT DO NOTHING;

-- Technical indicators
INSERT INTO technicals_daily (symbol, date, rsi, macd, macd_signal, sma_20, sma_50, sma_200, bollinger_upper, bollinger_middle, bollinger_lower)
VALUES 
    ('AAPL', CURRENT_DATE, 65.4, 2.1, 1.8, 185.20, 182.50, 175.80, 190.50, 186.75, 183.00),
    ('MSFT', CURRENT_DATE, 58.2, 5.2, 4.1, 408.90, 405.30, 395.20, 415.80, 411.25, 406.70),
    ('GOOGL', CURRENT_DATE, 52.1, -0.8, -0.5, 138.80, 140.20, 135.60, 142.30, 139.20, 136.10),
    ('TSLA', CURRENT_DATE, 72.8, 8.5, 6.2, 245.60, 240.30, 235.80, 255.20, 250.85, 246.50),
    ('NVDA', CURRENT_DATE, 68.9, 15.2, 12.8, 870.40, 850.20, 780.60, 890.30, 878.90, 867.50)
ON CONFLICT (symbol, date) DO NOTHING;

-- Analyst recommendations
INSERT INTO analyst_recommendations (symbol, analyst_firm, rating, target_price, current_price, date_published)
VALUES 
    ('AAPL', 'Goldman Sachs', 'BUY', 200.00, 186.75, CURRENT_DATE - INTERVAL '3 days'),
    ('AAPL', 'Morgan Stanley', 'OVERWEIGHT', 195.00, 186.75, CURRENT_DATE - INTERVAL '5 days'),
    ('MSFT', 'JP Morgan', 'OVERWEIGHT', 450.00, 411.25, CURRENT_DATE - INTERVAL '2 days'),
    ('GOOGL', 'Barclays', 'EQUAL WEIGHT', 145.00, 139.20, CURRENT_DATE - INTERVAL '1 day'),
    ('TSLA', 'Wedbush', 'OUTPERFORM', 300.00, 250.85, CURRENT_DATE - INTERVAL '4 days')
ON CONFLICT DO NOTHING;

-- Market data
INSERT INTO market_data (symbol, date, close_price, market_cap, volume, sector, industry)
VALUES 
    ('AAPL', CURRENT_DATE, 186.75, 2900000000000, 45000000, 'Technology', 'Consumer Electronics'),
    ('MSFT', CURRENT_DATE, 411.25, 3100000000000, 22000000, 'Technology', 'Software'),
    ('GOOGL', CURRENT_DATE, 139.20, 1750000000000, 18000000, 'Technology', 'Internet Services'),
    ('TSLA', CURRENT_DATE, 250.85, 800000000000, 85000000, 'Consumer Cyclical', 'Auto Manufacturers'),
    ('NVDA', CURRENT_DATE, 878.90, 2200000000000, 35000000, 'Technology', 'Semiconductors')
ON CONFLICT (symbol, date) DO NOTHING;

-- Dividends
INSERT INTO dividends (symbol, ex_date, record_date, payment_date, amount, yield_percent, frequency, type)
VALUES 
    ('AAPL', CURRENT_DATE - INTERVAL '30 days', CURRENT_DATE - INTERVAL '28 days', CURRENT_DATE - INTERVAL '7 days', 0.24, 0.52, 'Quarterly', 'Cash'),
    ('MSFT', CURRENT_DATE - INTERVAL '25 days', CURRENT_DATE - INTERVAL '23 days', CURRENT_DATE - INTERVAL '5 days', 0.75, 0.73, 'Quarterly', 'Cash'),
    ('GOOGL', CURRENT_DATE - INTERVAL '90 days', CURRENT_DATE - INTERVAL '88 days', CURRENT_DATE - INTERVAL '70 days', 0.20, 0.58, 'Quarterly', 'Cash')
ON CONFLICT (symbol, ex_date) DO NOTHING;

-- Portfolio risk data
INSERT INTO portfolio_risk (portfolio_id, date, risk_score, beta, var_95, sharpe_ratio, max_drawdown, volatility)
VALUES 
    ('default', CURRENT_DATE, 65.5, 1.15, -0.025, 1.2, -0.08, 0.18),
    ('aggressive', CURRENT_DATE, 85.2, 1.45, -0.045, 1.8, -0.15, 0.28),
    ('conservative', CURRENT_DATE, 35.8, 0.75, -0.015, 0.9, -0.05, 0.12)
ON CONFLICT (portfolio_id, date) DO NOTHING;

-- Sentiment data
INSERT INTO sentiment (symbol, date, sentiment_score, positive_mentions, negative_mentions, neutral_mentions, total_mentions, source)
VALUES 
    ('AAPL', CURRENT_DATE, 0.65, 150, 45, 105, 300, 'twitter'),
    ('MSFT', CURRENT_DATE, 0.72, 120, 30, 80, 230, 'twitter'),
    ('GOOGL', CURRENT_DATE, 0.45, 80, 60, 90, 230, 'twitter'),
    ('TSLA', CURRENT_DATE, 0.55, 200, 120, 180, 500, 'twitter'),
    ('NVDA', CURRENT_DATE, 0.78, 180, 25, 95, 300, 'twitter')
ON CONFLICT (symbol, date, source) DO NOTHING;

SELECT 'Dummy data inserted successfully!' as status;