#!/bin/bash

# Monitor all loaders and alert on issues
LOADERS=("loadpricedaily" "loadpriceweekly" "loadpricemonthly" "loadetfpricedaily" "loadetfpriceweekly" "loadetfpricemonthly")
LOG_DIR="/home/stocks/algo/logs"

# Function to check for errors
check_errors() {
    local logfile=$1
    local logname=$(basename $logfile)
    
    # Check for critical errors
    local error_count=$(grep -i "ERROR" "$logfile" 2>/dev/null | grep -v "period\|invalid\|delisted" | wc -l)
    local timeout_count=$(grep -i "timeout" "$logfile" 2>/dev/null | wc -l)
    local rate_limit_count=$(grep -i "rate limit\|Too Many Requests" "$logfile" 2>/dev/null | wc -l)
    
    if [ "$error_count" -gt 0 ]; then
        echo "⚠️  $logname: $error_count errors"
        grep "ERROR" "$logfile" 2>/dev/null | grep -v "period\|invalid\|delisted" | tail -3
    fi
    
    if [ "$timeout_count" -gt 5 ]; then
        echo "⚠️  $logname: $timeout_count timeouts (may need delay increase)"
    fi
    
    if [ "$rate_limit_count" -gt 10 ]; then
        echo "⚠️  $logname: $rate_limit_count rate limit hits (may need delay increase)"
    fi
}

# Monitor processes
echo "=== Loader Process Status ===" 
for loader in "${LOADERS[@]}"; do
    count=$(ps aux | grep "python3 $loader" | grep -v grep | wc -l)
    if [ "$count" -eq 0 ]; then
        echo "❌ $loader: NOT RUNNING - restarting..."
        cd /home/stocks/algo
        nohup python3 $loader.py > $LOG_DIR/$loader.log 2>&1 &
        sleep 1
    else
        echo "✅ $loader: Running"
    fi
done

# Check for errors in logs
echo ""
echo "=== Error Check ===" 
for loader in "${LOADERS[@]}"; do
    check_errors "$LOG_DIR/$loader.log"
done

# Show data coverage
echo ""
echo "=== Data Coverage ===" 
psql -h localhost -U stocks -d stocks -t -c "
SELECT 'price_daily: ' || COUNT(DISTINCT symbol) || '/5275' FROM price_daily
UNION ALL
SELECT 'price_weekly: ' || COUNT(DISTINCT symbol) || '/5275' FROM price_weekly
UNION ALL
SELECT 'price_monthly: ' || COUNT(DISTINCT symbol) || '/5275' FROM price_monthly
UNION ALL
SELECT 'etf_daily: ' || COUNT(DISTINCT symbol) || '/4863' FROM etf_price_daily
UNION ALL
SELECT 'etf_weekly: ' || COUNT(DISTINCT symbol) || '/4863' FROM etf_price_weekly
UNION ALL
SELECT 'etf_monthly: ' || COUNT(DISTINCT symbol) || '/4863' FROM etf_price_monthly;
" 2>/dev/null || echo "Database unavailable"

echo ""
echo "=== Latest Batch Progress ===" 
for loader in "${LOADERS[@]}"; do
    latest=$(tail -3 $LOG_DIR/$loader.log 2>/dev/null | grep -o "batch [0-9]*/" | tail -1)
    if [ -n "$latest" ]; then
        echo "$loader: $latest..."
    fi
done
