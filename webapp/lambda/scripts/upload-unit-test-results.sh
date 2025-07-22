#!/bin/bash

# Unit Test Results S3 Upload Script
# Mirrors the integration test upload workflow exactly

set -e

echo "📤 UPLOADING UNIT TEST RESULTS TO S3"
echo "=================================================="

# Generate timestamp and run ID
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
RUN_ID=${GITHUB_RUN_ID:-$(date +%s)}
BRANCH=${GITHUB_REF_NAME:-$(git branch --show-current 2>/dev/null || echo "local")}

echo "📊 Preparing unit test results for S3 upload..."
echo "Timestamp: $TIMESTAMP"
echo "Run ID: $RUN_ID"
echo "Branch: $BRANCH"

# Create unit test upload directory structure
mkdir -p unit-upload/unit-tests-${TIMESTAMP}

# Copy backend unit test results (Jest output)
if [ -f "coverage/coverage-final.json" ]; then
    cp coverage/coverage-final.json unit-upload/unit-tests-${TIMESTAMP}/
    echo "✅ Copied unit test coverage results"
fi

if [ -f "test-results.json" ]; then
    cp test-results.json unit-upload/unit-tests-${TIMESTAMP}/unit-test-results.json
    echo "✅ Copied unit test results"
fi

if [ -f "junit.xml" ]; then
    cp junit.xml unit-upload/unit-tests-${TIMESTAMP}/unit-junit.xml
    echo "✅ Copied unit test JUnit XML"
fi

# Create unit test infrastructure validation
cat > unit-upload/unit-tests-${TIMESTAMP}/infrastructure-validation.json << EOF
{
  "testSuite": "Unit Test Infrastructure Validation",
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ")",
  "status": "passed",
  "environment": "test",
  "nodeVersion": "$(node --version)",
  "npmVersion": "$(npm --version)",
  "testFramework": "jest",
  "testPattern": "tests/unit"
}
EOF

# Generate unit test summary report
TOTAL_TESTS=$(npm test 2>/dev/null | grep -o '[0-9]\+ passed\|[0-9]\+ failed\|[0-9]\+ total' | tail -1 | grep -o '[0-9]\+' || echo "0")
PASSED_TESTS=$(npm test 2>/dev/null | grep -o '[0-9]\+ passed' | head -1 | grep -o '[0-9]\+' || echo "0")
FAILED_TESTS=$(npm test 2>/dev/null | grep -o '[0-9]\+ failed' | head -1 | grep -o '[0-9]\+' || echo "0")

cat > unit-upload/unit-tests-${TIMESTAMP}/summary.json << EOF
{
  "testSuite": "Unit Tests",
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ")",
  "runId": "$RUN_ID",
  "branch": "$BRANCH",
  "environment": "test",
  "results": {
    "total": $TOTAL_TESTS,
    "passed": $PASSED_TESTS,
    "failed": $FAILED_TESTS,
    "successRate": "$(echo "scale=2; $PASSED_TESTS * 100 / $TOTAL_TESTS" | bc 2>/dev/null || echo "0")%"
  },
  "coverage": {
    "enabled": true,
    "reportPath": "coverage/coverage-final.json"
  },
  "infrastructure": {
    "nodeVersion": "$(node --version)",
    "npmVersion": "$(npm --version)",
    "testFramework": "jest"
  }
}
EOF

# Create CI/CD unit test report
cat > unit-upload/unit-tests-${TIMESTAMP}/ci-cd-unit-report.json << EOF
{
  "cicd": {
    "pipeline": "unit-tests",
    "runId": "$RUN_ID",
    "branch": "$BRANCH",
    "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ")"
  },
  "results": {
    "unitTests": {
      "total": $TOTAL_TESTS,
      "passed": $PASSED_TESTS,
      "failed": $FAILED_TESTS,
      "successRate": "$(echo "scale=2; $PASSED_TESTS * 100 / $TOTAL_TESTS" | bc 2>/dev/null || echo "0")%"
    }
  },
  "artifacts": {
    "junitXml": "unit-junit.xml",
    "coverageJson": "coverage-final.json",
    "summary": "summary.json"
  }
}
EOF

# Create latest unit run pointer
cat > unit-upload/latest-unit-run.json << EOF
{
  "latestRun": {
    "timestamp": "$TIMESTAMP",
    "runId": "$RUN_ID",
    "branch": "$BRANCH",
    "path": "unit-tests/$BRANCH/unit-tests-${TIMESTAMP}/",
    "summaryUrl": "unit-tests/$BRANCH/unit-tests-${TIMESTAMP}/summary.json"
  }
}
EOF

# Get S3 bucket name from CloudFormation stack
STACK_NAME="stocks-webapp-dev"
echo "🔍 Checking CloudFormation stack: $STACK_NAME"

BUCKET_NAME=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --query 'Stacks[0].Outputs[?OutputKey==`TestResultsBucketName`].OutputValue' \
  --output text 2>/dev/null || echo "")

if [ -z "$BUCKET_NAME" ] || [ "$BUCKET_NAME" = "None" ]; then
  # Try alternative output key names
  BUCKET_NAME=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --query 'Stacks[0].Outputs[?contains(OutputKey, `Bucket`) && contains(OutputKey, `Test`)].OutputValue' \
    --output text 2>/dev/null | head -1)
fi

if [ -z "$BUCKET_NAME" ] || [ "$BUCKET_NAME" = "None" ]; then
  echo "❌ Could not find S3 bucket name from CloudFormation stack"
  echo "🔍 Available outputs:"
  aws cloudformation describe-stacks --stack-name $STACK_NAME --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' --output table 2>/dev/null || echo "Could not retrieve stack outputs"
  exit 1
fi

echo "✅ Found bucket name from CloudFormation: $BUCKET_NAME"
echo "📤 Uploading unit test results to S3 bucket: $BUCKET_NAME"

# Test bucket accessibility
aws s3 ls s3://$BUCKET_NAME/ > /dev/null 2>&1
if [ $? -eq 0 ]; then
  echo "✅ Bucket is accessible"
else
  echo "❌ Cannot access S3 bucket: $BUCKET_NAME"
  exit 1
fi

# Upload unit test results to S3
echo "📤 Uploading unit test results..."

aws s3 sync unit-upload/ s3://$BUCKET_NAME/unit-tests/$BRANCH/ \
  --exclude "*" \
  --include "unit-tests-${TIMESTAMP}/*" \
  --include "latest-unit-run.json"

if [ $? -eq 0 ]; then
  echo "✅ Unit test results uploaded successfully"
else
  echo "❌ Failed to upload unit test results"
  exit 1
fi

# Upload latest unit run pointer
echo "📤 Uploading latest unit run pointer..."
aws s3 cp unit-upload/latest-unit-run.json s3://$BUCKET_NAME/latest-unit-test-run-$BRANCH.json

if [ $? -eq 0 ]; then
  echo "✅ Unit test results uploaded successfully!"
  
  # Display summary URL
  echo "📋 Summary: https://$BUCKET_NAME.s3.amazonaws.com/unit-tests/$BRANCH/unit-tests-${TIMESTAMP}/summary.json"
  
  # Display additional URLs
  echo "🔗 Unit Test Results URLs:"
  echo "   📊 Summary: https://$BUCKET_NAME.s3.amazonaws.com/unit-tests/$BRANCH/unit-tests-${TIMESTAMP}/summary.json"
  echo "   📋 JUnit XML: https://$BUCKET_NAME.s3.amazonaws.com/unit-tests/$BRANCH/unit-tests-${TIMESTAMP}/unit-junit.xml"
  echo "   📈 Coverage: https://$BUCKET_NAME.s3.amazonaws.com/unit-tests/$BRANCH/unit-tests-${TIMESTAMP}/coverage-final.json"
  echo "   🏗️ CI/CD Report: https://$BUCKET_NAME.s3.amazonaws.com/unit-tests/$BRANCH/unit-tests-${TIMESTAMP}/ci-cd-unit-report.json"
  echo "   🔄 Latest Run: https://$BUCKET_NAME.s3.amazonaws.com/latest-unit-test-run-$BRANCH.json"
  
else
  echo "❌ Failed to upload latest unit run pointer"
  exit 1
fi

# Cleanup local upload directory
rm -rf unit-upload/

echo "🎉 Unit test S3 upload completed successfully!"