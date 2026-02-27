#!/bin/bash

# MASTER LOADER SCRIPT - Get 100% of all data for all 4,988 stocks locally and in AWS

set -e  # Exit on error

export PGPASSWORD="bed0elAn"
export DB_HOST="localhost"
export DB_USER="stocks"
export DB_PASSWORD="bed0elAn"
export DB_NAME="stocks"

cd /home/arger/algo

echo "╔════════════════════════════════════════════════════════════════════════════════╗"
echo "║           🎯 MASTER DATA LOADER - GET ALL DATA FOR ALL STOCKS 🎯             ║"
echo "╚════════════════════════════════════════════════════════════════════════════════╝"
echo ""

# Array of critical loaders that MUST run in sequence
CRITICAL_LOADERS=(
  "loadstocksymbols.py"
  "loadpricedaily.py"
  "loadpriceweekly.py"
  "loadpricemonthly.py"
  "loadtechnicalindicators.py"
  "loadstockscores.py"
)

# Array of data loaders that can run in parallel
DATA_LOADERS=(
  "loadanalystsentiment.py"
  "loadanalystupgradedowngrade.py"
  "loadearningshistory.py"
  "loadinsidertransactions.py"
  "loadannualincomestatement.py"
  "loadannualcashflow.py"
  "loadquarterlybalancesheet.py"
  "loadbuyselldaily.py"
  "loadbuysellweekly.py"
  "loadbuysellmonthly.py"
  "loadearningsestimates.py"
  "loadbenchmarkdata.py"
  "loadmarketdata.py"
)

echo "🔴 RUNNING CRITICAL LOADERS (SEQUENTIAL):"
echo ""

for loader in "${CRITICAL_LOADERS[@]}"; do
  if [ -f "$loader" ]; then
    echo "▶️  Running: $loader"
    logfile="/tmp/loader_$(echo $loader | sed 's/.py//' | cut -c1-30).log"
    
    if python3 "$loader" > "$logfile" 2>&1; then
      echo "   ✅ SUCCESS"
    else
      echo "   ❌ FAILED - Check: $logfile"
      tail -5 "$logfile"
    fi
    echo ""
  fi
done

echo ""
echo "🟢 RUNNING DATA LOADERS (PARALLEL):"
echo ""

for loader in "${DATA_LOADERS[@]}"; do
  if [ -f "$loader" ]; then
    logfile="/tmp/loader_$(echo $loader | sed 's/.py//' | cut -c1-30).log"
    python3 "$loader" > "$logfile" 2>&1 &
    echo "   ⏳ Started: $loader (PID: $!)"
  fi
done

echo ""
echo "⏳ Waiting for parallel loaders to complete..."
wait

echo ""
echo "✅ ALL LOADERS COMPLETED"
