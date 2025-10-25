#!/bin/bash
# Monitor momentum loader and trigger loadstockscores when complete

echo "⏱️  Monitoring momentum loader..."
echo "Will start loadstockscores.py when momentum completes..."

# Check every 30 seconds
while true; do
    if ! pgrep -f "python3 loadmomentum.py" > /dev/null 2>&1; then
        echo "✅ Momentum loader completed!"
        sleep 2
        
        # Check final count
        FINAL_COUNT=$(psql -h localhost -U postgres -d stocks -c "SELECT COUNT(*) FROM momentum_metrics;" 2>/dev/null | tail -2 | head -1 | tr -d ' ')
        echo "📊 Final momentum metrics count: $FINAL_COUNT"
        
        # Now run loadstockscores
        echo "🚀 Starting loadstockscores.py..."
        cd /home/stocks/algo
        python3 loadstockscores.py 2>&1 | tee stockscores_run.log
        
        echo "✅ Stock scores reload complete!"
        exit 0
    fi
    
    # Show current progress
    CURRENT_COUNT=$(psql -h localhost -U postgres -d stocks -c "SELECT COUNT(*) FROM momentum_metrics;" 2>/dev/null | tail -2 | head -1 | tr -d ' ')
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Momentum metrics: $CURRENT_COUNT / ~5307"
    
    sleep 30
done
