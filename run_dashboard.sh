#!/bin/bash
# Proper startup sequence for dashboard development

set -e

echo "[1] Starting dev server..."
python3 api-pkg/dev_server.py &
DEV_SERVER_PID=$!

# Wait for dev server to be ready
echo "[2] Waiting for dev server to be ready..."
for i in {1..30}; do
    if curl -s -H "Authorization: Bearer dev-admin" http://localhost:3001/api/algo/config > /dev/null 2>&1; then
        echo "[OK] Dev server is ready!"
        break
    fi
    sleep 1
    if [ $i -eq 30 ]; then
        echo "[FAILED] Dev server didn't start in time"
        kill $DEV_SERVER_PID 2>/dev/null || true
        exit 1
    fi
done

# Wait a bit more to let dev server fully initialize
sleep 1

echo "[3] Starting dashboard with --local flag..."
python3 -m dashboard --local -w 30

# Cleanup on exit
trap "kill $DEV_SERVER_PID 2>/dev/null || true" EXIT
