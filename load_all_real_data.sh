#!/bin/bash
###############################################################################
# MASTER DATA LOADER - Loads ALL real data using existing main loaders
# 
# This script orchestrates all the main data loaders to populate the database
# with REAL DATA from legitimate sources (yfinance, SEC, etc)
#
# Best Practices:
# - No synthetic/fake data generation
# - No hardcoded fallback values
# - Returns NULL when real data unavailable
# - All data sourced from legitimate APIs
###############################################################################

set -e

echo "=========================================================================="
echo "🚀 STARTING MASTER DATA LOAD - REAL DATA ONLY"
echo "=========================================================================="
echo ""
echo "📅 Start Time: $(date)"
echo ""

# Configuration
REPO_ROOT="/home/stocks/algo"
LOG_DIR="/tmp/data_loads"
mkdir -p "$LOG_DIR"

# Main loaders in execution order (dependencies first)
declare -a LOADERS=(
    "loadcompanyprofile.py:Company Profiles"
    "loadsectors.py:Sectors"
    "loadmarket.py:Market Overview"
    "loadtechnicalsdaily.py:Technical Data"
    "loadvaluemetrics.py:Value Metrics"
    "loadscores.py:Composite Scores"
    "loadsentiment.py:Sentiment (Google Trends + Reddit)"
    "loadbuyselldaily.py:Buy/Sell Signals"
    "load_sector_performance.py:Sector Performance"
)

# Disabled loaders (synthetic data - DO NOT USE)
declare -a DISABLED_LOADERS=(
    ".disabled_loadsentiment_realtime.py:❌ DISABLED - Was generating random sentiment"
)

# Track results
SUCCESSFUL=0
FAILED=0
SKIPPED=0

echo "📋 LOADERS TO EXECUTE:"
for loader in "${LOADERS[@]}"; do
    IFS=':' read -r file desc <<< "$loader"
    if [ -f "$REPO_ROOT/$file" ]; then
        echo "   ✅ $file ($desc)"
    else
        echo "   ⏭️  $file ($desc) - NOT FOUND"
    fi
done

echo ""
echo "❌ DISABLED (SYNTHETIC DATA):"
for loader in "${DISABLED_LOADERS[@]}"; do
    IFS=':' read -r file desc <<< "$loader"
    echo "   $desc"
done

echo ""
echo "=========================================================================="
echo "⚙️  EXECUTING LOADERS..."
echo "=========================================================================="

for loader in "${LOADERS[@]}"; do
    IFS=':' read -r file desc <<< "$loader"
    
    if [ ! -f "$REPO_ROOT/$file" ]; then
        echo ""
        echo "⏭️  SKIPPING: $desc ($file not found)"
        ((SKIPPED++))
        continue
    fi
    
    echo ""
    echo "▶️  LOADING: $desc ($file)"
    echo "   Time: $(date '+%H:%M:%S')"
    
    LOG_FILE="$LOG_DIR/${file%.py}.log"
    
    if python3 "$REPO_ROOT/$file" > "$LOG_FILE" 2>&1; then
        echo "   ✅ SUCCESS"
        ((SUCCESSFUL++))
    else
        echo "   ❌ FAILED - See $LOG_FILE"
        ((FAILED++))
        tail -20 "$LOG_FILE"
    fi
done

echo ""
echo "=========================================================================="
echo "📊 RESULTS"
echo "=========================================================================="
echo "✅ Successful: $SUCCESSFUL"
echo "❌ Failed:     $FAILED"
echo "⏭️  Skipped:    $SKIPPED"
echo ""
echo "📅 End Time: $(date)"
echo ""

if [ $FAILED -eq 0 ]; then
    echo "🎉 ALL DATA LOADED SUCCESSFULLY!"
    echo ""
    echo "✨ Database now contains:"
    echo "   - Real company profiles (from yfinance)"
    echo "   - Real price data and technicals"
    echo "   - Real market metrics and sectors"
    echo "   - Real sentiment (Google Trends + Reddit)"
    echo "   - Real buy/sell signals"
    echo "   - Real performance metrics"
    echo ""
    echo "❌ NO SYNTHETIC/FAKE DATA"
    exit 0
else
    echo "⚠️  SOME LOADERS FAILED - Check logs in $LOG_DIR"
    exit 1
fi
