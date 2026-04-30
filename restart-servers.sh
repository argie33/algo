#!/bin/bash
# Restart both API and Frontend servers

echo "🔴 Stopping all Node processes..."
pkill -9 node 2>/dev/null || true
pkill -9 npm 2>/dev/null || true
sleep 2

echo "🟢 Starting API server on port 3001..."
cd /c/Users/arger/code/algo/webapp/lambda
nohup node index.js > /tmp/api.log 2>&1 &
sleep 3

echo "🟢 Starting Frontend server on port 5173..."
cd /c/Users/arger/code/algo/webapp/frontend
rm -rf .vite 2>/dev/null || true
nohup npm run dev > /tmp/frontend.log 2>&1 &
sleep 8

echo ""
echo "⏳ Checking servers..."
echo ""

# Check API
if curl -s http://localhost:3001/api/health | grep -q "healthy"; then
    echo "✅ API is running on http://localhost:3001"
else
    echo "❌ API failed to start - check /tmp/api.log"
    tail -20 /tmp/api.log
    exit 1
fi

# Check Frontend
if curl -s http://localhost:5173 | grep -q "root"; then
    echo "✅ Frontend is running on http://localhost:5173"
else
    echo "❌ Frontend failed to start - check /tmp/frontend.log"
    tail -20 /tmp/frontend.log
    exit 1
fi

echo ""
echo "🎉 Both servers are running!"
echo ""
echo "Access the app at: http://localhost:5173"
