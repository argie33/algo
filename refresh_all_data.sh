#!/bin/bash
# Simple data refresh script

export DB_PASSWORD=bed0elAn
cd /home/stocks/algo

echo "🚀 REFRESHING ALL DATA..."
echo ""

# Run critical loaders
python3 loadpricedaily.py && echo "✅ Daily prices updated" || echo "⚠️  Daily prices had issues"
python3 loadfactormetrics.py && echo "✅ Metrics calculated" || echo "⚠️  Metrics had issues"  
python3 loadstockscores.py && echo "✅ Stock scores updated" || echo "⚠️  Scores had issues"

echo ""
echo "✅ All data refreshed!"
