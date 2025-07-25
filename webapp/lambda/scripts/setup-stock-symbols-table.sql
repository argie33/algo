-- ============================================================================
-- STOCK SYMBOLS TABLE SETUP AND DATA LOADING
-- ============================================================================
-- This script creates the stock_symbols table that the stocks API expects
-- and loads sample data to resolve 503 Service Unavailable errors

-- Create stock_symbols table (the application expects this table name)
CREATE TABLE IF NOT EXISTS stock_symbols (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) UNIQUE NOT NULL,
    company_name VARCHAR(255) NOT NULL,
    sector VARCHAR(100),
    industry VARCHAR(100),
    market_cap BIGINT,
    pe_ratio DECIMAL(10,2),
    price DECIMAL(10,2),
    change_percent DECIMAL(5,2),
    volume BIGINT,
    is_active BOOLEAN DEFAULT TRUE,
    exchange VARCHAR(10) DEFAULT 'NASDAQ',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index for performance
CREATE INDEX IF NOT EXISTS idx_stock_symbols_sector ON stock_symbols(sector);
CREATE INDEX IF NOT EXISTS idx_stock_symbols_active ON stock_symbols(is_active);
CREATE INDEX IF NOT EXISTS idx_stock_symbols_symbol ON stock_symbols(symbol);

-- Insert sample data for testing (popular stocks)
INSERT INTO stock_symbols (symbol, company_name, sector, industry, market_cap, pe_ratio, price, change_percent, volume) VALUES
('AAPL', 'Apple Inc.', 'Technology', 'Consumer Electronics', 3000000000000, 28.5, 189.25, 1.2, 45000000),
('MSFT', 'Microsoft Corporation', 'Technology', 'Software', 2800000000000, 32.1, 378.85, 0.8, 35000000),
('GOOGL', 'Alphabet Inc.', 'Technology', 'Internet Services', 1700000000000, 25.3, 134.12, -0.5, 28000000),
('AMZN', 'Amazon.com Inc.', 'Consumer Discretionary', 'E-commerce', 1600000000000, 45.2, 145.78, 2.1, 32000000),
('TSLA', 'Tesla Inc.', 'Consumer Discretionary', 'Electric Vehicles', 800000000000, 65.8, 248.42, 3.5, 85000000),
('META', 'Meta Platforms Inc.', 'Technology', 'Social Media', 850000000000, 22.7, 338.15, 1.8, 25000000),
('NVDA', 'NVIDIA Corporation', 'Technology', 'Semiconductors', 1800000000000, 68.4, 734.25, 4.2, 42000000),
('JPM', 'JPMorgan Chase & Co.', 'Financial Services', 'Banking', 450000000000, 12.5, 158.95, 0.3, 15000000),
('JNJ', 'Johnson & Johnson', 'Healthcare', 'Pharmaceuticals', 420000000000, 15.8, 162.33, -0.2, 8500000),
('V', 'Visa Inc.', 'Financial Services', 'Payment Processing', 520000000000, 31.2, 248.67, 1.5, 6200000),
('PG', 'Procter & Gamble Co.', 'Consumer Staples', 'Household Products', 380000000000, 24.6, 158.42, 0.7, 7800000),
('HD', 'The Home Depot Inc.', 'Consumer Discretionary', 'Home Improvement', 350000000000, 26.4, 328.75, 1.9, 4200000),
('UNH', 'UnitedHealth Group Inc.', 'Healthcare', 'Health Insurance', 480000000000, 19.8, 515.28, 2.3, 3800000),
('DIS', 'The Walt Disney Company', 'Communication Services', 'Entertainment', 180000000000, 35.7, 98.45, -1.2, 12000000),
('KO', 'The Coca-Cola Company', 'Consumer Staples', 'Beverages', 260000000000, 26.1, 60.15, 0.4, 14000000),
('NFLX', 'Netflix Inc.', 'Communication Services', 'Streaming', 190000000000, 28.9, 445.03, 2.8, 6500000),
('ADBE', 'Adobe Inc.', 'Technology', 'Software', 240000000000, 42.3, 518.75, 1.6, 2800000),
('CRM', 'Salesforce Inc.', 'Technology', 'Cloud Software', 220000000000, 51.2, 224.86, 3.1, 4100000),
('PYPL', 'PayPal Holdings Inc.', 'Financial Services', 'Digital Payments', 85000000000, 18.5, 75.42, -0.8, 8900000),
('INTC', 'Intel Corporation', 'Technology', 'Semiconductors', 180000000000, 14.7, 43.25, 1.4, 38000000),
('PFE', 'Pfizer Inc.', 'Healthcare', 'Pharmaceuticals', 210000000000, 13.2, 37.15, -0.6, 42000000),
('XOM', 'Exxon Mobil Corporation', 'Energy', 'Oil & Gas', 420000000000, 12.8, 102.35, 2.5, 18000000),
('BAC', 'Bank of America Corporation', 'Financial Services', 'Banking', 290000000000, 11.9, 35.28, 0.9, 52000000),
('WMT', 'Walmart Inc.', 'Consumer Staples', 'Retail', 480000000000, 25.3, 159.67, 1.1, 8600000),
('CVX', 'Chevron Corporation', 'Energy', 'Oil & Gas', 320000000000, 14.5, 168.42, 1.8, 9200000);

-- Create portfolio_holdings table if it doesn't exist (referenced in health checks)
CREATE TABLE IF NOT EXISTS portfolio_holdings (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255),
    symbol VARCHAR(10) REFERENCES stock_symbols(symbol),
    quantity DECIMAL(15,6) NOT NULL,
    average_cost DECIMAL(15,4),
    current_price DECIMAL(15,4),
    market_value DECIMAL(15,4),
    unrealized_pnl DECIMAL(15,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create trading_history table if it doesn't exist (referenced in health checks)
CREATE TABLE IF NOT EXISTS trading_history (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255),
    symbol VARCHAR(10),
    side VARCHAR(10) NOT NULL, -- 'buy' or 'sell'
    quantity DECIMAL(15,6) NOT NULL,
    price DECIMAL(15,4) NOT NULL,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    order_type VARCHAR(20),
    status VARCHAR(20) DEFAULT 'filled'
);

-- Create user_accounts table if it doesn't exist (referenced in health checks)
CREATE TABLE IF NOT EXISTS user_accounts (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) UNIQUE,
    email VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- Insert sample user and portfolio data
INSERT INTO user_accounts (user_id, email) VALUES 
('test-user-1', 'test@example.com'),
('demo-user', 'demo@example.com')
ON CONFLICT (user_id) DO NOTHING;

INSERT INTO portfolio_holdings (user_id, symbol, quantity, average_cost, current_price, market_value, unrealized_pnl) VALUES
('test-user-1', 'AAPL', 10.0, 150.00, 189.25, 1892.50, 392.50),
('test-user-1', 'MSFT', 5.0, 300.00, 378.85, 1894.25, 394.25),
('test-user-1', 'GOOGL', 3.0, 120.00, 134.12, 402.36, 42.36),
('demo-user', 'TSLA', 2.0, 200.00, 248.42, 496.84, 96.84),
('demo-user', 'NVDA', 1.0, 600.00, 734.25, 734.25, 134.25)
ON CONFLICT DO NOTHING;

-- Update statistics for better query performance
ANALYZE stock_symbols;
ANALYZE portfolio_holdings;
ANALYZE trading_history;
ANALYZE user_accounts;

-- Display summary
SELECT 'Stock symbols loaded:' as status, COUNT(*) as count FROM stock_symbols;
SELECT 'Portfolio holdings loaded:' as status, COUNT(*) as count FROM portfolio_holdings;
SELECT 'User accounts loaded:' as status, COUNT(*) as count FROM user_accounts;