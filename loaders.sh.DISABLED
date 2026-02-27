#!/bin/bash
# Master Data Loader Script - Runs all 58 loaders in optimal order
# Works locally or in AWS ECS
# Set DB_HOST, DB_USER, DB_PASSWORD, DB_NAME before running

set +e  # Don't exit on errors - log and continue

export DB_HOST=${DB_HOST:-"localhost"}
export DB_PORT=${DB_PORT:-"5432"}
export DB_USER=${DB_USER:-"stocks"}
export DB_PASSWORD=${DB_PASSWORD:-"bed0elAn"}
export DB_NAME=${DB_NAME:-"stocks"}

echo "=========================================="
echo "MASTER DATA LOADER"
echo "=========================================="
echo "Database: $DB_NAME @ $DB_HOST"
echo "User: $DB_USER"
echo ""

# Create log file
LOGFILE="/tmp/loaders_$(date +%Y%m%d_%H%M%S).log"
echo "Logging to: $LOGFILE"
echo ""

# Test connection
echo "Testing database connection..."
if ! psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1" 2>/dev/null; then
    echo "⚠️  Database not accessible at $DB_HOST"
    echo "Continuing anyway - some loaders may fail"
fi

cd /home/arger/algo || cd /algo || exit 1

# Priority 1: Foundation (must have)
echo "========== PHASE 1: FOUNDATION =========="
LOADERS=("loadstocksymbols")
for loader in "${LOADERS[@]}"; do
    echo "Running: $loader"
    timeout 120 python3 ${loader}.py >> "$LOGFILE" 2>&1
    if [ $? -eq 0 ]; then
        echo "✅ ${loader}"
    else
        echo "⚠️  ${loader} (check log)"
    fi
done

# Priority 2: Prices (critical)
echo ""
echo "========== PHASE 2: PRICES =========="
LOADERS=("loadpricedaily" "loadpriceweekly" "loadpricemonthly" "loadetfpricedaily" "loadetfpriceweekly" "loadetfpricemonthly")
for loader in "${LOADERS[@]}"; do
    echo "Running: $loader"
    timeout 1800 python3 ${loader}.py >> "$LOGFILE" 2>&1
    if [ $? -eq 0 ]; then
        echo "✅ ${loader}"
    else
        echo "⚠️  ${loader} (check log)"
    fi
done

# Priority 3: Technical & Scores
echo ""
echo "========== PHASE 3: TECHNICAL & SCORES =========="
LOADERS=("loadtechnicalindicators" "loadstockscores" "load_real_scores")
for loader in "${LOADERS[@]}"; do
    echo "Running: $loader"
    timeout 600 python3 ${loader}.py >> "$LOGFILE" 2>&1
    if [ $? -eq 0 ]; then
        echo "✅ ${loader}"
    else
        echo "⚠️  ${loader} (check log)"
    fi
done

# Priority 4: Trading Signals
echo ""
echo "========== PHASE 4: TRADING SIGNALS =========="
LOADERS=("loadbuyselldaily" "loadbuysellweekly" "loadbuysellmonthly" "loadbuysell_etf_daily" "loadbuysell_etf_weekly" "loadbuysell_etf_monthly" "loadetfsignals")
for loader in "${LOADERS[@]}"; do
    echo "Running: $loader"
    timeout 600 python3 ${loader}.py >> "$LOGFILE" 2>&1
    if [ $? -eq 0 ]; then
        echo "✅ ${loader}"
    else
        echo "⚠️  ${loader} (check log)"
    fi
done

# Priority 5: Financial Data
echo ""
echo "========== PHASE 5: FINANCIAL DATA =========="
LOADERS=("loadannualincomestatement" "loadquarterlyincomestatement" "loadannualbalancesheet" "loadquarterlybalancesheet" "loadannualcashflow" "loadquarterlycashflow" "loadttmincomestatement" "loadttmcashflow")
for loader in "${LOADERS[@]}"; do
    echo "Running: $loader"
    timeout 600 python3 ${loader}.py >> "$LOGFILE" 2>&1
    if [ $? -eq 0 ]; then
        echo "✅ ${loader}"
    else
        echo "⚠️  ${loader} (check log)"
    fi
done

# Priority 6: Metrics & Analysis
echo ""
echo "========== PHASE 6: METRICS & ANALYSIS =========="
LOADERS=("loadfactormetrics" "loadearningsmetrics" "loadearningshistory" "loadearningsrevisions" "loadearningssurprise" "loadanalystupgradedowngrade" "loadguidance" "loadaaiidata" "loaddailycompanydata" "loadmarket" "loadmarketindices" "loadindustryranking" "loadsectorranking" "loadsectors" "loadnaaim" "loadfeargreed")
for loader in "${LOADERS[@]}"; do
    echo "Running: $loader"
    timeout 600 python3 ${loader}.py >> "$LOGFILE" 2>&1
    if [ $? -eq 0 ]; then
        echo "✅ ${loader}"
    else
        echo "⚠️  ${loader} (check log)"
    fi
done

# Priority 7: Additional Data
echo ""
echo "========== PHASE 7: ADDITIONAL DATA =========="
LOADERS=("loadinsidertransactions" "loadsecfilings" "loadoptionschains" "loadcalendar" "loadcommodities" "loadbenchmark" "loadseasonality" "loadrelativeperformance" "loadsentiment" "loadanalystsentiment" "loadnews" "loadlatestpricedaily" "loadlatestpriceweekly" "loadlatestpricemonthly" "loadalpacaportfolio")
for loader in "${LOADERS[@]}"; do
    echo "Running: $loader"
    timeout 600 python3 ${loader}.py >> "$LOGFILE" 2>&1
    if [ $? -eq 0 ]; then
        echo "✅ ${loader}"
    else
        echo "⚠️  ${loader} (check log)"
    fi
done

echo ""
echo "=========================================="
echo "LOADING COMPLETE"
echo "=========================================="
echo ""
echo "📊 Results logged to: $LOGFILE"
echo ""
echo "Check log for errors:"
echo "  grep ERROR $LOGFILE"
echo ""

# Show summary
echo "Database Status:"
psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c "
SELECT 
  (SELECT COUNT(*) FROM stock_symbols) as symbols,
  (SELECT COUNT(*) FROM stock_scores) as scores,
  (SELECT COUNT(*) FROM price_daily) as daily_prices,
  (SELECT COUNT(*) FROM buy_sell_daily) as signals
" 2>/dev/null || echo "  Could not verify"

echo ""
echo "Log file: $LOGFILE"
