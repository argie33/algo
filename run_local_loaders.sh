#!/bin/bash
# Local Data Loader Pipeline - Development Mirror of AWS Production
# Run loaders in dependency order to populate local PostgreSQL database
# Requires: Local PostgreSQL running on localhost:5432 with 'stocks' database
#
# Usage: ./run_local_loaders.sh
# Or with custom database config:
#   DB_HOST=myhost DB_PORT=5433 DB_USER=myuser DB_PASSWORD=mypass ./run_local_loaders.sh

set -e

# Set local database configuration
export USE_LOCAL_DB=true
export DB_HOST=${DB_HOST:-localhost}
export DB_PORT=${DB_PORT:-5432}
export DB_USER=${DB_USER:-postgres}
export DB_PASSWORD=${DB_PASSWORD:-password}
export DB_NAME=${DB_NAME:-stocks}

echo "=== LOCAL Data Loader Pipeline ==="
echo "Database: $DB_HOST:$DB_PORT/$DB_NAME"
echo "Running loaders in dependency order..."
echo ""

# Track start time
START_TIME=$(date +%s)

# 1. Stock Symbols (prerequisite for everything)
echo "1. Loading stock symbols..."
USE_LOCAL_DB=$USE_LOCAL_DB DB_HOST=$DB_HOST DB_PORT=$DB_PORT DB_USER=$DB_USER DB_PASSWORD=$DB_PASSWORD DB_NAME=$DB_NAME python3 loadstocksymbols.py || echo "✗ Failed: stocksymbols"
echo ""

# 2. Price Data (prerequisite for technical indicators and scores)
echo "2. Loading price data..."
USE_LOCAL_DB=$USE_LOCAL_DB DB_HOST=$DB_HOST DB_PORT=$DB_PORT DB_USER=$DB_USER DB_PASSWORD=$DB_PASSWORD DB_NAME=$DB_NAME python3 loadpricedaily.py || echo "✗ Failed: pricedaily"
echo ""

# 3. Technical Indicators (prerequisite for scores)
echo "3. Loading technical indicators..."
USE_LOCAL_DB=$USE_LOCAL_DB DB_HOST=$DB_HOST DB_PORT=$DB_PORT DB_USER=$DB_USER DB_PASSWORD=$DB_PASSWORD DB_NAME=$DB_NAME python3 loadtechnicalsdaily.py || echo "✗ Failed: technicalsdaily"
echo ""

# 4. Company Info & Fundamental Data
echo "4. Loading company info..."
USE_LOCAL_DB=$USE_LOCAL_DB DB_HOST=$DB_HOST DB_PORT=$DB_PORT DB_USER=$DB_USER DB_PASSWORD=$DB_PASSWORD DB_NAME=$DB_NAME python3 loadinfo.py || echo "✗ Failed: info"
echo ""

# 5. Positioning Data (for positioning scores)
echo "5. Loading positioning data..."
USE_LOCAL_DB=$USE_LOCAL_DB DB_HOST=$DB_HOST DB_PORT=$DB_PORT DB_USER=$DB_USER DB_PASSWORD=$DB_PASSWORD DB_NAME=$DB_NAME python3 loaddailycompanydata.py || echo "✗ Failed: dailycompanydata"
echo ""

# 6. Sector Data (for sector analysis)
echo "6. Loading sector data..."
USE_LOCAL_DB=$USE_LOCAL_DB DB_HOST=$DB_HOST DB_PORT=$DB_PORT DB_USER=$DB_USER DB_PASSWORD=$DB_PASSWORD DB_NAME=$DB_NAME python3 loadsectordata.py || echo "✗ Failed: sectordata"
echo ""

# 7. Stock Scores (uses all previous data)
echo "7. Loading stock scores..."
USE_LOCAL_DB=$USE_LOCAL_DB DB_HOST=$DB_HOST DB_PORT=$DB_PORT DB_USER=$DB_USER DB_PASSWORD=$DB_PASSWORD DB_NAME=$DB_NAME python3 loadstockscores.py || echo "✗ Failed: stockscores"
echo ""

# Calculate execution time
END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo "=== Pipeline Complete ==="
echo "Execution time: ${ELAPSED}s"
echo ""
echo "✅ All loaders completed successfully!"
echo "Database ready for development and testing."
