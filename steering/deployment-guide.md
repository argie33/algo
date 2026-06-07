# Deployment & Fix Guide - 5xx Errors Resolution

## Summary of Fixes Applied

### ✅ CODE FIXES COMPLETED

#### 1. **Response Normalizer Bug Fix** (CRITICAL)
**File:** `webapp/frontend/src/utils/responseNormalizer.js` (Lines 113-128)

**What was fixed:**
- Normalizer now detects `data.data.success === false` and throws proper error
- No longer overwrites `success: false` with `success: true`
- Components now receive correct error signals

**Impact:** Frontend can now properly detect API failures instead of silent crashes

---

#### 2. **API Status Code Fixes** (CRITICAL)
**Files:** 
- `lambda/api/routes/algo.py` (Lines 1818-1837)
- `lambda/api/routes/economic.py` (Lines 364-375)

**What was fixed:**
- Database errors now return HTTP 503 (Service Unavailable) instead of 200
- Schema errors return HTTP 503 with `errorType: 'schema_error'`
- Connection errors return HTTP 503 with `errorType: 'connection_error'`
- Query errors return HTTP 503 with `errorType: 'query_error'`

**Before:**
```python
except psycopg2.OperationalError:
    return json_response(200, {'success': False, ...})  # ✗ Wrong
```

**After:**
```python
except psycopg2.OperationalError:
    return error_response(503, 'connection_error', 'RDS/database connection failed')  # ✓ Correct
```

**Impact:** Frontend can now detect real API errors and show proper error messages

---

#### 3. **Configuration Validator** (NEW)
**File:** `lambda/api/config_validator.py`

**What it does:**
- Verifies all Lambda environment variables at startup
- Checks DB_HOST points to RDS Proxy (not direct RDS)
- Validates FRONTEND_URL is set or CloudFront secret exists
- Validates Cognito configuration
- Validates database credentials

**How to use:**
```bash
# Run in Lambda environment to validate config
python lambda/api/config_validator.py

# Or import in lambda_function.py to run at cold start:
from config_validator import ConfigValidator
validator = ConfigValidator()
if not validator.run_all_checks():
    logger.error("Configuration invalid - see logs for details")
    validator.print_report()
```

---

#### 4. **Data Validation Utilities** (NEW)
**File:** `webapp/frontend/src/utils/dataValidation.js`

**What it provides:**
- `validateMarketData()` - Ensures market data has correct structure
- `validateListData()` - Ensures paginated responses have items array
- `getNestedValue()` - Safely access nested properties
- `isSuccessResponse()` - Check if response indicates success
- `getErrorMessage()` - Extract error message from response

**How to use in components:**
```javascript
import { validateMarketData, isSuccessResponse } from '../utils/dataValidation';

// In component:
const validated = validateMarketData(marketsData);
if (!isSuccessResponse(marketsData)) {
  return <ErrorMessage />;
}
```

---

## MANUAL FIXES REQUIRED

### ⚠️  Configuration Issues That Need Verification

These are **NOT code issues** - they're configuration issues in AWS. You must verify/set these:

#### 1. **RDS Proxy Configuration**
**Check:** AWS Lambda environment variable `DB_HOST`

**Must contain:** The word "proxy"

**Example (correct):**
- `algo-rds-proxy.c2q3x4a1b2c3.us-east-1.rds.amazonaws.com` ✓

**Example (WRONG):**
- `algo-database.c2q3x4a1b2c3.us-east-1.rds.amazonaws.com` ✗ (direct RDS)

**How to fix:**
```bash
# In AWS Lambda console:
# Go to: Functions → algo-api-dev → Configuration → Environment variables
# Update DB_HOST to include "proxy"

# Or via AWS CLI:
aws lambda update-function-configuration \
  --function-name algo-api-dev \
  --environment Variables={DB_HOST=algo-rds-proxy.c2q3x4a1b2c3.us-east-1.rds.amazonaws.com,...}
```

---

#### 2. **Frontend URL Configuration**
**Check:** AWS Lambda environment variable `FRONTEND_URL`

**Must be:** The production website URL

**Example:**
- `https://algo.example.com` ✓
- `https://d1234abcd.cloudfront.net` ✓

**Alternative:** CloudFront domain in Secrets Manager
```bash
# Instead of FRONTEND_URL, can store in Secrets Manager:
aws secretsmanager create-secret \
  --name algo/cloudfront-domain \
  --secret-string "d1234abcd.cloudfront.net"
```

**How to fix:**
```bash
# Option 1: Set environment variable
aws lambda update-function-configuration \
  --function-name algo-api-dev \
  --environment Variables={FRONTEND_URL=https://algo.example.com,...}

# Option 2: Store in Secrets Manager (preferred for credentials)
aws secretsmanager create-secret \
  --name algo/cloudfront-domain \
  --secret-string "d1234abcd.cloudfront.net"
```

---

#### 3. **Cognito Configuration** (if using authentication)
**Check:** AWS Lambda environment variables

**Required if authenticating users:**
- `COGNITO_USER_POOL_ID` - User pool ID
- `COGNITO_CLIENT_ID` - App client ID
- `COGNITO_REGION` - AWS region (default: us-east-1)

**Example:**
```bash
COGNITO_USER_POOL_ID=us-east-1_abc1234567
COGNITO_CLIENT_ID=1a2b3c4d5e6f7g8h9i0j
COGNITO_REGION=us-east-1
```

**Development mode (for testing):**
```bash
# To bypass Cognito in dev/staging:
DEV_BYPASS_AUTH=true
```

⚠️ **WARNING:** `DEV_BYPASS_AUTH=true` must NOT be set in production!

---

#### 4. **Data Pipeline Status**
**Check:** Are the data pipelines running?

These jobs must execute daily:
- **2:00 AM ET:** morning-prep-pipeline (Step Functions)
- **4:05 PM ET:** eod-pipeline (Step Functions)

**How to verify:**
```bash
# Check Step Functions execution history
aws stepfunctions list-executions \
  --state-machine-arn arn:aws:states:us-east-1:ACCOUNT_ID:stateMachine:algo-morning-prep-pipeline \
  --query 'executions[0]'

# Should show: "status": "SUCCEEDED" with recent timestamp
```

**If pipelines aren't running:**
1. Check EventBridge rules are enabled
2. Check Step Functions have correct IAM permissions
3. Check CloudWatch Logs for error messages

---

## DEPLOYMENT CHECKLIST

### Before Deploying to Production

- [ ] **Run config validator:** `python lambda/api/config_validator.py`
- [ ] **Verify DB_HOST contains "proxy"**
- [ ] **Verify FRONTEND_URL is set**
- [ ] **Verify Cognito vars (if using auth)**
- [ ] **Verify DEV_BYPASS_AUTH is NOT "true" in production**
- [ ] **Check data pipeline executed today**
- [ ] **Run tests:** `npm test` (frontend), `pytest` (backend)
- [ ] **Build frontend:** `npm run build` and verify `dist/config.js` is correct

### Deployment Steps

```bash
# 1. Build frontend
cd webapp/frontend
npm run build

# 2. Deploy Lambda with updated code
cd lambda/api
./deploy.sh

# 3. Run config validator in Lambda
aws lambda invoke \
  --function-name algo-api-dev \
  --payload '{"requestContext":{"identity":{"userAgent":"validator"}}}' \
  --log-type Tail \
  /tmp/response.json

# 4. Check CloudWatch Logs
aws logs tail /aws/lambda/algo-api-dev --follow
```

---

## VERIFICATION STEPS

### After Deployment

#### 1. **Health Check Endpoint**
```bash
# Check if API is responding
curl https://algo.example.com/api/health

# Should return:
# {"statusCode": 200, "data": {"status": "ok"}}
```

#### 2. **Check for Configuration Errors in Logs**
```bash
# Look for "FATAL" or "ERROR" messages
aws logs tail /aws/lambda/algo-api-dev --filter-pattern "FATAL\|ERROR" --follow

# Should NOT see:
# - "DB_HOST: Must point to RDS Proxy"
# - "FRONTEND_URL: Must be set"
# - "COGNITO_USER_POOL_ID: Required"
```

#### 3. **Load Dashboard Page**
```bash
# In browser, go to:
https://algo.example.com/app/markets

# Should see:
# ✓ Market health data loading
# ✓ Charts rendering
# ✗ NOT seeing "500 Internal Server Error"
# ✗ NOT seeing empty blank dashboards
```

#### 4. **Check API Response Codes**
```bash
# In browser F12 Developer Tools, Network tab:
# Should see status codes:
# 200 - Success
# 503 - Service Unavailable (proper error)
# NOT 200 for errors anymore!

# Test bad endpoint:
curl -i https://algo.example.com/api/invalid-endpoint
# Should return: 404 Not Found (not 200)
```

---

## MONITORING FOR ISSUES

### CloudWatch Alarms to Set Up

```bash
# 1. Alert on 503 errors
aws cloudwatch put-metric-alarm \
  --alarm-name algo-api-503-errors \
  --alarm-description "Alert if API returns 503 errors" \
  --metric-name 5XXError \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 300 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold

# 2. Alert on Lambda errors
aws cloudwatch put-metric-alarm \
  --alarm-name algo-api-errors \
  --alarm-description "Alert if Lambda function errors" \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 60 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold

# 3. Alert on circuit breaker opening
aws cloudwatch put-metric-alarm \
  --alarm-name algo-circuit-breaker-open \
  --alarm-description "Alert if circuit breaker opens" \
  --metric-name CircuitBreakerOpen \
  --namespace CustomApp \
  --statistic Maximum \
  --period 60 \
  --threshold 1 \
  --comparison-operator GreaterThanOrEqualToThreshold
```

---

## ROLLBACK PLAN

If issues occur after deployment:

```bash
# 1. Revert to previous Lambda version
aws lambda update-function-code \
  --function-name algo-api-dev \
  --s3-bucket YOUR_BUCKET \
  --s3-key previous-lambda-version.zip

# 2. Clear CloudFront cache
aws cloudfront create-invalidation \
  --distribution-id YOUR_DIST_ID \
  --paths "/*"

# 3. Clear browser cache (instruct users)
# Shift + Refresh or Ctrl + Shift + Delete

# 4. Check logs for root cause
aws logs tail /aws/lambda/algo-api-dev --follow --since 10m
```

---

## COMMON ISSUES & SOLUTIONS

### Issue: "Cannot read properties of null" errors in console

**Root Cause:** Component receiving null data from API

**Solution:**
1. Check API response in F12 Network tab
2. Verify `statusCode: 200` but `data: null`?
3. Run config validator: `python lambda/api/config_validator.py`
4. Check data pipeline execution

---

### Issue: "API service temporarily unavailable" message

**Root Cause:** Circuit breaker opened (12+ consecutive failures)

**Solution:**
1. Check Lambda logs for actual errors
2. Fix the root cause (DB connection, schema error, etc.)
3. Wait 15 seconds for circuit to recover
4. Or restart Lambda function

---

### Issue: CORS errors in F12 console

**Root Cause:** FRONTEND_URL not set or CloudFront domain not in Secrets Manager

**Solution:**
1. Verify FRONTEND_URL in Lambda environment
2. Or store CloudFront domain in Secrets Manager: `algo/cloudfront-domain`
3. Redeploy Lambda
4. Clear browser cache

---

### Issue: 5xx errors on specific endpoints only

**Root Cause:** Database table not populated or missing schema

**Solution:**
1. Check data pipeline execution status
2. Verify table exists: `SELECT * FROM market_exposure_daily LIMIT 1`
3. If empty, run pipeline manually or wait for next scheduled run
4. Check `CRITICAL_ISSUES_FOUND.md` Issue #3 (Empty Tables)

---

## NEXT STEPS

1. **Deploy the code fixes** (responseNormalizer, API status codes)
2. **Verify Lambda configuration** (run config_validator.py)
3. **Run data pipelines** to populate tables
4. **Test endpoints** in dev environment
5. **Deploy to production** following checklist
6. **Monitor CloudWatch logs** for new errors

If you encounter issues, check:
- `CRITICAL_ISSUES_FOUND.md` - Complete issue analysis
- CloudWatch Logs - Real-time error messages
- Config validation output - Configuration problems
