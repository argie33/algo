-- Test data for loader tables that matches the routes' expectations
-- Insert basic stock symbols
INSERT INTO stock_symbols (symbol, exchange, security_name, market_category, etf) VALUES
('AAPL', 'NASDAQ', 'Apple Inc.', 'Q', 'N'),
('MSFT', 'NASDAQ', 'Microsoft Corporation', 'Q', 'N'),
('GOOGL', 'NASDAQ', 'Alphabet Inc. Class A', 'Q', 'N'),
('TSLA', 'NASDAQ', 'Tesla, Inc.', 'Q', 'N'),
('AMZN', 'NASDAQ', 'Amazon.com, Inc.', 'Q', 'N')
ON CONFLICT DO NOTHING;

-- Insert basic ETF symbols
INSERT INTO etf_symbols (symbol, exchange, security_name, market_category, etf) VALUES
('SPY', 'NYSE', 'SPDR S&P 500 ETF Trust', 'P', 'Y'),
('QQQ', 'NASDAQ', 'Invesco QQQ Trust', 'Q', 'Y')
ON CONFLICT DO NOTHING;

-- Insert fundamental metrics data
INSERT INTO fundamental_metrics (
    symbol, market_cap, pe_ratio, forward_pe, price_to_book, price_to_sales,
    dividend_yield, beta, sector, industry, revenue, net_income, earnings_per_share
) VALUES
('AAPL', 3000000000000, 28.5, 26.2, 45.8, 7.2, 0.44, 1.2, 'Technology', 'Consumer Electronics', 394328000000, 99803000000, 6.05),
('MSFT', 2800000000000, 32.1, 29.8, 12.9, 12.8, 0.68, 0.9, 'Technology', 'Software—Infrastructure', 211915000000, 72361000000, 9.65),
('GOOGL', 1700000000000, 25.8, 22.4, 5.2, 5.1, 0.00, 1.1, 'Communication Services', 'Internet Content & Information', 307394000000, 73795000000, 5.80),
('TSLA', 800000000000, 73.1, 60.2, 12.4, 8.9, 0.00, 2.0, 'Consumer Cyclical', 'Auto Manufacturers', 96773000000, 15000000000, 4.73),
('AMZN', 1600000000000, 58.9, 42.1, 8.3, 2.7, 0.00, 1.3, 'Consumer Cyclical', 'Internet Retail', 574785000000, 33364000000, 3.24)
ON CONFLICT (symbol) DO UPDATE SET
    market_cap = EXCLUDED.market_cap,
    pe_ratio = EXCLUDED.pe_ratio,
    updated_at = CURRENT_TIMESTAMP;

-- Insert price daily data (recent dates)
INSERT INTO price_daily (symbol, date, open, high, low, close, adj_close, volume) VALUES
('AAPL', CURRENT_DATE, 174.0, 176.5, 173.2, 175.8, 175.8, 55000000),
('AAPL', CURRENT_DATE - INTERVAL '1 day', 172.5, 174.8, 171.9, 174.0, 174.0, 48000000),
('MSFT', CURRENT_DATE, 415.2, 418.9, 412.1, 416.8, 416.8, 22000000),
('MSFT', CURRENT_DATE - INTERVAL '1 day', 412.0, 416.5, 410.8, 415.2, 415.2, 19000000),
('GOOGL', CURRENT_DATE, 165.4, 167.2, 164.1, 166.8, 166.8, 28000000),
('TSLA', CURRENT_DATE, 248.2, 252.1, 245.9, 250.4, 250.4, 95000000),
('AMZN', CURRENT_DATE, 145.8, 147.6, 144.2, 146.9, 146.9, 42000000)
ON CONFLICT DO NOTHING;

-- Insert positioning metrics data
INSERT INTO positioning_metrics (
    symbol, date, institutional_ownership_pct, smart_money_score,
    insider_sentiment_score, options_sentiment, short_squeeze_score, composite_positioning_score
) VALUES
('AAPL', CURRENT_DATE, 0.6234, 0.7821, 0.2341, 0.1234, 0.3456, 0.4567),
('MSFT', CURRENT_DATE, 0.7123, 0.8234, 0.3214, 0.2345, 0.4123, 0.5234),
('GOOGL', CURRENT_DATE, 0.6789, 0.7456, 0.1789, 0.3456, 0.2789, 0.4123),
('TSLA', CURRENT_DATE, 0.4321, 0.5678, -0.1234, -0.2345, 0.6789, 0.2678),
('AMZN', CURRENT_DATE, 0.5432, 0.6789, 0.0987, 0.1876, 0.3987, 0.3876)
ON CONFLICT (symbol, date) DO UPDATE SET
    institutional_ownership_pct = EXCLUDED.institutional_ownership_pct,
    updated_at = CURRENT_TIMESTAMP;

-- Insert retail sentiment data
INSERT INTO retail_sentiment (symbol, date, bullish_percentage, bearish_percentage, neutral_percentage, net_sentiment, source) VALUES
('AAPL', CURRENT_DATE, 65.2, 20.8, 14.0, 44.4, 'retail_tracker'),
('MSFT', CURRENT_DATE, 70.1, 18.5, 11.4, 51.6, 'retail_tracker'),
('GOOGL', CURRENT_DATE, 58.9, 25.3, 15.8, 33.6, 'retail_tracker'),
('TSLA', CURRENT_DATE, 72.4, 19.2, 8.4, 53.2, 'retail_tracker'),
('AMZN', CURRENT_DATE, 62.3, 22.1, 15.6, 40.2, 'retail_tracker')
ON CONFLICT (symbol, date, source) DO UPDATE SET
    bullish_percentage = EXCLUDED.bullish_percentage,
    bearish_percentage = EXCLUDED.bearish_percentage,
    neutral_percentage = EXCLUDED.neutral_percentage,
    net_sentiment = EXCLUDED.net_sentiment;

-- Insert market data
INSERT INTO market_data (
    ticker, current_price, regular_market_price, volume, regular_market_volume,
    market_cap, fifty_two_week_high, fifty_two_week_low
) VALUES
('AAPL', 175.8, 175.8, 55000000, 55000000, 3000000000000, 199.62, 164.08),
('MSFT', 416.8, 416.8, 22000000, 22000000, 2800000000000, 468.35, 362.90),
('GOOGL', 166.8, 166.8, 28000000, 28000000, 1700000000000, 191.75, 129.40),
('TSLA', 250.4, 250.4, 95000000, 95000000, 800000000000, 299.29, 138.80),
('AMZN', 146.9, 146.9, 42000000, 42000000, 1600000000000, 170.00, 118.35)
ON CONFLICT (ticker) DO UPDATE SET
    current_price = EXCLUDED.current_price,
    regular_market_price = EXCLUDED.regular_market_price,
    volume = EXCLUDED.volume,
    updated_at = CURRENT_TIMESTAMP;

-- Insert stock news
INSERT INTO stock_news (ticker, title, summary, publish_time, provider, sentiment_score) VALUES
('AAPL', 'Apple Reports Strong Q4 Earnings', 'Apple Inc. reported better than expected earnings for Q4', CURRENT_TIMESTAMP - INTERVAL '2 hours', 'Financial News', 0.75),
('MSFT', 'Microsoft Cloud Revenue Grows', 'Microsoft sees continued growth in cloud services', CURRENT_TIMESTAMP - INTERVAL '4 hours', 'Tech News', 0.68),
('GOOGL', 'Google AI Advances', 'Alphabet announces new AI capabilities', CURRENT_TIMESTAMP - INTERVAL '6 hours', 'Tech Today', 0.62),
('TSLA', 'Tesla Production Update', 'Tesla provides update on vehicle production targets', CURRENT_TIMESTAMP - INTERVAL '8 hours', 'Auto News', 0.45),
('AMZN', 'Amazon Prime Growth', 'Amazon reports growth in Prime memberships', CURRENT_TIMESTAMP - INTERVAL '10 hours', 'Retail News', 0.58)
ON CONFLICT DO NOTHING;

-- Insert analyst sentiment
INSERT INTO analyst_sentiment_analysis (
    symbol, date, analyst_count, strong_buy_count, buy_count, hold_count,
    sell_count, strong_sell_count, average_rating, target_price, sentiment_score
) VALUES
('AAPL', CURRENT_DATE, 25, 8, 12, 4, 1, 0, 2.1, 185.50, 0.72),
('MSFT', CURRENT_DATE, 28, 10, 14, 3, 1, 0, 2.0, 450.25, 0.78),
('GOOGL', CURRENT_DATE, 22, 6, 11, 4, 1, 0, 2.3, 175.80, 0.65),
('TSLA', CURRENT_DATE, 18, 3, 8, 5, 2, 0, 2.6, 275.40, 0.48),
('AMZN', CURRENT_DATE, 24, 7, 12, 4, 1, 0, 2.2, 158.90, 0.69)
ON CONFLICT (symbol, date) DO UPDATE SET
    analyst_count = EXCLUDED.analyst_count,
    average_rating = EXCLUDED.average_rating,
    target_price = EXCLUDED.target_price,
    sentiment_score = EXCLUDED.sentiment_score,
    updated_at = CURRENT_TIMESTAMP;