#!/bin/bash
echo "=== LOADER STATUS CHECK ==="
echo ""
echo "Price Loaders (should be running continuously):"
for loader in loadpricedaily loadpriceweekly loadpricemonthly; do
  COUNT=$(ps aux | grep "$loader.py" | grep -v grep | wc -l)
  if [ $COUNT -gt 0 ]; then
    PROGRESS=$(tail -1 ${loader}.log 2>/dev/null | grep -oP 'batch \K[0-9]+/[0-9]+' || echo "running")
    echo "  ✓ $loader.py - $PROGRESS"
  else
    echo "  ✗ $loader.py - NOT RUNNING"
  fi
done

echo ""
echo "ETF Price Loaders:"
for loader in loadetfpricedaily loadetfpriceweekly loadetfpricemonthly; do
  COUNT=$(ps aux | grep "$loader.py" | grep -v grep | wc -l)
  LAST_RUN=$(tail -5 ${loader}.log 2>/dev/null | grep "Done" | tail -1)
  if [ $COUNT -gt 0 ]; then
    PROGRESS=$(tail -1 ${loader}.log 2>/dev/null | grep -oP 'batch \K[0-9]+/[0-9]+' || echo "running")
    echo "  ↻ $loader.py - $PROGRESS"
  elif [ -n "$LAST_RUN" ]; then
    echo "  ✓ $loader.py - completed"
  else
    echo "  ✗ $loader.py - NOT STARTED"
  fi
done

echo ""
echo "Running Python Loaders:"
ps aux | grep "python3.*load" | grep -v grep | awk '{print "  " $11}' | sort
