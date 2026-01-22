#!/bin/bash

echo "=== LIVE LOADER MONITOR ==="
echo "Press Ctrl+C to stop"
echo ""

while true; do
  clear
  echo "=== LOADER MONITOR - $(date '+%H:%M:%S') ==="
  echo ""
  
  # Check running processes
  echo "Running Loaders:"
  DAILY=$(ps aux | grep "loadpricedaily.py" | grep -v grep | wc -l)
  WEEKLY=$(ps aux | grep "loadpriceweekly.py" | grep -v grep | wc -l)
  MONTHLY=$(ps aux | grep "loadpricemonthly.py" | grep -v grep | wc -l)
  
  [ $DAILY -gt 0 ] && echo "  ✓ Daily" || echo "  ✗ Daily - STOPPED"
  [ $WEEKLY -gt 0 ] && echo "  ✓ Weekly" || echo "  ✗ Weekly - STOPPED"
  [ $MONTHLY -gt 0 ] && echo "  ✓ Monthly" || echo "  ✗ Monthly - STOPPED"
  
  echo ""
  echo "Progress (last update):"
  
  # Daily progress
  DAILY_PROG=$(tail -1 loadpricedaily.log 2>/dev/null | grep -oP 'batch \K[0-9]+/[0-9]+' || echo "unknown")
  DAILY_SYM=$(tail -1 loadpricedaily.log 2>/dev/null | grep -oP '— \K[A-Z]+:' | sed 's/://' || echo "?")
  echo "  Daily:   $DAILY_PROG - $DAILY_SYM"
  
  # Weekly progress
  WEEKLY_PROG=$(tail -1 loadpriceweekly.log 2>/dev/null | grep -oP 'batch \K[0-9]+/[0-9]+' || echo "unknown")
  WEEKLY_SYM=$(tail -1 loadpriceweekly.log 2>/dev/null | grep -oP '— \K[A-Z]+:' | sed 's/://' || echo "?")
  echo "  Weekly:  $WEEKLY_PROG - $WEEKLY_SYM"
  
  # Monthly progress
  MONTHLY_PROG=$(tail -1 loadpricemonthly.log 2>/dev/null | grep -oP 'batch \K[0-9]+/[0-9]+' || echo "unknown")
  MONTHLY_SYM=$(tail -1 loadpricemonthly.log 2>/dev/null | grep -oP '— \K[A-Z]+:' | sed 's/://' || echo "?")
  echo "  Monthly: $MONTHLY_PROG - $MONTHLY_SYM"
  
  echo ""
  echo "Recent Errors (last 5 minutes):"
  
  # Check for recent errors
  ERROR_COUNT=$(find . -name "loadprice*.log" -mmin -5 -exec grep -i "ERROR\|CRITICAL\|exception\|Traceback" {} \; 2>/dev/null | tail -5)
  
  if [ -z "$ERROR_COUNT" ]; then
    echo "  ✓ No errors detected"
  else
    echo "$ERROR_COUNT" | head -5 | sed 's/^/  ⚠️ /'
  fi
  
  echo ""
  echo "Memory Usage:"
  ps aux | grep "python3.*loadprice" | grep -v grep | awk '{printf "  %s: %s MB\n", $11, int($6/1024)}'
  
  echo ""
  echo "─────────────────────────────────────────"
  echo "Refreshing in 10 seconds..."
  
  sleep 10
done
