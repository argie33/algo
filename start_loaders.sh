#!/bin/bash
cd /home/stocks/algo

# Loader restart trigger - 2026-01-24
# Database credentials for local/direct connection (bypasses Secrets Manager)
export DB_HOST="stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com"
export DB_PORT="5432"
export DB_USER="stocks"
export DB_PASSWORD="bed0elAn"
export DB_NAME="stocks"

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

# Start exactly one instance of each with database environment variables
echo "Starting loaders with direct DB connection (bypassing Secrets Manager)..."
env DB_HOST="$DB_HOST" DB_PORT="$DB_PORT" DB_USER="$DB_USER" DB_PASSWORD="$DB_PASSWORD" DB_NAME="$DB_NAME" nohup python3 loadpricedaily.py > loadpricedaily.log 2>&1 &
sleep 0.5
env DB_HOST="$DB_HOST" DB_PORT="$DB_PORT" DB_USER="$DB_USER" DB_PASSWORD="$DB_PASSWORD" DB_NAME="$DB_NAME" nohup python3 loadpriceweekly.py > loadpriceweekly.log 2>&1 &
sleep 0.5
env DB_HOST="$DB_HOST" DB_PORT="$DB_PORT" DB_USER="$DB_USER" DB_PASSWORD="$DB_PASSWORD" DB_NAME="$DB_NAME" nohup python3 loadpricemonthly.py > loadpricemonthly.log 2>&1 &
sleep 0.5
env DB_HOST="$DB_HOST" DB_PORT="$DB_PORT" DB_USER="$DB_USER" DB_PASSWORD="$DB_PASSWORD" DB_NAME="$DB_NAME" nohup python3 loadetfpricedaily.py > loadetfpricedaily.log 2>&1 &
sleep 0.5
env DB_HOST="$DB_HOST" DB_PORT="$DB_PORT" DB_USER="$DB_USER" DB_PASSWORD="$DB_PASSWORD" DB_NAME="$DB_NAME" nohup python3 loadetfpriceweekly.py > loadetfpriceweekly.log 2>&1 &
sleep 0.5
env DB_HOST="$DB_HOST" DB_PORT="$DB_PORT" DB_USER="$DB_USER" DB_PASSWORD="$DB_PASSWORD" DB_NAME="$DB_NAME" nohup python3 loadetfpricemonthly.py > loadetfpricemonthly.log 2>&1 &

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
