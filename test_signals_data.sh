#!/bin/bash
echo "======================================"
echo "Testing Signals Data Completeness"
echo "======================================"
echo ""

# Test Daily Signals
echo "1. Testing buy_sell_daily table..."
DAILY_COUNT=$(psql -U stocks -d stocks -t -c "SELECT COUNT(*) FROM buy_sell_daily;")
DAILY_WITH_STAGE=$(psql -U stocks -d stocks -t -c "SELECT COUNT(*) FROM buy_sell_daily WHERE market_stage IS NOT NULL;")
DAILY_WITH_QUALITY=$(psql -U stocks -d stocks -t -c "SELECT COUNT(*) FROM buy_sell_daily WHERE entry_quality_score IS NOT NULL;")

echo "   Total rows: $DAILY_COUNT"
echo "   Rows with market_stage: $DAILY_WITH_STAGE"
echo "   Rows with entry_quality_score: $DAILY_WITH_QUALITY"

if [ "$DAILY_COUNT" -gt 0 ] && [ "$DAILY_WITH_STAGE" -gt 0 ]; then
    echo "   ✅ Daily signals have swing metrics populated"
else
    echo "   ❌ Daily signals missing swing metrics"
fi
echo ""

# Test Weekly Signals
echo "2. Testing buy_sell_weekly table..."
WEEKLY_COUNT=$(psql -U stocks -d stocks -t -c "SELECT COUNT(*) FROM buy_sell_weekly;")
WEEKLY_WITH_STAGE=$(psql -U stocks -d stocks -t -c "SELECT COUNT(*) FROM buy_sell_weekly WHERE market_stage IS NOT NULL;")

echo "   Total rows: $WEEKLY_COUNT"
echo "   Rows with market_stage: $WEEKLY_WITH_STAGE"

if [ "$WEEKLY_COUNT" -gt 0 ] && [ "$WEEKLY_WITH_STAGE" -gt 0 ]; then
    echo "   ✅ Weekly signals have swing metrics populated"
else
    echo "   ❌ Weekly signals missing swing metrics"
fi
echo ""

# Test Monthly Signals  
echo "3. Testing buy_sell_monthly table..."
MONTHLY_COUNT=$(psql -U stocks -d stocks -t -c "SELECT COUNT(*) FROM buy_sell_monthly;")
MONTHLY_WITH_STAGE=$(psql -U stocks -d stocks -t -c "SELECT COUNT(*) FROM buy_sell_monthly WHERE market_stage IS NOT NULL;")

echo "   Total rows: $MONTHLY_COUNT"
echo "   Rows with market_stage: $MONTHLY_WITH_STAGE"

if [ "$MONTHLY_COUNT" -gt 0 ] && [ "$MONTHLY_WITH_STAGE" -gt 0 ]; then
    echo "   ✅ Monthly signals have swing metrics populated"
else
    echo "   ❌ Monthly signals missing swing metrics"
fi
echo ""

# Test API endpoint
echo "4. Testing API endpoints..."
DAILY_API=$(curl -s "http://localhost:5001/api/signals?timeframe=daily&limit=1" | grep -o '"success":true' | wc -l)
WEEKLY_API=$(curl -s "http://localhost:5001/api/signals?timeframe=weekly&limit=1" | grep -o '"success":true' | wc -l)

if [ "$DAILY_API" -eq 1 ]; then
    echo "   ✅ Daily API working"
else
    echo "   ❌ Daily API failing"
fi

if [ "$WEEKLY_API" -eq 1 ]; then
    echo "   ✅ Weekly API working"
else
    echo "   ❌ Weekly API failing"
fi

echo ""
echo "======================================"
echo "Test Complete"
echo "======================================"
