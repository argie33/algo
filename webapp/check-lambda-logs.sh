#!/bin/bash

echo "🔍 Checking Lambda CloudWatch logs for errors..."

# Your Lambda function name (from the workflow)
FUNCTION_NAME="financial-dashboard-api-${ENVIRONMENT:-dev}"

# Get the latest log group
LOG_GROUP="/aws/lambda/$FUNCTION_NAME"

echo "Checking log group: $LOG_GROUP"

# Get recent log streams (last 5)
echo "Getting recent log streams..."
aws logs describe-log-streams \
  --log-group-name "$LOG_GROUP" \
  --order-by LastEventTime \
  --descending \
  --limit 5 \
  --query 'logStreams[*].logStreamName' \
  --output table

echo ""
echo "Getting latest log events..."

# Get the most recent log stream
LATEST_STREAM=$(aws logs describe-log-streams \
  --log-group-name "$LOG_GROUP" \
  --order-by LastEventTime \
  --descending \
  --limit 1 \
  --query 'logStreams[0].logStreamName' \
  --output text)

echo "Latest log stream: $LATEST_STREAM"

# Get the most recent 50 log events
echo ""
echo "📋 Recent Lambda execution logs:"
echo "================================================"

aws logs get-log-events \
  --log-group-name "$LOG_GROUP" \
  --log-stream-name "$LATEST_STREAM" \
  --limit 50 \
  --query 'events[*].message' \
  --output text

echo ""
echo "================================================"
echo "🔍 Analysis: Look for error messages above that indicate:"
echo "- Missing environment variables"
echo "- Module loading errors"
echo "- Database connection issues"
echo "- VPC configuration problems"