#!/bin/bash

# Master loader script - runs ALL data loaders with error handling
# Usage: ./run_all_loaders.sh

set -e  # Exit on any error
LOG_DIR="/home/stocks/algo/logs/master"
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
MASTER_LOG="$LOG_DIR/master_run_$TIMESTAMP.log"

echo "═══════════════════════════════════════════════════════════" | tee "$MASTER_LOG"
echo "MASTER DATA LOADER - Starting $TIMESTAMP" | tee -a "$MASTER_LOG"
echo "═══════════════════════════════════════════════════════════" | tee -a "$MASTER_LOG"

# Track results
FAILED=()
PASSED=()

run_loader() {
    local loader_name=$1
    local loader_file=$2
    
    echo "" | tee -a "$MASTER_LOG"
    echo "▶ Running: $loader_name" | tee -a "$MASTER_LOG"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" | tee -a "$MASTER_LOG"
    
    if python3 "$loader_file" 2>&1 | tee -a "$MASTER_LOG"; then
        echo "✅ SUCCESS: $loader_name" | tee -a "$MASTER_LOG"
        PASSED+=("$loader_name")
    else
        echo "❌ FAILED: $loader_name (will retry)" | tee -a "$MASTER_LOG"
        FAILED+=("$loader_name")
        # Retry once
        echo "  Retrying..." | tee -a "$MASTER_LOG"
        sleep 5
        if python3 "$loader_file" 2>&1 | tee -a "$MASTER_LOG"; then
            echo "✅ SUCCESS on retry: $loader_name" | tee -a "$MASTER_LOG"
            FAILED=("${FAILED[@]/$loader_name}")  # Remove from failed
            PASSED+=("$loader_name")
        else
            echo "❌ FAILED on retry: $loader_name" | tee -a "$MASTER_LOG"
        fi
    fi
}

# Load in proper order
echo "" | tee -a "$MASTER_LOG"
echo "STEP 1: Foundation Data" | tee -a "$MASTER_LOG"
run_loader "loadstocksymbols" "loadstocksymbols.py"

echo "" | tee -a "$MASTER_LOG"
echo "STEP 2: Price Data (Stocks)" | tee -a "$MASTER_LOG"
run_loader "loadpricedaily" "loadpricedaily.py"
run_loader "loadpriceweekly" "loadpriceweekly.py"
run_loader "loadpricemonthly" "loadpricemonthly.py"

echo "" | tee -a "$MASTER_LOG"
echo "STEP 3: Price Data (ETFs)" | tee -a "$MASTER_LOG"
run_loader "loadetfpricedaily" "loadetfpricedaily.py"
run_loader "loadetfpriceweekly" "loadetfpriceweekly.py"
run_loader "loadetfpricemonthly" "loadetfpricemonthly.py"

echo "" | tee -a "$MASTER_LOG"
echo "STEP 4: Company Data & Positioning" | tee -a "$MASTER_LOG"
run_loader "loaddailycompanydata" "loaddailycompanydata.py"

echo "" | tee -a "$MASTER_LOG"
echo "STEP 5: Financial Metrics" | tee -a "$MASTER_LOG"
run_loader "loadfactormetrics" "loadfactormetrics.py"

echo "" | tee -a "$MASTER_LOG"
echo "STEP 6: Stock Scores (Final)" | tee -a "$MASTER_LOG"
run_loader "loadstockscores" "loadstockscores.py"

# Summary
echo "" | tee -a "$MASTER_LOG"
echo "═══════════════════════════════════════════════════════════" | tee -a "$MASTER_LOG"
echo "SUMMARY" | tee -a "$MASTER_LOG"
echo "═══════════════════════════════════════════════════════════" | tee -a "$MASTER_LOG"
echo "✅ PASSED: ${#PASSED[@]} loaders" | tee -a "$MASTER_LOG"
printf '   - %s\n' "${PASSED[@]}" | tee -a "$MASTER_LOG"

if [ ${#FAILED[@]} -gt 0 ]; then
    echo "❌ FAILED: ${#FAILED[@]} loaders" | tee -a "$MASTER_LOG"
    printf '   - %s\n' "${FAILED[@]}" | tee -a "$MASTER_LOG"
    echo "See: $MASTER_LOG" | tee -a "$MASTER_LOG"
    exit 1
else
    echo "🎉 ALL LOADERS PASSED!" | tee -a "$MASTER_LOG"
    exit 0
fi
