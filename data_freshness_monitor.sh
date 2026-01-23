#!/bin/bash
# Continuous data freshness monitoring - runs every hour

MONITOR_LOG="/tmp/data_freshness_alerts.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

{
  echo "[$TIMESTAMP] === DATA FRESHNESS CHECK ==="
  
  # Check 1: Signal data freshness
  SIGNAL_DATE=$(psql -U stocks -d stocks -h localhost -c "SELECT MAX(date)::text FROM buy_sell_daily;" 2>&1 | grep -oE '2026-[0-9-]+' | tail -1)
  TODAY=$(date '+%Y-%m-%d')
  
  if [ "$SIGNAL_DATE" = "$TODAY" ]; then
    echo "✅ Signal data is TODAY"
  else
    echo "❌ ALERT: Signal data is STALE (latest: $SIGNAL_DATE, today: $TODAY)"
  fi
  
  # Check 2: Price data freshness
  PRICE_DATE=$(psql -U stocks -d stocks -h localhost -c "SELECT MAX(date)::text FROM price_daily;" 2>&1 | grep -oE '2026-[0-9-]+' | tail -1)
  
  if [ "$PRICE_DATE" = "$TODAY" ]; then
    echo "✅ Price data is TODAY"
  else
    echo "❌ ALERT: Price data is STALE (latest: $PRICE_DATE, today: $TODAY)"
  fi
  
  # Check 3: Loader processes
  STOCK_DAILY=$(pgrep -f "python3 loadbuyselldaily.py" | wc -l)
  PRICE_DAILY=$(pgrep -f "python3 loadpricedaily.py" | wc -l)
  
  if [ $STOCK_DAILY -gt 0 ] || [ $PRICE_DAILY -gt 0 ]; then
    echo "✅ Daily loaders running ($STOCK_DAILY stock daily, $PRICE_DAILY price daily)"
  else
    echo "⚠️  No daily loaders running (may have completed)"
  fi
  
  # Check 4: Record counts for today
  SIGNAL_COUNT=$(psql -U stocks -d stocks -h localhost -c "SELECT COUNT(*) FROM buy_sell_daily WHERE date = CURRENT_DATE;" 2>&1 | grep -oE '[0-9]+' | tail -1)
  PRICE_COUNT=$(psql -U stocks -d stocks -h localhost -c "SELECT COUNT(*) FROM price_daily WHERE date = CURRENT_DATE;" 2>&1 | grep -oE '[0-9]+' | tail -1)
  
  echo "📊 Today's data: $SIGNAL_COUNT signals, $PRICE_COUNT prices"
  
  if [ "$SIGNAL_DATE" != "$TODAY" ] || [ "$PRICE_DATE" != "$TODAY" ]; then
    echo "🚨 CRITICAL: Data not fresh - check loaders immediately!"
  fi
  
  echo ""
  
} >> "$MONITOR_LOG"

tail -20 "$MONITOR_LOG"
