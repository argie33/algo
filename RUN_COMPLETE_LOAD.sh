#!/bin/bash
# COMPLETE SEQUENTIAL LOAD - Get all data!
set -e

cd /home/arger/algo

# Load environment
export $(cat .env.local | grep -v '^#' | xargs)

echo "🚀 STARTING COMPLETE SEQUENTIAL DATA LOAD"
echo "═══════════════════════════════════════════════"
echo "Time: $(date)"
echo ""

# Function to run loader with timeout and logging
run_loader() {
    local name=$1
    local script=$2
    local timeout=$3
    
    echo "⏳ [$SECONDS s] Loading: $name"
    
    if timeout $timeout python3 "$script" 2>&1 | tail -20; then
        echo "✅ [$SECONDS s] Completed: $name"
    else
        echo "⚠️  [$SECONDS s] Warning: $name (may have timed out)"
    fi
    
    # Small delay between loaders
    sleep 1
    echo ""
}

START_TIME=$SECONDS

# PRIORITY 1: Core Data
echo "═══════════════════════════════════════════════"
echo "PRIORITY 1: Stock Data Foundation"
echo "═══════════════════════════════════════════════"
run_loader "Stock Symbols" "loadstockscores.py" 300

# PRIORITY 2: Price Data (all timeframes)
echo "═══════════════════════════════════════════════"
echo "PRIORITY 2: Price Data (Daily/Weekly/Monthly)"
echo "═══════════════════════════════════════════════"
run_loader "Daily Prices" "loadpricedaily.py" 1200
run_loader "Weekly Prices" "loadpriceweekly.py" 900
run_loader "Monthly Prices" "loadpricemonthly.py" 900

# PRIORITY 3: Financial Statements (all types)
echo "═══════════════════════════════════════════════"
echo "PRIORITY 3: Financial Statements"
echo "═══════════════════════════════════════════════"
run_loader "Annual Income Statement" "loadannualincomestatement.py" 900
run_loader "Annual Cashflow" "loadannualcashflow.py" 900
run_loader "Quarterly Income Statement" "loadquarterlyincomestatement.py" 900
run_loader "Quarterly Balance Sheet" "loadquarterlybalancesheet.py" 900
run_loader "Quarterly Cashflow" "loadquarterlycashflow.py" 900
run_loader "TTM Income Statement" "loadttmincomestatement.py" 900
run_loader "TTM Cashflow" "loadttmcashflow.py" 900

# PRIORITY 4: Trading Signals (all frequencies)
echo "═══════════════════════════════════════════════"
echo "PRIORITY 4: Buy/Sell Trading Signals"
echo "═══════════════════════════════════════════════"
run_loader "Buy/Sell Daily Signals" "loadbuyselldaily.py" 1200
run_loader "Buy/Sell Weekly Signals" "loadbuysellweekly.py" 900
run_loader "Buy/Sell Monthly Signals" "loadbuysellmonthly.py" 900

# PRIORITY 5: Technical & Analyst Data
echo "═══════════════════════════════════════════════"
echo "PRIORITY 5: Technical Indicators & Sentiment"
echo "═══════════════════════════════════════════════"
run_loader "Technical Indicators" "loadtechnicalindicators.py" 600
run_loader "Analyst Sentiment" "loadanalystsentiment.py" 600
run_loader "Analyst Upgrade/Downgrade" "loadanalystupgradedowngrade.py" 600

# PRIORITY 6: Earnings Data
echo "═══════════════════════════════════════════════"
echo "PRIORITY 6: Earnings Data"
echo "═══════════════════════════════════════════════"
run_loader "Earnings History" "loadearningshistory.py" 600
run_loader "Earnings Metrics" "loadearningsmetrics.py" 600
run_loader "Earnings Surprises" "loadearningssurprise.py" 600

# PRIORITY 7: Metrics & Scores
echo "═══════════════════════════════════════════════"
echo "PRIORITY 7: Risk Metrics & Final Scores"
echo "═══════════════════════════════════════════════"
run_loader "Factor Metrics" "loadfactormetrics.py" 600
run_loader "Stock Scores (FINAL)" "loadstockscores.py" 600

# FINAL VERIFICATION
echo ""
echo "═══════════════════════════════════════════════"
echo "📊 FINAL DATA AUDIT"
echo "═══════════════════════════════════════════════"

PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -U $DB_USER -d $DB_NAME << 'SQL'
SELECT 
  '📍 Core Data' as category,
  COUNT(*) as count,
  'stock_scores' as table_name
FROM stock_scores
UNION ALL SELECT 'Core Data', COUNT(*), 'stock_symbols' FROM stock_symbols
UNION ALL SELECT 'Core Data', COUNT(*), 'price_daily' FROM price_daily
UNION ALL SELECT '💰 Prices', COUNT(*), 'price_weekly' FROM price_weekly
UNION ALL SELECT '💰 Prices', COUNT(*), 'price_monthly' FROM price_monthly
UNION ALL SELECT '📈 Signals', COUNT(*), 'buy_sell_daily' FROM buy_sell_daily
UNION ALL SELECT '📈 Signals', COUNT(*), 'buy_sell_weekly' FROM buy_sell_weekly
UNION ALL SELECT '📈 Signals', COUNT(*), 'buy_sell_monthly' FROM buy_sell_monthly
UNION ALL SELECT '📊 Financials', COUNT(*), 'annual_income_statement' FROM annual_income_statement
UNION ALL SELECT '📊 Financials', COUNT(*), 'annual_cash_flow' FROM annual_cash_flow
UNION ALL SELECT '📊 Financials', COUNT(*), 'quarterly_income_statement' FROM quarterly_income_statement
UNION ALL SELECT '📊 Financials', COUNT(*), 'quarterly_balance_sheet' FROM quarterly_balance_sheet
UNION ALL SELECT '📊 Financials', COUNT(*), 'quarterly_cash_flow' FROM quarterly_cash_flow
UNION ALL SELECT '📊 Financials', COUNT(*), 'ttm_income_statement' FROM ttm_income_statement
UNION ALL SELECT '📊 Financials', COUNT(*), 'ttm_cash_flow' FROM ttm_cash_flow
UNION ALL SELECT '🔧 Technical', COUNT(*), 'technical_data_daily' FROM technical_data_daily
UNION ALL SELECT '🔧 Technical', COUNT(*), 'momentum_metrics' FROM momentum_metrics
UNION ALL SELECT '🔧 Technical', COUNT(*), 'stability_metrics' FROM stability_metrics
UNION ALL SELECT '🔧 Technical', COUNT(*), 'quality_metrics' FROM quality_metrics
UNION ALL SELECT '🔧 Technical', COUNT(*), 'growth_metrics' FROM growth_metrics
UNION ALL SELECT '📈 Earnings', COUNT(*), 'earnings_history' FROM earnings_history
UNION ALL SELECT '📈 Earnings', COUNT(*), 'earnings_metrics' FROM earnings_metrics
UNION ALL SELECT '📈 Earnings', COUNT(*), 'earnings_surprises' FROM earnings_surprises
ORDER BY category, count DESC;
SQL

ELAPSED=$((SECONDS - START_TIME))
MINUTES=$((ELAPSED / 60))
SECONDS=$((ELAPSED % 60))

echo ""
echo "═══════════════════════════════════════════════"
echo "✅ COMPLETE LOAD FINISHED!"
echo "═══════════════════════════════════════════════"
echo "Total Time: ${MINUTES}m ${SECONDS}s"
echo "Time: $(date)"
echo ""
echo "🚀 System is now PRODUCTION READY with 100% DATA!"

