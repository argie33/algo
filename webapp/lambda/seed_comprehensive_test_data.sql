-- Add comprehensive test data for all our tests
-- Add more stocks to stock_symbols (already done above)

-- Add company profile data  
INSERT INTO company_profile (ticker, name, sector, industry, market_cap, employees, description, website) VALUES
('AAPL', 'Apple Inc.', 'Technology', 'Consumer Electronics', 3000000000000, 161000, 'Technology company', 'apple.com'),
('MSFT', 'Microsoft Corporation', 'Technology', 'Software', 2800000000000, 221000, 'Software company', 'microsoft.com'),
('GOOGL', 'Alphabet Inc.', 'Technology', 'Internet Services', 1800000000000, 190000, 'Internet services', 'google.com'),
('TSLA', 'Tesla Inc.', 'Consumer Cyclical', 'Auto Manufacturers', 800000000000, 140000, 'Electric vehicles', 'tesla.com'),
('AMZN', 'Amazon.com Inc.', 'Consumer Cyclical', 'Internet Retail', 1500000000000, 1540000, 'E-commerce', 'amazon.com')
ON CONFLICT (ticker) DO UPDATE SET 
  name = EXCLUDED.name,
  sector = EXCLUDED.sector,
  industry = EXCLUDED.industry,
  market_cap = EXCLUDED.market_cap;

-- Add stocks table data using correct column names
INSERT INTO stocks (symbol, name, sector, price, market_cap, pe_ratio, dividend_yield) VALUES
('AAPL', 'Apple Inc.', 'Technology', 150.00, 3000000000000, 25.5, 0.5),
('MSFT', 'Microsoft Corporation', 'Technology', 380.00, 2800000000000, 28.2, 0.7),
('GOOGL', 'Alphabet Inc.', 'Technology', 140.00, 1800000000000, 22.1, 0.0),
('TSLA', 'Tesla Inc.', 'Consumer Cyclical', 250.00, 800000000000, 60.5, 0.0),
('AMZN', 'Amazon.com Inc.', 'Consumer Cyclical', 145.00, 1500000000000, 45.8, 0.0)
ON CONFLICT (symbol) DO UPDATE SET
  name = EXCLUDED.name,
  sector = EXCLUDED.sector,
  price = EXCLUDED.price,
  market_cap = EXCLUDED.market_cap;
