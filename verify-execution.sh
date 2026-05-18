#!/bin/bash
# Verify AWS loader execution success via CloudWatch logs

set -e

API_URL="https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com"
AWS_REGION="us-east-1"

echo "════════════════════════════════════════════════════════════"
echo "  VERIFYING AWS LOADER EXECUTION SUCCESS"
echo "════════════════════════════════════════════════════════════"
echo ""

# Check if CloudWatch logs exist and have content
check_logs() {
    local log_group=$1
    local loader_name=$2

    echo -n "  $loader_name: "

    # Get latest log stream
    STREAM=$(aws logs describe-log-streams \
        --log-group-name "$log_group" \
        --order-by LastEventTime \
        --descending \
        --region $AWS_REGION \
        --query 'logStreams[0].logStreamName' \
        --output text 2>/dev/null || echo "")

    if [ -z "$STREAM" ] || [ "$STREAM" = "None" ]; then
        echo "⏳ No logs yet"
        return 1
    fi

    # Get recent log messages
    LOGS=$(aws logs get-log-events \
        --log-group-name "$log_group" \
        --log-stream-name "$STREAM" \
        --region $AWS_REGION \
        --query 'events[*].message' \
        --output text 2>/dev/null || echo "")

    if echo "$LOGS" | grep -q "Inserted\|Loaded"; then
        echo "✅ Data loaded"
        return 0
    elif echo "$LOGS" | grep -q "error\|ERROR\|failed"; then
        echo "❌ Error in logs"
        return 1
    elif [ -n "$LOGS" ]; then
        echo "⏳ Still loading..."
        return 2
    else
        echo "⏳ No output yet"
        return 2
    fi
}

echo "📊 CloudWatch Logs Status:"
echo ""

# Check stock symbols
check_logs "/ecs/algo-stock_symbols-loader" "Stock Symbols (Tier 0)" || true

# Check prices
check_logs "/ecs/algo-stock_prices_daily-loader" "Prices Daily (Tier 1)" || true

echo ""
echo "API Status:"
echo -n "  Health Check: "
if curl -s -f "$API_URL/api/health" > /dev/null 2>&1; then
    echo "✅ Responding"
else
    echo "❌ Not responding"
fi

echo ""
echo "════════════════════════════════════════════════════════════"
echo ""
echo "To manually check CloudWatch logs:"
echo "  aws logs tail /ecs/algo-stock_symbols-loader --follow --region us-east-1"
echo ""
echo "To check if data loaded:"
echo "  curl $API_URL/api/stocks?limit=1"
echo ""
