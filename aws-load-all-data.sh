#!/bin/bash
# AWS Data Loading Script
# Runs all data loaders on AWS ECS for RDS database
# Triggered by GitHub Actions or manual deployment

set -e

echo "🚀 AWS Data Loading Script Started"
echo "Timestamp: $(date)"
echo ""

# Database configuration (from AWS Secrets Manager or environment)
export DB_HOST=${DB_HOST:-algo-db.us-east-1.rds.amazonaws.com}
export DB_PORT=${DB_PORT:-5432}
export DB_USER=${DB_USER:-stocks}
export DB_PASSWORD=${DB_PASSWORD:-}
export DB_NAME=${DB_NAME:-stocks}
export PGPASSWORD=$DB_PASSWORD

# Verify database connectivity
echo "📋 Verifying database connection..."
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT 'Database connected' as status;" 2>&1 || exit 1

echo "✅ Database connected successfully"
echo ""

# Array to track loaders
declare -a LOADERS=(
    "loadstocksymbols.py"
    "loadpricedaily.py"
    "loadpriceweekly.py"
    "loadpricemonthly.py"
    "loadtechnicalindicators.py"
    "loadbuyselldaily.py"
    "loadbuyselldaily.py"  # Run twice for better coverage
    "loadstockscores.py"
    "loadanalystsentiment.py"
    "loadanalystupgradedowngrade.py"
    "loadearningsmetrics.py"
    "loadearningsrevisions.py"
    "loadearningssurprise.py"
    "loadmarket.py"
    "loadsectors.py"
    "loadindustryranking.py"
)

echo "📊 Starting ${#LOADERS[@]} data loaders..."
echo ""

# Run loaders
success_count=0
fail_count=0

for loader in "${LOADERS[@]}"; do
    if [ -f "$loader" ]; then
        echo "🔄 Running: $loader"
        if timeout 600 python3 "$loader" 2>&1 | tail -5; then
            ((success_count++))
            echo "✅ $loader completed"
        else
            ((fail_count++))
            echo "⚠️  $loader encountered issues but continued"
        fi
        echo ""
    else
        echo "❌ Loader not found: $loader"
        ((fail_count++))
    fi
done

echo "════════════════════════════════════════════════════════════════"
echo "📊 DATA LOADING SUMMARY"
echo "════════════════════════════════════════════════════════════════"
echo "✅ Successful: $success_count loaders"
echo "⚠️  Issues: $fail_count loaders"
echo ""
echo "Final Data Count:"
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "
SELECT 'Stock Symbols' as metric, COUNT(*) FROM stock_symbols
UNION ALL SELECT 'Daily Prices', COUNT(*) FROM price_daily
UNION ALL SELECT 'Stock Scores', COUNT(*) FROM stock_scores
UNION ALL SELECT 'Buy/Sell Signals', COUNT(*) FROM buy_sell_daily
UNION ALL SELECT 'Technical Data', COUNT(*) FROM technical_data_daily
ORDER BY 1;
"

echo ""
echo "✅ AWS Data Loading Complete - $(date)"
