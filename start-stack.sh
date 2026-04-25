#!/bin/bash

echo "🚀 Starting API server (port 3001)..."
node webapp/lambda/index.js > /tmp/api.log 2>&1 &
API_PID=$!

sleep 2

echo "📊 Testing API..."
curl -s "http://localhost:3001/api/signals/stocks?timeframe=daily&limit=5" | head -c 200

echo ""
echo "✅ API is running (PID: $API_PID)"
echo ""
echo "🎨 Starting frontend dev server (port 5174)..."
cd webapp/frontend-admin
npm run dev > /tmp/frontend.log 2>&1 &
FRONTEND_PID=$!

sleep 3

echo "✅ Frontend is running (PID: $FRONTEND_PID)"
echo ""
echo "📱 Open browser: http://localhost:5174"
echo ""
echo "Logs:"
echo "  API: tail -f /tmp/api.log"
echo "  Frontend: tail -f /tmp/frontend.log"
echo ""
echo "PIDs: API=$API_PID, Frontend=$FRONTEND_PID"
