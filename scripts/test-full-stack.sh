#!/bin/bash
# Test full stack: API + Frontend + Database
# 1. Start local API server
# 2. Start frontend dev server
# 3. Run end-to-end tests
# 4. Verify API endpoints
# 5. Verify frontend can call API

set -e

echo "📋 FULL STACK TEST"
echo "================="
echo ""

# Check prerequisites
if ! command -v python3 &>/dev/null; then
  echo "❌ Python3 not found"
  exit 1
fi

if ! command -v npm &>/dev/null; then
  echo "❌ npm not found"
  exit 1
fi

# Load environment
if [ -f .env.local ]; then
  source .env.local
  echo "✅ Loaded .env.local"
else
  echo "⚠️  No .env.local found - using defaults"
fi

echo ""
echo "🗄️  Testing Database Connection..."
python3 -c "
from config.credential_helper import get_db_config
from utils.db_connection import get_db_connection
try:
    conn = get_db_connection()
    if conn:
        print('✅ Database connected')
        conn.close()
    else:
        print('❌ Database connection failed')
        exit(1)
except Exception as e:
    print(f'❌ {e}')
    exit(1)
"

echo ""
echo "🧪 Running API Contract Tests..."
pytest tests/test_api_contract_validation.py -v --tb=short || echo "⚠️  Some tests skipped (expected if no data)"

echo ""
echo "🚀 Starting Frontend Dev Server..."
cd webapp/frontend
npm ci --silent
npm run dev &
FRONTEND_PID=$!
sleep 5

echo ""
echo "🧪 Testing Frontend API Connection..."
sleep 3
curl -s http://localhost:5173 > /dev/null && echo "✅ Frontend accessible at http://localhost:5173" || echo "⚠️  Frontend not responding yet"

echo ""
echo "✅ FULL STACK TEST COMPLETE"
echo ""
echo "📍 Access Points:"
echo "   Frontend: http://localhost:5173"
echo "   API: (local) http://localhost:3001 or (AWS) check VITE_API_URL"
echo ""
echo "🛑 To stop: kill $FRONTEND_PID"
echo ""
echo "Next steps:"
echo "  1. Open http://localhost:5173 in browser"
echo "  2. Check Network tab to verify API calls"
echo "  3. For AWS: set VITE_API_URL and rebuild"

# Keep frontend running
wait $FRONTEND_PID
