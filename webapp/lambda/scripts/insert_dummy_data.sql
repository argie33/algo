-- Insert dummy data using existing table structures

-- Economic data (using existing columns: indicator, value, period, etc.)
INSERT INTO economic_data (indicator, value, period, unit, description, name, frequency)
VALUES 
    ('GDPC1', 27000.5, CURRENT_DATE - INTERVAL '30 days', 'Billions', 'Real Gross Domestic Product', 'Real GDP', 'Quarterly'),
    ('UNRATE', 3.7, CURRENT_DATE - INTERVAL '30 days', 'Percent', 'Unemployment Rate', 'Unemployment Rate', 'Monthly'),
    ('CPIAUCSL', 307.8, CURRENT_DATE - INTERVAL '30 days', 'Index', 'Consumer Price Index for All Urban Consumers', 'CPI', 'Monthly'),
    ('FEDFUNDS', 5.25, CURRENT_DATE - INTERVAL '30 days', 'Percent', 'Federal Funds Effective Rate', 'Fed Funds Rate', 'Monthly'),
    ('DGS10', 4.35, CURRENT_DATE - INTERVAL '30 days', 'Percent', '10-Year Treasury Constant Maturity Rate', '10-Year Treasury', 'Daily'),
    ('SP500', 4750.2, CURRENT_DATE - INTERVAL '30 days', 'Index', 'S&P 500', 'S&P 500 Index', 'Daily')
ON CONFLICT DO NOTHING;

-- Market data (using ticker column)
INSERT INTO market_data (ticker, current_price, regular_market_price, volume, market_cap, 
                        fifty_two_week_low, fifty_two_week_high, fifty_day_avg, two_hundred_day_avg)
VALUES 
    ('AAPL', 186.75, 186.75, 45000000, 2900000000000, 124.17, 199.62, 185.20, 175.80),
    ('MSFT', 411.25, 411.25, 22000000, 3100000000000, 309.45, 468.35, 408.90, 395.20),
    ('GOOGL', 139.20, 139.20, 18000000, 1750000000000, 83.45, 153.78, 138.80, 135.60),
    ('TSLA', 250.85, 250.85, 85000000, 800000000000, 101.81, 299.29, 245.60, 235.80),
    ('NVDA', 878.90, 878.90, 35000000, 2200000000000, 180.96, 974.00, 870.40, 780.60)
ON CONFLICT (ticker) DO UPDATE SET
    current_price = EXCLUDED.current_price,
    regular_market_price = EXCLUDED.regular_market_price,
    volume = EXCLUDED.volume,
    market_cap = EXCLUDED.market_cap;

-- Check if price_daily table exists and insert data
INSERT INTO price_daily (symbol, date, open, high, low, close, adj_close, volume, dividends, stock_splits)
SELECT * FROM (VALUES 
    ('AAPL', CURRENT_DATE, 185.50, 187.20, 184.80, 186.75, 186.75, 45000000, 0, 0),
    ('AAPL', CURRENT_DATE - INTERVAL '1 day', 183.20, 185.60, 182.90, 185.50, 185.50, 42000000, 0, 0),
    ('MSFT', CURRENT_DATE, 410.30, 412.80, 408.50, 411.25, 411.25, 22000000, 0, 0),
    ('MSFT', CURRENT_DATE - INTERVAL '1 day', 408.75, 410.40, 407.20, 410.30, 410.30, 21500000, 0, 0),
    ('GOOGL', CURRENT_DATE, 138.45, 139.80, 137.90, 139.20, 139.20, 18000000, 0, 0),
    ('TSLA', CURRENT_DATE, 248.60, 252.30, 247.10, 250.85, 250.85, 85000000, 0, 0),
    ('NVDA', CURRENT_DATE, 875.20, 882.50, 870.40, 878.90, 878.90, 35000000, 0, 0)
) AS v(symbol, date, open, high, low, close, adj_close, volume, dividends, stock_splits)
WHERE EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'price_daily')
ON CONFLICT (symbol, date) DO NOTHING;

-- Create missing tables that APIs expect
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

-- Insert sample data for new tables
INSERT INTO news (symbol, headline, summary, url, published_at, sentiment, relevance_score, source)
VALUES 
    ('AAPL', 'Apple Reports Strong Q4 Earnings', 'Apple Inc. reported better than expected earnings for Q4 with revenue growth across all segments.', 'https://example.com/apple-earnings', CURRENT_TIMESTAMP - INTERVAL '2 hours', 0.8, 0.9, 'Reuters'),
    ('MSFT', 'Microsoft Cloud Revenue Surges', 'Microsoft Azure cloud services revenue increased 30% year-over-year in latest quarter.', 'https://example.com/msft-cloud', CURRENT_TIMESTAMP - INTERVAL '4 hours', 0.7, 0.85, 'Bloomberg'),
    ('TSLA', 'Tesla Delivers Record Number of Vehicles', 'Tesla delivered a record number of electric vehicles in Q4, beating analyst expectations.', 'https://example.com/tesla-deliveries', CURRENT_TIMESTAMP - INTERVAL '6 hours', 0.6, 0.8, 'CNBC')
ON CONFLICT DO NOTHING;

INSERT INTO analyst_recommendations (symbol, analyst_firm, rating, target_price, current_price, date_published)
VALUES 
    ('AAPL', 'Goldman Sachs', 'BUY', 200.00, 186.75, CURRENT_DATE - INTERVAL '3 days'),
    ('AAPL', 'Morgan Stanley', 'OVERWEIGHT', 195.00, 186.75, CURRENT_DATE - INTERVAL '5 days'),
    ('MSFT', 'JP Morgan', 'OVERWEIGHT', 450.00, 411.25, CURRENT_DATE - INTERVAL '2 days'),
    ('GOOGL', 'Barclays', 'EQUAL WEIGHT', 145.00, 139.20, CURRENT_DATE - INTERVAL '1 day'),
    ('TSLA', 'Wedbush', 'OUTPERFORM', 300.00, 250.85, CURRENT_DATE - INTERVAL '4 days')
ON CONFLICT DO NOTHING;

INSERT INTO dividends (symbol, ex_date, record_date, payment_date, amount, yield_percent, frequency, type)
VALUES 
    ('AAPL', CURRENT_DATE - INTERVAL '30 days', CURRENT_DATE - INTERVAL '28 days', CURRENT_DATE - INTERVAL '7 days', 0.24, 0.52, 'Quarterly', 'Cash'),
    ('MSFT', CURRENT_DATE - INTERVAL '25 days', CURRENT_DATE - INTERVAL '23 days', CURRENT_DATE - INTERVAL '5 days', 0.75, 0.73, 'Quarterly', 'Cash'),
    ('GOOGL', CURRENT_DATE - INTERVAL '90 days', CURRENT_DATE - INTERVAL '88 days', CURRENT_DATE - INTERVAL '70 days', 0.20, 0.58, 'Quarterly', 'Cash')
ON CONFLICT (symbol, ex_date) DO NOTHING;

INSERT INTO portfolio_risk (portfolio_id, date, risk_score, beta, var_95, sharpe_ratio, max_drawdown, volatility)
VALUES 
    ('default', CURRENT_DATE, 65.5, 1.15, -0.025, 1.2, -0.08, 0.18),
    ('aggressive', CURRENT_DATE, 85.2, 1.45, -0.045, 1.8, -0.15, 0.28),
    ('conservative', CURRENT_DATE, 35.8, 0.75, -0.015, 0.9, -0.05, 0.12)
ON CONFLICT (portfolio_id, date) DO NOTHING;

INSERT INTO sentiment (symbol, date, sentiment_score, positive_mentions, negative_mentions, neutral_mentions, total_mentions, source)
VALUES 
    ('AAPL', CURRENT_DATE, 0.65, 150, 45, 105, 300, 'twitter'),
    ('MSFT', CURRENT_DATE, 0.72, 120, 30, 80, 230, 'twitter'),
    ('GOOGL', CURRENT_DATE, 0.45, 80, 60, 90, 230, 'twitter'),
    ('TSLA', CURRENT_DATE, 0.55, 200, 120, 180, 500, 'twitter'),
    ('NVDA', CURRENT_DATE, 0.78, 180, 25, 95, 300, 'twitter')
ON CONFLICT (symbol, date, source) DO NOTHING;

SELECT 'Dummy data inserted successfully with existing table structures!' as status;