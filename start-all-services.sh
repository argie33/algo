#!/bin/bash
# Complete startup script for all services
# Ensures proper API connectivity and configuration

set -e

echo "=========================================="
echo "Starting All Services"
echo "=========================================="
echo ""

# Kill any existing processes
echo "📋 Cleaning up existing processes..."
pkill -f "node.*index.js" 2>/dev/null || true
pkill -f "node.*vite" 2>/dev/null || true
pkill -f "npm.*frontend" 2>/dev/null || true
sleep 2

# Start PostgreSQL check
echo "📊 Checking PostgreSQL..."
if ! pg_isready -h localhost -p 5432 > /dev/null 2>&1; then
    echo "❌ PostgreSQL not running on localhost:5432"
    exit 1
fi
echo "✅ PostgreSQL running"
echo ""

# Start Backend
echo "🚀 Starting Backend API (:3001)..."
cd /home/stocks/algo/webapp/lambda
npm start > /tmp/backend.log 2>&1 &
BACKEND_PID=$!
sleep 8

# Check backend is running
if ! lsof -i :3001 > /dev/null 2>&1; then
    echo "❌ Backend failed to start"
    cat /tmp/backend.log | tail -20
    exit 1
fi
echo "✅ Backend running on :3001 (PID: $BACKEND_PID)"
echo ""

# Start Frontend with API_URL env var
echo "🎨 Starting Frontend (:5173/5174/5175...)..."
cd /home/stocks/algo/webapp/frontend

# Set API_URL environment variable before running setup-dev
export API_URL="http://localhost:3001"
export VITE_API_URL="http://localhost:3001"

npm start > /tmp/frontend.log 2>&1 &
FRONTEND_PID=$!
sleep 15

# Check frontend is running
if ! lsof -i :5173 2>/dev/null | grep -q node && \
   ! lsof -i :5174 2>/dev/null | grep -q node && \
   ! lsof -i :5175 2>/dev/null | grep -q node && \
   ! lsof -i :5176 2>/dev/null | grep -q node; then
    echo "❌ Frontend failed to start"
    cat /tmp/frontend.log | tail -20
    exit 1
fi

FRONTEND_PORT=$(lsof -i :51* 2>/dev/null | grep node | head -1 | awk '{print $9}' | cut -d':' -f2)
echo "✅ Frontend running on :$FRONTEND_PORT (PID: $FRONTEND_PID)"
echo ""

# Verify configuration
echo "🔍 Verifying Configuration..."
CONFIG_CHECK=$(grep -o "localhost:3001" /home/stocks/algo/webapp/frontend/public/config.js || echo "NOT_FOUND")
if [ "$CONFIG_CHECK" = "localhost:3001" ]; then
    echo "✅ Frontend API config: localhost:3001 (CORRECT)"
else
    echo "❌ Frontend API config is WRONG"
    cat /home/stocks/algo/webapp/frontend/public/config.js
    exit 1
fi
echo ""

# Test API connectivity
echo "🧪 Testing API Connectivity..."
if timeout 5 curl -s http://localhost:3001/api/scores > /dev/null 2>&1; then
    echo "✅ Backend API responding"
else
    echo "❌ Backend API not responding"
    exit 1
fi
echo ""

echo "=========================================="
echo "✅ ALL SERVICES RUNNING SUCCESSFULLY"
echo "=========================================="
echo ""
echo "📊 Backend API:  http://localhost:3001"
echo "🎨 Frontend:     http://localhost:$FRONTEND_PORT"
echo "📡 Database:     localhost:5432"
echo ""
echo "🔗 Frontend API Configuration:"
echo "   API_URL = http://localhost:3001"
echo ""
echo "To stop all services:"
echo "  kill $BACKEND_PID $FRONTEND_PID"
echo ""
echo "To view logs:"
echo "  tail -f /tmp/backend.log   (Backend)"
echo "  tail -f /tmp/frontend.log  (Frontend)"
echo ""
