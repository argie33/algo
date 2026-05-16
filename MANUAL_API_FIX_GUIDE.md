# Manual API 401 Fix Guide

If Terraform deployment takes too long or fails, here's how to manually fix the API Gateway authentication.

---

## Problem
API Gateway routes still enforce JWT authentication despite `cognito_enabled = false` in Terraform config.

## Root Cause
The Terraform apply hasn't completed yet, so the API Gateway resource definition hasn't been updated from JWT to NONE auth.

---

## Solution: Manual AWS Console Fix

### Step 1: Go to AWS Console
1. Open: https://console.aws.amazon.com
2. Search for "API Gateway"
3. Click on API Gateway service

### Step 2: Find the Algo API
1. Look for API named something like "algo-api" or "algo" or with the API ID "2iqq1qhltj"
2. Click to open it

### Step 3: Update Authorization Type
1. Click "Resources" in left sidebar
2. Find the "/*" or "api" route
3. Click it to select
4. Click "Method" → "ANY"
5. Click the blue box showing "JWT" (or "Cognito User Pool")
6. In popup, change:
   - Authorization: "NONE"
   - Click "Update"

### Step 4: Deploy API
1. Click "Actions" dropdown
2. Select "Deploy API"
3. In popup:
   - Stage: "prod" or "default"
   - Description: "Manual fix - disable Cognito auth"
   - Click "Deploy"

### Step 5: Verify Fix
```bash
curl -i https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/status

# Should return: HTTP 200 OK (not 401 Unauthorized)
```

---

## If That Doesn't Work

### Check Current Auth Configuration
1. In API Gateway console, select the API
2. Click "Resources"
3. Click the route (e.g., "/{proxy+}")
4. Click "ANY" method
5. Look at "Authorization" field
6. Note current setting

### Check for Multiple Routes
1. The API might have multiple routes with different auth
2. Check ALL routes:
   - /api/* routes
   - /app/* routes
   - /{proxy+} routes
3. Make sure ALL are set to "NONE" auth

### Manual Parameter Fix
If routes have custom authorizer, you may need to:
1. Click the method
2. Remove custom authorizer
3. Set to "NONE"
4. Deploy

---

## Verify Changes

Once fixed, all endpoints should return 200:

```bash
# Check status endpoint
curl -i https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/status

# Check stocks endpoint  
curl -i 'https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/stocks?limit=5'

# Should both return HTTP 200 (with Content-Type: application/json)
# NOT HTTP 401 Unauthorized
```

---

## Terraform Automatic Fix (Preferred)

If you want to wait for Terraform to deploy automatically:

1. Check GitHub Actions: https://github.com/argie33/algo/actions
2. Find "Deploy All Infrastructure" workflow
3. Wait for it to complete (usually 15-30 minutes)
4. Once done, all auth changes apply automatically

---

## What to Do Next

Once API returns 200 (not 401):

```bash
# Run automated verification
python3 VERIFICATION_SUITE.py
```

This will test all phases and tell you what else needs fixing.

---

**Timeline:**
- Automatic: 15-30 minutes (waiting for Terraform)
- Manual: 5 minutes (console clicks + deploy)
- Verification: 10-15 minutes (run VERIFICATION_SUITE.py)

Choose whichever works best for you!
