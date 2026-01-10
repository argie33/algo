#!/bin/bash

while true; do
  echo "=== $(date) ==="
  
  # Check if all 6 loaders are running
  COUNT=$(ps aux | grep -E "loadprice|loadetf" | grep python3 | grep -v grep | wc -l)
  if [ $COUNT -ne 6 ]; then
    echo "WARNING: Expected 6 loaders but found $COUNT"
    ps aux | grep -E "loadprice|loadetf" | grep python3 | grep -v grep | awk '{print $11, $12}'
  fi
  
  # Show data progress
  psql -h localhost -U stocks -d stocks << 'SQL'
SELECT 
  table_name,
  symbols || ' / ' || total as progress,
  ROUND(100.0*symbols/total, 1) || '%' as pct
FROM (
  SELECT 'price_daily' as table_name, COUNT(DISTINCT symbol) as symbols, 5275 as total FROM price_daily
  UNION ALL
  SELECT 'price_weekly', COUNT(DISTINCT symbol), 5275 FROM price_weekly
  UNION ALL
  SELECT 'price_monthly', COUNT(DISTINCT symbol), 5275 FROM price_monthly
  UNION ALL
  SELECT 'etf_price_daily', COUNT(DISTINCT symbol), 4863 FROM etf_price_daily
  UNION ALL
  SELECT 'etf_price_weekly', COUNT(DISTINCT symbol), 4863 FROM etf_price_weekly
  UNION ALL
  SELECT 'etf_price_monthly', COUNT(DISTINCT symbol), 4863 FROM etf_price_monthly
) x
ORDER BY table_name;
SQL
  
  # Check for errors in logs
  ERRORS=$(find . -name "*.log" -type f -exec grep -l "ERROR\|Exception\|Traceback" {} \; 2>/dev/null | wc -l)
  if [ $ERRORS -gt 0 ]; then
    echo "ERROR: Found errors in $ERRORS log files"
    find . -name "*.log" -type f -exec grep "ERROR\|Exception" {} + | tail -5
  fi
  
  echo ""
  sleep 300  # Check every 5 minutes
done
