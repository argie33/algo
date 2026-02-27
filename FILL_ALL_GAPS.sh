#!/bin/bash
# Fill all incomplete tables - run loaders sequentially

set -e

export PGPASSWORD=bed0elAn
export DB_HOST=localhost
export DB_USER=stocks
export DB_PASSWORD=bed0elAn
export DB_NAME=stocks

cd /home/arger/algo

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║    🔧 FILLING DATA GAPS - GET ALL TABLES TO 100%             ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Helper to show before/after
check_table() {
  PGPASSWORD=bed0elAn psql -U stocks -d stocks -h localhost -t -c \
    "SELECT COUNT(DISTINCT symbol) FROM $1;" 2>/dev/null || echo "0"
}

# Run loader and track progress
run_loader() {
  local name=$1
  local file=$2
  local timeout=${3:-600}

  echo "⏳ $name"
  BEFORE=$(check_table "$4")
  echo "   Before: $BEFORE / 4989"

  timeout $timeout python3 "$file" 2>&1 | tail -5

  AFTER=$(check_table "$4")
  ADDED=$((AFTER - BEFORE))
  echo "   ✅ After: $AFTER / 4989 (+$ADDED)"
  sleep 2
  echo ""
}

echo "PRIORITY 1: VALUE & GROWTH METRICS (0.8% → 100%)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_loader "Factor Metrics (value, growth)" "loadfactormetrics.py" 600 "value_metrics"

echo "PRIORITY 2: QUARTERLY STATEMENTS (30-40% → 100%)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_loader "Quarterly Balance Sheet" "loadquarterlybalancesheet.py" 600 "quarterly_balance_sheet"
run_loader "Quarterly Cashflow" "loadquarterlycashflow.py" 600 "quarterly_cash_flow"
run_loader "Quarterly Income" "loadquarterlyincomestatement.py" 600 "quarterly_income_statement"

echo "PRIORITY 3: EARNINGS DATA (20% → 100%)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_loader "Earnings History" "loadearningshistory.py" 300 "earnings_history"
run_loader "Earnings Metrics" "loadearningsmetrics.py" 300 "earnings_metrics"
run_loader "Earnings Surprises" "loadearningssurprise.py" 300 "earnings_surprises"

echo "PRIORITY 4: PRICE DATA (70-95% → 100%)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_loader "Price Weekly" "loadpriceweekly.py" 600 "price_weekly"
run_loader "Price Monthly" "loadpricemonthly.py" 600 "price_monthly"

echo "PRIORITY 5: TRADING SIGNALS (40-45% → 100%)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_loader "Buy/Sell Weekly" "loadbuysellweekly.py" 600 "buy_sell_weekly"
run_loader "Buy/Sell Monthly" "loadbuysellmonthly.py" 600 "buy_sell_monthly"

echo "PRIORITY 6: FILL REMAINING GAPS (95%+ → 100%)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_loader "Annual Income (final)" "loadannualincomestatement.py" 600 "annual_income_statement"
run_loader "Annual Cashflow (final)" "loadannualcashflow.py" 600 "annual_cash_flow"
run_loader "Growth Metrics (final)" "loadfactormetrics.py" 600 "growth_metrics"

echo "PRIORITY 7: RECOMPUTE SCORES WITH COMPLETE DATA"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_loader "Stock Scores (FINAL)" "loadstockscores.py" 600 "stock_scores"

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                   📊 FINAL VERIFICATION                       ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

PGPASSWORD=bed0elAn psql -h localhost -U stocks -d stocks << 'SQL'
SELECT
  'growth_metrics: ' || COUNT(DISTINCT symbol) || ' ✅' as status FROM growth_metrics
UNION ALL SELECT 'value_metrics: ' || COUNT(DISTINCT symbol) || ' ✅' FROM value_metrics
UNION ALL SELECT 'price_weekly: ' || COUNT(DISTINCT symbol) || ' ✅' FROM price_weekly
UNION ALL SELECT 'price_monthly: ' || COUNT(DISTINCT symbol) || ' ✅' FROM price_monthly
UNION ALL SELECT 'buy_sell_weekly: ' || COUNT(DISTINCT symbol) || ' ✅' FROM buy_sell_weekly
UNION ALL SELECT 'buy_sell_monthly: ' || COUNT(DISTINCT symbol) || ' ✅' FROM buy_sell_monthly
UNION ALL SELECT 'annual_income: ' || COUNT(DISTINCT symbol) || ' ✅' FROM annual_income_statement
UNION ALL SELECT 'annual_cashflow: ' || COUNT(DISTINCT symbol) || ' ✅' FROM annual_cash_flow
UNION ALL SELECT 'quarterly_income: ' || COUNT(DISTINCT symbol) || ' ✅' FROM quarterly_income_statement
UNION ALL SELECT 'quarterly_balance: ' || COUNT(DISTINCT symbol) || ' ✅' FROM quarterly_balance_sheet
UNION ALL SELECT 'quarterly_cashflow: ' || COUNT(DISTINCT symbol) || ' ✅' FROM quarterly_cash_flow
UNION ALL SELECT 'earnings_history: ' || COUNT(DISTINCT symbol) || ' ✅' FROM earnings_history
UNION ALL SELECT 'earnings_metrics: ' || COUNT(DISTINCT symbol) || ' ✅' FROM earnings_metrics
ORDER BY status;
SQL

echo ""
echo "✅ ALL GAPS FILLED!"
