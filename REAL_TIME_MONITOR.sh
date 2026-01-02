#!/bin/bash
# Real-time data loading monitor with detailed error tracking

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║          REAL-TIME DATA LOADING MONITOR                       ║"
echo "║     Tracking: Scores, Prices, Earnings - AUTO-UPDATING       ║"
echo "╚════════════════════════════════════════════════════════════════╝"

while true; do
    clear
    echo "═══════════════════════════════════════════════════════════════"
    echo "STATUS: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    
    # Get all metrics in one DB call
    psql -h localhost -U stocks -d stocks << 'SQL' 2>/dev/null
\pset format unaligned
SELECT '📊 STOCK SCORES' as metric;
SELECT 'Calculated: ' || COUNT(*) || ' / 5300 (' || ROUND(COUNT()*100.0/5300,1) || '%)' FROM stock_scores;
SELECT 'Status: ' || CASE WHEN COUNT() >= 5300 THEN '✅ COMPLETE' ELSE '🔄 LOADING' END FROM stock_scores;

SELECT '';
SELECT '💰 PRICE DATA' as metric;
SELECT 'Daily (stocks): ' || COUNT(*) || ' rows, Latest: ' || COALESCE(MAX(date)::text, 'NULL') FROM price_daily;
SELECT 'Weekly (stocks): ' || COUNT(*) || ' rows, Latest: ' || COALESCE(MAX(date)::text, 'NULL') FROM price_weekly;
SELECT 'Monthly (stocks): ' || COUNT(*) || ' rows, Latest: ' || COALESCE(MAX(date)::text, 'NULL') FROM price_monthly;
SELECT 'Daily (ETFs): ' || COUNT(*) || ' rows, Latest: ' || COALESCE(MAX(date)::text, 'NULL') FROM etf_price_daily;
SELECT 'Weekly (ETFs): ' || COUNT(*) || ' rows, Latest: ' || COALESCE(MAX(date)::text, 'NULL') FROM etf_price_weekly;
SELECT 'Monthly (ETFs): ' || COUNT(*) || ' rows, Latest: ' || COALESCE(MAX(date)::text, 'NULL') FROM etf_price_monthly;

SELECT '';
SELECT '📋 FINANCIALS' as metric;
SELECT 'Earnings History: ' || COUNT(*) || ' rows' FROM earnings_history;
SELECT 'Earnings Estimates: ' || COUNT(*) || ' rows' FROM earnings_estimates;

SELECT '';
SELECT '⚙️ ACTIVE PROCESSES' as metric;
SQL

    # Count active loaders
    ACTIVE=$(ps aux | grep python3 | grep -E 'load|score' | grep -v grep | wc -l)
    echo "Active Loaders: $ACTIVE"
    echo ""
    
    # Check for errors in logs
    echo "═══════════════════════════════════════════════════════════════"
    echo "⚠️  RECENT ERRORS:"
    echo "═══════════════════════════════════════════════════════════════"
    
    if [ -f /home/stocks/algo/loadstockscores_run.log ]; then
        grep -i "error\|exception\|failed" /home/stocks/algo/loadstockscores_run.log 2>/dev/null | tail -5 || echo "No errors in score log"
    fi
    
    if [ -f /home/stocks/algo/loaddailycompanydata_run.log ]; then
        grep -i "error.*500" /home/stocks/algo/loaddailycompanydata_run.log 2>/dev/null | tail -3 || echo "No HTTP 500 errors in company data log"
    fi
    
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "🚀 NEXT STEPS (when scores reach 5300):"
    echo "   1. Update daily/monthly prices to 2025-12-31"
    echo "   2. Final verification"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    echo "Updating every 30 seconds... (Ctrl+C to stop)"
    sleep 30
done
