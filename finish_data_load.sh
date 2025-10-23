#!/bin/bash

# Kill the slow monitoring script
pkill -f "monitor_and_continue"

echo "🎯 Waiting for key metrics loader to finish..."
echo ""

# Wait for the log to show completion
while ! grep -q "✅ Complete" /home/stocks/algo/complete_load_20251023_031733.log; do
    sleep 10
    LAST_LINE=$(tail -1 /home/stocks/algo/complete_load_20251023_031733.log)
    echo "Status: $LAST_LINE"
done

echo ""
echo "✅ Key metrics loading complete!"
echo ""

# Get final counts
KEY_METRICS=$(psql -h localhost -U postgres -d stocks -c "SELECT COUNT(*) FROM key_metrics;" 2>/dev/null | sed -n '3p' | xargs)
echo "📊 Key metrics loaded: $KEY_METRICS"
echo ""

# Set database environment variables
export DB_HOST="localhost"
export DB_PORT="5432"
export DB_USER="postgres"
export DB_PASSWORD="password"
export DB_NAME="stocks"

# ==========================================
echo "⏳ Running Value Metrics Loader..."
echo "============================================"
python3 /home/stocks/algo/loadvaluemetrics.py 2>&1 | tail -50

echo ""
echo "============================================"
echo "⏳ Running Stock Scores Recalculation..."
echo "============================================"
python3 /home/stocks/algo/loadstockscores.py 2>&1 | tail -50

echo ""
echo "============================================"
echo "✅ DATA LOAD COMPLETE!"
echo "============================================"
echo ""

# Final data summary
psql -h localhost -U postgres -d stocks << 'EOF'
SELECT 
  COUNT(*) as total_symbols,
  SUM(CASE WHEN value_score IS NULL THEN 1 ELSE 0 END) as null_value_scores,
  SUM(CASE WHEN momentum_score IS NULL THEN 1 ELSE 0 END) as null_momentum_scores,
  SUM(CASE WHEN composite_score IS NULL THEN 1 ELSE 0 END) as null_composite_scores
FROM stock_scores;
EOF

