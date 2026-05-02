#!/bin/bash
# Simple progress checker - run anytime to see loader status

echo "========== BASE PATTERN LOADER - PROGRESS =========="
echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# Recent log
echo "Recent activity (last 5 lines):"
tail -5 /tmp/loader_output.log 2>/dev/null | sed 's/^/  /'
echo ""

# Check if running
if ps aux | grep -q "[l]oaddaily.py"; then
    echo "Status: RUNNING"
else
    echo "Status: IDLE (may be complete)"
fi

echo ""
echo "Database patterns (Tier 1 professional detection):"
psql -h localhost -U stocks -d stocks -t -c "
  SELECT COALESCE(base_type, 'None detected') as pattern, COUNT(*) as count, ROUND(COUNT()*100.0/741686,1) as pct
  FROM buy_sell_daily
  WHERE base_type IN ('Cup', 'Flat Base', 'Double Bottom', 'Base on Base') OR base_type IS NULL
  GROUP BY COALESCE(base_type, 'None detected')
  ORDER BY count DESC
" 2>/dev/null | while read line; do echo "  $line"; done

echo ""
echo "View full log:"
echo "  tail -50 /tmp/loader_output.log"
echo ""
