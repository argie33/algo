-- Fix missing symbol column in company_profile table
-- Create table if it doesn't exist and add symbol column

CREATE TABLE IF NOT EXISTS company_profile (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) UNIQUE NOT NULL,
    name VARCHAR(255),
    sector VARCHAR(100),
    market_cap BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add sample data if table is empty
INSERT INTO company_profile (symbol, name, sector, market_cap)
VALUES
    ('AAPL', 'Apple Inc.', 'Technology', 3000000000000),
    ('MSFT', 'Microsoft Corporation', 'Technology', 2800000000000),
    ('GOOGL', 'Alphabet Inc.', 'Technology', 1700000000000),
    ('AMZN', 'Amazon.com Inc.', 'Consumer Discretionary', 1600000000000),
    ('TSLA', 'Tesla Inc.', 'Consumer Discretionary', 800000000000)
ON CONFLICT (symbol) DO NOTHING;