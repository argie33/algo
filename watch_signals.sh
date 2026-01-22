#!/bin/bash
echo "=== SIGNAL LOADER MONITOR ==="
echo ""
echo "Running loaders:"
ps aux | grep "python3.*loadbuysell" | grep -v grep | awk '{printf "  %s (PID %s) - CPU: %s%%\n", $11, $2, $3}'

echo ""
echo "Recent progress:"
for log in loadbuysellmonthly_run.log loadbuysellweekly_run.log loadbuysell_etf_monthly_run.log loadbuysell_etf_weekly_run.log; do
  if [ -f "$log" ]; then
    SYMBOL=$(tail -20 "$log" | grep "===" | tail -1 | grep -oP '=== \K[A-Z0-9]+' || echo "?")
    TRADE=$(tail -5 "$log" | grep "→ Trades:" | tail -1 | grep -oP 'Trades:\K[0-9]+' || echo "")
    echo "  $(basename $log .log | sed 's/_run//'): processing $SYMBOL ${TRADE:+(${TRADE} trades)}"
  fi
done

echo ""
echo "Any errors?"
grep -h "ERROR\|Exception\|Traceback" loadbuysell*_run.log 2>/dev/null | tail -3 || echo "  ✓ No errors"
