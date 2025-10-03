#!/bin/bash
# Comprehensive test script for all StockDetail page APIs
# Tests all endpoints that the StockDetail page uses

echo "=========================================="
echo "Testing All StockDetail APIs for AAPL"
echo "=========================================="
echo ""

BASE_URL="http://localhost:5001"
SYMBOL="AAPL"

# Test 1: Profile API
echo "1. Testing Profile API..."
PROFILE=$(curl -s "$BASE_URL/api/stocks/$SYMBOL/profile")
if echo "$PROFILE" | grep -q "Apple Inc"; then
    echo "   ✅ Profile API - SUCCESS (Found company name)"
else
    echo "   ❌ Profile API - FAIL"
    echo "   Response: $PROFILE"
fi
echo ""

# Test 2: Metrics API
echo "2. Testing Metrics API..."
METRICS=$(curl -s "$BASE_URL/api/metrics/$SYMBOL")
if echo "$METRICS" | grep -q "free_cashflow"; then
    CASHFLOW=$(echo "$METRICS" | grep -o '"free_cashflow":[0-9]*' | grep -o '[0-9]*')
    echo "   ✅ Metrics API - SUCCESS (Free Cash Flow: \$$CASHFLOW)"
else
    echo "   ❌ Metrics API - FAIL"
    echo "   Response: $METRICS"
fi
echo ""

# Test 3: Balance Sheet API
echo "3. Testing Balance Sheet API..."
BALANCE=$(curl -s "$BASE_URL/api/financials/$SYMBOL/balance-sheet?period=annual")
if echo "$BALANCE" | grep -q "totalAssets"; then
    RECORDS=$(echo "$BALANCE" | grep -o '"data":\[' | wc -l)
    echo "   ✅ Balance Sheet API - SUCCESS (Has data array)"
else
    echo "   ❌ Balance Sheet API - FAIL"
    echo "   Response: $BALANCE"
fi
echo ""

# Test 4: Income Statement API
echo "4. Testing Income Statement API..."
INCOME=$(curl -s "$BASE_URL/api/financials/$SYMBOL/income-statement?period=annual")
if echo "$INCOME" | grep -q "revenue"; then
    echo "   ✅ Income Statement API - SUCCESS (Has revenue data)"
else
    echo "   ❌ Income Statement API - FAIL"
    echo "   Response: $INCOME"
fi
echo ""

# Test 5: Cash Flow API
echo "5. Testing Cash Flow API..."
CASHFLOW_STMT=$(curl -s "$BASE_URL/api/financials/$SYMBOL/cash-flow?period=annual")
if echo "$CASHFLOW_STMT" | grep -q "operatingCashFlow"; then
    echo "   ✅ Cash Flow API - SUCCESS (Has cash flow data)"
else
    echo "   ❌ Cash Flow API - FAIL"
    echo "   Response: $CASHFLOW_STMT"
fi
echo ""

# Test 6: Analyst Recommendations API
echo "6. Testing Analyst Recommendations API..."
RECS=$(curl -s "$BASE_URL/api/analysts/$SYMBOL/recommendations")
if echo "$RECS" | grep -q "Goldman Sachs"; then
    echo "   ✅ Analyst Recommendations API - SUCCESS (Has recommendations)"
else
    echo "   ❌ Analyst Recommendations API - FAIL"
    echo "   Response: $RECS"
fi
echo ""

# Test 7: Analyst Overview API
echo "7. Testing Analyst Overview API..."
OVERVIEW=$(curl -s "$BASE_URL/api/analysts/$SYMBOL/overview")
if echo "$OVERVIEW" | grep -q "eps_revisions"; then
    echo "   ✅ Analyst Overview API - SUCCESS (Has EPS data)"
else
    echo "   ❌ Analyst Overview API - FAIL"
    echo "   Response: $OVERVIEW"
fi
echo ""

# Test 8: Recent Prices API
echo "8. Testing Recent Prices API..."
PRICES=$(curl -s "$BASE_URL/api/stocks/$SYMBOL/prices/recent?limit=30")
if echo "$PRICES" | grep -q "close"; then
    echo "   ✅ Recent Prices API - SUCCESS (Has price data)"
else
    echo "   ❌ Recent Prices API - FAIL"
    echo "   Response: $PRICES"
fi
echo ""

# Test 9: Events API
echo "9. Testing Events API..."
EVENTS=$(curl -s "$BASE_URL/api/calendar/events?symbol=$SYMBOL&type=upcoming&page=1&limit=10")
if echo "$EVENTS" | grep -q "success"; then
    echo "   ✅ Events API - SUCCESS (Returns data)"
else
    echo "   ❌ Events API - FAIL"
    echo "   Response: $EVENTS"
fi
echo ""

echo "=========================================="
echo "Test Summary Complete"
echo "=========================================="
echo ""
echo "✅ All APIs tested"
echo "Now test the frontend at: http://localhost:5173/stocks/AAPL"
