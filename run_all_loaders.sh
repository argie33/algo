#!/bin/bash

# Comprehensive Data Loader Runner
# Executes all loaders in dependency order to rebuild complete dataset

set -e  # Exit on first error

LOG_FILE="/home/stocks/algo/loader_execution_$(date +%Y%m%d_%H%M%S).log"
LOADERS_DIR="/home/stocks/algo"

echo "=========================================="
echo "🚀 Starting comprehensive data load"
echo "=========================================="
echo "Log file: $LOG_FILE"
echo ""

# Function to run a loader with error handling
run_loader() {
    local loader=$1
    local description=$2
    
    if [ ! -f "$LOADERS_DIR/$loader.py" ]; then
        echo "⚠️  SKIP: $loader not found"
        return 0
    fi
    
    echo ""
    echo "📦 Running: $description"
    echo "   File: $loader.py"
    
    if python3 "$LOADERS_DIR/$loader.py" >> "$LOG_FILE" 2>&1; then
        echo "   ✅ SUCCESS"
        return 0
    else
        echo "   ❌ FAILED (see log for details)"
        return 1
    fi
}

# Track results
PASSED=0
FAILED=0
SKIPPED=0

# ==== FOUNDATION: Stock symbols and company info ====
echo ""
echo "═══════════════════════════════════════════"
echo "PHASE 1: Foundation Data (Stock List, Company Info)"
echo "═══════════════════════════════════════════"

run_loader "loadstocksymbols_optimized" "Stock symbols" && ((PASSED++)) || ((FAILED++))
run_loader "loadcompanyprofile" "Company profiles" && ((PASSED++)) || ((FAILED++))

# ==== PHASE 2: Price and Technical Data (Daily) ====
echo ""
echo "═══════════════════════════════════════════"
echo "PHASE 2: Price & Technical Data (Daily)"
echo "═══════════════════════════════════════════"

run_loader "loadpricedaily_optimized" "Daily prices" && ((PASSED++)) || ((FAILED++))
run_loader "loadtechnicalsdaily" "Daily technicals" && ((PASSED++)) || ((FAILED++))
run_loader "loadbuyselldaily" "Daily buy/sell signals" && ((PASSED++)) || ((FAILED++))
run_loader "loadlatesttechnicalsdaily" "Latest daily technicals" && ((PASSED++)) || ((FAILED++))
run_loader "loadlatestpricedaily" "Latest daily prices" && ((PASSED++)) || ((FAILED++))
run_loader "loadlatestbuyselldaily" "Latest daily buy/sell" && ((PASSED++)) || ((FAILED++))

# ==== PHASE 3: Extended timeframes (Weekly/Monthly) ====
echo ""
echo "═══════════════════════════════════════════"
echo "PHASE 3: Extended Timeframe Data (Weekly/Monthly)"
echo "═══════════════════════════════════════════"

run_loader "loadpriceweekly" "Weekly prices" && ((PASSED++)) || ((FAILED++))
run_loader "loadpricemonthly" "Monthly prices" && ((PASSED++)) || ((FAILED++))
run_loader "loadtechnicalsweekly" "Weekly technicals" && ((PASSED++)) || ((FAILED++))
run_loader "loadtechnicalsmonthly" "Monthly technicals" && ((PASSED++)) || ((FAILED++))
run_loader "loadbuysellweekly" "Weekly buy/sell signals" && ((PASSED++)) || ((FAILED++))
run_loader "loadbuysellmonthly" "Monthly buy/sell signals" && ((PASSED++)) || ((FAILED++))
run_loader "loadlatestpriceweekly" "Latest weekly prices" && ((PASSED++)) || ((FAILED++))
run_loader "loadlatestpricemonthly" "Latest monthly prices" && ((PASSED++)) || ((FAILED++))
run_loader "loadlatesttechnicalsweekly" "Latest weekly technicals" && ((PASSED++)) || ((FAILED++))
run_loader "loadlatesttechnicalsmonthly" "Latest monthly technicals" && ((PASSED++)) || ((FAILED++))
run_loader "loadlatestbuysellweekly" "Latest weekly buy/sell" && ((PASSED++)) || ((FAILED++))
run_loader "loadlatestbuysellmonthly" "Latest monthly buy/sell" && ((PASSED++)) || ((FAILED++))

# ==== PHASE 4: Fundamental Financial Data ====
echo ""
echo "═══════════════════════════════════════════"
echo "PHASE 4: Fundamental Financial Data"
echo "═══════════════════════════════════════════"

run_loader "loadannualincomestatement" "Annual income statements" && ((PASSED++)) || ((FAILED++))
run_loader "loadannualbalancesheet" "Annual balance sheets" && ((PASSED++)) || ((FAILED++))
run_loader "loadannualcashflow" "Annual cash flows" && ((PASSED++)) || ((FAILED++))
run_loader "loadquarterlyincomestatement" "Quarterly income statements" && ((PASSED++)) || ((FAILED++))
run_loader "loadquarterlybalancesheet" "Quarterly balance sheets" && ((PASSED++)) || ((FAILED++))
run_loader "loadquarterlycashflow" "Quarterly cash flows" && ((PASSED++)) || ((FAILED++))
run_loader "loadttmincomestatement" "TTM income statements" && ((PASSED++)) || ((FAILED++))
run_loader "loadttmcashflow" "TTM cash flows" && ((PASSED++)) || ((FAILED++))
run_loader "loadearningsestimate" "Earnings estimates" && ((PASSED++)) || ((FAILED++))
run_loader "loadearningshistory" "Earnings history" && ((PASSED++)) || ((FAILED++))
run_loader "loadearningsmetrics" "Earnings metrics" && ((PASSED++)) || ((FAILED++))

# ==== PHASE 5: Computed Metrics ====
echo ""
echo "═══════════════════════════════════════════"
echo "PHASE 5: Computed Metrics (Quality, Growth, Value, Risk, Positioning)"
echo "═══════════════════════════════════════════"

run_loader "loadqualitymetrics" "Quality metrics" && ((PASSED++)) || ((FAILED++))
run_loader "loadgrowthmetrics" "Growth metrics" && ((PASSED++)) || ((FAILED++))
run_loader "loadvaluemetrics" "Value metrics" && ((PASSED++)) || ((FAILED++))
run_loader "loadriskmetrics" "Risk metrics" && ((PASSED++)) || ((FAILED++))
run_loader "loadpositioning" "Positioning metrics" && ((PASSED++)) || ((FAILED++))

# ==== PHASE 6: Sentiment and Market Data ====
echo ""
echo "═══════════════════════════════════════════"
echo "PHASE 6: Sentiment & Market Data"
echo "═══════════════════════════════════════════"

run_loader "loadsentiment" "Sentiment data" && ((PASSED++)) || ((FAILED++))
run_loader "loadanalystupgradedowngrade" "Analyst ratings" && ((PASSED++)) || ((FAILED++))
run_loader "loadnews" "News data" && ((PASSED++)) || ((FAILED++))
run_loader "loadsectors" "Sector rankings" && ((PASSED++)) || ((FAILED++))
run_loader "load_sector_performance" "Sector & Industry Technical Data" && ((PASSED++)) || ((FAILED++))

# ==== PHASE 7: Final - Stock Scores (depends on everything) ====
echo ""
echo "═══════════════════════════════════════════"
echo "PHASE 7: Final - Stock Scores Calculation"
echo "═══════════════════════════════════════════"

run_loader "loadstockscores" "Stock scores calculation" && ((PASSED++)) || ((FAILED++))

# ==== SUMMARY ====
echo ""
echo "=========================================="
echo "📊 EXECUTION SUMMARY"
echo "=========================================="
echo "✅ Passed: $PASSED"
echo "❌ Failed: $FAILED"
echo "⏭️  Skipped: $SKIPPED"
echo "📝 Log: $LOG_FILE"
echo ""

if [ $FAILED -eq 0 ]; then
    echo "🎉 All loaders completed successfully!"
    exit 0
else
    echo "⚠️  Some loaders failed. Check log for details."
    exit 1
fi
