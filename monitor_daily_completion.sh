#!/bin/bash

while true; do
  # Check if loaders running
  STOCK_COUNT=$(ps aux | grep "loadbuyselldaily.py" | grep -v grep | wc -l)
  ETF_COUNT=$(ps aux | grep "loadbuysell_etf_daily.py" | grep -v grep | wc -l)
  
  if [ $STOCK_COUNT -eq 0 ] && [ $ETF_COUNT -eq 0 ]; then
    echo "[$(date)] ✅ DAILY LOADERS COMPLETED"
    tail -5 loadbuyselldaily_complete.log
    echo ""
    tail -5 loadbuysell_etf_daily_complete.log
    break
  fi
  
  # Show progress
  echo "[$(date)] Loaders running: stock=$STOCK_COUNT, etf=$ETF_COUNT"
  
  # Check database progress
  psql -h localhost -U stocks -d stocks << 'SQL' 2>/dev/null
SELECT 'buy_sell_daily' as table_name, COUNT(DISTINCT symbol) as symbols FROM buy_sell_daily
UNION ALL
SELECT 'buy_sell_daily_etf', COUNT(DISTINCT symbol) FROM buy_sell_daily_etf;
SQL
  
  echo ""
  sleep 60
done
