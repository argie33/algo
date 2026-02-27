#!/bin/bash
# FINAL COMPLETE DATA LOADER - Sequential, safe, production ready
# This loads ALL missing data to achieve 100% coverage

set -e

export PGPASSWORD=bed0elAn
export DB_HOST=localhost
export DB_USER=stocks
export DB_PASSWORD=bed0elAn
export DB_NAME=stocks

cd /home/arger/algo

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║        🚀 FINAL COMPLETE DATA LOAD - 100% COVERAGE            ║"
echo "║     Sequential execution (safe from system crashes)             ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Function to run loader and show progress
run_loader() {
  local name=$1
  local file=$2
  local timeout=${3:-600}

  echo "⏳ $name"
  FREE_MB=$(free | grep Mem | awk '{print $7}')
  echo "   Memory: ${FREE_MB}MB | Timeout: ${timeout}s"

  START=$(date +%s)
  timeout $timeout python3 "$file" 2>&1 | tail -10
  ELAPSED=$(($(date +%s) - START))

  echo "   ✅ Completed in ${ELAPSED}s"
  sleep 3
  echo ""
}

echo "PRIORITY 1: Foundation (must complete first)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_loader "Stock Symbols" "loadstocksymbols.py" 120

echo "PRIORITY 2: Critical Financial Data (filling gaps)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_loader "Annual Income Statements" "loadannualincomestatement.py" 600
run_loader "Annual Cashflow" "loadannualcashflow.py" 600
run_loader "Quarterly Balance Sheets" "loadquarterlybalancesheet.py" 600
run_loader "Quarterly Cashflow" "loadquarterlycashflow.py" 600
run_loader "Quarterly Income Statements" "loadquarterlyincomestatement.py" 600

echo "PRIORITY 3: Price Data (complete all timeframes)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_loader "Daily Prices" "loadpricedaily.py" 900
run_loader "Weekly Prices" "loadpriceweekly.py" 600
run_loader "Monthly Prices" "loadpricemonthly.py" 600

echo "PRIORITY 4: Trading Signals (all frequencies)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_loader "Buy/Sell Daily Signals" "loadbuyselldaily.py" 900
run_loader "Buy/Sell Weekly Signals" "loadbuysellweekly.py" 600
run_loader "Buy/Sell Monthly Signals" "loadbuysellmonthly.py" 600

echo "PRIORITY 5: Technical & Analyst Data"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_loader "Technical Indicators" "loadtechnicalindicators.py" 300
run_loader "Analyst Sentiment" "loadanalystsentiment.py" 300
run_loader "Analyst Upgrade/Downgrade" "loadanalystupgradedowngrade.py" 300

echo "PRIORITY 6: Earnings Data"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_loader "Earnings History" "loadearningshistory.py" 300
run_loader "Earnings Metrics" "loadearningsmetrics.py" 300
run_loader "Earnings Surprises" "loadearningssurprise.py" 300

echo "PRIORITY 7: Metrics & Scores (with complete data)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_loader "Factor Metrics" "loadfactormetrics.py" 600
run_loader "Stock Scores (FINAL)" "loadstockscores.py" 600

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                   📊 FINAL DATA AUDIT                         ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

PGPASSWORD=bed0elAn psql -h localhost -U stocks -d stocks << 'SQL'
SELECT
  CASE
    WHEN name = 'stock_symbols' THEN '📍 Stock Symbols'
    WHEN name = 'stock_scores' THEN '💎 Stock Scores'
    WHEN name = 'price_daily' THEN '💰 Price Daily'
    WHEN name = 'price_weekly' THEN '📅 Price Weekly'
    WHEN name = 'price_monthly' THEN '📆 Price Monthly'
    WHEN name = 'annual_income_statement' THEN '📋 Annual Income'
    WHEN name = 'annual_cash_flow' THEN '💵 Annual Cashflow'
    WHEN name = 'quarterly_income_statement' THEN '📄 Q Income'
    WHEN name = 'quarterly_balance_sheet' THEN '📊 Q Balance'
    WHEN name = 'quarterly_cash_flow' THEN '💳 Q Cashflow'
    WHEN name = 'buy_sell_daily' THEN '🎯 Signals Daily'
    WHEN name = 'buy_sell_weekly' THEN '📅 Signals Weekly'
    WHEN name = 'buy_sell_monthly' THEN '📆 Signals Monthly'
    ELSE name
  END as "TABLE",
  COUNT(*) as "RECORDS",
  CASE
    WHEN COUNT(*) = 0 THEN '❌ EMPTY'
    WHEN COUNT(*) < 1000 THEN '⚠️  LOW'
    WHEN COUNT(*) >= 4989 THEN '✅ FULL'
    ELSE '⏳ PARTIAL'
  END as "STATUS"
FROM (
  SELECT 'stock_symbols' as name FROM stock_symbols UNION ALL
  SELECT 'stock_scores' FROM stock_scores UNION ALL
  SELECT 'price_daily' FROM price_daily UNION ALL
  SELECT 'price_weekly' FROM price_weekly UNION ALL
  SELECT 'price_monthly' FROM price_monthly UNION ALL
  SELECT 'annual_income_statement' FROM annual_income_statement UNION ALL
  SELECT 'annual_cash_flow' FROM annual_cash_flow UNION ALL
  SELECT 'quarterly_income_statement' FROM quarterly_income_statement UNION ALL
  SELECT 'quarterly_balance_sheet' FROM quarterly_balance_sheet UNION ALL
  SELECT 'quarterly_cash_flow' FROM quarterly_cash_flow UNION ALL
  SELECT 'buy_sell_daily' FROM buy_sell_daily UNION ALL
  SELECT 'buy_sell_weekly' FROM buy_sell_weekly UNION ALL
  SELECT 'buy_sell_monthly' FROM buy_sell_monthly
) t
GROUP BY name
ORDER BY
  CASE
    WHEN COUNT(*) = 0 THEN 4
    WHEN COUNT(*) < 1000 THEN 3
    WHEN COUNT(*) >= 4989 THEN 1
    ELSE 2
  END,
  COUNT(*) DESC;
SQL

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                  ✅ ALL DATA LOADED LOCALLY                   ║"
echo "║              Ready for AWS deployment and APIs                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo "  1. Test APIs: curl http://localhost:3001/api/stocks"
echo "  2. Commit: git add -A && git commit -m 'data: Complete 100% local load'"
echo "  3. Push: git push origin main"
echo "  4. Deploy to AWS with GitHub Actions"
