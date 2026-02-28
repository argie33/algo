#!/bin/bash
# Comprehensive Data Loader Script
# Runs all essential loaders with proper environment setup

set -a
export AWS_REGION=us-east-1
export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=stocks
export DB_PASSWORD=bed0elAn
export DB_NAME=stocks
export PGPASSWORD=bed0elAn
export PGUSER=stocks
export PGHOST=localhost
export PGPORT=5432
export PGDATABASE=stocks
set +a

echo "🚀 STARTING ALL DATA LOADERS"
echo "Environment: AWS_REGION=$AWS_REGION, DB=$DB_USER@$DB_HOST/$DB_NAME"
echo ""

# Directory for logs
mkdir -p /home/arger/algo/loader_logs

# Track completion
STARTED=0
COMPLETED=0
FAILED=0

run_loader() {
    local loader=$1
    local description=$2

    if [ ! -f "$loader" ]; then
        echo "⚠️  $loader not found, skipping"
        return 1
    fi

    STARTED=$((STARTED + 1))
    local logfile="/home/arger/algo/loader_logs/$(basename $loader .py).log"

    echo "[$(date '+%H:%M:%S')] Starting: $description"
    timeout 600 python3 "$loader" > "$logfile" 2>&1 &
    local pid=$!

    # Wait for completion
    wait $pid
    local exit_code=$?

    if [ $exit_code -eq 0 ] || [ $exit_code -eq 124 ]; then
        COMPLETED=$((COMPLETED + 1))
        echo "✅ $description (PID: $pid)"
    else
        FAILED=$((FAILED + 1))
        echo "❌ $description (Exit: $exit_code)"
        echo "   Log: $logfile"
        tail -20 "$logfile"
    fi
    echo ""
}

# CRITICAL LOADERS (Stock Scores and Core Data)
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "PRIORITY 1: CORE DATA"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_loader "/home/arger/algo/loadstockscores.py" "Stock Scores"
run_loader "/home/arger/algo/loadpricedaily.py" "Daily Prices"
run_loader "/home/arger/algo/loadfactormetrics.py" "Factor Metrics"

# SIGNALS
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "PRIORITY 2: BUY/SELL SIGNALS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_loader "/home/arger/algo/loadbuysell_etf_daily.py" "Buy/Sell Daily"

# FINANCIAL STATEMENTS
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "PRIORITY 3: FINANCIAL STATEMENTS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_loader "/home/arger/algo/loadannualincomestatement.py" "Annual Income Statements"
run_loader "/home/arger/algo/loadannualbalancesheet.py" "Annual Balance Sheets"
run_loader "/home/arger/algo/loadannualcashflow.py" "Annual Cash Flows"

# SENTIMENT & ANALYSIS
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "PRIORITY 4: SENTIMENT & ANALYSIS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_loader "/home/arger/algo/loadanalystsentiment.py" "Analyst Sentiment"
run_loader "/home/arger/algo/loadearningshistory.py" "Earnings History"

# MARKET DATA
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "PRIORITY 5: MARKET DATA"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_loader "/home/arger/algo/loadmarketindices.py" "Market Indices"
run_loader "/home/arger/algo/loadbenchmark.py" "Benchmark Data"
run_loader "/home/arger/algo/loadsectorranking.py" "Sector Rankings"

# COMPANY DATA
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "PRIORITY 6: COMPANY DATA & NEWS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_loader "/home/arger/algo/loaddailycompanydata.py" "Daily Company Data"

echo ""
echo "════════════════════════════════════════════════"
echo "📊 LOADER SUMMARY"
echo "════════════════════════════════════════════════"
echo "Started:   $STARTED"
echo "Completed: $COMPLETED ✅"
echo "Failed:    $FAILED ❌"
echo ""
echo "Logs available in: /home/arger/algo/loader_logs/"
echo "════════════════════════════════════════════════"
