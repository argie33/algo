#!/bin/bash
cd /home/stocks/algo

# Loader restart trigger - 2026-01-24
# Kill any existing loaders
echo "Stopping any existing loaders..."
killall -9 loadpricedaily.py loadpriceweekly.py loadpricemonthly.py loadetfpricedaily.py loadetfpriceweekly.py loadetfpricemonthly.py 2>/dev/null || true
sleep 2

# Verify none are running
COUNT=$(ps aux | grep -E "loadprice|loadetf" | grep python3 | grep -v grep | wc -l)
if [ $COUNT -ne 0 ]; then
  echo "ERROR: $COUNT loader processes still running, cannot start"
  ps aux | grep -E "loadprice|loadetf" | grep python3 | grep -v grep
  exit 1
fi

# Start exactly one instance of each
echo "Starting loaders..."
nohup python3 loadpricedaily.py > loadpricedaily.log 2>&1 &
sleep 0.5
nohup python3 loadpriceweekly.py > loadpriceweekly.log 2>&1 &
sleep 0.5
nohup python3 loadpricemonthly.py > loadpricemonthly.log 2>&1 &
sleep 0.5
nohup python3 loadetfpricedaily.py > loadetfpricedaily.log 2>&1 &
sleep 0.5
nohup python3 loadetfpriceweekly.py > loadetfpriceweekly.log 2>&1 &
sleep 0.5
nohup python3 loadetfpricemonthly.py > loadetfpricemonthly.log 2>&1 &

sleep 3

# Verify exactly 6 are running
COUNT=$(ps aux | grep -E "loadprice|loadetf" | grep python3 | grep -v grep | wc -l)
echo "Loaders running: $COUNT"

if [ $COUNT -eq 6 ]; then
  echo "SUCCESS: All 6 loaders started"
  ps aux | grep -E "loadprice|loadetf" | grep python3 | grep -v grep | awk '{print $11}'
else
  echo "ERROR: Expected 6 loaders but found $COUNT"
  ps aux | grep -E "loadprice|loadetf" | grep python3 | grep -v grep
  exit 1
fi
