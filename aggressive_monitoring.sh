#!/bin/bash
# Ultra-aggressive monitoring - catches everything that could fail

ALERT_LOG="/tmp/loader_health_alerts.log"
DB_CONFIG="-U stocks -d stocks -h localhost"

check_critical_failures() {
  local TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
  
  # FAIL 1: No today's data at all
  PRICE_TODAY=$(psql $DB_CONFIG -c "SELECT COUNT(*) FROM price_daily WHERE date = CURRENT_DATE;" 2>&1 | grep -E '^\s+[0-9]+\s*$' | xargs)
  if [ -z "$PRICE_TODAY" ] || [ "$PRICE_TODAY" -eq 0 ]; then
    echo "[$TIMESTAMP] 🚨 CRITICAL: Zero price records for today!" >> "$ALERT_LOG"
    return 1
  fi
  
  # FAIL 2: Data completely stale
  LATEST_PRICE=$(psql $DB_CONFIG -c "SELECT MAX(date)::text FROM price_daily;" 2>&1 | grep -oE '2026-[0-9-]+' | tail -1)
  if [ "$LATEST_PRICE" != "$(date '+%Y-%m-%d')" ]; then
    echo "[$TIMESTAMP] 🚨 CRITICAL: Latest price is $LATEST_PRICE, not today!" >> "$ALERT_LOG"
    return 1
  fi
  
  # FAIL 3: Hung database transaction (>1 hour old)
  HUNG_TXN=$(psql $DB_CONFIG -c "SELECT COUNT(*) FROM pg_stat_activity WHERE state = 'idle in transaction' AND (now() - query_start) > interval '1 hour';" 2>&1 | grep -E '^\s+[0-9]+\s*$' | xargs)
  if [ "$HUNG_TXN" -gt 0 ]; then
    echo "[$TIMESTAMP] 🚨 CRITICAL: $HUNG_TXN stuck transactions >1 hour!" >> "$ALERT_LOG"
    return 1
  fi
  
  # FAIL 4: Process using too much memory (>80% RAM)
  for proc in loadbuyselldaily loadpricedaily; do
    MEM=$(ps aux | grep "$proc" | grep -v grep | awk '{print $4}' | head -1)
    if [ ! -z "$MEM" ] && [ $(echo "$MEM > 80" | bc) -eq 1 ]; then
      echo "[$TIMESTAMP] 🚨 WARNING: $proc using ${MEM}% memory!" >> "$ALERT_LOG"
    fi
  done
  
  # FAIL 5: Records dropped dramatically (compare to yesterday)
  TODAY_COUNT=$(psql $DB_CONFIG -c "SELECT COUNT(*) FROM price_daily WHERE date = CURRENT_DATE;" 2>&1 | grep -E '^\s+[0-9]+\s*$' | xargs)
  YESTERDAY_COUNT=$(psql $DB_CONFIG -c "SELECT COUNT(*) FROM price_daily WHERE date = CURRENT_DATE - 1;" 2>&1 | grep -E '^\s+[0-9]+\s*$' | xargs)
  
  if [ ! -z "$TODAY_COUNT" ] && [ ! -z "$YESTERDAY_COUNT" ]; then
    RATIO=$(echo "scale=2; $TODAY_COUNT / $YESTERDAY_COUNT" | bc)
    if [ $(echo "$RATIO < 0.5" | bc) -eq 1 ]; then
      echo "[$TIMESTAMP] 🚨 CRITICAL: Today's records ($TODAY_COUNT) < 50% of yesterday ($YESTERDAY_COUNT)!" >> "$ALERT_LOG"
      return 1
    fi
  fi
  
  # FAIL 6: Symbol mismatch (loader using wrong symbol list)
  SYMBOLS_IN_DB=$(psql $DB_CONFIG -c "SELECT COUNT(*) FROM stock_symbols;" 2>&1 | grep -E '^\s+[0-9]+\s*$' | xargs)
  SYMBOLS_IN_PRICES=$(psql $DB_CONFIG -c "SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = CURRENT_DATE;" 2>&1 | grep -E '^\s+[0-9]+\s*$' | xargs)
  
  if [ "$SYMBOLS_IN_PRICES" -lt "$((SYMBOLS_IN_DB / 2))" ]; then
    echo "[$TIMESTAMP] ⚠️  WARNING: Only $SYMBOLS_IN_PRICES/$SYMBOLS_IN_DB symbols loaded today" >> "$ALERT_LOG"
  fi
  
  # FAIL 7: Loader not updating logs (stuck with no progress)
  for loader in loadbuyselldaily loadpricedaily; do
    LAST_LOG_TIME=$(ls -t /tmp/${loader}* 2>/dev/null | head -1 | xargs stat -c %Y 2>/dev/null || echo 0)
    CURRENT_TIME=$(date +%s)
    TIME_DIFF=$((CURRENT_TIME - LAST_LOG_TIME))
    
    if [ $TIME_DIFF -gt 1800 ]; then  # 30 minutes no update
      if pgrep -f "$loader" > /dev/null; then
        echo "[$TIMESTAMP] 🚨 CRITICAL: $loader running but no log updates for 30+ minutes!" >> "$ALERT_LOG"
      fi
    fi
  done
}

# Run all checks
check_critical_failures

# Summary
echo ""
echo "=== LOADER HEALTH CHECK SUMMARY ==="
tail -20 "$ALERT_LOG" 2>/dev/null || echo "✅ No alerts (system healthy)"

