#!/bin/bash

set -e
LOG_FILE="/home/stocks/algo/loader_execution_$(date +%Y%m%d_%H%M%S).log"
LOADERS_DIR="/home/stocks/algo"

echo "=========================================="
echo "🚀 Starting essential data load"
echo "=========================================="
echo "Log file: $LOG_FILE"
echo ""

run_loader() {
    local loader=$1
    local description=$2
    
    if [ ! -f "$LOADERS_DIR/$loader.py" ]; then
        echo "⚠️  SKIP: $loader not found"
        return 0
    fi
    
    echo ""
    echo "📦 $description"
    echo "   Executing: python3 $loader.py"
    
    if python3 "$LOADERS_DIR/$loader.py" >> "$LOG_FILE" 2>&1; then
        echo "   ✅ SUCCESS"
        return 0
    else
        echo "   ❌ FAILED"
        tail -20 "$LOG_FILE" | head -10
        return 1
    fi
}

PASSED=0
FAILED=0

# ==== Key loaders (non-optimized versions) ====
echo ""
echo "═══════════════════════════════════════════"
echo "Essential Loaders"
echo "═══════════════════════════════════════════"

# Company and symbol data
run_loader "loadcompanyprofile" "Company profiles" && ((PASSED++)) || ((FAILED++))

# Price data
run_loader "loadpricedaily" "Daily prices" && ((PASSED++)) || ((FAILED++))

# Technical data  
run_loader "loadtechnicalsdaily" "Daily technicals" && ((PASSED++)) || ((FAILED++))

# Buy/sell signals
run_loader "loadbuysellsdaily" "Buy/sell daily signals" && ((PASSED++)) || ((FAILED++))

# Weekly/Monthly extended
run_loader "loadpriceweekly" "Weekly prices" && ((PASSED++)) || ((FAILED++))
run_loader "loadpricemonthly" "Monthly prices" && ((PASSED++)) || ((FAILED++))
run_loader "loadtechnicalsweekly" "Weekly technicals" && ((PASSED++)) || ((FAILED++))
run_loader "loadtechnicalsmonthly" "Monthly technicals" && ((PASSED++)) || ((FAILED++))

# Metrics (critical for scores)
run_loader "loadqualitymetrics" "Quality metrics" && ((PASSED++)) || ((FAILED++))
run_loader "loadgrowthmetrics" "Growth metrics" && ((PASSED++)) || ((FAILED++))
run_loader "loadvaluemetrics" "Value metrics" && ((PASSED++)) || ((FAILED++))
run_loader "loadriskmetrics" "Risk metrics" && ((PASSED++)) || ((FAILED++))
run_loader "loadpositioning" "Positioning metrics" && ((PASSED++)) || ((FAILED++))

# Final: Stock scores (depends on all above)
run_loader "loadstockscores" "Stock scores" && ((PASSED++)) || ((FAILED++))

# ==== SUMMARY ====
echo ""
echo "=========================================="
echo "📊 EXECUTION SUMMARY"
echo "=========================================="
echo "✅ Passed: $PASSED"
echo "❌ Failed: $FAILED"
echo "📝 Full log: $LOG_FILE"
echo ""

if [ $FAILED -eq 0 ]; then
    echo "🎉 All essential loaders completed!"
else
    echo "⚠️  Some loaders failed. Check log."
fi
