-- Add sample stock market data for tests with correct column names

-- Add sample market data
INSERT INTO market_data (symbol, name, current_price, volume, market_cap, pe_ratio, updated_at) VALUES
('AAPL', 'Apple Inc.', 175.43, 45678901, 2800000000000, 28.5, NOW()),
('MSFT', 'Microsoft Corporation', 338.11, 23456789, 2500000000000, 32.1, NOW()),
('GOOGL', 'Alphabet Inc.', 127.05, 34567890, 1600000000000, 24.8, NOW()),
('TSLA', 'Tesla Inc.', 248.50, 67890123, 785000000000, 78.2, NOW()),
('AMZN', 'Amazon.com Inc.', 145.86, 45678912, 1500000000000, 52.4, NOW())
ON CONFLICT (symbol) DO UPDATE SET
    current_price = EXCLUDED.current_price,
    volume = EXCLUDED.volume,
    market_cap = EXCLUDED.market_cap,
    pe_ratio = EXCLUDED.pe_ratio,
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

-- Add sample news
INSERT INTO news (symbol, headline, source, published_at, sentiment_score) VALUES
('AAPL', 'Apple Reports Strong Q4 Earnings', 'Reuters', NOW() - INTERVAL '2 hours', 0.8),
('MSFT', 'Microsoft Cloud Revenue Grows 20%', 'Bloomberg', NOW() - INTERVAL '4 hours', 0.7),
('TSLA', 'Tesla Delivers Record Number of Vehicles', 'CNBC', NOW() - INTERVAL '6 hours', 0.6),
('GOOGL', 'Google AI Breakthrough in Healthcare', 'TechCrunch', NOW() - INTERVAL '8 hours', 0.9)
ON CONFLICT DO NOTHING;