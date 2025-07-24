#!/bin/bash

# Setup Local Development Database Script
# This script creates a local PostgreSQL database with sample data to bypass AWS Secrets Manager issues

set -e  # Exit on error

echo "🚀 Setting up local development database..."

# Database configuration
DB_NAME="stocks"
DB_USER="postgres"
DB_HOST="localhost"
DB_PORT="5432"

# Check if PostgreSQL is running
if ! pg_isready -h $DB_HOST -p $DB_PORT -U $DB_USER > /dev/null 2>&1; then
    echo "❌ PostgreSQL is not running. Please start PostgreSQL first:"
    echo "   sudo service postgresql start    (Linux)"
    echo "   brew services start postgresql  (macOS)"
    exit 1
fi

echo "✅ PostgreSQL is running"

# Create database if it doesn't exist
echo "📦 Creating database '$DB_NAME'..."
createdb -h $DB_HOST -p $DB_PORT -U $DB_USER $DB_NAME 2>/dev/null || echo "Database already exists"

# Initialize core schema
echo "🏗️  Initializing core schema..."
psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f sql/initialize-required-tables.sql

# Add comprehensive test data for frontend development
echo "📊 Adding comprehensive test data..."
psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME << 'EOF'
-- Insert sample users
INSERT INTO users (user_id, email, first_name, last_name, is_active) 
VALUES 
    (1, 'demo@example.com', 'Demo', 'User', true),
    (2, 'test@example.com', 'Test', 'User', true)
ON CONFLICT (email) DO NOTHING;

-- Insert sample API keys (encrypted dummy data)
INSERT INTO user_api_keys (user_id, provider, api_key_encrypted, secret_encrypted, masked_api_key, is_sandbox, is_active, validation_status)
VALUES 
    ('demo@example.com', 'alpaca', 'dummy_encrypted_key_123', 'dummy_encrypted_secret_456', 'PK***ABC', true, true, 'validated'),
    ('test@example.com', 'alpaca', 'dummy_encrypted_key_789', 'dummy_encrypted_secret_012', 'PK***XYZ', true, true, 'validated')
ON CONFLICT (user_id, provider) DO NOTHING;

-- Insert diverse portfolio holdings
INSERT INTO portfolio_holdings (user_id, api_key_id, symbol, quantity, avg_cost, current_price, market_value, unrealized_pl, sector, industry, company)
VALUES 
    ('demo@example.com', 1, 'AAPL', 100.00, 150.00, 175.50, 17550.00, 2550.00, 'Technology', 'Consumer Electronics', 'Apple Inc.'),
    ('demo@example.com', 1, 'MSFT', 50.00, 300.00, 350.25, 17512.50, 2512.50, 'Technology', 'Software', 'Microsoft Corporation'),
    ('demo@example.com', 1, 'GOOGL', 10.00, 2500.00, 2750.00, 27500.00, 2500.00, 'Technology', 'Internet', 'Alphabet Inc.'),
    ('demo@example.com', 1, 'TSLA', 25.00, 800.00, 750.00, 18750.00, -1250.00, 'Consumer Cyclical', 'Auto Manufacturers', 'Tesla Inc.'),
    ('demo@example.com', 1, 'AMZN', 15.00, 3000.00, 3200.00, 48000.00, 3000.00, 'Consumer Cyclical', 'Internet Retail', 'Amazon.com Inc.'),
    ('demo@example.com', 1, 'NVDA', 20.00, 400.00, 850.00, 17000.00, 9000.00, 'Technology', 'Semiconductors', 'NVIDIA Corporation'),
    ('demo@example.com', 1, 'JPM', 30.00, 140.00, 155.00, 4650.00, 450.00, 'Financial Services', 'Banks', 'JPMorgan Chase & Co.'),
    ('demo@example.com', 1, 'JNJ', 40.00, 160.00, 165.00, 6600.00, 200.00, 'Healthcare', 'Drug Manufacturers', 'Johnson & Johnson'),
    ('test@example.com', 2, 'SPY', 50.00, 400.00, 420.00, 21000.00, 1000.00, 'ETF', 'Index Fund', 'SPDR S&P 500 ETF'),
    ('test@example.com', 2, 'QQQ', 25.00, 350.00, 375.00, 9375.00, 625.00, 'ETF', 'Technology', 'Invesco QQQ Trust')
ON CONFLICT (user_id, api_key_id, symbol) DO UPDATE SET
    current_price = EXCLUDED.current_price,
    market_value = EXCLUDED.market_value,
    unrealized_pl = EXCLUDED.unrealized_pl,
    updated_at = CURRENT_TIMESTAMP;

-- Insert portfolio metadata
INSERT INTO portfolio_metadata (user_id, api_key_id, account_type, total_equity, total_market_value, buying_power, cash, broker)
VALUES 
    ('demo@example.com', 1, 'paper', 162562.50, 156962.50, 50000.00, 5600.00, 'alpaca'),
    ('test@example.com', 2, 'paper', 35375.00, 30375.00, 15000.00, 5000.00, 'alpaca')
ON CONFLICT (user_id) DO UPDATE SET
    total_equity = EXCLUDED.total_equity,
    total_market_value = EXCLUDED.total_market_value,
    buying_power = EXCLUDED.buying_power,
    cash = EXCLUDED.cash,
    updated_at = CURRENT_TIMESTAMP;

-- Insert comprehensive market data for popular stocks
INSERT INTO market_data (symbol, price, volume, market_cap, pe_ratio, dividend_yield, beta, fifty_two_week_high, fifty_two_week_low, sector, industry, exchange)
VALUES 
    ('AAPL', 175.50, 45000000, 2800000000000, 25.5, 0.52, 1.2, 182.00, 124.17, 'Technology', 'Consumer Electronics', 'NASDAQ'),
    ('MSFT', 350.25, 28000000, 2600000000000, 28.2, 0.75, 0.9, 384.52, 224.26, 'Technology', 'Software', 'NASDAQ'),
    ('GOOGL', 2750.00, 1200000, 1800000000000, 22.8, 0.00, 1.1, 3030.93, 2044.16, 'Technology', 'Internet', 'NASDAQ'),
    ('TSLA', 750.00, 25000000, 750000000000, 45.2, 0.00, 2.1, 1243.49, 138.80, 'Consumer Cyclical', 'Auto Manufacturers', 'NASDAQ'),
    ('AMZN', 3200.00, 3500000, 1600000000000, 52.1, 0.00, 1.3, 3773.08, 2671.45, 'Consumer Cyclical', 'Internet Retail', 'NASDAQ'),
    ('NVDA', 850.00, 18000000, 2100000000000, 68.5, 0.14, 1.8, 1037.99, 180.68, 'Technology', 'Semiconductors', 'NASDAQ'),
    ('JPM', 155.00, 12000000, 450000000000, 11.2, 2.8, 1.1, 172.96, 126.06, 'Financial Services', 'Banks', 'NYSE'),
    ('JNJ', 165.00, 8000000, 430000000000, 15.8, 2.9, 0.7, 186.69, 143.83, 'Healthcare', 'Drug Manufacturers', 'NYSE'),
    ('SPY', 420.00, 85000000, 380000000000, 0.0, 1.3, 1.0, 459.44, 348.11, 'ETF', 'Index Fund', 'NYSE'),
    ('QQQ', 375.00, 42000000, 180000000000, 0.0, 0.5, 1.1, 408.71, 284.91, 'ETF', 'Technology', 'NASDAQ')
ON CONFLICT (symbol) DO UPDATE SET
    price = EXCLUDED.price,
    volume = EXCLUDED.volume,
    market_cap = EXCLUDED.market_cap,
    pe_ratio = EXCLUDED.pe_ratio,
    dividend_yield = EXCLUDED.dividend_yield,
    beta = EXCLUDED.beta,
    fifty_two_week_high = EXCLUDED.fifty_two_week_high,
    fifty_two_week_low = EXCLUDED.fifty_two_week_low,
    sector = EXCLUDED.sector,
    industry = EXCLUDED.industry,
    exchange = EXCLUDED.exchange,
    updated_at = CURRENT_TIMESTAMP;

-- Insert stock symbols for screener functionality
INSERT INTO stock_symbols (symbol, company_name, sector, industry, exchange, market_cap, is_active)
VALUES 
    ('AAPL', 'Apple Inc.', 'Technology', 'Consumer Electronics', 'NASDAQ', 2800000000000, true),
    ('MSFT', 'Microsoft Corporation', 'Technology', 'Software', 'NASDAQ', 2600000000000, true),
    ('GOOGL', 'Alphabet Inc.', 'Technology', 'Internet', 'NASDAQ', 1800000000000, true),
    ('TSLA', 'Tesla Inc.', 'Consumer Cyclical', 'Auto Manufacturers', 'NASDAQ', 750000000000, true),
    ('AMZN', 'Amazon.com Inc.', 'Consumer Cyclical', 'Internet Retail', 'NASDAQ', 1600000000000, true),
    ('NVDA', 'NVIDIA Corporation', 'Technology', 'Semiconductors', 'NASDAQ', 2100000000000, true),
    ('JPM', 'JPMorgan Chase & Co.', 'Financial Services', 'Banks', 'NYSE', 450000000000, true),
    ('JNJ', 'Johnson & Johnson', 'Healthcare', 'Drug Manufacturers', 'NYSE', 430000000000, true),
    ('SPY', 'SPDR S&P 500 ETF', 'ETF', 'Index Fund', 'NYSE', 380000000000, true),
    ('QQQ', 'Invesco QQQ Trust', 'ETF', 'Technology', 'NASDAQ', 180000000000, true),
    ('META', 'Meta Platforms Inc.', 'Technology', 'Internet', 'NASDAQ', 800000000000, true),
    ('BRK.B', 'Berkshire Hathaway Inc.', 'Financial Services', 'Conglomerates', 'NYSE', 750000000000, true),
    ('V', 'Visa Inc.', 'Financial Services', 'Credit Services', 'NYSE', 500000000000, true),
    ('UNH', 'UnitedHealth Group Inc.', 'Healthcare', 'Healthcare Plans', 'NYSE', 480000000000, true),
    ('HD', 'The Home Depot Inc.', 'Consumer Cyclical', 'Home Improvement Retail', 'NYSE', 350000000000, true)
ON CONFLICT (symbol) DO UPDATE SET
    company_name = EXCLUDED.company_name,
    sector = EXCLUDED.sector,
    industry = EXCLUDED.industry,
    exchange = EXCLUDED.exchange,
    market_cap = EXCLUDED.market_cap,
    updated_at = CURRENT_TIMESTAMP;

-- Also populate legacy symbols table for compatibility
INSERT INTO symbols (symbol, company, sector, industry, exchange, market_cap, is_active)
SELECT symbol, company_name, sector, industry, exchange, market_cap, is_active
FROM stock_symbols
ON CONFLICT (symbol) DO UPDATE SET
    company = EXCLUDED.company,
    sector = EXCLUDED.sector,
    industry = EXCLUDED.industry,
    exchange = EXCLUDED.exchange,
    market_cap = EXCLUDED.market_cap,
    updated_at = CURRENT_TIMESTAMP;

-- Update sequence values
SELECT setval('users_user_id_seq', (SELECT MAX(user_id) FROM users));
SELECT setval('user_api_keys_id_seq', (SELECT COALESCE(MAX(id), 1) FROM user_api_keys));
SELECT setval('portfolio_holdings_holding_id_seq', (SELECT COALESCE(MAX(holding_id), 1) FROM portfolio_holdings));
SELECT setval('portfolio_metadata_metadata_id_seq', (SELECT COALESCE(MAX(metadata_id), 1) FROM portfolio_metadata));
SELECT setval('market_data_id_seq', (SELECT COALESCE(MAX(id), 1) FROM market_data));
SELECT setval('stock_symbols_id_seq', (SELECT COALESCE(MAX(id), 1) FROM stock_symbols));
SELECT setval('symbols_id_seq', (SELECT COALESCE(MAX(id), 1) FROM symbols));

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;

\echo 'Local development database setup completed successfully!'
EOF

# Configure Lambda to use local database
echo "🔧 Configuring Lambda for local database..."
cd /home/stocks/algo/webapp/lambda

# Backup current .env if it exists
if [ -f .env ]; then
    cp .env .env.backup
    echo "📋 Backed up current .env to .env.backup"
fi

# Create local development .env
cat > .env << EOF
# Local Development Configuration
NODE_ENV=development

# Local Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=postgres
DB_NAME=stocks
DB_SSL=false

# AWS Configuration (for other services)
AWS_REGION=us-east-1
WEBAPP_AWS_REGION=us-east-1

# Authentication Configuration
ALLOW_DEV_BYPASS=true

# CORS Configuration
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173

# Disable AWS Secrets Manager for local development
USE_AWS_SECRETS=false
EOF

echo "✅ Local development environment configured!"
echo ""
echo "🎉 Setup complete! Your local development database is ready with:"
echo "   • 2 demo users with API keys"
echo "   • 10 portfolio holdings across different sectors"
echo "   • 15 stocks with market data"
echo "   • All required tables and indexes"
echo ""
echo "🚀 Next steps:"
echo "   1. Start your Lambda development server: npm run dev"
echo "   2. Start your frontend: cd ../frontend && npm run dev"
echo "   3. Visit http://localhost:3000 to see live data!"
echo ""
echo "💡 To revert to AWS configuration: mv .env.backup .env"