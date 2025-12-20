-- Test Data Fixture for Local Development
-- Matches schema created by Python loaders: loadinfo.py, loadtechnicalsdaily.py, etc.
-- Run with: psql -h localhost -U postgres -d stocks -f test-data.sql

-- Clear existing test data
TRUNCATE TABLE company_profile, market_data, key_metrics, price_daily, technical_data_daily CASCADE;

-- Insert comprehensive company_profile data (from loadinfo.py schema)
INSERT INTO company_profile (
  ticker, short_name, long_name, display_name, website_url, employee_count,
  country, business_summary, sector, industry, exchange, full_exchange_name
) VALUES
  ('AAPL', 'Apple Inc.', 'Apple Inc.', 'Apple Inc.',
   'https://www.apple.com', 161000, 'United States',
   'Apple Inc. designs, manufactures, and markets smartphones, personal computers, tablets, wearables, and accessories worldwide.',
   'Technology', 'Consumer Electronics', 'NASDAQ', 'NasdaqGS'),

  ('MSFT', 'Microsoft Corporation', 'Microsoft Corporation', 'Microsoft',
   'https://www.microsoft.com', 221000, 'United States',
   'Microsoft Corporation develops, licenses, and supports software, services, devices, and solutions worldwide.',
   'Technology', 'Software—Infrastructure', 'NASDAQ', 'NasdaqGS'),

  ('GOOGL', 'Alphabet Inc.', 'Alphabet Inc.', 'Alphabet',
   'https://abc.xyz', 190234, 'United States',
   'Alphabet Inc. offers various products and platforms in the United States, Europe, the Middle East, Africa, the Asia-Pacific, Canada, and Latin America.',
   'Communication Services', 'Internet Content & Information', 'NASDAQ', 'NasdaqGS'),

  ('TSLA', 'Tesla, Inc.', 'Tesla, Inc.', 'Tesla',
   'https://www.tesla.com', 127855, 'United States',
   'Tesla, Inc. designs, develops, manufactures, leases, and sells electric vehicles, and energy generation and storage systems.',
   'Consumer Cyclical', 'Auto Manufacturers', 'NASDAQ', 'NasdaqGS'),

  ('AMZN', 'Amazon.com, Inc.', 'Amazon.com, Inc.', 'Amazon',
   'https://www.amazon.com', 1541000, 'United States',
   'Amazon.com, Inc. engages in the retail sale of consumer products and subscriptions in North America and internationally.',
   'Consumer Cyclical', 'Internet Retail', 'NASDAQ', 'NasdaqGS');

-- Insert market_data (from loadinfo.py schema)
INSERT INTO market_data (
  ticker, market_cap, current_price, previous_close, volume,
  fifty_two_week_low, fifty_two_week_high
) VALUES
  ('AAPL', 3450000000000, 225.50, 224.75, 52000000, 164.08, 237.23),
  ('MSFT', 2980000000000, 425.30, 424.10, 21000000, 309.45, 468.35),
  ('GOOGL', 2100000000000, 165.80, 164.95, 18500000, 121.46, 175.50),
  ('TSLA', 850000000000, 265.75, 263.50, 98000000, 152.37, 299.29),
  ('AMZN', 1950000000000, 188.45, 187.90, 45000000, 139.52, 201.20);

-- Insert key_metrics (financial metrics from loadinfo.py)
INSERT INTO key_metrics (
  ticker, trailing_pe, forward_pe, price_to_book, dividend_yield,
  eps_trailing, total_revenue, profit_margin_pct, debt_to_equity
) VALUES
  ('AAPL', 38.76, 30.74, 57.65, 0.41, 6.59, 408624988160, 24.30, 154.49),
  ('MSFT', 39.25, 32.10, 12.50, 0.72, 12.45, 227583000000, 36.20, 45.80),
  ('GOOGL', 27.80, 23.50, 7.20, 0, 6.18, 307394000000, 25.90, 10.50),
  ('TSLA', 95.30, 78.60, 15.40, 0, 3.62, 96773000000, 15.50, 22.30),
  ('AMZN', 85.20, 42.30, 9.80, 0, 3.01, 574785000000, 7.10, 68.90);

-- Insert price_daily data (from loadpricedaily.py schema - last 5 days)
INSERT INTO price_daily (symbol, date, open, high, low, close, adj_close, volume) VALUES
  -- AAPL last 5 days
  ('AAPL', '2025-10-02', 224.50, 226.80, 223.90, 225.50, 225.50, 52000000),
  ('AAPL', '2025-10-01', 223.20, 225.10, 222.50, 224.75, 224.75, 48500000),
  ('AAPL', '2025-09-30', 221.80, 223.90, 221.20, 223.20, 223.20, 45000000),
  ('AAPL', '2025-09-29', 220.50, 222.30, 219.80, 221.80, 221.80, 42000000),
  ('AAPL', '2025-09-28', 219.20, 221.10, 218.50, 220.50, 220.50, 40000000),

  -- MSFT last 5 days
  ('MSFT', '2025-10-02', 424.10, 426.50, 423.20, 425.30, 425.30, 21000000),
  ('MSFT', '2025-10-01', 422.80, 424.90, 422.10, 424.10, 424.10, 19500000),
  ('MSFT', '2025-09-30', 421.50, 423.40, 420.80, 422.80, 422.80, 18000000),
  ('MSFT', '2025-09-29', 420.20, 422.10, 419.50, 421.50, 421.50, 17000000),
  ('MSFT', '2025-09-28', 418.90, 420.80, 418.20, 420.20, 420.20, 16500000),

  -- GOOGL last 5 days
  ('GOOGL', '2025-10-02', 164.95, 166.20, 164.50, 165.80, 165.80, 18500000),
  ('GOOGL', '2025-10-01', 163.80, 165.50, 163.40, 164.95, 164.95, 17000000),
  ('GOOGL', '2025-09-30', 162.60, 164.30, 162.20, 163.80, 163.80, 16000000),
  ('GOOGL', '2025-09-29', 161.40, 163.10, 161.00, 162.60, 162.60, 15500000),
  ('GOOGL', '2025-09-28', 160.20, 161.90, 159.80, 161.40, 161.40, 15000000),

  -- TSLA last 5 days
  ('TSLA', '2025-10-02', 263.50, 267.20, 262.80, 265.75, 265.75, 98000000),
  ('TSLA', '2025-10-01', 261.20, 264.50, 260.50, 263.50, 263.50, 95000000),
  ('TSLA', '2025-09-30', 259.80, 262.30, 258.90, 261.20, 261.20, 92000000),
  ('TSLA', '2025-09-29', 258.40, 260.90, 257.50, 259.80, 259.80, 90000000),
  ('TSLA', '2025-09-28', 257.00, 259.50, 256.20, 258.40, 258.40, 88000000),

  -- AMZN last 5 days
  ('AMZN', '2025-10-02', 187.90, 189.20, 187.30, 188.45, 188.45, 45000000),
  ('AMZN', '2025-10-01', 186.70, 188.50, 186.20, 187.90, 187.90, 43000000),
  ('AMZN', '2025-09-30', 185.50, 187.30, 185.00, 186.70, 186.70, 41000000),
  ('AMZN', '2025-09-29', 184.30, 186.10, 183.80, 185.50, 185.50, 39000000),
  ('AMZN', '2025-09-28', 183.10, 184.90, 182.60, 184.30, 184.30, 37000000);

-- Insert technical_data_daily (from loadtechnicalsdaily.py schema)
INSERT INTO technical_data_daily (
  symbol, date, rsi, macd, macd_signal, sma_20, sma_50, sma_200,
  ema_21, adx, atr, pivot_high, pivot_low
) VALUES
  ('AAPL', '2025-10-02', 68.5, 2.30, 1.80, 220.50, 215.30, 195.40, 222.10, 25.5, 3.20, 226.80, 223.90),
  ('MSFT', '2025-10-02', 72.1, 3.50, 3.10, 418.20, 410.50, 385.60, 420.30, 28.3, 4.50, 426.50, 423.20),
  ('GOOGL', '2025-10-02', 65.3, 1.80, 1.50, 160.80, 155.20, 145.30, 162.50, 22.8, 2.10, 166.20, 164.50),
  ('TSLA', '2025-10-02', 55.2, -1.20, -0.80, 255.30, 248.90, 220.10, 258.60, 35.7, 8.90, 267.20, 262.80),
  ('AMZN', '2025-10-02', 62.8, 2.10, 1.70, 182.40, 178.20, 165.50, 184.30, 24.6, 3.80, 189.20, 187.30);

-- Verify data was inserted
SELECT 'company_profile' as table_name, COUNT(*) as row_count FROM company_profile
UNION ALL
SELECT 'market_data', COUNT(*) FROM market_data
UNION ALL
SELECT 'key_metrics', COUNT(*) FROM key_metrics
UNION ALL
SELECT 'price_daily', COUNT(*) FROM price_daily
UNION ALL
SELECT 'technical_data_daily', COUNT(*) FROM technical_data_daily;
