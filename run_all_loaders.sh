#!/bin/bash
# Comprehensive data loader orchestration script

export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=postgres
export DB_PASSWORD=password
export DB_NAME=stocks

echo "🚀 STARTING ALL DATA LOADERS"
echo "================================"

# Kill any existing processes
pkill -f "python3 load.*\.py" 2>/dev/null
sleep 2

# Start price loader
echo "📊 Starting price data loader..."
python3 loadpricedaily.py 2>&1 | tee /tmp/load_prices.log &
PRICE_PID=$!
echo "   ✅ PID: $PRICE_PID"

sleep 2

# Start technical loader
echo "📈 Starting technical data loader..."
python3 loadtechnicalsdaily.py 2>&1 | tee /tmp/load_technical.log &
TECH_PID=$!
echo "   ✅ PID: $TECH_PID"

sleep 2

# Start scores loader
echo "🎯 Starting stock scores loader..."
python3 loadstockscores.py 2>&1 | tee /tmp/load_scores.log &
SCORES_PID=$!
echo "   ✅ PID: $SCORES_PID"

sleep 2

# Start signals loader
echo "🎯 Starting trading signals loader..."
python3 loadbuyselldaily.py 2>&1 | tee /tmp/load_signals.log &
SIGNALS_PID=$!
echo "   ✅ PID: $SIGNALS_PID"

echo ""
echo "📊 All loaders started!"
echo ""
echo "Monitor progress with:"
echo "  tail -f /tmp/load_prices.log"
echo "  tail -f /tmp/load_technical.log"
echo "  tail -f /tmp/load_scores.log"
echo "  tail -f /tmp/load_signals.log"
echo ""

# Keep monitoring
sleep 5
ps aux | grep "python3 load" | grep -v grep | wc -l | xargs echo "Active loaders:"
