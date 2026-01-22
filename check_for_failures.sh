#!/bin/bash
# Quick failure detection - run this periodically

echo "=== FAILURE CHECK $(date '+%H:%M:%S') ==="
echo ""

# Check if any loader stopped unexpectedly
DAILY=$(ps aux | grep "loadpricedaily.py" | grep -v grep | wc -l)
WEEKLY=$(ps aux | grep "loadpriceweekly.py" | grep -v grep | wc -l)
MONTHLY=$(ps aux | grep "loadpricemonthly.py" | grep -v grep | wc -l)

FAILURES=0

if [ $DAILY -eq 0 ]; then
  echo "❌ DAILY LOADER STOPPED"
  echo "Last 10 lines:"
  tail -10 loadpricedaily.log | grep -E "ERROR|Exception|Traceback|CRITICAL" || tail -3 loadpricedaily.log
  FAILURES=$((FAILURES + 1))
fi

if [ $WEEKLY -eq 0 ]; then
  echo "❌ WEEKLY LOADER STOPPED"
  echo "Last 10 lines:"
  tail -10 loadpriceweekly.log | grep -E "ERROR|Exception|Traceback|CRITICAL" || tail -3 loadpriceweekly.log
  FAILURES=$((FAILURES + 1))
fi

if [ $MONTHLY -eq 0 ]; then
  echo "❌ MONTHLY LOADER STOPPED"
  echo "Last 10 lines:"
  tail -10 loadpricemonthly.log | grep -E "ERROR|Exception|Traceback|CRITICAL" || tail -3 loadpricemonthly.log
  FAILURES=$((FAILURES + 1))
fi

# Check for recent errors in logs
RECENT_ERRORS=$(find . -name "loadprice*.log" -mmin -2 -exec grep -l "ERROR\|CRITICAL\|Traceback" {} \; 2>/dev/null)

if [ -n "$RECENT_ERRORS" ]; then
  echo ""
  echo "⚠️ RECENT ERRORS FOUND IN:"
  echo "$RECENT_ERRORS"
  for log in $RECENT_ERRORS; do
    echo ""
    echo "From $log:"
    grep -A 3 "ERROR\|CRITICAL\|Traceback" "$log" | tail -10
  done
  FAILURES=$((FAILURES + 1))
fi

echo ""
if [ $FAILURES -eq 0 ]; then
  echo "✅ All loaders running, no errors detected"
  exit 0
else
  echo "❌ $FAILURES issue(s) detected"
  exit 1
fi
