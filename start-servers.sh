#!/bin/bash
set -e

cd /c/Users/arger/code/algo

echo "=== Starting Financial Dashboard ==="
echo "Killing any existing node processes..."
pkill -f "node" 2>/dev/null || true
sleep 2

echo "Starting API server on port 3001..."
nohup node webapp/lambda/index.js > api.log 2>&1 &
API_PID=$!
echo "API started with PID $API_PID"

sleep 5

echo "Checking API health..."
for i in {1..10}; do
  if curl -s http://localhost:3001/api/status > /dev/null 2>&1; then
    echo "✅ API is responding"
    break
  fi
  if [ $i -eq 10 ]; then
    echo "❌ API failed to start"
    exit 1
  fi
  sleep 1
done

echo ""
echo "Starting Frontend server on port 5173..."
cd webapp/frontend
nohup npm run dev > frontend.log 2>&1 &
FRONTEND_PID=$!
echo "Frontend started with PID $FRONTEND_PID"

sleep 8

echo ""
echo "=== SERVERS RUNNING ==="
echo "API: http://localhost:3001/api/status"
echo "Frontend: http://localhost:5173"
echo ""
echo "Monitor logs with:"
echo "  tail -f api.log"
echo "  tail -f webapp/frontend/frontend.log"
