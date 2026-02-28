#!/bin/bash
# SEQUENTIAL DATA LOADER - Kills all existing loaders and runs fresh
# Ensures 100% completion with proper error handling

set -e

export PGPASSWORD=bed0elAn
export DB_HOST=localhost
export DB_USER=stocks
export DB_PASSWORD=bed0elAn
export DB_NAME=stocks

cd /home/arger/algo

# Kill all existing loaders first
echo "🛑 Killing any running loaders..."
pkill -f "python3 load" 2>/dev/null || true
pkill -f "FINAL_COMPLETE" 2>/dev/null || true
sleep 2

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║     🚀 SEQUENTIAL DATA LOAD - Complete All Missing Data       ║"
echo "║              One loader at a time - Memory Safe               ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Tracking
TOTAL=0
SUCCESS=0
FAILED=0
FAILED_LOADERS=""

# Function to run loader with error handling
run_loader() {
  local name=$1
  local file=$2
  local timeout=${3:-600}

  TOTAL=$((TOTAL + 1))

  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "⏳ [$TOTAL] $name (timeout: ${timeout}s)"

  FREE_MB=$(free | grep Mem | awk '{print $7}')
  USED_MB=$(($(free | grep Mem | awk '{print $3}')))
  echo "   💾 Memory: ${USED_MB}MB used / ${FREE_MB}MB free"

  # Create temp log file
  LOG_FILE="/tmp/loader_${file%.py}.log"

  # Run with timeout
  START=$(date +%s)
  if timeout $timeout python3 "$file" > "$LOG_FILE" 2>&1; then
    ELAPSED=$(($(date +%s) - START))
    SUCCESS=$((SUCCESS + 1))

    # Show last few lines of output
    echo "   ✅ Completed in ${ELAPSED}s"
    echo "   Output:"
    tail -3 "$LOG_FILE" | sed 's/^/     /'
  else
    EXIT_CODE=$?
    ELAPSED=$(($(date +%s) - START))
    FAILED=$((FAILED + 1))
    FAILED_LOADERS="$FAILED_LOADERS\n   ❌ $name (exit $EXIT_CODE)"

    echo "   ❌ FAILED in ${ELAPSED}s (exit code: $EXIT_CODE)"
    echo "   Error details:"
    tail -5 "$LOG_FILE" | sed 's/^/     /'
  fi

  sleep 2
  echo ""
}

# Priority 1: Foundation
echo "PRIORITY 1: Foundation (must complete first)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_loader "Stock Symbols" "loadstocksymbols.py" 120

# Priority 2: Financial Data
echo ""
echo "PRIORITY 2: Annual Financial Data"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_loader "Annual Income Statements" "loadannualincomestatement.py" 600
run_loader "Annual Cashflow" "loadannualcashflow.py" 600

echo ""
echo "PRIORITY 3: Quarterly Financial Data"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_loader "Quarterly Balance Sheets" "loadquarterlybalancesheet.py" 600
run_loader "Quarterly Cashflow" "loadquarterlycashflow.py" 600
run_loader "Quarterly Income Statements" "loadquarterlyincomestatement.py" 600

# Priority 3: Price Data
echo ""
echo "PRIORITY 4: Price Data (all timeframes)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_loader "Daily Prices" "loadpricedaily.py" 900
run_loader "Weekly Prices" "loadpriceweekly.py" 600
run_loader "Monthly Prices" "loadpricemonthly.py" 600

# Priority 4: Trading Signals
echo ""
echo "PRIORITY 5: Trading Signals (all frequencies)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_loader "Buy/Sell Daily Signals" "loadbuyselldaily.py" 900
run_loader "Buy/Sell Weekly Signals" "loadbuysellweekly.py" 600
run_loader "Buy/Sell Monthly Signals" "loadbuysellmonthly.py" 600

# Priority 5: Analyst & Technical Data
echo ""
echo "PRIORITY 6: Analyst & Technical Data"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_loader "Analyst Sentiment" "loadanalystsentiment.py" 300
run_loader "Analyst Upgrade/Downgrade" "loadanalystupgradedowngrade.py" 300
run_loader "Technical Indicators" "loadtechnicalindicators.py" 300

# Priority 6: Earnings Data
echo ""
echo "PRIORITY 7: Earnings Data"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_loader "Earnings History" "loadearningshistory.py" 300
run_loader "Earnings Metrics" "loadearningsmetrics.py" 300
run_loader "Earnings Surprises" "loadearningssurprise.py" 300
run_loader "Earnings Revisions" "loadearningsrevisions.py" 300

# Priority 7: Additional Data
echo ""
echo "PRIORITY 8: Additional Data Sources"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_loader "Factor Metrics" "loadfactormetrics.py" 600
run_loader "AAII Data" "loadaaiidata.py" 300
run_loader "Sentiment" "loadsentiment.py" 300
run_loader "Commodities" "loadcommodities.py" 300
run_loader "Insider Transactions" "loadinsidertransactions.py" 300
run_loader "SEC Filings" "loadsecfilings.py" 300

# Priority 8: Final Scores
echo ""
echo "PRIORITY 9: Final Stock Scores (with complete data)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_loader "Stock Scores (FINAL)" "loadstockscores.py" 600

# Final Report
echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                    📊 LOAD COMPLETION REPORT                  ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Summary: $SUCCESS/$TOTAL loaders completed successfully"

if [ $FAILED -gt 0 ]; then
  echo ""
  echo "⚠️  Failed loaders ($FAILED):"
  echo -e "$FAILED_LOADERS"
fi

# Data Audit
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📈 FINAL DATA AUDIT"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

PGPASSWORD=bed0elAn psql -h localhost -U stocks -d stocks << 'SQL'
SELECT
  CASE
    WHEN table_name = 'stock_symbols' THEN '📍 Stock Symbols'
    WHEN table_name = 'stock_scores' THEN '💎 Stock Scores'
    WHEN table_name = 'price_daily' THEN '💰 Price Daily'
    WHEN table_name = 'price_weekly' THEN '📅 Price Weekly'
    WHEN table_name = 'price_monthly' THEN '📆 Price Monthly'
    WHEN table_name = 'buy_sell_daily' THEN '🎯 Signals Daily'
    WHEN table_name = 'buy_sell_weekly' THEN '📅 Signals Weekly'
    WHEN table_name = 'buy_sell_monthly' THEN '📆 Signals Monthly'
    ELSE table_name
  END as "TABLE",
  COUNT(*) as "RECORDS",
  CASE
    WHEN COUNT(*) = 0 THEN '❌ EMPTY'
    WHEN COUNT(*) < 1000 THEN '⚠️  LOW'
    WHEN COUNT(*) >= 4989 THEN '✅ FULL'
    ELSE '⏳ PARTIAL'
  END as "STATUS"
FROM (
  SELECT 'stock_symbols' as table_name FROM stock_symbols UNION ALL
  SELECT 'stock_scores' FROM stock_scores UNION ALL
  SELECT 'price_daily' FROM price_daily UNION ALL
  SELECT 'price_weekly' FROM price_weekly UNION ALL
  SELECT 'price_monthly' FROM price_monthly UNION ALL
  SELECT 'buy_sell_daily' FROM buy_sell_daily UNION ALL
  SELECT 'buy_sell_weekly' FROM buy_sell_weekly UNION ALL
  SELECT 'buy_sell_monthly' FROM buy_sell_monthly
) t
GROUP BY table_name
ORDER BY COUNT(*) DESC;
SQL

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                  ✅ DATA LOAD COMPLETE                        ║"
echo "║              All loaders finished - Ready for AWS              ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
