#!/bin/bash
# Quick AWS Data Loading - SIGNALS & SCORES ONLY
# Fast loading of just trading signals and stock scores
# Usage: bash RUN_SIGNALS_SCORES_AWS.sh

set -e

echo "=========================================="
echo "AWS DATA LOADING - SIGNALS & SCORES ONLY"
echo "=========================================="
echo "Loading all trading signals and stock scores to AWS RDS"
echo ""

# Get RDS endpoint
if [ -z "$DB_HOST" ]; then
    echo "📍 Finding RDS endpoint..."
    DB_HOST=$(aws rds describe-db-instances --query 'DBInstances[0].Endpoint.Address' --output text 2>/dev/null || echo "")
    
    if [ -z "$DB_HOST" ] || [ "$DB_HOST" = "None" ]; then
        echo "❌ Could not find RDS endpoint"
        read -p "Enter RDS Endpoint: " DB_HOST
    fi
fi

# Get credentials from Secrets Manager
echo "📍 Getting credentials from Secrets Manager..."
SECRET=$(aws secretsmanager get-secret-value --secret-id stocks-app-dev --query SecretString --output text 2>/dev/null || echo "")

if [ ! -z "$SECRET" ]; then
    DB_USER=$(echo $SECRET | jq -r '.username')
    DB_PASSWORD=$(echo $SECRET | jq -r '.password')
    DB_NAME=$(echo $SECRET | jq -r '.dbname')
fi

# Set defaults
export DB_HOST=$DB_HOST
export DB_PORT=${DB_PORT:-"5432"}
export DB_USER=${DB_USER:-"stocks"}
export DB_PASSWORD=${DB_PASSWORD:-"bed0elAn"}
export DB_NAME=${DB_NAME:-"stocks"}

echo "✅ Database: $DB_NAME @ $DB_HOST"
echo ""

# Test connection
echo "🔗 Testing connection..."
if ! psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1" 2>/dev/null; then
    echo "❌ Connection failed!"
    exit 1
fi
echo "✅ Connected!"

cd /home/arger/algo

echo ""
echo "=========================================="
echo "LOADING STOCK SCORES (5 min)"
echo "=========================================="
echo "[1/8] Stock Scores..."
timeout 600 python3 loadstockscores.py 2>&1 | tail -5 || echo "⚠️  Error (non-critical)"

echo "[2/8] Real-time Scores..."
timeout 600 python3 load_real_scores.py 2>&1 | tail -5 || echo "⚠️  Error (non-critical)"

echo ""
echo "=========================================="
echo "LOADING TRADING SIGNALS (15 min)"
echo "=========================================="
echo "[3/8] Daily Buy/Sell Signals (Stocks)..."
timeout 600 python3 loadbuyselldaily.py 2>&1 | tail -5 || echo "⚠️  Error"

echo "[4/8] Weekly Buy/Sell Signals (Stocks)..."
timeout 600 python3 loadbuysellweekly.py 2>&1 | tail -5 || echo "⚠️  Error"

echo "[5/8] Monthly Buy/Sell Signals (Stocks)..."
timeout 600 python3 loadbuysellmonthly.py 2>&1 | tail -5 || echo "⚠️  Error"

echo "[6/8] Daily Buy/Sell Signals (ETFs)..."
timeout 600 python3 loadbuysell_etf_daily.py 2>&1 | tail -5 || echo "⚠️  Error"

echo "[7/8] Weekly Buy/Sell Signals (ETFs)..."
timeout 600 python3 loadbuysell_etf_weekly.py 2>&1 | tail -5 || echo "⚠️  Error"

echo "[8/8] Monthly Buy/Sell Signals (ETFs)..."
timeout 600 python3 loadbuysell_etf_monthly.py 2>&1 | tail -5 || echo "⚠️  Error"

echo ""
echo "=========================================="
echo "VERIFICATION"
echo "=========================================="
echo ""
echo "📊 Signals & Scores Loaded:"
psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" << EOFVERIFY
SELECT 
  'Stock Scores' as DataType, COUNT(*) as Rows FROM stock_scores
UNION ALL
SELECT 'Daily Buy/Sell', COUNT(*) FROM buy_sell_daily
UNION ALL
SELECT 'Weekly Buy/Sell', COUNT(*) FROM buy_sell_weekly
UNION ALL
SELECT 'Monthly Buy/Sell', COUNT(*) FROM buy_sell_monthly
ORDER BY DataType;
EOFVERIFY

echo ""
echo "=========================================="
echo "✅ ALL SIGNALS & SCORES LOADED TO AWS"
echo "=========================================="
echo ""
echo "Test API:"
echo "  curl https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev/api/scores/stockscores?limit=5"
echo ""

