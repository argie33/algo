#!/bin/bash

# Real-time loader monitoring script
# Usage: bash MONITOR_LOADERS.sh

export PGPASSWORD="bed0elAn"

echo "╔═══════════════════════════════════════════════════════════════════════════╗"
echo "║                    📊 LOADER MONITORING DASHBOARD 📊                    ║"
echo "╚═══════════════════════════════════════════════════════════════════════════╝"
echo ""
echo "Refreshing every 10 seconds... Press Ctrl+C to stop"
echo ""

while true; do
  clear

  echo "🕐 Time: $(date '+%H:%M:%S CST') | Started: ~20:05 CST | Est. Completion: ~21:15 CST"
  echo ""

  echo "📝 LOADER FILES STATUS:"
  echo "═══════════════════════════════════════════════════════════════════════════"

  # Check each critical loader
  for loader in loadstocksymbols loadpricedaily loadpriceweekly loadpricemonthly loadtechnicalindicators loadstockscores; do
    logfile="/tmp/loader_${loader}.log"
    if [ -f "$logfile" ]; then
      lines=$(wc -l < "$logfile")
      size=$(du -h "$logfile" | awk '{print $1}')

      # Check if complete
      if grep -q "✅\|COMPLETE\|SUCCESS" "$logfile" 2>/dev/null; then
        echo "✅ $loader ($lines lines, $size)"
      elif grep -q "ERROR\|FAILED\|Traceback" "$logfile" 2>/dev/null; then
        echo "❌ $loader ($lines lines, $size) - HAS ERRORS!"
      else
        echo "⏳ $loader ($lines lines, $size)"
      fi
    fi
  done

  echo ""
  echo "📊 DATABASE ROW COUNTS:"
  echo "═══════════════════════════════════════════════════════════════════════════"

  psql -h localhost -U stocks -d stocks -t -c "
  WITH counts AS (
    SELECT 'Stock Symbols' as name, COUNT(*) as cnt FROM stock_symbols
    UNION ALL
    SELECT 'Daily Prices', COUNT(*) FROM price_daily
    UNION ALL
    SELECT 'Daily Technical', COUNT(*) FROM technical_data_daily
    UNION ALL
    SELECT 'Stock Scores', COUNT(*) FROM stock_scores
    UNION ALL
    SELECT 'Daily Signals (symbols)', COUNT(DISTINCT symbol) FROM buy_sell_daily
    UNION ALL
    SELECT 'Daily Signals (records)', COUNT(*) FROM buy_sell_daily
  )
  SELECT name, cnt::text FROM counts ORDER BY name;
  " 2>/dev/null | sed 's/^/  /'

  echo ""
  echo "🎯 KEY METRIC: Buy/Sell Daily Signal Coverage"
  symbol_count=$(psql -h localhost -U stocks -d stocks -t -c "SELECT COUNT(DISTINCT symbol) FROM buy_sell_daily" 2>/dev/null)
  percent=$(( (symbol_count * 100) / 4988 ))
  echo "  Symbols: $symbol_count / 4,988 ($percent%)"

  if [ "$symbol_count" -ge 4000 ]; then
    echo "  ✅ MAJOR SUCCESS! Most symbols loaded!"
  elif [ "$symbol_count" -ge 1000 ]; then
    echo "  ⏳ Good progress, still loading..."
  elif [ "$symbol_count" -ge 100 ]; then
    echo "  ⏳ Early stage, still loading..."
  elif [ "$symbol_count" -eq 46 ]; then
    echo "  ⚠️ Still only has old data (46 symbols). Loader may not have run yet."
  fi

  echo ""
  echo "💾 LATEST LOG ENTRIES:"
  echo "═══════════════════════════════════════════════════════════════════════════"

  # Show last line from price loader
  if [ -f "/tmp/loader_loadpricedaily.log" ]; then
    echo "Price Loader: $(tail -1 /tmp/loader_loadpricedaily.log)"
  fi

  # Show last line from main script
  if [ -f "/tmp/loader_run.log" ]; then
    echo "Main Script: $(tail -1 /tmp/loader_run.log | cut -c1-80)..."
  fi

  echo ""
  echo "Press Ctrl+C to stop monitoring"
  sleep 10
done
