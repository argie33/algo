#!/bin/bash
set -e
echo "🚀 RUNNING ALL DATA LOADERS"
echo "================================"

loaders=("loadsectors.py" "loadtechnicalsdaily.py" "loadtechnicalsweekly.py" "loadtechnicalsmonthly.py" "loadlatesttechnicalsdaily.py" "loadpricedaily.py" "loadpriceweekly.py" "loadpricemonthly.py" "loadlatestpricedaily.py" "loadbuyselldaily.py" "loadbuysellweekly.py" "loadbuysellmonthly.py" "loadlatestbuyselldaily.py" "loadstockscores.py")

success_count=0
fail_count=0

for loader in "${loaders[@]}"; do
  echo ""
  echo "▶ Running $loader..."
  if timeout 600 python3 "$loader" 2>&1 | tail -5; then
    echo "✅ $loader completed"
    ((success_count++))
  else
    echo "❌ $loader FAILED"
    ((fail_count++))
  fi
done

echo ""
echo "================================"
echo "📊 RESULTS: $success_count passed, $fail_count failed"
