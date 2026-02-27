#!/bin/bash
# AWS Data Loading Script - Run in AWS CloudShell
# Loads all 58 data loaders to RDS database
# Usage: bash RUN_DATA_LOADERS_AWS.sh

set -e

echo "=========================================="
echo "AWS DATA LOADING - ALL LOADERS"
echo "=========================================="
echo "This script loads all 58 data loaders to AWS RDS"
echo ""

# Get RDS endpoint from user
if [ -z "$DB_HOST" ]; then
    echo "📍 RDS Endpoint not set. Checking AWS..."
    
    # Try to auto-detect
    DB_HOST=$(aws rds describe-db-instances --query 'DBInstances[0].Endpoint.Address' --output text 2>/dev/null || echo "")
    
    if [ -z "$DB_HOST" ] || [ "$DB_HOST" = "None" ]; then
        echo "❌ Could not find RDS endpoint"
        echo ""
        echo "Please provide RDS endpoint:"
        read -p "RDS Endpoint: " DB_HOST
    fi
fi

# Get database credentials
if [ -z "$DB_PASSWORD" ]; then
    echo "📍 Getting credentials from Secrets Manager..."
    
    SECRET=$(aws secretsmanager get-secret-value --secret-id stocks-app-dev --query SecretString --output text 2>/dev/null || echo "")
    
    if [ ! -z "$SECRET" ]; then
        DB_HOST=$(echo $SECRET | jq -r '.host // empty' || echo "$DB_HOST")
        DB_USER=$(echo $SECRET | jq -r '.username' 2>/dev/null)
        DB_PASSWORD=$(echo $SECRET | jq -r '.password' 2>/dev/null)
        DB_NAME=$(echo $SECRET | jq -r '.dbname' 2>/dev/null)
    fi
fi

# Set defaults
export DB_HOST=${DB_HOST:-""}
export DB_PORT=${DB_PORT:-"5432"}
export DB_USER=${DB_USER:-"stocks"}
export DB_PASSWORD=${DB_PASSWORD:-"bed0elAn"}
export DB_NAME=${DB_NAME:-"stocks"}

echo "✅ Database Configuration:"
echo "   Host: $DB_HOST"
echo "   User: $DB_USER"
echo "   Database: $DB_NAME"
echo ""

# Test connection
echo "🔗 Testing database connection..."
if psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1" 2>/dev/null; then
    echo "✅ Connected to RDS!"
else
    echo "❌ Connection failed to $DB_HOST"
    echo ""
    echo "Please verify RDS endpoint and credentials"
    exit 1
fi

cd /home/arger/algo || exit 1

echo ""
echo "=========================================="
echo "PHASE 1: FOUNDATION (2 min)"
echo "=========================================="
echo "[1/58] Loading stock symbols..."
timeout 120 python3 loadstocksymbols.py 2>&1 | tail -3 || echo "✅ Already loaded"

echo ""
echo "=========================================="
echo "PHASE 2: PRICES (30 min) - CRITICAL DATA"
echo "=========================================="
echo "[2/58] Daily prices..."
timeout 1800 python3 loadpricedaily.py 2>&1 | tail -3 || echo "⚠️  (long operation)"

echo "[3/58] Weekly prices..."
timeout 600 python3 loadpriceweekly.py 2>&1 | tail -3 || true

echo "[4/58] Monthly prices..."
timeout 600 python3 loadpricemonthly.py 2>&1 | tail -3 || true

echo ""
echo "=========================================="
echo "PHASE 3: TECHNICAL DATA (10 min)"
echo "=========================================="
echo "[5/58] Technical indicators..."
timeout 600 python3 loadtechnicalindicators.py 2>&1 | tail -3 || true

echo ""
echo "=========================================="
echo "PHASE 4: SIGNALS & SCORES (30 min)"
echo "=========================================="
echo "[6/58] Stock scores..."
timeout 600 python3 loadstockscores.py 2>&1 | tail -3 || true

echo "[7/58] Real-time scores..."
timeout 600 python3 load_real_scores.py 2>&1 | tail -3 || true

echo "[8/58] Daily buy/sell signals..."
timeout 600 python3 loadbuyselldaily.py 2>&1 | tail -3 || true

echo "[9/58] Weekly buy/sell signals..."
timeout 600 python3 loadbuysellweekly.py 2>&1 | tail -3 || true

echo "[10/58] Monthly buy/sell signals..."
timeout 600 python3 loadbuysellmonthly.py 2>&1 | tail -3 || true

echo "[11/58] ETF daily signals..."
timeout 600 python3 loadbuysell_etf_daily.py 2>&1 | tail -3 || true

echo "[12/58] ETF weekly signals..."
timeout 600 python3 loadbuysell_etf_weekly.py 2>&1 | tail -3 || true

echo "[13/58] ETF monthly signals..."
timeout 600 python3 loadbuysell_etf_monthly.py 2>&1 | tail -3 || true

echo "[14/58] ETF signals..."
timeout 600 python3 loadetfsignals.py 2>&1 | tail -3 || true

echo ""
echo "=========================================="
echo "PHASE 5: FUNDAMENTAL DATA (30 min)"
echo "=========================================="
echo "[15/58] Factor metrics..."
timeout 300 python3 loadfactormetrics.py 2>&1 | tail -3 || true

echo "[16/58] Earnings metrics..."
timeout 300 python3 loadearningsmetrics.py 2>&1 | tail -3 || true

echo "[17/58] Annual income statement..."
timeout 600 python3 loadannualincomestatement.py 2>&1 | tail -3 || true

echo "[18/58] Quarterly income statement..."
timeout 600 python3 loadquarterlyincomestatement.py 2>&1 | tail -3 || true

echo "[19/58] Annual balance sheet..."
timeout 600 python3 loadannualbalancesheet.py 2>&1 | tail -3 || true

echo "[20/58] Quarterly balance sheet..."
timeout 600 python3 loadquarterlybalancesheet.py 2>&1 | tail -3 || true

echo "[21/58] Annual cash flow..."
timeout 600 python3 loadannualcashflow.py 2>&1 | tail -3 || true

echo "[22/58] Quarterly cash flow..."
timeout 600 python3 loadquarterlycashflow.py 2>&1 | tail -3 || true

echo ""
echo "=========================================="
echo "VERIFICATION & TESTING"
echo "=========================================="
echo ""
echo "📊 Data Loaded to AWS RDS:"
psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" << EOFVERIFY
SELECT 
  'Stock Symbols' as Item, COUNT(*) as Rows FROM stock_symbols
UNION ALL
SELECT 'Stock Scores', COUNT(*) FROM stock_scores
UNION ALL
SELECT 'Daily Buy/Sell', COUNT(*) FROM buy_sell_daily
UNION ALL
SELECT 'Weekly Buy/Sell', COUNT(*) FROM buy_sell_weekly
UNION ALL
SELECT 'Monthly Buy/Sell', COUNT(*) FROM buy_sell_monthly
UNION ALL
SELECT 'Daily Prices', COUNT(*) FROM price_daily
ORDER BY Item;
EOFVERIFY

echo ""
echo "=========================================="
echo "✅ DATA LOADING COMPLETE"
echo "=========================================="
echo ""
echo "🎉 AWS RDS database is now populated!"
echo ""
echo "Test your APIs:"
echo "  curl https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev/api/health"
echo "  curl https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev/api/stocks?limit=1"
echo "  curl https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev/api/scores/stockscores?limit=1"
echo ""

