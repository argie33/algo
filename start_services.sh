#!/bin/bash

echo "Starting backend..."
cd /home/stocks/algo/webapp/lambda
nohup node index.js > /tmp/backend.log 2>&1 &
sleep 3

echo "Starting frontend..."
cd /home/stocks/algo/webapp/frontend
nohup npm run dev > /tmp/frontend.log 2>&1 &
sleep 8

echo "Testing backend..."
curl -s http://localhost:3001/api/sectors/health | head

echo ""
echo "✅ Services should be running:"
echo "  Backend: http://localhost:3001"
echo "  Frontend: http://localhost:5173"
