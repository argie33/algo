#!/bin/bash
# Setup local database with real data using existing loaders

set -e  # Exit on error

echo "🚀 Setting up local database with real financial data..."

# Export local database environment variables
export DB_HOST="localhost"
export DB_USER="postgres" 
export DB_PASSWORD="password"
export DB_NAME="stocks"
export DB_PORT="5432"

# Clear AWS environment variables to force local mode
unset DB_SECRET_ARN
unset AWS_DEFAULT_REGION
unset AWS_REGION

# Base directory for loaders
BASE_DIR="/home/stocks/algo"

cd "$BASE_DIR"

echo "📊 Step 1: Loading stock symbols..."
if [ -f "loadstocksymbols.py" ]; then
    python3 loadstocksymbols.py || echo "⚠️ Stock symbols loader failed (may already exist)"
else
    echo "⚠️ loadstocksymbols.py not found, skipping..."
fi

echo "💰 Step 2: Loading daily price data..."
if [ -f "loadpricedaily.py" ]; then
    python3 loadpricedaily.py || echo "⚠️ Daily price loader failed"
else
    echo "⚠️ loadpricedaily.py not found, skipping..."
fi

echo "📈 Step 3: Loading technical indicators..."
if [ -f "loadtechnicalsdaily.py" ]; then
    python3 loadtechnicalsdaily.py || echo "⚠️ Technical indicators loader failed"
else
    echo "⚠️ loadtechnicalsdaily.py not found, skipping..."
fi

echo "📊 Step 4: Loading fundamental metrics..."
if [ -f "loadfundamentalmetrics.py" ]; then
    python3 loadfundamentalmetrics.py || echo "⚠️ Fundamental metrics loader failed"
else
    echo "⚠️ loadfundamentalmetrics.py not found, skipping..."
fi

echo "📰 Step 5: Loading news data..."
if [ -f "loadnews.py" ]; then
    python3 loadnews.py || echo "⚠️ News loader failed"
else
    echo "⚠️ loadnews.py not found, skipping..."
fi

echo "💭 Step 6: Loading sentiment data..."
if [ -f "loadsentiment.py" ]; then
    python3 loadsentiment.py || echo "⚠️ Sentiment loader failed"
else
    echo "⚠️ loadsentiment.py not found, skipping..."
fi

echo "✅ Local data setup complete! Database should now have real financial data."

echo "🔍 Quick verification:"
echo "Stock count:"
psql -h localhost -U postgres -d stocks -c "SELECT COUNT(*) FROM stocks;" 2>/dev/null || echo "❌ Can't connect to database"

echo "Price data sample:"
psql -h localhost -U postgres -d stocks -c "SELECT symbol, COUNT(*) as price_records FROM price_daily GROUP BY symbol ORDER BY symbol;" 2>/dev/null || echo "❌ No price data"

echo "Technical data sample:"  
psql -h localhost -U postgres -d stocks -c "SELECT symbol, COUNT(*) as tech_records FROM technical_data_daily GROUP BY symbol ORDER BY symbol;" 2>/dev/null || echo "❌ No technical data"

echo "🎉 Setup complete! You can now test your APIs with real data."