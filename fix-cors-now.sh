#!/bin/bash
# Quick CORS fix script

echo "🔍 Step 1: Check current CloudFormation stacks"
# This would normally be: aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE
echo "Need to check GitHub Actions to see if deployment ran"

echo "🔍 Step 2: The issue is the old API Gateway is still returning 500s"
echo "Current API: https://rovlbpwbh1.execute-api.us-east-1.amazonaws.com/dev"
echo "This API Gateway Lambda is crashing, so no CORS headers"

echo "🔍 Step 3: Solutions in order of preference:"
echo "  A) Deploy new API Gateway with working Lambda (initialbuild stack)"
echo "  B) Fix the existing Lambda function at rovlbpwbh1"
echo "  C) Add API Gateway-level CORS (not Lambda-level)"

echo "🔍 Step 4: Check if GitHub Actions ran"
echo "Go to: https://github.com/[your-repo]/actions"
echo "Look for 'Deploy Serverless Webapp' workflow"

echo "🔍 Step 5: If deployment didn't run, trigger it manually"
echo "Go to Actions tab → Deploy Serverless Webapp → Run workflow"

echo "🔍 Step 6: If deployment ran, get the new API Gateway URL"
echo "Check CloudFormation stack outputs for new API URL"

echo "🔍 Step 7: Update frontend to use new API URL"
echo "Edit webapp/frontend/src/config or environment variables"

echo "🔍 Step 8: Test new API Gateway"
echo "curl -H 'Origin: https://d1zb7knau41vl9.cloudfront.net' [NEW-API-URL]/health"

echo "🔍 Step 9: If still not working, add API Gateway CORS directly"
echo "Add CORS configuration to API Gateway resource in CloudFormation"

echo "🔍 Step 10: Last resort - fix the existing Lambda function"
echo "Update the Lambda function code at rovlbpwbh1 API Gateway"