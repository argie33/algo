#!/bin/bash
# EMERGENCY CLEANUP - Run this when system is about to crash

set +e  # Don't exit on error

echo "🚨 EMERGENCY MEMORY CLEANUP"
echo "================================"

# Kill all loaders
echo "Killing all data loaders..."
pkill -9 -f "load.*\.py" 2>/dev/null
pkill -9 -f "loadprice" 2>/dev/null
pkill -9 -f "loadsignal" 2>/dev/null
pkill -9 -f "loadfinancial" 2>/dev/null

# Kill dev servers
echo "Killing dev servers..."
pkill -9 -f "vite" 2>/dev/null
pkill -9 -f "webpack" 2>/dev/null
pkill -9 node 2>/dev/null
pkill -9 npm 2>/dev/null

# Wait for cleanup
sleep 3

# Show memory
echo ""
echo "Memory status after cleanup:"
free -h
echo ""
echo "✅ Ready for safe sequential loading"
echo ""
echo "Next step: bash /home/arger/algo/safe_loaders.sh"
