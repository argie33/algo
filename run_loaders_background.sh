#!/bin/bash
# Production background loader that won't timeout
# Run with: nohup bash /home/stocks/algo/run_loaders_background.sh > /var/log/data_loader.log 2>&1 &

LOG_FILE="/var/log/stocks_loader_$(date +%Y%m%d_%H%M%S).log"
mkdir -p /var/log

{
  echo "╔════════════════════════════════════════════════════╗"
  echo "║  PRODUCTION DATA LOADER - $(date)  ║"
  echo "╚════════════════════════════════════════════════════╝"
  echo ""
  
  # Ensure no duplicate loaders
  killall -9 loaddailycompanydata.py 2>/dev/null || true
  sleep 2
  
  # PHASE 1: Company Data (1-2 hours)
  echo "PHASE 1: Loading company data from yfinance..."
  cd /home/stocks/algo
  python3 loaddailycompanydata.py
  
  # Check if Phase 1 succeeded
  COMPANY_ROWS=$(psql -h localhost -U stocks -d stocks -c "SELECT COUNT(*) FROM key_metrics" 2>&1 | tail -1 | grep -oE '[0-9]+' | head -1)
  echo "Phase 1 complete: $COMPANY_ROWS rows in key_metrics"
  
  if [ "$COMPANY_ROWS" -lt 100 ]; then
    echo "ERROR: Phase 1 failed (only $COMPANY_ROWS rows)"
    exit 1
  fi
  
  # PHASE 2: Factor Metrics (20-30 min)
  echo ""
  echo "PHASE 2: Calculating factor metrics..."
  python3 loadfactormetrics.py
  
  # PHASE 3: Stock Scores (5-10 min)
  echo ""
  echo "PHASE 3: Calculating stock scores..."
  python3 loadstockscores.py
  
  echo ""
  echo "╔════════════════════════════════════════════════════╗"
  echo "║  ✅ ALL DATA LOADED SUCCESSFULLY                   ║"
  echo "╚════════════════════════════════════════════════════╝"
  
} 2>&1 | tee "$LOG_FILE"

echo "Loader completed. Log: $LOG_FILE"
