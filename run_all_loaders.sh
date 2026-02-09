#!/bin/bash

export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=stocks
export DB_PASSWORD=bed0elAn
export DB_NAME=stocks

echo "🚀 STARTING ALL CRITICAL DATA LOADERS"
echo "====================================="
echo ""

# Price loaders (fresh daily data)
echo "1️⃣  Price Loaders..."
python3 loadlatestpricedaily.py > /tmp/latest_price_daily.log 2>&1 &
PID1=$!
python3 loadlatestpriceweekly.py > /tmp/latest_price_weekly.log 2>&1 &
PID2=$!
python3 loadlatestpricemonthly.py > /tmp/latest_price_monthly.log 2>&1 &
PID3=$!

# Sentiment loaders
echo "2️⃣  Sentiment Loaders..."
python3 loadfeargreed.py > /tmp/loadfeargreed.log 2>&1 &
PID4=$!
python3 loadaaiidata.py > /tmp/loadaaiidata.log 2>&1 &
PID5=$!
python3 loadnaaim.py > /tmp/loadnaaim.log 2>&1 &
PID6=$!

# Buy/sell signals
echo "3️⃣  Trading Signals..."
python3 loadbuyselldaily.py > /tmp/loadbuyselldaily.log 2>&1 &
PID7=$!
python3 loadbuysellweekly.py > /tmp/loadbuysellweekly.log 2>&1 &
PID8=$!
python3 loadbuysellmonthly.py > /tmp/loadbuysellmonthly.log 2>&1 &
PID9=$!

# ETF signals
echo "4️⃣  ETF Signals..."
python3 loadbuysell_etf_daily.py > /tmp/loadbuysell_etf_daily.log 2>&1 &
PID10=$!

echo ""
echo "All loaders started. Waiting for completion..."
echo "Use: tail -f /tmp/load*.log to monitor progress"
echo ""

wait $PID1 $PID2 $PID3 $PID4 $PID5 $PID6 $PID7 $PID8 $PID9 $PID10

echo "✅ All loaders completed!"
