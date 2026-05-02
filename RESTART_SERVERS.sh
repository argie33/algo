#!/bin/bash
# Quick restart script for both servers with auto-restart
# Run this if servers crash: ./RESTART_SERVERS.sh

echo "Stopping PM2..."
pm2 kill

echo "Waiting 3 seconds..."
sleep 3

echo "Starting all servers with PM2 (auto-restart enabled)..."
PORT=3001 pm2 start node --name "api" -- webapp/lambda/index.js
sleep 3
pm2 start "npm run dev" --cwd webapp/frontend --name "frontend"

echo ""
echo "Waiting for startup..."
sleep 8

echo ""
echo "=== SERVER STATUS ==="
pm2 status

echo ""
echo "=== TESTING SERVERS ==="
echo "API (port 3001):"
curl -s http://localhost:3001/api/status | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  Status: {d[\"data\"][\"status\"]}')" 2>/dev/null || echo "  Not responding yet..."

echo "Frontend (port 5173):"
curl -s -o /dev/null -w "  HTTP %{http_code}\n" http://localhost:5173

echo ""
echo "✅ Servers running with auto-restart enabled"
echo "View logs with: pm2 logs"
echo "Restart anytime: ./RESTART_SERVERS.sh"
