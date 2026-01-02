#!/bin/bash
# Critical Data Loaders - Run in Correct Order
# This script loads the minimum required data for stock scoring

set -e  # Exit on error

echo "=========================================="
echo "Critical Data Loading Script"
echo "=========================================="
echo "Date: $(date)"
echo ""

# Check database connection
echo "Checking database connection..."
if ! psql -h localhost -U stocks -d stocks -c "SELECT 1;" > /dev/null 2>&1; then
    echo "❌ ERROR: Cannot connect to database"
    echo "   Make sure PostgreSQL is running and credentials are correct"
    exit 1
fi
echo "✅ Database connection successful"
echo ""

# Function to check table row count
check_table() {
    local table=$1
    local count=$(psql -h localhost -U stocks -d stocks -t -c "SELECT COUNT(*) FROM $table;" 2>/dev/null | tr -d ' ')
    echo "  $table: $count rows"
}

# Show current state
echo "=========================================="
echo "Current Database State (BEFORE)"
echo "=========================================="
check_table "stock_symbols"
check_table "company_profile"
check_table "earnings"
check_table "stock_scores"
check_table "price_daily"
echo ""

# Step 1: Load company data + earnings
echo "=========================================="
echo "Step 1: Loading Company Data + Earnings"
echo "=========================================="
echo "Loader: loaddailycompanydata.py"
echo "Estimated time: 45-90 minutes"
echo "API calls: ~5,300 (one per stock)"
echo ""
read -p "Press ENTER to start or Ctrl+C to cancel..."

echo ""
echo "🚀 Starting loaddailycompanydata.py..."
python3 loaddailycompanydata.py

if [ $? -eq 0 ]; then
    echo "✅ loaddailycompanydata.py completed successfully"
else
    echo "❌ loaddailycompanydata.py failed"
    exit 1
fi
echo ""

# Verify earnings loaded
echo "Verifying earnings data..."
EARNINGS_COUNT=$(psql -h localhost -U stocks -d stocks -t -c "SELECT COUNT(*) FROM earnings;" | tr -d ' ')
echo "Earnings rows: $EARNINGS_COUNT"

if [ "$EARNINGS_COUNT" -lt "10000" ]; then
    echo "⚠️  WARNING: Expected > 50,000 earnings rows, got $EARNINGS_COUNT"
    echo "   This may indicate incomplete data load"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "✅ Earnings data loaded successfully"
fi
echo ""

# Step 2: Calculate stock scores
echo "=========================================="
echo "Step 2: Calculating Stock Scores"
echo "=========================================="
echo "Loader: loadstockscores.py"
echo "Estimated time: 10-20 minutes"
echo "Dependencies: earnings, factor_metrics, price_daily"
echo ""
read -p "Press ENTER to start or Ctrl+C to cancel..."

echo ""
echo "🚀 Starting loadstockscores.py..."
python3 loadstockscores.py

if [ $? -eq 0 ]; then
    echo "✅ loadstockscores.py completed successfully"
else
    echo "❌ loadstockscores.py failed"
    exit 1
fi
echo ""

# Final verification
echo "=========================================="
echo "Final Database State (AFTER)"
echo "=========================================="
check_table "stock_symbols"
check_table "company_profile"
check_table "earnings"
check_table "stock_scores"
check_table "price_daily"
echo ""

# Detailed stock_scores stats
echo "=========================================="
echo "Stock Scores Statistics"
echo "=========================================="
psql -h localhost -U stocks -d stocks -c "
SELECT
  COUNT(*) as total_scores,
  COUNT(*) FILTER (WHERE composite_score IS NOT NULL) as with_composite,
  COUNT(*) FILTER (WHERE value_score IS NOT NULL) as with_value,
  COUNT(*) FILTER (WHERE quality_score IS NOT NULL) as with_quality,
  COUNT(*) FILTER (WHERE momentum_score IS NOT NULL) as with_momentum,
  ROUND(AVG(composite_score), 2) as avg_composite,
  ROUND(AVG(value_score), 2) as avg_value
FROM stock_scores;
"
echo ""

# Check for missing scores
echo "=========================================="
echo "Stocks Missing Scores (if any)"
echo "=========================================="
psql -h localhost -U stocks -d stocks -c "
SELECT symbol, sector,
       composite_score IS NULL as missing_composite,
       value_score IS NULL as missing_value
FROM stock_scores
WHERE composite_score IS NULL
LIMIT 10;
"
echo ""

echo "=========================================="
echo "✅ Data Loading Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Review the statistics above"
echo "2. Check DATA_LOADING_PLAN.md for verification queries"
echo "3. Run your custom scoring script (after adapting for PostgreSQL)"
echo ""
echo "Note: If you see missing scores, check the logs for errors"
echo "      Some stocks may legitimately have no scores due to missing data"
echo ""
