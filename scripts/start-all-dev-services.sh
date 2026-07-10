#!/bin/bash
# Start all development services in parallel with monitoring

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

echo "=================================="
echo "Starting All Development Services"
echo "=================================="
echo ""

# Ensure Python environment is set up
if [ ! -d "venv" ]; then
    echo "[!] Python virtual environment not found."
    echo "[*] Creating venv..."
    python3 -m venv venv
    source venv/bin/activate
    pip install --quiet -r requirements.txt
else
    source venv/bin/activate
fi

# Start dev_server in background
echo "[1/2] Starting Python dev_server (port 3001)..."
cd api-pkg
python dev_server.py &
DEV_SERVER_PID=$!
sleep 2

# Check if dev_server started successfully
if ! kill -0 $DEV_SERVER_PID 2>/dev/null; then
    echo "[ERROR] Dev server failed to start. Check logs above."
    exit 1
fi
echo "[OK] Dev server running (PID: $DEV_SERVER_PID)"

# Return to root
cd "$SCRIPT_DIR"

# Start React dev server
echo "[2/2] Starting React dev server (port 5173)..."
cd webapp/frontend
npm run dev &
REACT_PID=$!
sleep 3

# Check if React server started
if ! kill -0 $REACT_PID 2>/dev/null; then
    echo "[ERROR] React server failed to start."
    kill $DEV_SERVER_PID 2>/dev/null || true
    exit 1
fi
echo "[OK] React server running (PID: $REACT_PID)"

echo ""
echo "=================================="
echo "✅ All services running!"
echo "=================================="
echo ""
echo "Dashboard:  http://localhost:5173"
echo "API:        http://localhost:3001"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Handle Ctrl+C to stop all services
cleanup() {
    echo ""
    echo "Stopping services..."
    kill $DEV_SERVER_PID 2>/dev/null || true
    kill $REACT_PID 2>/dev/null || true
    wait $DEV_SERVER_PID 2>/dev/null
    wait $REACT_PID 2>/dev/null
    echo "Done."
}

trap cleanup INT TERM

# Wait for both processes
wait
