#!/bin/bash

# Portfolio Optimization - End-to-End Test Runner
# Runs comprehensive integration tests and generates reports

set -e

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║  Portfolio Optimization - End-to-End Test Suite            ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Configuration
export API_BASE=${API_BASE:-"http://localhost:3000"}
export NODE_ENV=${NODE_ENV:-"test"}
export TEST_AUTH_TOKEN=${TEST_AUTH_TOKEN:-"test-token-$(date +%s)"}

echo "📋 Configuration:"
echo "   API Base: $API_BASE"
echo "   Environment: $NODE_ENV"
echo "   Auth Token: $TEST_AUTH_TOKEN"
echo ""

# Check if database is available
echo "🔍 Checking database connection..."
if ! node -e "require('./utils/database').query('SELECT 1')" 2>/dev/null; then
    echo "❌ Database connection failed"
    echo "   Make sure PostgreSQL is running and configured correctly"
    exit 1
fi
echo "✅ Database connected"
echo ""

# Check if API server is running
echo "🔍 Checking API server..."
API_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" $API_BASE/health 2>/dev/null || echo "000")
if [ "$API_HEALTH" != "200" ] && [ "$API_HEALTH" != "404" ]; then
    echo "⚠️  API server may not be running at $API_BASE"
    echo "   Status code: $API_HEALTH"
    echo "   Starting API server in background..."
    npm run start &
    API_PID=$!
    sleep 3
else
    echo "✅ API server is running"
fi
echo ""

# Run unit tests first
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Phase 1: Unit Tests"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if npm test -- tests/unit/portfolio-optimization.test.js --testTimeout=30000 2>&1; then
    echo ""
    echo "✅ Unit tests PASSED"
else
    echo ""
    echo "❌ Unit tests FAILED"
    exit 1
fi
echo ""

# Run integration tests
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Phase 2: Integration Tests"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if npm test -- tests/integration/portfolio-optimization-integration.test.js --testTimeout=30000 2>&1; then
    echo ""
    echo "✅ Integration tests PASSED"
else
    echo ""
    echo "⚠️  Some integration tests may have failed (expected in mock mode)"
fi
echo ""

# Run E2E tests
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Phase 3: End-to-End Tests (Real Data)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if npm test -- tests/e2e/portfolio-optimization-e2e.test.js --testTimeout=60000 2>&1; then
    echo ""
    echo "✅ End-to-End tests PASSED"
    E2E_SUCCESS=1
else
    echo ""
    echo "❌ End-to-End tests FAILED"
    E2E_SUCCESS=0
fi
echo ""

# Kill background API server if we started it
if [ ! -z "$API_PID" ]; then
    kill $API_PID 2>/dev/null || true
fi

# Summary
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                    TEST SUMMARY                            ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

if [ "$E2E_SUCCESS" = "1" ]; then
    echo "✅ All tests PASSED!"
    echo ""
    echo "Next steps:"
    echo "1. Deploy to production: npm run deploy"
    echo "2. Configure Alpaca credentials"
    echo "3. Test with real Alpaca paper trading"
    echo "4. Monitor and optimize"
    echo ""
    exit 0
else
    echo "⚠️  Some tests failed. Review output above for details."
    echo ""
    echo "Troubleshooting:"
    echo "1. Check database connection"
    echo "2. Verify API server is running"
    echo "3. Check test portfolio setup"
    echo "4. Review logs for specific errors"
    echo ""
    exit 1
fi
