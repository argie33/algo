#!/bin/bash
# Restart failed loaders and monitor their execution

echo "================================"
echo "RESTARTING FAILED LOADERS"
echo "================================"
echo ""

# Kill any existing instances
echo "Stopping old instances..."
killall -9 python3 2>/dev/null || true
sleep 2

echo "✅ All Python processes stopped"
echo ""

# Start loadearningsmetrics
echo "Starting loadearningsmetrics.py..."
nohup python3 /home/stocks/algo/loadearningsmetrics.py > /tmp/loadearningsmetrics.log 2>&1 &
EARNINGS_PID=$!
echo "PID: $EARNINGS_PID"

# Start loadtechnicalindicators
echo "Starting loadtechnicalindicators.py..."
nohup python3 /home/stocks/algo/loadtechnicalindicators.py > /tmp/loadtechnicalindicators.log 2>&1 &
TECHNICAL_PID=$!
echo "PID: $TECHNICAL_PID"

sleep 3

echo ""
echo "=== LOADER STATUS ==="
if ps -p $EARNINGS_PID > /dev/null 2>&1; then
  echo "✅ loadearningsmetrics RUNNING (PID: $EARNINGS_PID)"
else
  echo "❌ loadearningsmetrics FAILED"
  echo "Check log: tail -50 /tmp/loadearningsmetrics.log"
fi

if ps -p $TECHNICAL_PID > /dev/null 2>&1; then
  echo "✅ loadtechnicalindicators RUNNING (PID: $TECHNICAL_PID)"
else
  echo "❌ loadtechnicalindicators FAILED"
  echo "Check log: tail -50 /tmp/loadtechnicalindicators.log"
fi

echo ""
echo "=== MONITORING OUTPUT (30 seconds) ==="
sleep 30

echo ""
echo "EARNINGS METRICS LOG (last 10 lines):"
tail -10 /tmp/loadearningsmetrics.log
echo ""
echo "TECHNICAL INDICATORS LOG (last 10 lines):"
tail -10 /tmp/loadtechnicalindicators.log

echo ""
echo "================================"
echo "Loaders restarted!"
echo "================================"
