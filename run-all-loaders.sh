#!/bin/bash
echo "Starting ALL data loaders (stock analysis platform)..."
echo "======================================================="

# Array to collect all PIDs for final wait
declare -a PIDS
declare -a NAMES

# Function to start a loader
start_loader() {
  local loader=$1
  local logname=$2
  python "$loader" > "/tmp/$logname.log" 2>&1 &
  local pid=$!
  PIDS+=($pid)
  NAMES+=("$loader")
  echo "✓ $loader (PID: $pid)"
}

echo "=== PRICE DATA (Required for all analysis) ==="
start_loader "loadpricedaily.py" "price-daily"
start_loader "loadpriceweekly.py" "price-weekly"
start_loader "loadpricemonthly.py" "price-monthly"
start_loader "loadlatestpricedaily.py" "latest-price-daily"
start_loader "loadlatestpriceweekly.py" "latest-price-weekly"
start_loader "loadlatestpricemonthly.py" "latest-price-monthly"

echo ""
echo "=== ETF DATA ==="
start_loader "loadetfpricedaily.py" "etf-price-daily"
start_loader "loadetfpriceweekly.py" "etf-price-weekly"
start_loader "loadetfpricemonthly.py" "etf-price-monthly"
start_loader "loadetfsignals.py" "etf-signals"

echo ""
echo "=== TECHNICAL INDICATORS ==="
start_loader "loadtechnicalsdaily.py" "technical-daily"
start_loader "loadtechnicalsweekly.py" "technical-weekly"
start_loader "loadtechnicalsmonthly.py" "technical-monthly"

echo ""
echo "=== BUY/SELL SIGNALS (Trading signals pages) ==="
start_loader "loadbuyselldaily.py" "buysell-daily"
start_loader "loadbuysellweekly.py" "buysell-weekly"
start_loader "loadbuysellmonthly.py" "buysell-monthly"
start_loader "loadbuysell_etf_daily.py" "buysell-etf-daily"
start_loader "loadbuysell_etf_weekly.py" "buysell-etf-weekly"
start_loader "loadbuysell_etf_monthly.py" "buysell-etf-monthly"

echo ""
echo "=== COMPANY DATA (Earnings, positioning, fundamentals) ==="
start_loader "loaddailycompanydata.py" "company-daily"
start_loader "loadearningshistory.py" "earnings-history"

echo ""
echo "=== ANALYST & SENTIMENT DATA ==="
start_loader "loadanalystsentiment.py" "analyst-sentiment"
start_loader "loadanalystupgradedowngrade.py" "analyst-upgrades"

echo ""
echo "=== OPTIONS DATA ==="
start_loader "loadoptionschains.py" "options-chains"

echo ""
echo "=== FINANCIAL STATEMENTS (Annual) ==="
start_loader "loadannualincomestatement.py" "annual-income"
start_loader "loadannualbalancesheet.py" "annual-balance"
start_loader "loadannualcashflow.py" "annual-cashflow"

echo ""
echo "=== FINANCIAL STATEMENTS (Quarterly) ==="
start_loader "loadquarterlyincomestatement.py" "quarterly-income"
start_loader "loadquarterlybalancesheet.py" "quarterly-balance"
start_loader "loadquarterlycashflow.py" "quarterly-cashflow"

echo ""
echo "=== FINANCIAL STATEMENTS (TTM) ==="
start_loader "loadttmincomestatement.py" "ttm-income"
start_loader "loadttmcashflow.py" "ttm-cashflow"

echo ""
echo "=== SECTOR & INDUSTRY RANKINGS ==="
start_loader "loadsectorranking.py" "sector-ranking"
start_loader "loadindustryranking.py" "industry-ranking"

echo ""
echo "=== STOCK SCORES (Quality, growth, momentum, etc.) ==="
start_loader "loadstockscores.py" "stock-scores"

echo ""
echo "=== ADDITIONAL METRICS ==="
start_loader "loadfactormetrics.py" "factor-metrics"
start_loader "loadmarket.py" "market-data"
start_loader "loadmarketindices.py" "market-indices"

echo ""
echo "======================================================="
echo "All ${#PIDS[@]} loaders started. Waiting for completion..."
echo "Monitor logs in /tmp/*.log"
echo ""

# Wait for all loaders to complete
wait "${PIDS[@]}"

echo ""
echo "✅ All loaders complete!"
echo ""
echo "Summary:"
for i in "${!PIDS[@]}"; do
  if wait ${PIDS[$i]} 2>/dev/null; then
    echo "✓ ${NAMES[$i]}"
  else
    echo "✗ ${NAMES[$i]} (check /tmp/...log)"
  fi
done
