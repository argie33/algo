#!/bin/bash
# Start local development environment with dev_server + dashboard
# Usage: bash scripts/start_dev_environment.sh

set -e

echo "==========================================="
echo "Starting Algo Dev Environment"
echo "==========================================="

# Check if dev_server is already running
if netstat -an 2>/dev/null | grep -q "3001.*LISTENING"; then
    echo "[OK] Dev server already running on port 3001"
    DEV_SERVER_RUNNING=true
else
    echo "[INFO] Starting dev_server on port 3001..."
    python3 api-pkg/dev_server.py &
    DEV_SERVER_PID=$!
    echo "[OK] Dev server started (PID: $DEV_SERVER_PID)"
    sleep 3
    DEV_SERVER_RUNNING=false
fi

# Wait for dev_server to be responsive
echo "[INFO] Waiting for dev_server to respond..."
MAX_ATTEMPTS=30
ATTEMPT=0
while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if curl -s http://localhost:3001/api/sectors -H "Authorization: Bearer dev-admin" > /dev/null 2>&1; then
        echo "[OK] Dev server is responsive"
        break
    fi
    ATTEMPT=$((ATTEMPT + 1))
    if [ $ATTEMPT -lt $MAX_ATTEMPTS ]; then
        sleep 1
    fi
done

if [ $ATTEMPT -ge $MAX_ATTEMPTS ]; then
    echo "[ERROR] Dev server did not respond after $MAX_ATTEMPTS seconds"
    exit 1
fi

# Start dashboard
echo ""
echo "[INFO] Starting dashboard..."
echo "Press Ctrl+C to stop both services"
echo ""

python3 -m dashboard --local

# Cleanup: kill dev_server if we started it
if [ "$DEV_SERVER_RUNNING" = false ] && [ -n "$DEV_SERVER_PID" ]; then
    echo ""
    echo "[INFO] Cleaning up dev_server..."
    kill $DEV_SERVER_PID 2>/dev/null || true
fi
