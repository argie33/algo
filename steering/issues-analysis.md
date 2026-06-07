# Issue Analysis: 5xx Errors and Data Display Problems

## Executive Summary

Site experiencing "tons of 5xx errors" caused by **9 interconnected issues**. Root cause: API responses treated as successful even when they fail, causing frontend components to crash on null data. Cascade effect blocks entire dashboard with error pages.

**Status:** 3 critical code bugs fixed. 6 configuration/data issues identified requiring manual verification.

---

## Issue Catalog

### CRITICAL ISSUES (Code Bugs - Now Fixed)

#### Issue #1: Response Normalizer Overwrites Error Flag
**Severity:** CRITICAL - Silent API failures
**File:** `webapp/frontend/src/utils/responseNormalizer.js` (Lines 114-119)
**Status:** ✅ FIXED

**Problem:**
When API returned `{statusCode: 200, data: {success: false, current: null}}`, normalizer spread the data object and added `success: true`, overwriting the error flag. Frontend thought data loaded successfully when it actually failed.

**Before:**
```javascript
return {
  ...data.data,           // includes {success: false, ...}
  statusCode: httpStatus,
  success: true,          // OVERWRITES success: false!
};
```

**After:**
```javascript
// If nested data has success: false, throw error
if (data.data.success === false) {
  const errorMsg = data.data.message || data.data.error || 'API request failed';
  const error = new Error(errorMsg);
  error.code = data.data.errorType;
  error.status = httpStatus;
  throw error;
}
```

**Impact:** Prevented components from detecting API errors, leading to null reference crashes.

---

#### Issue #2: API Returns 200 Status for Errors
**Severity:** CRITICAL - Frontend can't detect errors
**Files:** 
- `lambda/api/routes/algo.py` (Lines 1818-1837)
- `lambda/api/routes/economic.py` (Lines 364-375)
**Status:** ✅ FIXED

**Problem:**
When databases failed or tables didn't exist, routes returned HTTP 200 with `{success: false}`. Frontend expects HTTP error status codes (4xx/5xx) to detect failures.

**Before:**
```python
except psycopg2.OperationalError:
    return json_response(200, {'success': False, ...})  # Wrong status!
```

**After:**
```python
except psycopg2.OperationalError:
    return error_response(503, 'connection_error', 'RDS/database connection failed')  # Correct status
```

**Impact:** Frontend couldn't detect database errors, treated them as successful responses.

---

#### Issue #9: Component Null Reference Errors
**Severity:** HIGH - Cascading React crashes
**Files:** Multiple pages (MarketsHealth, Dashboard, etc.)
**Status:** ✅ PARTIALLY FIXED

**Problem:**
When API returned null data due to issues #1-#2, components tried to access properties on null objects, causing React crashes. ErrorBoundary would catch errors but show unhelpful error page instead of "Data loading" message.

**Example Crash:**
```javascript
function RegimeBanner({ markets }) {
  const tier = markets.active_tier || {};  // OK: has fallback
  const exposure = cur.exposure_pct;       // CRASH: cur could be null
}
```

**Fix Applied:**
Created `dataValidation.js` with safe validation utilities:
```javascript
export const validateMarketData = (data) => {
  if (!data || typeof data !== 'object') return fallback;
  return {
    current: data.current && typeof data.current === 'object' ? data.current : null,
    active_tier: data.active_tier && typeof data.active_tier === 'object' ? data.active_tier : {},
    // ... safe validation for all fields
  };
};
```

**Impact:** Components can now safely validate data before rendering, preventing null reference crashes.

---

### CONFIGURATION ISSUES (Require Manual Verification)

#### Issue #3: Empty Database Tables
**Severity:** HIGH - No data to display
**Status:** ⚠️ NEEDS VERIFICATION

**Problem:**
API queries expect data in tables like:
- `market_exposure_daily` - Used by MarketsHealth, Dashboard
- `market_health_daily` - Used by technicals, market health displays
- `sector_ranking` - Used by sector analysis
- `swing_trader_scores` - Used by scoring dashboards

These tables may be empty because data pipelines aren't running.

**Verification Steps:**
```bash
# Check if pipelines executed today
aws stepfunctions list-executions \
  --state-machine-arn arn:aws:states:us-east-1:ACCOUNT:stateMachine:algo-morning-prep-pipeline

# Check table data
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT MAX(date) FROM market_exposure_daily;"
```

**Expected:** Max date should be today
**If empty:** Data pipelines not running or failed

**Root Cause:**
Data pipelines scheduled to run:
- 2:00 AM ET: morning-prep-pipeline (Step Functions)
- 4:05 PM ET: eod-pipeline (Step Functions)

If these don't execute, tables stay empty and all queries return no data.

**Fix:** Run pipelines manually or verify EventBridge rules are enabled.

---

#### Issue #4: RDS Proxy Not Configured
**Severity:** HIGH - Database connection failures
**Status:** ⚠️ NEEDS VERIFICATION

**Problem:**
Lambda validates that `DB_HOST` points to RDS Proxy (for connection pooling), not direct RDS. If misconfigured, connection pool gets exhausted and all queries fail.

**Check in Lambda Environment:**
```
DB_HOST = algo-rds-proxy.xxxxx.us-east-1.rds.amazonaws.com  ✓ (has "proxy")
DB_HOST = algo-database.xxxxx.us-east-1.rds.amazonaws.com    ✗ (direct RDS)
```

**How to Verify:**
```bash
aws lambda get-function-configuration --function-name algo-api-dev | grep DB_HOST
```

**Fix:** Update Lambda environment variable to point to RDS Proxy endpoint.

---

#### Issue #5: Frontend URL Not Configured for CORS
**Severity:** HIGH - API requests blocked by CORS
**Status:** ⚠️ NEEDS VERIFICATION

**Problem:**
Lambda needs to know the frontend URL to add correct `Access-Control-Allow-Origin` header. Without it, all cross-origin API requests from frontend fail with CORS error.

**Check in Lambda Environment:**
```
FRONTEND_URL = https://algo.example.com           ✓
FRONTEND_URL = https://d1234.cloudfront.net       ✓
FRONTEND_URL = (empty)                            ✗
```

**Alternative:** CloudFront domain in Secrets Manager
```bash
aws secretsmanager get-secret-value --secret-id algo/cloudfront-domain
```

**Fix:** Set either `FRONTEND_URL` env var or store domain in Secrets Manager.

---

#### Issue #6: Cognito Authentication Configuration
**Severity:** MEDIUM - Authentication failures
**Status:** ⚠️ NEEDS VERIFICATION

**Problem:**
If Cognito is enabled (COGNITO_USER_POOL_ID set), all required Cognito vars must be configured:
- `COGNITO_USER_POOL_ID` - User pool identifier
- `COGNITO_CLIENT_ID` - App client ID
- `COGNITO_REGION` - AWS region

If any are missing, authentication fails with 403 Forbidden on protected routes.

**Check in Lambda Environment:**
```bash
aws lambda get-function-configuration --function-name algo-api-dev | \
  grep -E "COGNITO_|DEV_BYPASS"
```

**For Development:** Can set `DEV_BYPASS_AUTH=true` to skip authentication
**For Production:** Must have all Cognito vars configured and `DEV_BYPASS_AUTH` not set (or "false")

**Fix:** Set all Cognito environment variables or disable Cognito authentication.

---

### OPTIMIZATION ISSUES (Not Critical Yet)

#### Issue #7: Circuit Breaker Blocks API After 12 Failures
**Severity:** MEDIUM - Dashboard becomes unresponsive temporarily
**File:** `webapp/frontend/src/services/api.js` (Lines 76-123)
**Status:** ⚠️ WORKING AS DESIGNED

**How It Works:**
- After 12 consecutive API failures, circuit breaker opens
- All requests rejected for 15 seconds (RECOVERY_TIMEOUT)
- After 15 seconds, attempts recovery (HALF_OPEN state)
- Needs 3 successful requests to close circuit

**Current Thresholds:**
```javascript
FAILURE_THRESHOLD: 12      // Open after 12 failures
RECOVERY_TIMEOUT: 15000    // Wait 15 seconds before retry
SUCCESS_THRESHOLD: 3       // Need 3 successes to close
```

**Optimization:** If data pipeline issues persist, consider:
- Increasing FAILURE_THRESHOLD to 20+ (more resilient)
- Reducing RECOVERY_TIMEOUT to 5-10s (faster recovery)
- Add alerting when circuit breaker opens

---

#### Issue #8: Query Timeouts on Complex Database Joins
**Severity:** MEDIUM - Slow dashboards when DB under load
**File:** `lambda/api/routes/market.py` (Lines 32-84, 174-242)
**Status:** ⚠️ KNOWN LIMITATION

**Problem:**
These endpoints use complex self-joins over large datasets:
- `/api/market/breadth` - Joins price_daily (9000+ symbols × 25 days)
- `/api/market/top-movers` - Same complexity

Current timeout: 8 seconds

**When Queries Timeout:**
- Database is under heavy write load (during data pipeline runs)
- RDS Proxy connection pool is exhausted
- Network latency between Lambda and RDS
- Slow queries exceed timeout

**Result:** Query gets canceled, returns 503 error

**Optimization:**
1. Increase timeout (acceptable up to ~20 seconds before API Gateway timeout)
2. Implement caching with longer TTL for these endpoints
3. Monitor RDS slow query logs for optimization opportunities
4. Consider pre-computing breadth data in data pipeline

---

## Issue Matrix

| # | Issue | Type | Severity | Fixed? | Impact |
|---|-------|------|----------|--------|--------|
| 1 | Normalizer overwrites success flag | Code Bug | CRITICAL | ✅ YES | Silent failures → crashes |
| 2 | API returns 200 for errors | Code Bug | CRITICAL | ✅ YES | Can't detect errors |
| 3 | Empty database tables | Data Pipeline | HIGH | ⚠️ VERIFY | No data to display |
| 4 | RDS Proxy misconfigured | Configuration | HIGH | ⚠️ VERIFY | Connection failures |
| 5 | Frontend URL missing | Configuration | HIGH | ⚠️ VERIFY | CORS errors block API |
| 6 | Cognito misconfigured | Configuration | MEDIUM | ⚠️ VERIFY | Auth failures |
| 7 | Circuit breaker too aggressive | Design | MEDIUM | ⚠️ OPTIMIZE | Temporary outages |
| 8 | Query timeouts | Performance | MEDIUM | ⚠️ OPTIMIZE | Slow dashboards |
| 9 | Null reference errors | Code Issue | HIGH | ✅ PARTIAL | React crashes |

---

## How Issues Cascade into 5xx Errors

```
┌─ Issue #3 (Empty Tables)
├─ Issue #4 (RDS Proxy Down)
├─ Issue #5 (Frontend URL Missing)
│
├─ API Returns Error or No Data
│  (But returns HTTP 200 - Issue #2)
│
├─ Frontend Normalizer Treats as Success
│  (Overwrites error flag - Issue #1)
│
├─ Component Receives: {success: true, current: null}
│  (Conflicting signals)
│
├─ Component Tries to Render Null Data
│  (Null reference error - Issue #9)
│
├─ React Crashes with "Cannot read properties of null"
│
├─ ErrorBoundary Catches Error
│  (Shows generic error page)
│
├─ User Sees: "Oops, something went wrong" with 500 error UI
│
└─ Circuit Breaker May Open
   (After 12+ failures - Issue #7)
   └─ Blocks ALL API requests for 15 seconds
      └─ Dashboard becomes completely unresponsive
```

---

## Verification Checklist

### Code Fixes (Already Applied)
- [ ] responseNormalizer.js detects error responses
- [ ] algo.py _get_markets() returns proper error codes
- [ ] economic.py yield curve returns proper error codes
- [ ] dataValidation.js provides safe validators

### Configuration (Needs Your Verification)
- [ ] DB_HOST contains "proxy"
- [ ] FRONTEND_URL is set OR algo/cloudfront-domain exists in Secrets Manager
- [ ] COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID set (if using auth)
- [ ] DEV_BYPASS_AUTH is NOT "true" in production
- [ ] Data pipelines executed today
- [ ] market_exposure_daily has recent data
- [ ] market_health_daily has recent data
- [ ] sector_ranking has recent data

### Runtime (Test After Deployment)
- [ ] Health check returns 200: `curl /api/health`
- [ ] Dashboard loads without errors
- [ ] API responses have correct status codes
- [ ] No "Cannot read properties of null" errors
- [ ] No circuit breaker opening messages
- [ ] CloudWatch logs show no FATAL errors

---

## Related Configuration Files

See `steering/deployment-guide.md` for:
- Deployment checklist
- Configuration verification procedures
- Monitoring and alerting setup
- Common troubleshooting steps
- Rollback procedures

For development procedures, see `steering/algo.md` system architecture and procedures.
