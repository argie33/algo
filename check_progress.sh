#!/bin/bash
echo "=========================================="
echo "DATA LOADING PROGRESS - $(date)"
echo "=========================================="
echo ""
echo "📊 LOADER 1: loaddailycompanydata.py"
COMPANY_PROGRESS=$(grep "✅" loaddailycompanydata_run.log 2>/dev/null | wc -l || echo "0")
echo "  Stocks processed: $COMPANY_PROGRESS / 5300"
LAST_COMPANY=$(tail -5 loaddailycompanydata_run.log 2>/dev/null | grep "✅" | tail -1 | cut -d: -f5 | cut -d'{' -f1 | tr -d ' ')
if [ -n "$LAST_COMPANY" ]; then
  echo "  Last stock: $LAST_COMPANY"
fi
echo ""

echo "💰 LOADER 2: loadstockscores.py"
if grep -q "Processing.*[0-9]" loadstockscores_run.log 2>/dev/null; then
  STOCKS_SCORING=$(grep "Processing.*[0-9]" loadstockscores_run.log 2>/dev/null | tail -1 | grep -o "[0-9]\+/[0-9]\+" || echo "?")
  echo "  Stocks scored: $STOCKS_SCORING"
  LAST_SYMBOL=$(tail -10 loadstockscores_run.log 2>/dev/null | grep "✅" | tail -1 | awk '{print $2}' | cut -d: -f1)
  if [ -n "$LAST_SYMBOL" ]; then
    echo "  Last stock: $LAST_SYMBOL"
  fi
else
  echo "  Status: Loading metrics..."
fi
echo ""

echo "📈 DATABASE STATUS"
psql -h localhost -U stocks -d stocks -c "
SELECT 
  'stock_scores' as table_name, COUNT(*) as rows FROM stock_scores
UNION ALL
SELECT 'earnings_history', COUNT(*) FROM earnings_history
UNION ALL  
SELECT 'key_metrics', COUNT(*) FROM key_metrics
ORDER BY 1;" 2>/dev/null
echo ""
echo "=========================================="
