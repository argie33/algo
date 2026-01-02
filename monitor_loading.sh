#!/bin/bash
# Real-time data loading monitor

while true; do
  clear
  echo "=========================================="
  echo "DATA LOADING PROGRESS - $(date '+%Y-%m-%d %H:%M:%S')"
  echo "=========================================="
  echo ""
  
  # Company data loader
  COMPANY_DONE=$(grep -c "✅" loaddailycompanydata_run.log 2>/dev/null || echo "0")
  COMPANY_LAST=$(tail -1 loaddailycompanydata_run.log 2>/dev/null | grep -o "[A-Z]*:" | head -1 | tr -d ':')
  echo "📊 COMPANY DATA LOADER"
  echo "   Completed: $COMPANY_DONE / 5300 stocks"
  if [ -n "$COMPANY_LAST" ]; then
    echo "   Last stock: $COMPANY_LAST"
  fi
  
  # Check if running
  if pgrep -f "loaddailycompanydata.py" > /dev/null 2>&1; then
    echo "   Status: ✅ RUNNING"
  else
    echo "   Status: ⏸️ STOPPED"
  fi
  echo ""
  
  # Stock scores loader
  SCORES_DONE=$(grep -c "Composite=" loadstockscores_run.log 2>/dev/null || echo "0")
  SCORES_LAST=$(tail -3 loadstockscores_run.log 2>/dev/null | grep "Processing" | tail -1 | grep -o "[A-Z0-9]*" | tail -1)
  echo "💰 STOCK SCORES LOADER"
  echo "   Completed: $SCORES_DONE / 5297 stocks"
  if [ -n "$SCORES_LAST" ]; then
    echo "   Processing: $SCORES_LAST"
  fi
  
  # Check if running
  if pgrep -f "loadstockscores.py" > /dev/null 2>&1; then
    echo "   Status: ✅ RUNNING"
  else
    echo "   Status: ⏸️ STOPPED"
  fi
  echo ""
  
  # Database status
  echo "📈 DATABASE STATUS"
  psql -h localhost -U stocks -d stocks -t -c "SELECT 'Stock Scores: ' || COUNT(*) FROM stock_scores;" 2>/dev/null || echo "   DB: Connection error"
  echo ""
  
  echo "=========================================="
  echo "Press Ctrl+C to exit. Updates every 30 seconds."
  sleep 30
done
