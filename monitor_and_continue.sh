#!/bin/bash

# Monitor key metrics loader and automatically continue with value metrics and scores

LOG_FILE="/home/stocks/algo/complete_load_20251023_031733.log"

echo "🔍 Monitoring key metrics loader..."
echo "Log file: $LOG_FILE"
echo ""

# Wait for key metrics loader to complete
while true; do
    sleep 30

    if tail -1 "$LOG_FILE" 2>/dev/null | grep -q "✅ Complete"; then
        echo "✅ Key metrics loading complete!"
        break
    fi

    # Show current progress
    LAST_PROGRESS=$(tail -20 "$LOG_FILE" | grep "Progress:" | tail -1)
    if [ ! -z "$LAST_PROGRESS" ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - $LAST_PROGRESS"
    fi
done

echo ""
echo "=" | sed 's/./-/g' | head -c 80
echo ""
echo "🔄 Key metrics complete. Starting value metrics loader..."
echo ""

# Set database environment variables
export DB_HOST="localhost"
export DB_PORT="5432"
export DB_USER="postgres"
export DB_PASSWORD="password"
export DB_NAME="stocks"

# Step 2: Load value metrics
VALUE_METRICS_LOG="/home/stocks/algo/valuemetrics_$(date +%Y%m%d_%H%M%S).log"
echo "⏳ Loading value metrics... (log: $VALUE_METRICS_LOG)"
python3 /home/stocks/algo/loadvaluemetrics.py 2>&1 | tee "$VALUE_METRICS_LOG"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Value metrics complete!"

    # Step 3: Recalculate stock scores
    echo ""
    echo "=" | sed 's/./-/g' | head -c 80
    echo ""
    echo "🎯 Recalculating stock scores..."
    SCORES_LOG="/home/stocks/algo/stockscores_$(date +%Y%m%d_%H%M%S).log"
    echo "⏳ Loading stock scores... (log: $SCORES_LOG)"
    python3 /home/stocks/algo/loadstockscores.py 2>&1 | tee "$SCORES_LOG"

    if [ $? -eq 0 ]; then
        echo ""
        echo "=" | sed 's/./-/g' | head -c 80
        echo ""
        echo "🎉 COMPLETE DATA LOAD SEQUENCE FINISHED!"
        echo ""
        echo "Summary:"
        echo "  ✅ Step 1: Key metrics loaded"
        echo "  ✅ Step 2: Value metrics calculated"
        echo "  ✅ Step 3: Stock scores recalculated"
        echo ""
        echo "Log files:"
        echo "  - Key metrics:    $LOG_FILE"
        echo "  - Value metrics:  $VALUE_METRICS_LOG"
        echo "  - Stock scores:   $SCORES_LOG"
        echo ""
    else
        echo "❌ Stock scores loader failed!"
        echo "Check log: $SCORES_LOG"
        exit 1
    fi
else
    echo "❌ Value metrics loader failed!"
    echo "Check log: $VALUE_METRICS_LOG"
    exit 1
fi
