#!/bin/bash
# Continuous monitoring - logs failures to a file

MONITOR_LOG="loader_monitor_$(date +%Y%m%d_%H%M%S).log"
echo "Starting continuous monitoring... Output: $MONITOR_LOG"
echo "Press Ctrl+C to stop"

while true; do
  TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
  
  # Check running status
  DAILY=$(ps aux | grep "loadpricedaily.py" | grep -v grep | wc -l)
  WEEKLY=$(ps aux | grep "loadpriceweekly.py" | grep -v grep | wc -l)
  MONTHLY=$(ps aux | grep "loadpricemonthly.py" | grep -v grep | wc -l)
  
  # Get progress
  DAILY_PROG=$(tail -1 loadpricedaily.log 2>/dev/null | grep -oP 'batch \K[0-9]+/[0-9]+' || echo "?")
  WEEKLY_PROG=$(tail -1 loadpriceweekly.log 2>/dev/null | grep -oP 'batch \K[0-9]+/[0-9]+' || echo "?")
  MONTHLY_PROG=$(tail -1 loadpricemonthly.log 2>/dev/null | grep -oP 'batch \K[0-9]+/[0-9]+' || echo "?")
  
  # Log status
  echo "[$TIMESTAMP] D:$DAILY($DAILY_PROG) W:$WEEKLY($WEEKLY_PROG) M:$MONTHLY($MONTHLY_PROG)" >> "$MONITOR_LOG"
  
  # Alert if any stopped
  if [ $DAILY -eq 0 ] || [ $WEEKLY -eq 0 ] || [ $MONTHLY -eq 0 ]; then
    echo "[$TIMESTAMP] ⚠️ ALERT: Loader(s) stopped! D=$DAILY W=$WEEKLY M=$MONTHLY" | tee -a "$MONITOR_LOG"
  fi
  
  # Check for crashes (Traceback in last minute)
  if find . -name "loadprice*.log" -mmin -1 -exec grep -l "Traceback" {} \; 2>/dev/null | grep -q .; then
    echo "[$TIMESTAMP] 🔥 CRASH DETECTED" | tee -a "$MONITOR_LOG"
    find . -name "loadprice*.log" -mmin -1 -exec grep -A 5 "Traceback" {} \; | tee -a "$MONITOR_LOG"
  fi
  
  sleep 30
done
