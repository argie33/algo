#!/bin/bash
# Full-stack startup script for Stock Analytics Platform
# Starts: Database, Backend API, Frontend, Orchestrator

set -e

echo "=========================================="
echo "STOCK ANALYTICS PLATFORM - FULL STACK"
echo "=========================================="
echo ""

# Set environment variables
export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=stocks
export DB_PASSWORD=postgres
export DB_NAME=stocks
export APCA_API_KEY_ID="PKAZZLZK2HX7JB6P7GBVDORY76"
export APCA_API_SECRET_KEY="HEzu13fSdQwwDStWWwjEFyh25XjE17cfM9uJ7267mK73"
export APCA_API_BASE_URL="https://paper-api.alpaca.markets"
export FRED_API_KEY="450ae65f7efbaedbd1f1a8bb02582fcb"

echo "✓ Environment variables configured"
echo ""

# Check database connection
echo "Checking database connection..."
python3 -c "
import psycopg2
import os
try:
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST'),
        port=int(os.getenv('DB_PORT')),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME')
    )
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM price_daily')
    count = cur.fetchone()[0]
    print(f'✓ Database connected ({count:,} price records)')
    cur.close()
    conn.close()
except Exception as e:
    print(f'✗ Database error: {e}')
    exit(1)
" 2>&1

echo ""
echo "=========================================="
echo "COMPONENT STARTUP"
echo "=========================================="
echo ""

# Function to run in background with trap handling
run_service() {
    local name=$1
    local cmd=$2
    local port=$3

    echo "Starting: $name"
    $cmd &
    local pid=$!
    echo "  ✓ PID: $pid (port: $port)"
    sleep 2
}

# Start Backend API Server
echo "[1/2] Backend API Server"
run_service "API Server" "python3 server.py" "3001"

# Start Frontend Dev Server
echo "[2/2] Frontend Dev Server"
cd webapp/frontend
run_service "Frontend" "npm run dev" "5173"
cd ../..

echo ""
echo "=========================================="
echo "SYSTEM READY"
echo "=========================================="
echo ""
echo "🌐 Access the Platform:"
echo "  Frontend:     http://localhost:5173"
echo "  API Server:   http://localhost:3001"
echo "  Health Check: http://localhost:3001/health"
echo ""
echo "📊 Test the Orchestrator:"
echo "  python3 algo/algo_orchestrator.py --dry-run"
echo ""
echo "🧪 Run Tests:"
echo "  Backend:  python3 -m pytest tests/ -v"
echo "  Frontend: cd webapp/frontend && npm test"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Keep the script running
wait
