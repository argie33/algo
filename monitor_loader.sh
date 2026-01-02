#!/bin/bash
# Monitor Stock Scores Loader Progress

echo "=========================================="
echo "📊 Stock Scores Loader - Progress Monitor"
echo "=========================================="
echo ""

# Check if loader is running
LOADER_PID=$(pgrep -f "python3 loadstockscores.py" | head -1)

if [ -z "$LOADER_PID" ]; then
    echo "❌ Loader is NOT running"
    echo ""
    echo "Start with: python3 loadstockscores.py"
    exit 1
fi

echo "✅ Loader is running (PID: $LOADER_PID)"
echo ""

# Get database counts
echo "Database Progress:"
echo "-----------------------------------------"

STOCK_COUNT=$(psql -h localhost -U stocks -d stocks -t -c "SELECT COUNT(*) FROM stock_scores;" 2>/dev/null | tr -d ' ')
TOTAL_STOCKS=5297

if [ -z "$STOCK_COUNT" ]; then
    STOCK_COUNT=0
fi

PERCENTAGE=$((STOCK_COUNT * 100 / TOTAL_STOCKS))

echo "Stocks Scored: $STOCK_COUNT / $TOTAL_STOCKS ($PERCENTAGE%)"
echo ""

# Calculate estimated time remaining
if [ "$STOCK_COUNT" -gt 0 ]; then
    # Get process start time and current time
    START_TIME=$(ps -p $LOADER_PID -o lstart= | xargs date +%s -d)
    CURRENT_TIME=$(date +%s)
    ELAPSED_SECONDS=$((CURRENT_TIME - START_TIME))

    # Calculate rate (stocks per second)
    RATE=$(echo "scale=2; $STOCK_COUNT / $ELAPSED_SECONDS" | bc)

    # Calculate estimated remaining time
    REMAINING_STOCKS=$((TOTAL_STOCKS - STOCK_COUNT))
    REMAINING_SECONDS=$(echo "$REMAINING_STOCKS / $RATE" | bc)
    REMAINING_HOURS=$((REMAINING_SECONDS / 3600))
    REMAINING_MINS=$(( (REMAINING_SECONDS % 3600) / 60 ))

    echo "Processing Rate: $RATE stocks/second"
    echo "Elapsed Time: $(($ELAPSED_SECONDS / 3600)) hours $(( ($ELAPSED_SECONDS % 3600) / 60 )) mins"
    echo "Estimated Time Remaining: $REMAINING_HOURS hours $REMAINING_MINS mins"
    echo ""
fi

# Check for errors in logs
ERROR_COUNT=$(grep -c "ERROR" /tmp/claude/-home-stocks-algo/tasks/b89398b.output 2>/dev/null || echo 0)
WARNING_COUNT=$(grep -c "WARNING" /tmp/claude/-home-stocks-algo/tasks/b89398b.output 2>/dev/null || echo 0)

echo "Errors & Warnings:"
echo "-----------------------------------------"
echo "Errors: $ERROR_COUNT"
echo "Warnings: $WARNING_COUNT"
echo ""

# Show last few completed stocks
echo "Recently Completed Stocks:"
echo "-----------------------------------------"
grep "✅.*Composite" /tmp/claude/-home-stocks-algo/tasks/b89398b.output 2>/dev/null | tail -5

echo ""
echo "=========================================="
echo "Last updated: $(date)"
echo "=========================================="
