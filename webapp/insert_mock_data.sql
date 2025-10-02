-- Mock data for local development
-- This script populates the database with sample data for testing

-- Insert mock company profiles with sectors
-- First try stocks table (used by market.js), fallback to company_profile
INSERT INTO stocks (symbol, name, sector, industry, market_cap) VALUES
('AAPL', 'Apple Inc.', 'Technology', 'Consumer Electronics', 2800000000000),
('MSFT', 'Microsoft Corp.', 'Technology', 'Software', 2500000000000),
('GOOGL', 'Alphabet Inc.', 'Technology', 'Internet Services', 1700000000000),
('AMZN', 'Amazon.com Inc.', 'Consumer Cyclical', 'Internet Retail', 1500000000000),
('TSLA', 'Tesla Inc.', 'Consumer Cyclical', 'Auto Manufacturers', 800000000000),
('JPM', 'JPMorgan Chase', 'Financial Services', 'Banks', 450000000000),
('BAC', 'Bank of America', 'Financial Services', 'Banks', 320000000000),
('WFC', 'Wells Fargo', 'Financial Services', 'Banks', 180000000000),
('JNJ', 'Johnson & Johnson', 'Healthcare', 'Drug Manufacturers', 420000000000),
('PFE', 'Pfizer Inc.', 'Healthcare', 'Drug Manufacturers', 180000000000),
('UNH', 'UnitedHealth Group', 'Healthcare', 'Healthcare Plans', 480000000000),
('XOM', 'Exxon Mobil', 'Energy', 'Oil & Gas', 420000000000),
('CVX', 'Chevron Corp.', 'Energy', 'Oil & Gas', 280000000000),
('NEE', 'NextEra Energy', 'Utilities', 'Utilities', 150000000000),
('DUK', 'Duke Energy', 'Utilities', 'Utilities', 78000000000),
('PG', 'Procter & Gamble', 'Consumer Defensive', 'Household Products', 360000000000),
('KO', 'Coca-Cola', 'Consumer Defensive', 'Beverages', 260000000000),
('PEP', 'PepsiCo', 'Consumer Defensive', 'Beverages', 230000000000),
('WMT', 'Walmart', 'Consumer Defensive', 'Discount Stores', 410000000000),
('HD', 'Home Depot', 'Consumer Cyclical', 'Home Improvement', 330000000000),
('NKE', 'Nike Inc.', 'Consumer Cyclical', 'Footwear & Accessories', 160000000000),
('DIS', 'Walt Disney', 'Communication Services', 'Entertainment', 180000000000),
('NFLX', 'Netflix Inc.', 'Communication Services', 'Entertainment', 190000000000),
('BA', 'Boeing', 'Industrials', 'Aerospace & Defense', 120000000000),
('CAT', 'Caterpillar', 'Industrials', 'Construction Equipment', 160000000000),
('GE', 'General Electric', 'Industrials', 'Conglomerates', 130000000000),
('LMT', 'Lockheed Martin', 'Industrials', 'Aerospace & Defense', 110000000000),
('RTX', 'Raytheon Technologies', 'Industrials', 'Aerospace & Defense', 140000000000),
('V', 'Visa Inc.', 'Financial Services', 'Credit Services', 520000000000),
('MA', 'Mastercard', 'Financial Services', 'Credit Services', 380000000000)
ON CONFLICT (symbol) DO UPDATE SET
  name = EXCLUDED.name,
  sector = EXCLUDED.sector,
  industry = EXCLUDED.industry,
  market_cap = EXCLUDED.market_cap;

-- Insert mock price data for the last 30 days
DO $$
DECLARE
  stock_ticker TEXT;
  base_price NUMERIC;
  day_offset INTEGER;
  current_date DATE;
  daily_change NUMERIC;
  current_price NUMERIC;
BEGIN
  -- Loop through each stock
  FOR stock_ticker, base_price IN
    SELECT ticker,
           CASE ticker
             WHEN 'AAPL' THEN 178.50
             WHEN 'MSFT' THEN 380.00
             WHEN 'GOOGL' THEN 142.00
             WHEN 'AMZN' THEN 145.00
             WHEN 'TSLA' THEN 245.00
             WHEN 'JPM' THEN 152.00
             WHEN 'BAC' THEN 32.50
             WHEN 'WFC' THEN 45.00
             WHEN 'JNJ' THEN 158.00
             WHEN 'PFE' THEN 29.50
             WHEN 'UNH' THEN 520.00
             WHEN 'XOM' THEN 115.00
             WHEN 'CVX' THEN 158.00
             WHEN 'NEE' THEN 64.00
             WHEN 'DUK' THEN 98.00
             WHEN 'PG' THEN 153.00
             WHEN 'KO' THEN 61.50
             WHEN 'PEP' THEN 172.00
             WHEN 'WMT' THEN 165.00
             WHEN 'HD' THEN 330.00
             WHEN 'NKE' THEN 105.00
             WHEN 'DIS' THEN 92.00
             WHEN 'NFLX' THEN 485.00
             WHEN 'BA' THEN 192.00
             WHEN 'CAT' THEN 325.00
             WHEN 'GE' THEN 115.00
             WHEN 'LMT' THEN 465.00
             WHEN 'RTX' THEN 98.00
             WHEN 'V' THEN 265.00
             WHEN 'MA' THEN 420.00
             ELSE 100.00
           END
    FROM stocks
    WHERE symbol IN ('AAPL','MSFT','GOOGL','AMZN','TSLA','JPM','BAC','WFC','JNJ','PFE',
                     'UNH','XOM','CVX','NEE','DUK','PG','KO','PEP','WMT','HD',
                     'NKE','DIS','NFLX','BA','CAT','GE','LMT','RTX','V','MA')
  LOOP
    current_price := base_price;

    -- Generate 30 days of price data
    FOR day_offset IN 0..29 LOOP
      current_date := CURRENT_DATE - day_offset;

      -- Random daily change between -2% and +2%
      daily_change := (random() * 4 - 2) / 100;
      current_price := current_price * (1 + daily_change);

      -- Insert or update price data
      INSERT INTO price_daily (
        symbol, date, open, high, low, close, volume
      ) VALUES (
        stock_ticker,
        current_date,
        current_price * 0.99,
        current_price * 1.01,
        current_price * 0.98,
        current_price,
        (1000000 + random() * 9000000)::BIGINT
      )
      ON CONFLICT (symbol, date) DO UPDATE SET
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        volume = EXCLUDED.volume;
    END LOOP;
  END LOOP;
END $$;

-- Insert mock economic indicators
INSERT INTO economic_data (indicator_name, value, date, category) VALUES
('GDP Growth Rate', 2.1, CURRENT_DATE - INTERVAL '15 days', 'growth'),
('Unemployment Rate', 3.8, CURRENT_DATE - INTERVAL '5 days', 'employment'),
('Inflation Rate', 3.2, CURRENT_DATE - INTERVAL '7 days', 'inflation'),
('Federal Funds Rate', 5.33, CURRENT_DATE - INTERVAL '1 day', 'monetary'),
('10-Year Treasury Yield', 4.25, CURRENT_DATE, 'rates'),
('Consumer Confidence', 102.6, CURRENT_DATE - INTERVAL '10 days', 'sentiment')
ON CONFLICT DO NOTHING;

-- Verify data was inserted
SELECT 'Stocks inserted:' as info, COUNT(*) as count FROM stocks;
SELECT 'Price records inserted:' as info, COUNT(*) as count FROM price_daily;
SELECT 'Sectors available:' as info, COUNT(DISTINCT sector) as count FROM stocks WHERE sector IS NOT NULL;
