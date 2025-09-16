-- Test data population script for local development
-- Run this script against your local PostgreSQL database
-- Uses existing table structures from loader scripts

-- Populate technical_data_daily with test data for momentum signals
INSERT INTO technical_data_daily (symbol, rsi, macd, momentum, volume, date, fetched_at)
VALUES 
    ('AAPL', 65.2, 0.45, 0.7800, 45234567, CURRENT_DATE, CURRENT_TIMESTAMP),
    ('MSFT', 58.7, 0.32, 0.6500, 28456789, CURRENT_DATE, CURRENT_TIMESTAMP),
    ('GOOGL', 72.1, 0.58, 0.8200, 32567890, CURRENT_DATE, CURRENT_TIMESTAMP),
    ('TSLA', 42.3, -0.25, 0.3500, 67890123, CURRENT_DATE, CURRENT_TIMESTAMP),
    ('AMZN', 68.9, 0.41, 0.7300, 38901234, CURRENT_DATE, CURRENT_TIMESTAMP),
    ('NVDA', 78.4, 0.65, 0.8700, 55600000, CURRENT_DATE, CURRENT_TIMESTAMP)
ON CONFLICT (symbol, date) DO UPDATE SET
    rsi = EXCLUDED.rsi,
    macd = EXCLUDED.macd,
    momentum = EXCLUDED.momentum,
    volume = EXCLUDED.volume,
    fetched_at = EXCLUDED.fetched_at;

-- Populate technical_data_weekly with test data
INSERT INTO technical_data_weekly (symbol, rsi, macd, momentum, volume, date, created_at)
VALUES 
    ('AAPL', 68.5, 0.52, 0.8100, 225000000, DATE_TRUNC('week', CURRENT_DATE), CURRENT_TIMESTAMP),
    ('MSFT', 61.2, 0.38, 0.7200, 140000000, DATE_TRUNC('week', CURRENT_DATE), CURRENT_TIMESTAMP),
    ('GOOGL', 74.8, 0.61, 0.8500, 162000000, DATE_TRUNC('week', CURRENT_DATE), CURRENT_TIMESTAMP)
ON CONFLICT (symbol, date) DO UPDATE SET
    rsi = EXCLUDED.rsi,
    macd = EXCLUDED.macd,
    momentum = EXCLUDED.momentum,
    volume = EXCLUDED.volume,
    updated_at = CURRENT_TIMESTAMP;

-- Populate market_data table
INSERT INTO market_data (ticker, current_price, volume, market_cap, regular_market_open, day_high, day_low)
VALUES 
    ('SPY', 445.67, 52340000, 405000000000, 444.20, 446.80, 443.50),
    ('QQQ', 378.23, 28560000, 185000000000, 377.45, 379.20, 376.80),
    ('IWM', 198.45, 15670000, 32000000000, 197.90, 199.20, 197.50),
    ('VIX', 18.45, 0, 0, 18.20, 19.50, 17.80)
ON CONFLICT (ticker) DO UPDATE SET
    current_price = EXCLUDED.current_price,
    volume = EXCLUDED.volume,
    market_cap = EXCLUDED.market_cap,
    regular_market_open = EXCLUDED.regular_market_open,
    day_high = EXCLUDED.day_high,
    day_low = EXCLUDED.day_low;

-- Populate fear_greed_index table
INSERT INTO fear_greed_index (index_value, rating, date, fetched_at)
VALUES
    (72, 'Greed', CURRENT_DATE, CURRENT_TIMESTAMP),
    (68, 'Greed', CURRENT_DATE - INTERVAL '1 day', CURRENT_TIMESTAMP),
    (65, 'Greed', CURRENT_DATE - INTERVAL '2 days', CURRENT_TIMESTAMP)
ON CONFLICT (date) DO UPDATE SET
    index_value = EXCLUDED.index_value,
    rating = EXCLUDED.rating,
    fetched_at = EXCLUDED.fetched_at;

-- Populate naaim table  
INSERT INTO naaim (date, mean_exposure, naaim_number_mean, bullish, bearish, created_at)
VALUES 
    (CURRENT_DATE, 72.5, 75.2, 68.3, 31.7, CURRENT_TIMESTAMP),
    (CURRENT_DATE - INTERVAL '7 days', 69.8, 72.1, 65.2, 34.8, CURRENT_TIMESTAMP),
    (CURRENT_DATE - INTERVAL '14 days', 71.2, 74.5, 67.8, 32.2, CURRENT_TIMESTAMP)
ON CONFLICT (date) DO UPDATE SET
    mean_exposure = EXCLUDED.mean_exposure,
    naaim_number_mean = EXCLUDED.naaim_number_mean,
    bullish = EXCLUDED.bullish,
    bearish = EXCLUDED.bearish;

-- Populate AAII sentiment data
INSERT INTO aaii_sentiment (bullish, neutral, bearish, date, created_at)
VALUES 
    (38.5, 31.2, 30.3, CURRENT_DATE, CURRENT_TIMESTAMP)
ON CONFLICT (date) DO UPDATE SET
    bullish = EXCLUDED.bullish,
    neutral = EXCLUDED.neutral,
    bearish = EXCLUDED.bearish;

-- Populate economic data
INSERT INTO economic_data (indicator, value, unit, period, created_at)
VALUES 
    ('GDP Growth Rate', 2.1, '%', CURRENT_DATE, CURRENT_TIMESTAMP),
    ('Unemployment Rate', 3.7, '%', CURRENT_DATE, CURRENT_TIMESTAMP),
    ('Inflation Rate', 3.2, '%', CURRENT_DATE, CURRENT_TIMESTAMP),
    ('Federal Funds Rate', 5.25, '%', CURRENT_DATE, CURRENT_TIMESTAMP);

-- Populate stock_symbols table
INSERT INTO stock_symbols (symbol, exchange, security_name, market_category, etf, test_issue)
VALUES 
    ('AAPL', 'NASDAQ', 'Apple Inc.', 'Q', 'N', 'N'),
    ('MSFT', 'NASDAQ', 'Microsoft Corporation', 'Q', 'N', 'N'),
    ('GOOGL', 'NASDAQ', 'Alphabet Inc. Class A', 'Q', 'N', 'N'),
    ('TSLA', 'NASDAQ', 'Tesla Inc.', 'Q', 'N', 'N'),
    ('AMZN', 'NASDAQ', 'Amazon.com Inc.', 'Q', 'N', 'N'),
    ('NVDA', 'NASDAQ', 'NVIDIA Corporation', 'Q', 'N', 'N');

-- Populate stocks table
INSERT INTO stocks (symbol, name, sector, market_cap, price, volume, exchange, currency, is_active, last_updated)
VALUES 
    ('AAPL', 'Apple Inc.', 'Technology', 3000000000000, 186.95, 45234567, 'NASDAQ', 'USD', true, CURRENT_TIMESTAMP),
    ('MSFT', 'Microsoft Corporation', 'Technology', 2800000000000, 379.12, 28456789, 'NASDAQ', 'USD', true, CURRENT_TIMESTAMP),
    ('GOOGL', 'Alphabet Inc.', 'Technology', 1700000000000, 139.85, 32567890, 'NASDAQ', 'USD', true, CURRENT_TIMESTAMP),
    ('TSLA', 'Tesla Inc.', 'Consumer Discretionary', 800000000000, 251.80, 67890123, 'NASDAQ', 'USD', true, CURRENT_TIMESTAMP),
    ('AMZN', 'Amazon.com Inc.', 'Consumer Discretionary', 1500000000000, 153.45, 38901234, 'NASDAQ', 'USD', true, CURRENT_TIMESTAMP),
    ('NVDA', 'NVIDIA Corporation', 'Technology', 1200000000000, 885.30, 55600000, 'NASDAQ', 'USD', true, CURRENT_TIMESTAMP)
ON CONFLICT (symbol) DO UPDATE SET
    name = EXCLUDED.name,
    sector = EXCLUDED.sector,
    market_cap = EXCLUDED.market_cap,
    price = EXCLUDED.price,
    volume = EXCLUDED.volume,
    last_updated = EXCLUDED.last_updated;

-- Populate price_daily table
INSERT INTO price_daily (symbol, date, open, high, low, close, volume, fetched_at)
VALUES 
    ('AAPL', CURRENT_DATE, 185.20, 187.45, 184.80, 186.95, 45234567, CURRENT_TIMESTAMP),
    ('AAPL', CURRENT_DATE - INTERVAL '1 day', 184.50, 186.20, 183.10, 185.20, 52340000, CURRENT_TIMESTAMP),
    ('MSFT', CURRENT_DATE, 378.45, 380.20, 376.80, 379.12, 28456789, CURRENT_TIMESTAMP),
    ('MSFT', CURRENT_DATE - INTERVAL '1 day', 376.20, 378.45, 375.50, 378.45, 31200000, CURRENT_TIMESTAMP),
    ('GOOGL', CURRENT_DATE, 138.20, 140.15, 137.80, 139.85, 32567890, CURRENT_TIMESTAMP),
    ('TSLA', CURRENT_DATE, 248.50, 252.30, 247.20, 251.80, 67890123, CURRENT_TIMESTAMP),
    ('AMZN', CURRENT_DATE, 152.80, 154.20, 151.90, 153.45, 38901234, CURRENT_TIMESTAMP),
    ('NVDA', CURRENT_DATE, 875.20, 890.50, 872.10, 885.30, 55600000, CURRENT_TIMESTAMP);

-- Verify data was inserted
SELECT 'stocks' as table_name, COUNT(*) as row_count FROM stocks
UNION ALL
SELECT 'price_daily' as table_name, COUNT(*) as row_count FROM price_daily  
UNION ALL
SELECT 'technical_data_daily' as table_name, COUNT(*) as row_count FROM technical_data_daily
UNION ALL
SELECT 'technical_data_weekly' as table_name, COUNT(*) as row_count FROM technical_data_weekly
UNION ALL
SELECT 'market_data' as table_name, COUNT(*) as row_count FROM market_data
UNION ALL
SELECT 'fear_greed_index' as table_name, COUNT(*) as row_count FROM fear_greed_index
UNION ALL
SELECT 'naaim' as table_name, COUNT(*) as row_count FROM naaim
UNION ALL
SELECT 'aaii_sentiment' as table_name, COUNT(*) as row_count FROM aaii_sentiment
UNION ALL
SELECT 'economic_data' as table_name, COUNT(*) as row_count FROM economic_data;