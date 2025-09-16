-- Test Data Seeding Script for Integration Tests
-- This script inserts comprehensive test data for all tables

-- Clean existing test data
DELETE FROM watchlist_items;
DELETE FROM watchlists;
DELETE FROM orders_paper;
DELETE FROM portfolio_performance;
DELETE FROM portfolio_holdings;
DELETE FROM comprehensive_scores;
DELETE FROM sentiment_analysis;
DELETE FROM profitability_metrics;
DELETE FROM price_daily;
DELETE FROM latest_technicals_daily;
DELETE FROM technical_data_daily;
DELETE FROM swing_trading_signals;
DELETE FROM buy_sell_monthly;
DELETE FROM buy_sell_weekly;
DELETE FROM buy_sell_daily;
DELETE FROM news_articles;
DELETE FROM stocks;
DELETE FROM company_profile;
DELETE FROM stock_symbols;

-- Reset sequences
SELECT setval('stock_symbols_id_seq', 1, false) WHERE EXISTS (SELECT 1 FROM information_schema.sequences WHERE sequence_name = 'stock_symbols_id_seq');

-- Insert stock symbols
INSERT INTO stock_symbols (symbol, security_name, exchange) VALUES
('AAPL', 'Apple Inc.', 'NASDAQ'),
('MSFT', 'Microsoft Corporation', 'NASDAQ'),
('GOOGL', 'Alphabet Inc.', 'NASDAQ'),
('TSLA', 'Tesla Inc.', 'NASDAQ'),
('NVDA', 'NVIDIA Corporation', 'NASDAQ'),
('META', 'Meta Platforms Inc.', 'NASDAQ'),
('AMZN', 'Amazon.com Inc.', 'NASDAQ'),
('NFLX', 'Netflix Inc.', 'NASDAQ'),
('AMD', 'Advanced Micro Devices Inc.', 'NASDAQ'),
('CRM', 'Salesforce Inc.', 'NYSE'),
('JPM', 'JPMorgan Chase & Co.', 'NYSE'),
('BAC', 'Bank of America Corp.', 'NYSE'),
('KO', 'The Coca-Cola Company', 'NYSE'),
('PG', 'Procter & Gamble Co.', 'NYSE'),
('JNJ', 'Johnson & Johnson', 'NYSE'),
('SPY', 'SPDR S&P 500 ETF Trust', 'NYSE'),
('QQQ', 'Invesco QQQ Trust', 'NASDAQ'),
('VTI', 'Vanguard Total Stock Market ETF', 'NYSE'),
('IWM', 'iShares Russell 2000 ETF', 'NYSE'),
('GLD', 'SPDR Gold Shares', 'NYSE');

-- Insert company profiles
INSERT INTO company_profile (symbol, name, sector, industry, market_cap, description) VALUES
('AAPL', 'Apple Inc.', 'Technology', 'Consumer Electronics', 2800000000000, 'Apple Inc. designs, manufactures, and markets smartphones, personal computers, tablets, wearables, and accessories worldwide.'),
('MSFT', 'Microsoft Corporation', 'Technology', 'Software', 2500000000000, 'Microsoft Corporation develops, licenses, and supports software, services, devices, and solutions worldwide.'),
('GOOGL', 'Alphabet Inc.', 'Technology', 'Internet Content & Information', 1600000000000, 'Alphabet Inc. provides online advertising services in the United States, Europe, the Middle East, Africa, the Asia-Pacific, Canada, and Latin America.'),
('TSLA', 'Tesla Inc.', 'Consumer Discretionary', 'Automobiles', 800000000000, 'Tesla, Inc. designs, develops, manufactures, leases, and sells electric vehicles, and energy generation and storage systems.'),
('NVDA', 'NVIDIA Corporation', 'Technology', 'Semiconductors', 1200000000000, 'NVIDIA Corporation operates as a computing company in the United States and internationally.'),
('META', 'Meta Platforms Inc.', 'Technology', 'Internet Content & Information', 750000000000, 'Meta Platforms, Inc. develops products that enable people to connect and share with friends and family through mobile devices, personal computers, virtual reality headsets, wearables, and in-home devices worldwide.'),
('AMZN', 'Amazon.com Inc.', 'Consumer Discretionary', 'Internet & Direct Marketing Retail', 1400000000000, 'Amazon.com, Inc. engages in the retail sale of consumer products and subscriptions in North America and internationally.'),
('JPM', 'JPMorgan Chase & Co.', 'Financials', 'Banks', 450000000000, 'JPMorgan Chase & Co. operates as a financial services company worldwide.'),
('BAC', 'Bank of America Corp.', 'Financials', 'Banks', 250000000000, 'Bank of America Corporation, through its subsidiaries, provides banking and financial products and services for individual consumers, small and middle-market businesses, institutional investors, large corporations, and governments worldwide.'),
('KO', 'The Coca-Cola Company', 'Consumer Staples', 'Beverages', 260000000000, 'The Coca-Cola Company, a beverage company, manufactures, markets, and sells various nonalcoholic beverages worldwide.');

-- Insert stocks table data
INSERT INTO stocks (symbol, name, sector, price, market_cap) VALUES
('AAPL', 'Apple Inc.', 'Technology', 178.50, 2800000000000),
('MSFT', 'Microsoft Corporation', 'Technology', 338.25, 2500000000000),
('GOOGL', 'Alphabet Inc.', 'Technology', 138.75, 1600000000000),
('TSLA', 'Tesla Inc.', 'Consumer Discretionary', 248.42, 800000000000),
('NVDA', 'NVIDIA Corporation', 'Technology', 465.30, 1200000000000),
('META', 'Meta Platforms Inc.', 'Technology', 298.75, 750000000000),
('AMZN', 'Amazon.com Inc.', 'Consumer Discretionary', 145.86, 1400000000000),
('JPM', 'JPMorgan Chase & Co.', 'Financials', 148.25, 450000000000),
('BAC', 'Bank of America Corp.', 'Financials', 35.42, 250000000000),
('KO', 'The Coca-Cola Company', 'Consumer Staples', 61.85, 260000000000);

-- Insert daily trading signals (last 30 days)
INSERT INTO buy_sell_daily (symbol, date, signal, buylevel, selllevel, stoplevel, price, inposition) VALUES
('AAPL', CURRENT_DATE - INTERVAL '1 day', 'Buy', 178.50, NULL, 165.75, 178.50, TRUE),
('AAPL', CURRENT_DATE - INTERVAL '2 days', 'Hold', NULL, NULL, NULL, 180.25, FALSE),
('AAPL', CURRENT_DATE - INTERVAL '3 days', 'Sell', NULL, 182.00, NULL, 182.00, FALSE),
('AAPL', CURRENT_DATE - INTERVAL '5 days', 'Buy', 175.30, NULL, 162.50, 175.30, TRUE),
('MSFT', CURRENT_DATE - INTERVAL '1 day', 'Buy', 338.25, NULL, 320.00, 338.25, TRUE),
('MSFT', CURRENT_DATE - INTERVAL '2 days', 'Hold', NULL, NULL, NULL, 342.75, FALSE),
('MSFT', CURRENT_DATE - INTERVAL '4 days', 'Sell', NULL, 345.50, NULL, 345.50, FALSE),
('GOOGL', CURRENT_DATE - INTERVAL '1 day', 'Hold', NULL, NULL, NULL, 138.75, FALSE),
('GOOGL', CURRENT_DATE - INTERVAL '3 days', 'Buy', 135.25, NULL, 125.00, 135.25, TRUE),
('TSLA', CURRENT_DATE - INTERVAL '1 day', 'Sell', NULL, 248.42, NULL, 248.42, FALSE),
('TSLA', CURRENT_DATE - INTERVAL '2 days', 'Hold', NULL, NULL, NULL, 252.10, FALSE),
('NVDA', CURRENT_DATE - INTERVAL '1 day', 'Buy', 465.30, NULL, 445.00, 465.30, TRUE),
('META', CURRENT_DATE - INTERVAL '1 day', 'Hold', NULL, NULL, NULL, 298.75, FALSE),
('AMZN', CURRENT_DATE - INTERVAL '1 day', 'Buy', 145.86, NULL, 138.00, 145.86, TRUE),
('JPM', CURRENT_DATE - INTERVAL '1 day', 'Sell', NULL, 148.25, NULL, 148.25, FALSE),
('BAC', CURRENT_DATE - INTERVAL '1 day', 'Buy', 35.42, NULL, 33.50, 35.42, TRUE);

-- Generate more historical signals for the past 30 days
DO $$
DECLARE
    sym VARCHAR(10);
    symbols VARCHAR(10)[] := ARRAY['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'META', 'AMZN'];
    dt DATE;
    sig VARCHAR(10);
    signals VARCHAR(10)[] := ARRAY['Buy', 'Sell', 'Hold'];
    price_val DECIMAL(10,2);
    base_prices DECIMAL(10,2)[] := ARRAY[178.50, 338.25, 138.75, 248.42, 465.30, 298.75, 145.86];
    i INTEGER;
BEGIN
    FOR i IN 1..array_length(symbols, 1) LOOP
        sym := symbols[i];
        price_val := base_prices[i];
        
        FOR dt IN SELECT generate_series(CURRENT_DATE - INTERVAL '29 days', CURRENT_DATE - INTERVAL '6 days', '1 day'::interval)::date LOOP
            sig := signals[1 + floor(random() * 3)::int];
            price_val := price_val + (random() - 0.5) * price_val * 0.02; -- +/- 2% variation
            
            INSERT INTO buy_sell_daily (symbol, date, signal, buylevel, selllevel, stoplevel, price, inposition) 
            VALUES (
                sym, 
                dt, 
                sig,
                CASE WHEN sig = 'Buy' THEN price_val ELSE NULL END,
                CASE WHEN sig = 'Sell' THEN price_val ELSE NULL END,
                CASE WHEN sig = 'Buy' THEN price_val * 0.92 WHEN sig = 'Sell' THEN price_val * 1.08 ELSE NULL END,
                price_val,
                sig = 'Buy'
            ) ON CONFLICT (symbol, date) DO NOTHING;
        END LOOP;
    END LOOP;
END $$;

-- Insert weekly and monthly signals
INSERT INTO buy_sell_weekly (symbol, date, signal, buylevel, selllevel, stoplevel, price, inposition) VALUES
('AAPL', date_trunc('week', CURRENT_DATE), 'Buy', 178.50, NULL, 165.75, 178.50, TRUE),
('MSFT', date_trunc('week', CURRENT_DATE), 'Hold', NULL, NULL, NULL, 338.25, FALSE),
('GOOGL', date_trunc('week', CURRENT_DATE), 'Buy', 138.75, NULL, 128.00, 138.75, TRUE),
('TSLA', date_trunc('week', CURRENT_DATE), 'Sell', NULL, 248.42, NULL, 248.42, FALSE),
('NVDA', date_trunc('week', CURRENT_DATE), 'Buy', 465.30, NULL, 445.00, 465.30, TRUE);

INSERT INTO buy_sell_monthly (symbol, date, signal, buylevel, selllevel, stoplevel, price, inposition) VALUES
('AAPL', date_trunc('month', CURRENT_DATE), 'Buy', 178.50, NULL, 165.75, 178.50, TRUE),
('MSFT', date_trunc('month', CURRENT_DATE), 'Buy', 338.25, NULL, 320.00, 338.25, TRUE),
('GOOGL', date_trunc('month', CURRENT_DATE), 'Hold', NULL, NULL, NULL, 138.75, FALSE);

-- Insert swing trading signals
INSERT INTO swing_trading_signals (symbol, signal, entry_price, target_price, stop_loss, date) VALUES
('AAPL', 'Buy', 178.50, 195.00, 165.75, CURRENT_DATE - INTERVAL '1 day'),
('MSFT', 'Buy', 338.25, 360.00, 320.00, CURRENT_DATE - INTERVAL '2 days'),
('GOOGL', 'Sell', 138.75, 125.00, 148.00, CURRENT_DATE - INTERVAL '1 day'),
('TSLA', 'Buy', 248.42, 275.00, 230.00, CURRENT_DATE - INTERVAL '3 days'),
('NVDA', 'Hold', 465.30, 500.00, 445.00, CURRENT_DATE - INTERVAL '1 day'),
('META', 'Buy', 298.75, 320.00, 280.00, CURRENT_DATE - INTERVAL '2 days'),
('AMZN', 'Sell', 145.86, 135.00, 155.00, CURRENT_DATE - INTERVAL '4 days');

-- Insert technical data
INSERT INTO technical_data_daily (symbol, date, rsi_14, sma_20, sma_50, sma_200, price_vs_sma_200, volume, price) VALUES
('AAPL', CURRENT_DATE - INTERVAL '1 day', 62.5, 175.30, 172.85, 168.50, 5.93, 45000000, 178.50),
('MSFT', CURRENT_DATE - INTERVAL '1 day', 58.2, 335.75, 330.20, 315.80, 7.10, 28000000, 338.25),
('GOOGL', CURRENT_DATE - INTERVAL '1 day', 45.8, 140.25, 135.60, 130.40, 6.41, 32000000, 138.75),
('TSLA', CURRENT_DATE - INTERVAL '1 day', 72.1, 255.80, 248.30, 230.75, 7.66, 85000000, 248.42),
('NVDA', CURRENT_DATE - INTERVAL '1 day', 68.9, 460.25, 445.80, 420.30, 10.70, 55000000, 465.30);

INSERT INTO latest_technicals_daily (symbol, date, rsi_14, sma_20, sma_50, sma_200, volume, price) VALUES
('AAPL', CURRENT_DATE - INTERVAL '1 day', 62.5, 175.30, 172.85, 168.50, 45000000, 178.50),
('MSFT', CURRENT_DATE - INTERVAL '1 day', 58.2, 335.75, 330.20, 315.80, 28000000, 338.25),
('GOOGL', CURRENT_DATE - INTERVAL '1 day', 45.8, 140.25, 135.60, 130.40, 32000000, 138.75),
('TSLA', CURRENT_DATE - INTERVAL '1 day', 72.1, 255.80, 248.30, 230.75, 85000000, 248.42),
('NVDA', CURRENT_DATE - INTERVAL '1 day', 68.9, 460.25, 445.80, 420.30, 55000000, 465.30);

-- Insert price data
INSERT INTO price_daily (symbol, date, open_price, high_price, low_price, close, volume) VALUES
('AAPL', CURRENT_DATE - INTERVAL '1 day', 177.25, 179.85, 176.50, 178.50, 45000000),
('MSFT', CURRENT_DATE - INTERVAL '1 day', 340.50, 342.75, 336.80, 338.25, 28000000),
('GOOGL', CURRENT_DATE - INTERVAL '1 day', 139.50, 140.85, 137.25, 138.75, 32000000),
('TSLA', CURRENT_DATE - INTERVAL '1 day', 252.10, 254.75, 246.30, 248.42, 85000000),
('NVDA', CURRENT_DATE - INTERVAL '1 day', 468.75, 472.50, 462.10, 465.30, 55000000);

-- Insert sentiment data
INSERT INTO sentiment_analysis (symbol, date, sentiment_score, news_count) VALUES
('AAPL', CURRENT_DATE - INTERVAL '1 day', 0.75, 45),
('MSFT', CURRENT_DATE - INTERVAL '1 day', 0.68, 32),
('GOOGL', CURRENT_DATE - INTERVAL '1 day', 0.42, 28),
('TSLA', CURRENT_DATE - INTERVAL '1 day', 0.85, 78),
('NVDA', CURRENT_DATE - INTERVAL '1 day', 0.92, 65),
('META', CURRENT_DATE - INTERVAL '1 day', 0.55, 38),
('AMZN', CURRENT_DATE - INTERVAL '1 day', 0.62, 42);

-- Insert profitability metrics
INSERT INTO profitability_metrics (symbol, date, roe, roa, trailing_pe, revenue_growth_1y) VALUES
('AAPL', CURRENT_DATE - INTERVAL '1 day', 26.4, 18.2, 28.5, 8.1),
('MSFT', CURRENT_DATE - INTERVAL '1 day', 36.7, 15.8, 32.2, 12.3),
('GOOGL', CURRENT_DATE - INTERVAL '1 day', 18.9, 12.4, 22.8, 15.7),
('TSLA', CURRENT_DATE - INTERVAL '1 day', 19.3, 8.9, 58.2, 47.2),
('NVDA', CURRENT_DATE - INTERVAL '1 day', 55.8, 35.2, 65.8, 126.4);

-- Insert comprehensive scores
INSERT INTO comprehensive_scores (symbol, quality_score, growth_score, value_score, momentum_score, sentiment_score, positioning_score, composite_score, calculation_date, data_quality) VALUES
('AAPL', 0.85, 0.78, 0.65, 0.72, 0.75, 0.82, 0.76, CURRENT_DATE, 95),
('MSFT', 0.92, 0.85, 0.58, 0.68, 0.68, 0.78, 0.75, CURRENT_DATE, 98),
('GOOGL', 0.78, 0.88, 0.72, 0.45, 0.42, 0.65, 0.65, CURRENT_DATE, 92),
('TSLA', 0.65, 0.95, 0.35, 0.85, 0.85, 0.75, 0.73, CURRENT_DATE, 88),
('NVDA', 0.88, 0.98, 0.42, 0.92, 0.92, 0.88, 0.83, CURRENT_DATE, 96);

-- Insert test user watchlists
INSERT INTO watchlists (user_id, name, description, is_default, is_public) VALUES
('test-user-123', 'My Stocks', 'Main watchlist', TRUE, FALSE),
('test-user-123', 'Tech Stocks', 'Technology companies', FALSE, FALSE),
('test-user-123', 'Growth Stocks', 'High growth potential', FALSE, FALSE);

INSERT INTO watchlist_items (watchlist_id, symbol, notes) VALUES
(1, 'AAPL', 'Strong fundamentals'),
(1, 'MSFT', 'Cloud leader'),
(1, 'GOOGL', 'Search dominance'),
(1, 'NVDA', 'AI chipmaker'),
(1, 'TSLA', 'EV pioneer'),
(2, 'AAPL', 'Premium tech'),
(2, 'MSFT', 'Enterprise software'),
(2, 'GOOGL', 'Internet giant'),
(3, 'TSLA', 'Disruptive growth'),
(3, 'NVDA', 'AI revolution');

-- Insert test portfolio holdings
INSERT INTO portfolio_holdings (user_id, symbol, quantity, avg_price, current_price, market_value) VALUES
('test-user-123', 'AAPL', 50.0, 165.25, 178.50, 8925.00),
('test-user-123', 'MSFT', 25.0, 320.50, 338.25, 8456.25),
('test-user-123', 'GOOGL', 75.0, 125.30, 138.75, 10406.25),
('test-user-123', 'TSLA', 20.0, 235.80, 248.42, 4968.40),
('test-user-123', 'NVDA', 15.0, 445.20, 465.30, 6979.50);

-- Insert portfolio performance history
DO $$
DECLARE
    dt DATE;
    base_value DECIMAL(15,2) := 39735.40;
    daily_return DECIMAL(10,4);
    total_return DECIMAL(10,4) := 0.0;
BEGIN
    FOR dt IN SELECT generate_series(CURRENT_DATE - INTERVAL '30 days', CURRENT_DATE - INTERVAL '1 day', '1 day'::interval)::date LOOP
        daily_return := (random() - 0.5) * 0.04; -- +/- 2% daily variation
        total_return := total_return + daily_return;
        base_value := base_value * (1 + daily_return);
        
        INSERT INTO portfolio_performance (user_id, date, total_value, daily_return, total_return) 
        VALUES ('test-user-123', dt, base_value, daily_return, total_return);
    END LOOP;
END $$;

-- Insert test orders
INSERT INTO orders_paper (user_id, symbol, side, quantity, type, price, status) VALUES
('test-user-123', 'AAPL', 'buy', 10.0, 'market', NULL, 'filled'),
('test-user-123', 'MSFT', 'buy', 5.0, 'limit', 335.00, 'pending'),
('test-user-123', 'GOOGL', 'sell', 25.0, 'limit', 145.00, 'pending'),
('test-user-123', 'TSLA', 'buy', 8.0, 'stop_limit', 245.00, 'pending'),
('test-user-123', 'NVDA', 'sell', 3.0, 'market', NULL, 'cancelled');

-- Insert news articles
INSERT INTO news_articles (title, content, symbol, category, published_at, sentiment_score) VALUES
('Apple Reports Strong Q3 Earnings', 'Apple Inc. reported better-than-expected quarterly earnings...', 'AAPL', 'earnings', CURRENT_TIMESTAMP - INTERVAL '2 hours', 0.82),
('Microsoft Azure Growth Continues', 'Microsoft''s cloud computing platform shows robust growth...', 'MSFT', 'earnings', CURRENT_TIMESTAMP - INTERVAL '4 hours', 0.75),
('Tesla Delivers Record Vehicles', 'Tesla announced record vehicle deliveries for the quarter...', 'TSLA', 'business', CURRENT_TIMESTAMP - INTERVAL '6 hours', 0.88),
('NVIDIA AI Chip Demand Surges', 'NVIDIA sees unprecedented demand for AI processors...', 'NVDA', 'technology', CURRENT_TIMESTAMP - INTERVAL '1 day', 0.95),
('Google Search Algorithm Update', 'Alphabet announces major search algorithm improvements...', 'GOOGL', 'technology', CURRENT_TIMESTAMP - INTERVAL '8 hours', 0.65);

COMMIT;