-- Add sample stock market data for tests
-- This will populate the key tables that the frontend tests expect

-- Add sample market data
INSERT INTO market_data (symbol, current_price, change_amount, change_percent, volume, market_cap, updated_at) VALUES
('AAPL', 175.43, 2.15, 1.24, 45678901, 2800000000000, NOW()),
('MSFT', 338.11, -1.22, -0.36, 23456789, 2500000000000, NOW()),
('GOOGL', 127.05, 0.85, 0.67, 34567890, 1600000000000, NOW()),
('TSLA', 248.50, 5.20, 2.14, 67890123, 785000000000, NOW()),
('AMZN', 145.86, -0.75, -0.51, 45678912, 1500000000000, NOW())
ON CONFLICT (symbol) DO UPDATE SET
    current_price = EXCLUDED.current_price,
    change_amount = EXCLUDED.change_amount,
    change_percent = EXCLUDED.change_percent,
    volume = EXCLUDED.volume,
    market_cap = EXCLUDED.market_cap,
    updated_at = EXCLUDED.updated_at;

-- Add sample price data
INSERT INTO price_daily (symbol, date, open, high, low, close, volume) VALUES
('AAPL', CURRENT_DATE, 174.20, 176.80, 173.50, 175.43, 45678901),
('AAPL', CURRENT_DATE - INTERVAL '1 day', 172.85, 175.30, 172.10, 173.28, 52345678),
('AAPL', CURRENT_DATE - INTERVAL '2 days', 171.50, 173.90, 170.80, 172.85, 48234567),
('MSFT', CURRENT_DATE, 339.50, 340.20, 337.80, 338.11, 23456789),
('MSFT', CURRENT_DATE - INTERVAL '1 day', 341.20, 342.15, 338.90, 339.33, 28345672),
('GOOGL', CURRENT_DATE, 126.80, 128.50, 125.90, 127.05, 34567890),
('TSLA', CURRENT_DATE, 245.30, 250.80, 244.90, 248.50, 67890123),
('AMZN', CURRENT_DATE, 146.90, 147.60, 145.20, 145.86, 45678912)
ON CONFLICT (symbol, date) DO UPDATE SET
    open = EXCLUDED.open,
    high = EXCLUDED.high,
    low = EXCLUDED.low,
    close = EXCLUDED.close,
    volume = EXCLUDED.volume;

-- Add sample technical indicators
INSERT INTO technical_data_daily (symbol, date, rsi, macd, bb_upper, bb_lower, sma_20, sma_50, volume) VALUES
('AAPL', CURRENT_DATE, 62.4, 1.25, 178.50, 172.30, 174.85, 171.20, 45678901),
('MSFT', CURRENT_DATE, 58.7, 0.85, 342.20, 334.80, 339.10, 335.50, 23456789),
('GOOGL', CURRENT_DATE, 55.2, -0.45, 130.20, 124.80, 127.50, 125.90, 34567890),
('TSLA', CURRENT_DATE, 71.8, 3.25, 255.20, 240.80, 248.90, 245.30, 67890123),
('AMZN', CURRENT_DATE, 48.3, -1.15, 149.80, 142.20, 146.50, 144.90, 45678912)
ON CONFLICT (symbol, date) DO UPDATE SET
    rsi = EXCLUDED.rsi,
    macd = EXCLUDED.macd,
    bb_upper = EXCLUDED.bb_upper,
    bb_lower = EXCLUDED.bb_lower,
    sma_20 = EXCLUDED.sma_20,
    sma_50 = EXCLUDED.sma_50,
    volume = EXCLUDED.volume;

-- Add sample fundamental metrics
INSERT INTO fundamental_metrics (symbol, pe_ratio, eps, dividend_yield, book_value, debt_to_equity, roe, updated_at) VALUES
('AAPL', 28.5, 6.16, 0.48, 3.85, 1.73, 175.0, NOW()),
('MSFT', 32.1, 10.53, 0.72, 13.55, 0.35, 38.0, NOW()),
('GOOGL', 24.8, 5.12, 0.0, 67.40, 0.11, 14.0, NOW()),
('TSLA', 78.2, 3.18, 0.0, 18.42, 0.17, 23.0, NOW()),
('AMZN', 52.4, 2.78, 0.0, 15.33, 0.38, 12.0, NOW())
ON CONFLICT (symbol) DO UPDATE SET
    pe_ratio = EXCLUDED.pe_ratio,
    eps = EXCLUDED.eps,
    dividend_yield = EXCLUDED.dividend_yield,
    book_value = EXCLUDED.book_value,
    debt_to_equity = EXCLUDED.debt_to_equity,
    roe = EXCLUDED.roe,
    updated_at = EXCLUDED.updated_at;

-- Add sample market indices
INSERT INTO market_indices (index_name, symbol, current_value, change_amount, change_percent, updated_at) VALUES
('S&P 500', 'SPX', 4567.89, 23.45, 0.52, NOW()),
('NASDAQ', 'IXIC', 14234.56, -45.67, -0.32, NOW()),
('Dow Jones', 'DJI', 34567.89, 89.12, 0.26, NOW()),
('Russell 2000', 'RUT', 1987.65, 12.34, 0.63, NOW())
ON CONFLICT (symbol) DO UPDATE SET
    current_value = EXCLUDED.current_value,
    change_amount = EXCLUDED.change_amount,
    change_percent = EXCLUDED.change_percent,
    updated_at = EXCLUDED.updated_at;

-- Add sample news
INSERT INTO news (symbol, headline, content, source, published_at, sentiment_score) VALUES
('AAPL', 'Apple Reports Strong Q4 Earnings', 'Apple Inc. reported better-than-expected quarterly earnings...', 'Reuters', NOW() - INTERVAL '2 hours', 0.8),
('MSFT', 'Microsoft Cloud Revenue Grows 20%', 'Microsoft Azure continues to show strong growth...', 'Bloomberg', NOW() - INTERVAL '4 hours', 0.7),
('TSLA', 'Tesla Delivers Record Number of Vehicles', 'Tesla announced record vehicle deliveries for the quarter...', 'CNBC', NOW() - INTERVAL '6 hours', 0.6),
('GOOGL', 'Google AI Breakthrough in Healthcare', 'Alphabet subsidiary makes significant AI advancement...', 'TechCrunch', NOW() - INTERVAL '8 hours', 0.9)
ON CONFLICT DO NOTHING;

COMMIT;