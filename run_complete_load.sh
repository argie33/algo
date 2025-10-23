#!/bin/bash
set -e

LOG_FILE="/home/stocks/algo/complete_load_$(date +%Y%m%d_%H%M%S).log"

echo "════════════════════════════════════════════════════════════"
echo "🚀 COMPLETE DATA LOAD SEQUENCE"
echo "════════════════════════════════════════════════════════════"
echo "Log: $LOG_FILE"
echo ""

# Step 1: Key Metrics (all 5,315 stocks)
echo "📊 STEP 1: Loading Key Metrics for 5,315 stocks"
echo "   This will take 30-60 minutes (with rate limiting)"
python3 loadkeymetrics_simple.py 2>&1 | tee -a "$LOG_FILE"

echo ""
echo "✓ Key Metrics Complete"
echo ""

# Step 2: Value Metrics (depends on key metrics)
echo "💰 STEP 2: Calculating Value Metrics"
python3 loadvaluemetrics.py 2>&1 | tee -a "$LOG_FILE"

echo ""
echo "✓ Value Metrics Complete"
echo ""

# Step 3: Stock Scores (final calculation with all data)
echo "⭐ STEP 3: Recalculating Stock Scores"
python3 loadstockscores.py 2>&1 | tee -a "$LOG_FILE"

echo ""
echo "════════════════════════════════════════════════════════════"
echo "✅ COMPLETE DATA LOAD FINISHED"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "Summary:"
psql -h localhost -U postgres -d stocks -c "
SELECT 
  'Key Metrics' as metric, COUNT(*) as count 
FROM key_metrics
UNION ALL
SELECT 
  'Value Inputs', COUNT(DISTINCT symbol)
FROM stock_scores 
WHERE value_inputs IS NOT NULL
UNION ALL
SELECT
  'Stock Scores',  COUNT(*)
FROM stock_scores;" 2>/dev/null

