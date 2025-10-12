#!/bin/bash
# Critical Data Loader Pipeline
# Run loaders in dependency order to populate database

set -e

echo "=== Critical Data Loader Pipeline ==="
echo "Running loaders in dependency order..."

# 1. Stock Symbols (prerequisite for everything)
echo "1. Loading stock symbols..."
python3 loadstocksymbols.py || echo "✗ Failed: stocksymbols"

# 2. Price Data (prerequisite for technical indicators and scores)
echo "2. Loading price data..."
python3 loadpricedaily.py || echo "✗ Failed: pricedaily"

# 3. Technical Indicators (prerequisite for scores)
echo "3. Loading technical indicators..."
python3 loadtechnicalsdaily.py || echo "✗ Failed: technicalsdaily"

# 4. Company Info & Fundamental Data
echo "4. Loading company info..."
python3 loadinfo.py || echo "✗ Failed: info"

# 5. Positioning Data (for positioning scores)
echo "5. Loading positioning data..."
python3 loaddailycompanydata.py || echo "✗ Failed: dailycompanydata"

# 6. Sector Data (for sector analysis)
echo "6. Loading sector data..."
python3 loadsectordata.py || echo "✗ Failed: sectordata"

# 7. Stock Scores (uses all previous data)
echo "7. Loading stock scores..."
python3 loadstockscores.py || echo "✗ Failed: stockscores"

echo "=== Pipeline Complete ==="
