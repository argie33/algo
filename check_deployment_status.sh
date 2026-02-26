#!/bin/bash

cat << 'EOF'
════════════════════════════════════════════════════════════════════════════════
                    GitHub Actions Deployment Status Checker
════════════════════════════════════════════════════════════════════════════════

HOW TO CHECK DEPLOYMENT STATUS:

1. GitHub Actions (Real-time logs)
   ═════════════════════════════════════════════════════════════════════════════
   URL: https://github.com/argie33/algo/actions

   Look for: "deploy-webapp" workflow
   Jobs to check:
     • setup - Set environment variables
     • filter - Detect changed components
     • deploy_infrastructure - Deploy Lambda and API Gateway
     • deploy_frontend - Build and deploy React app
     • deploy_frontend_admin - Build and deploy admin panel
     • verify_deployment - Run health checks

   Each job should show:
     ✅ Success (green checkmark)
     ❌ Failed (red X)

   Click on failed jobs to see error details.

2. CloudFormation Stack (AWS Console)
   ═════════════════════════════════════════════════════════════════════════════
   URL: https://console.aws.amazon.com/cloudformation/

   Look for: "stocks-webapp-dev" stack
   Status should be:
     ✅ CREATE_COMPLETE
     ✅ UPDATE_COMPLETE
     ❌ ROLLBACK_COMPLETE (failed)
     ❌ CREATE_FAILED (failed)

   Click "Events" tab to see what's happening.

3. Lambda Function (AWS Console)
   ═════════════════════════════════════════════════════════════════════════════
   URL: https://console.aws.amazon.com/lambda/

   Look for: "stocks-webapp-api-dev" function
   Check:
     • Memory: Should be 512 MB (was 128 MB)
     • Timeout: Should be 300 seconds (was 60 seconds)
     • Recent executions: Should show "succeeded"

   Click "Monitor" tab to see CloudWatch metrics.

4. CloudWatch Logs (AWS Console)
   ═════════════════════════════════════════════════════════════════════════════
   URL: https://console.aws.amazon.com/cloudwatch/

   Log Group: /aws/lambda/stocks-webapp-dev-*

   Look for entries like:
     ✅ "Successfully connected to database"
     ✅ "Database config loaded"
     ❌ "Connection refused"
     ❌ "TIMEOUT"
     ❌ "FATAL"

5. API Gateway (AWS Console)
   ═════════════════════════════════════════════════════════════════════════════
   URL: https://console.aws.amazon.com/apigateway/

   Look for: "stocks-webapp-api-dev"
   Stage: "dev"

   Test endpoint:
     https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/health

════════════════════════════════════════════════════════════════════════════════

QUICK TESTS:

Test 1: API Health Check
──────────────────────────────────────────────────────────────────────────────

From any machine with internet:
  curl https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/health

Expected response:
  {"success":true,"data":{"status":"healthy",...}}

Test 2: Get Stocks
──────────────────────────────────────────────────────────────────────────────

curl "https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/api/stocks?limit=5"

Expected response:
  {"success":true,"data":[{"symbol":"AAPL","scores":{...}},{...}]}

Test 3: Check Memory (from AWS Console)
──────────────────────────────────────────────────────────────────────────────

AWS Console → Lambda → stocks-webapp-api-dev

Memory allocated: 512 MB ✓ (if fix applied)

════════════════════════════════════════════════════════════════════════════════

COMMON ISSUES & FIXES:

Issue: GitHub Actions shows "No changes detected"
───────────────────────────────────────────────────────────────────────────────
Cause: Filter step thinks no relevant files changed
Fix: Files matching these paths trigger deployment:
  • webapp/**
  • template-webapp-lambda.yml ✓ (our change)
  • .github/workflows/deploy-webapp.yml

Issue: CloudFormation stack failed
───────────────────────────────────────────────────────────────────────────────
Fix:
  1. Go to AWS CloudFormation console
  2. Right-click stack → Delete Stack
  3. Wait for deletion
  4. Go to GitHub Actions → Re-run jobs
  5. It will create new stack

Issue: "Failed to get database secret ARN"
───────────────────────────────────────────────────────────────────────────────
Fix:
  1. Check that stocks-app-dev stack exists
  2. Verify it has outputs: StocksApp-SecretArn, StocksApp-DBEndpoint
  3. Lambda execution role needs secretsmanager:GetSecretValue permission

Issue: Frontend build failed
───────────────────────────────────────────────────────────────────────────────
Fix:
  1. Check npm install succeeded
  2. Verify Node.js version is 20.x
  3. Check for TypeScript errors: npm run build (locally)
  4. Clear cache: rm -rf node_modules package-lock.json && npm ci

════════════════════════════════════════════════════════════════════════════════

WHAT TO EXPECT:

Timeline: ~5-10 minutes from push to deployed

  0-2 min: GitHub Actions builds SAM application
  2-5 min: SAM deploys CloudFormation stack
  5-7 min: Frontend builds and deploys to S3
  7-9 min: Admin frontend builds and deploys
  9-10 min: Health checks run and verify

Success indicators:
  ✅ GitHub Actions: All jobs show green checkmarks
  ✅ CloudFormation: Stack shows UPDATE_COMPLETE
  ✅ CloudFront: Distribution is Enabled
  ✅ API health endpoint returns 200
  ✅ Lambda memory shows 512 MB
  ✅ Lambda timeout shows 300 seconds

════════════════════════════════════════════════════════════════════════════════

NEXT STEPS AFTER DEPLOYMENT:

1. Wait for GitHub Actions to complete (green checkmarks)
2. Run data loaders: bash /tmp/run_critical_loaders.sh
3. Test API endpoints (see tests above)
4. Visit frontend: https://stocks-webapp-frontend-dev-626216981288.cloudfront.net

═══════════════════════════════════════════════════════════════════════════════

For detailed info, read: GITHUB_DEPLOYMENT_GUIDE.md

EOF
