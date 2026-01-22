#!/bin/bash

echo "Starting continuous error monitoring..."
echo "Checking logs every 30 seconds for new errors..."
echo ""

LAST_ERROR_COUNT=0

while true; do
  # Count ERROR lines
  ERROR_COUNT=$(grep -i "ERROR\|CRITICAL\|FATAL" loadpricedaily.log loadpriceweekly.log loadpricemonthly.log loadetfpricedaily.log loadetfpriceweekly.log loadetfpricemonthly.log 2>/dev/null | wc -l)
  
  # Count loaders
  LOADER_COUNT=$(ps aux | grep -E "loadprice|loadetf" | grep python3 | grep -v grep | wc -l)
  
  # Check for duplicates
  DUPS=$(psql -h localhost -U stocks -d stocks << 'SQL' 2>/dev/null | grep -c " 0$"
SELECT COUNT(*) - COUNT(DISTINCT (symbol, date)) FROM price_daily
UNION ALL
SELECT COUNT(*) - COUNT(DISTINCT (symbol, date)) FROM price_weekly
UNION ALL
SELECT COUNT(*) - COUNT(DISTINCT (symbol, date)) FROM price_monthly
UNION ALL
SELECT COUNT(*) - COUNT(DISTINCT (symbol, date)) FROM etf_price_daily
UNION ALL
SELECT COUNT(*) - COUNT(DISTINCT (symbol, date)) FROM etf_price_weekly
UNION ALL
SELECT COUNT(*) - COUNT(DISTINCT (symbol, date)) FROM etf_price_monthly;
SQL
)
  
  if [ $ERROR_COUNT -ne $LAST_ERROR_COUNT ]; then
    echo "[$(date '+%H:%M:%S')] NEW ERRORS FOUND: $ERROR_COUNT total (was $LAST_ERROR_COUNT)"
    grep -i "ERROR\|CRITICAL\|FATAL" loadpricedaily.log loadpriceweekly.log loadpricemonthly.log loadetfpricedaily.log loadetfpriceweekly.log loadetfpricemonthly.log 2>/dev/null | tail -5
    LAST_ERROR_COUNT=$ERROR_COUNT
  fi
  
  if [ $LOADER_COUNT -ne 6 ]; then
    echo "[$(date '+%H:%M:%S')] WARNING: $LOADER_COUNT loaders running (expected 6)"
  fi
  
  if [ $DUPS -ne 6 ]; then
    echo "[$(date '+%H:%M:%S')] WARNING: DUPLICATES DETECTED!"
  fi
  
  sleep 30
done
