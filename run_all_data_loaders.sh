#!/bin/bash
# COMPLETE DATA LOADER - Runs ALL loaders in parallel
# Captures everything into the database

set -a
export AWS_REGION=us-east-1
export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=stocks
export DB_PASSWORD=bed0elAn
export DB_NAME=stocks
export PGPASSWORD=bed0elAn
set +a

mkdir -p /home/arger/algo/loader_logs

echo "════════════════════════════════════════════════════════════════"
echo "🚀 COMPREHENSIVE DATA LOADER - ALL TABLES"
echo "════════════════════════════════════════════════════════════════"
echo "Started: $(date)"
echo ""

# Array to track all pids
declare -a PIDS
declare -a NAMES

run_loader_bg() {
    local loader=$1
    local name=$2

    if [ ! -f "$loader" ]; then
        echo "⚠️  $loader not found"
        return 1
    fi

    local logfile="/home/arger/algo/loader_logs/$(basename $loader .py).log"

    timeout 1200 python3 "$loader" > "$logfile" 2>&1 &
    local pid=$!

    PIDS+=($pid)
    NAMES+=("$name")

    echo "[PID $pid] Starting: $name"
}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "LAUNCHING ALL LOADERS IN PARALLEL..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# CORE DATA
run_loader_bg "/home/arger/algo/loadstockscores.py" "Stock Scores"
run_loader_bg "/home/arger/algo/loadpricedaily.py" "Daily Prices"
run_loader_bg "/home/arger/algo/loadfactormetrics.py" "Factor Metrics"

# SIGNALS
run_loader_bg "/home/arger/algo/loadbuysell_etf_daily.py" "Buy/Sell Daily"

# FINANCIAL STATEMENTS
run_loader_bg "/home/arger/algo/loadannualincomestatement.py" "Income Statements"
run_loader_bg "/home/arger/algo/loadannualbalancesheet.py" "Balance Sheets"
run_loader_bg "/home/arger/algo/loadannualcashflow.py" "Cash Flow Statements"

# EARNINGS & ANALYSIS
run_loader_bg "/home/arger/algo/loadearningshistory.py" "Earnings History"
run_loader_bg "/home/arger/algo/loadearningsrevisions.py" "Earnings Revisions"
run_loader_bg "/home/arger/algo/loadanalystsentiment.py" "Analyst Sentiment"
run_loader_bg "/home/arger/algo/loadanalystupgradedowngrade.py" "Analyst Upgrades"

# MARKET & INDICES
run_loader_bg "/home/arger/algo/loadmarket.py" "Market Data"
run_loader_bg "/home/arger/algo/loadmarketindices.py" "Market Indices"
run_loader_bg "/home/arger/algo/loadbenchmark.py" "Benchmarks"
run_loader_bg "/home/arger/algo/loadsectorranking.py" "Sector Rankings"

# COMPANY DATA
run_loader_bg "/home/arger/algo/loaddailycompanydata.py" "Company Data"

# SENTIMENT INDICATORS
run_loader_bg "/home/arger/algo/loadfeargreed.py" "Fear & Greed"

# ECONOMIC DATA
run_loader_bg "/home/arger/algo/loadecondata.py" "Economic Data"

# NEWS
run_loader_bg "/home/arger/algo/loadnews.py" "Market News"

# SEC FILINGS
run_loader_bg "/home/arger/algo/loadsecfilings.py" "SEC Filings"

echo ""
echo "Total loaders: ${#PIDS[@]}"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "MONITORING PROGRESS..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Monitor progress
completed=0
failed=0

while [ $completed -lt ${#PIDS[@]} ]; do
    completed=0
    failed=0
    running=0

    for i in "${!PIDS[@]}"; do
        pid=${PIDS[$i]}
        name=${NAMES[$i]}

        if ! kill -0 $pid 2>/dev/null; then
            wait $pid
            exit_code=$?

            if [ $exit_code -eq 0 ] || [ $exit_code -eq 124 ]; then
                completed=$((completed + 1))
                echo "✅ [DONE] $name"
            else
                failed=$((failed + 1))
                echo "❌ [FAIL] $name (exit: $exit_code)"
                echo "   Log: /home/arger/algo/loader_logs/$(basename $name).log"
            fi

            unset PIDS[$i]
            unset NAMES[$i]
        else
            running=$((running + 1))
        fi
    done

    # Reindex arrays
    PIDS=("${PIDS[@]}")
    NAMES=("${NAMES[@]}")

    if [ $running -gt 0 ]; then
        total=$((completed + failed + running))
        echo "[$(date '+%H:%M:%S')] Progress: ✅ $completed | ❌ $failed | ⏳ $running / $total"
        sleep 30
    fi
done

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "📊 DATA LOADING COMPLETE"
echo "════════════════════════════════════════════════════════════════"
echo "Completed: $completed loaders ✅"
echo "Failed:    $failed loaders ❌"
echo "Finished: $(date)"
echo "Logs: /home/arger/algo/loader_logs/"
echo "════════════════════════════════════════════════════════════════"
