#!/bin/bash
set -e

echo "🚀 Starting Financial Dashboard (API + Frontend)..."
echo ""

# Check if PM2 is installed globally
if ! command -v pm2 &> /dev/null; then
  echo "📦 Installing PM2..."
  npm install -g pm2 > /dev/null 2>&1
fi

# Stop any existing processes
pm2 delete-all 2>/dev/null || true
sleep 2

# Start API server
echo "📡 Starting API server (port 3001)..."
cd /c/Users/arger/code/algo
pm2 start webapp/lambda/index.js --name "api" --env NODE_ENV=development > /dev/null 2>&1

# Start Frontend server
echo "🎨 Starting Frontend (port 5173)..."
cd /c/Users/arger/code/algo/webapp/frontend
pm2 start "npm run dev" --name "frontend" --env NODE_ENV=development > /dev/null 2>&1

# Save PM2 process list
pm2 save > /dev/null 2>&1

# Wait for servers to start
sleep 5

# Show status
echo ""
echo "✅ Servers started!"
echo ""
pm2 list
echo ""
echo "📊 API:      http://localhost:3001/api/status"
echo "🎨 Frontend: http://localhost:5173"
echo ""
echo "💡 Commands:"
echo "   pm2 logs api        - View API logs"
echo "   pm2 logs frontend   - View Frontend logs"
echo "   pm2 logs           - View all logs"
echo "   pm2 stop all       - Stop all services"
echo "   pm2 restart all    - Restart all services"
echo ""
