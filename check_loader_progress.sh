#!/bin/bash
# Check loader progress in real-time

echo "=================================="
echo "BASE PATTERN DETECTION - PROGRESS"
echo "=================================="
echo ""
echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# Check database
echo "Database Status:"
psql -h localhost -U stocks -d stocks -t -c "
  SELECT
    'Total signals' as metric,
    COUNT(*) as value
  FROM buy_sell_daily
  UNION ALL
  SELECT 'Patterns detected', COUNT(*)
  FROM buy_sell_daily
  WHERE base_type IS NOT NULL
  UNION ALL
  SELECT 'Detection rate (%)',
    ROUND(COUNT(*) * 100.0 / 741686, 1)
  FROM buy_sell_daily
  WHERE base_type IS NOT NULL
" 2>/dev/null || echo "Database offline"

echo ""
echo "Pattern Distribution:"
psql -h localhost -U stocks -d stocks -t -c "
  SELECT
    COALESCE(base_type, 'Unknown') as pattern,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / 741686, 1) as pct
  FROM buy_sell_daily
  GROUP BY COALESCE(base_type, 'Unknown')
  ORDER BY count DESC
" 2>/dev/null || echo "Database offline"

echo ""
echo "Run Status:"
if ps aux | grep -q "[l]oaddaily.py"; then
    echo "Status: RUNNING"
    uptime | awk '{print "Uptime:", $NF}'
else
    echo "Status: IDLE (check if completed or check output file)"
fi

echo ""
echo "=================================="
echo "Run this again to see progress"
