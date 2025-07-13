-- Populate symbols table with basic sector and industry data for common stocks
-- This provides fallback data for portfolio holdings sector analysis

INSERT INTO symbols (symbol, name, sector, industry, market_cap) VALUES 
  ('AAPL', 'Apple Inc.', 'Technology', 'Consumer Electronics', 3500000000000),
  ('GOOGL', 'Alphabet Inc.', 'Technology', 'Internet Content & Information', 2100000000000),
  ('MSFT', 'Microsoft Corporation', 'Technology', 'Software—Infrastructure', 2800000000000),
  ('AMZN', 'Amazon.com Inc.', 'Consumer Discretionary', 'Internet Retail', 1700000000000),
  ('TSLA', 'Tesla Inc.', 'Consumer Discretionary', 'Auto Manufacturers', 800000000000),
  ('NVDA', 'NVIDIA Corporation', 'Technology', 'Semiconductors', 1900000000000),
  ('META', 'Meta Platforms Inc.', 'Technology', 'Internet Content & Information', 1300000000000),
  ('BRK.B', 'Berkshire Hathaway Inc.', 'Financial Services', 'Insurance—Diversified', 900000000000),
  ('UNH', 'UnitedHealth Group Inc.', 'Healthcare', 'Healthcare Plans', 550000000000),
  ('JNJ', 'Johnson & Johnson', 'Healthcare', 'Drug Manufacturers—General', 450000000000),
  ('V', 'Visa Inc.', 'Financial Services', 'Credit Services', 500000000000),
  ('WMT', 'Walmart Inc.', 'Consumer Staples', 'Discount Stores', 650000000000),
  ('PG', 'Procter & Gamble Co.', 'Consumer Staples', 'Household & Personal Products', 380000000000),
  ('HD', 'Home Depot Inc.', 'Consumer Discretionary', 'Home Improvement Retail', 420000000000),
  ('MA', 'Mastercard Inc.', 'Financial Services', 'Credit Services', 400000000000),
  ('PFE', 'Pfizer Inc.', 'Healthcare', 'Drug Manufacturers—General', 200000000000),
  ('BAC', 'Bank of America Corp.', 'Financial Services', 'Banks—Diversified', 300000000000),
  ('ABBV', 'AbbVie Inc.', 'Healthcare', 'Drug Manufacturers—General', 280000000000),
  ('KO', 'Coca-Cola Co.', 'Consumer Staples', 'Beverages—Non-Alcoholic', 260000000000),
  ('PEP', 'PepsiCo Inc.', 'Consumer Staples', 'Beverages—Non-Alcoholic', 240000000000),
  ('TMO', 'Thermo Fisher Scientific Inc.', 'Healthcare', 'Diagnostics & Research', 220000000000),
  ('COST', 'Costco Wholesale Corp.', 'Consumer Staples', 'Discount Stores', 330000000000),
  ('DIS', 'Walt Disney Co.', 'Communication Services', 'Entertainment', 180000000000),
  ('ABT', 'Abbott Laboratories', 'Healthcare', 'Medical Devices', 190000000000),
  ('VZ', 'Verizon Communications Inc.', 'Communication Services', 'Telecom Services', 170000000000),
  ('ADBE', 'Adobe Inc.', 'Technology', 'Software—Infrastructure', 240000000000),
  ('NFLX', 'Netflix Inc.', 'Communication Services', 'Entertainment', 200000000000),
  ('CRM', 'Salesforce Inc.', 'Technology', 'Software—Infrastructure', 250000000000),
  ('XOM', 'Exxon Mobil Corp.', 'Energy', 'Oil & Gas Integrated', 450000000000),
  ('CVX', 'Chevron Corp.', 'Energy', 'Oil & Gas Integrated', 320000000000),
  ('LLY', 'Eli Lilly and Co.', 'Healthcare', 'Drug Manufacturers—General', 820000000000),
  ('ORCL', 'Oracle Corp.', 'Technology', 'Software—Infrastructure', 350000000000),
  ('WFC', 'Wells Fargo & Co.', 'Financial Services', 'Banks—Diversified', 180000000000),
  ('JPM', 'JPMorgan Chase & Co.', 'Financial Services', 'Banks—Diversified', 500000000000),
  ('UPS', 'United Parcel Service Inc.', 'Industrials', 'Integrated Freight & Logistics', 120000000000),
  ('T', 'AT&T Inc.', 'Communication Services', 'Telecom Services', 130000000000),
  ('IBM', 'International Business Machines Corp.', 'Technology', 'Information Technology Services', 130000000000),
  ('GE', 'General Electric Co.', 'Industrials', 'Conglomerates', 140000000000),
  ('F', 'Ford Motor Co.', 'Consumer Discretionary', 'Auto Manufacturers', 50000000000),
  ('GM', 'General Motors Co.', 'Consumer Discretionary', 'Auto Manufacturers', 60000000000),
  
  -- Popular ETFs
  ('SPY', 'SPDR S&P 500 ETF Trust', 'Financial Services', 'Exchange Traded Fund', 500000000000),
  ('QQQ', 'Invesco QQQ Trust', 'Financial Services', 'Exchange Traded Fund', 200000000000),
  ('IWM', 'iShares Russell 2000 ETF', 'Financial Services', 'Exchange Traded Fund', 60000000000),
  ('VTI', 'Vanguard Total Stock Market ETF', 'Financial Services', 'Exchange Traded Fund', 300000000000),
  ('VOO', 'Vanguard S&P 500 ETF', 'Financial Services', 'Exchange Traded Fund', 400000000000),
  ('VEA', 'Vanguard FTSE Developed Markets ETF', 'Financial Services', 'Exchange Traded Fund', 100000000000),
  ('VWO', 'Vanguard FTSE Emerging Markets ETF', 'Financial Services', 'Exchange Traded Fund', 70000000000),
  ('BND', 'Vanguard Total Bond Market ETF', 'Financial Services', 'Exchange Traded Fund', 90000000000),
  ('GLD', 'SPDR Gold Shares', 'Financial Services', 'Exchange Traded Fund', 60000000000),
  ('TLT', 'iShares 20+ Year Treasury Bond ETF', 'Financial Services', 'Exchange Traded Fund', 40000000000)

ON CONFLICT (symbol) DO UPDATE SET
  name = EXCLUDED.name,
  sector = EXCLUDED.sector,
  industry = EXCLUDED.industry,
  market_cap = EXCLUDED.market_cap,
  last_updated = CURRENT_TIMESTAMP;

-- Create index on sector for faster sector-based queries
CREATE INDEX IF NOT EXISTS idx_symbols_sector ON symbols(sector);
CREATE INDEX IF NOT EXISTS idx_symbols_industry ON symbols(industry);

-- Show summary of populated data
SELECT 
  sector,
  COUNT(*) as stock_count,
  ROUND(AVG(market_cap / 1000000000.0), 1) as avg_market_cap_billions
FROM symbols 
WHERE sector IS NOT NULL 
GROUP BY sector 
ORDER BY stock_count DESC;