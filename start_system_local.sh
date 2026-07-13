#!/bin/bash
# Local system startup - dev server + dashboard

set -e

echo "========================================"
echo "Algo Trading System - Local Startup"
echo "========================================"
echo

# Check if dev server is already running
if curl -s http://localhost:3001/api/algo/portfolio -H "Authorization: Bearer dev-admin" >/dev/null 2>&1; then
    echo "Dev server already running on port 3001"
else
    echo "Starting dev server on port 3001..."
    python3 lambda/api/dev_server.py &
    DEV_SERVER_PID=$!
    sleep 3
    echo "Dev server started (PID: $DEV_SERVER_PID)"
fi

echo
echo "Starting dashboard in local mode..."
echo "Press Ctrl+C to stop"
echo

python3 -m dashboard --local -w 30

# Clean up
if [ -n "$DEV_SERVER_PID" ]; then
    kill $DEV_SERVER_PID 2>/dev/null || true
fi
