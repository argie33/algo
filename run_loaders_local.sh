#!/bin/bash
# Populate local database with stock data

export DB_HOST="${DB_HOST:-localhost}"
export DB_PORT="${DB_PORT:-5432}"
export DB_USER="${DB_USER:-postgres}"
export DB_PASSWORD="${DB_PASSWORD:-password}"
export DB_NAME="${DB_NAME:-stocks}"

echo "Starting local data population..."

# Stock symbols first
echo "Loading stock symbols..."
python3 loadstocksymbols.py 2>&1 | head -50

# Price data
echo "Loading price data for top symbols..."
python3 loadpricedaily.py 2>&1 | head -50

# Technical indicators
echo "Loading technical data..."
python3 loadtechnicalsdaily.py 2>&1 | head -50

# Buy/Sell signals (requires price + technical data)
echo "Loading buy/sell signals..."
python3 loadbuyselldaily.py 2>&1 | head -50

# Stock scores (requires all above)
echo "Loading stock scores..."
python3 loadstockscores.py 2>&1 | head -50

echo "Data population complete!"
