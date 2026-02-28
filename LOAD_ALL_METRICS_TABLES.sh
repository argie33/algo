#!/bin/bash
# Load all missing metric tables to LOCAL + AWS

export PGPASSWORD='bed0elAn'
export DB_HOST='localhost'
export DB_USER='stocks'
export DB_PASSWORD='bed0elAn'
export DB_NAME='stocks'

cd /home/arger/algo

echo "🚀 LOADING ALL METRIC TABLES - LOCAL + AWS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Run all metrics loaders that exist
for loader in loadfactormetrics loadtechnicalindicators loadsectorranking loadstockscores; do
  if [ -f "${loader}.py" ]; then
    echo "▶️  Loading $loader..."
    timeout 3600 python3 -u "${loader}.py" 2>&1 | tail -20
    echo "✅ ${loader} complete"
    echo ""
  fi
done

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Metrics loading complete"
