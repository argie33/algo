#!/bin/bash

# Trading Signals Server - Clean Startup Script
# This ensures only ONE server instance runs at a time

echo "=================================================="
echo "Trading Signals API Server - Clean Startup"
echo "=================================================="

# Kill any existing Node processes
echo "Cleaning up old processes..."
ps aux | grep "node" | grep -v grep | awk '{print $2}' | while read pid; do
  kill -9 $pid 2>/dev/null
  echo "  Killed PID $pid"
done

# Wait for cleanup
sleep 2

# Start fresh server
echo ""
echo "Starting fresh server instance..."
cd "$(dirname "$0")"

# Run server in background
nohup node index.js > /tmp/api.log 2>&1 &
SERVER_PID=$!

echo "Server started with PID: $SERVER_PID"
echo ""

# Wait for server to boot
sleep 5

# Verify server is running
if curl -s http://localhost:3001/api/status > /dev/null 2>&1; then
  echo "SUCCESS: Server is responding on port 3001"
  echo ""
  echo "Available endpoints:"
  echo "  - Swing Trading:    http://localhost:3001/api/signals"
  echo "  - Range Trading:    http://localhost:3001/api/signals/range"
  echo "  - Mean Reversion:   http://localhost:3001/api/signals/mean-reversion"
  echo ""
  echo "Logs available at: /tmp/api.log"
  echo ""
  echo "To stop server: kill $SERVER_PID"
else
  echo "ERROR: Server failed to start"
  echo "Check logs: tail -100 /tmp/api.log"
  exit 1
fi
