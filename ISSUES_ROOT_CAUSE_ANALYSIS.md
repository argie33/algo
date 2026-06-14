# ROOT CAUSE ANALYSIS - Why Nothing Works

## Summary
The system has **fundamental architectural and integration failures** preventing end-to-end functionality. The recent commits show attempts to fix fallback/error handling, but they exposed deeper issues that were masked by the fallbacks.

---

## TIER 1: BLOCKING ISSUES (System won't start/initialize)

### **BLOCK-001: Database Connection Pooling Not Working**
- **Location:** Lambda API depends on RDS Proxy, but proxy may not be properly configured
- **Error Pattern:** API Lambda starts but can't execute any queries
- **Why it blocks:** All endpoints require database access. Without working connection, entire API is dead
- **Severity:** CRITICAL
- **Root Cause:** RDS Proxy configuration mismatch or security group rules blocking traffic
- **Fix:**
  1. Verify RDS Proxy endpoint in terraform.tfvars matches what Lambda is using
  2. Check Lambda security group can reach RDS Proxy security group on port 5432
  3. Test from Lambda: `psql -h <RDS_PROXY_ENDPOINT> -U postgres -d postgres -c "SELECT 1"`

### **BLOCK-002: Terraform State is Corrupted/Invalid**
- **Location:** `/terraform/errored.tfstate` exists (3.4MB)
- **Indicator:** Terraform failed to complete deployment
- **Why it blocks:** Can't deploy updates, infrastructure may be partially created
- **Severity:** CRITICAL
- **Root Cause:** Previous terraform run crashed and state file wasn't recovered
- **Fix:**
  1. Check what's in `errored.tfstate`: `cat terraform/errored.tfstate | jq '.resources[] | .type' | sort | uniq`
  2. Decide: restore from backup or rebuild (recommend backup if available)
  3. Run: `terraform state pull` to see actual state
  4. If diverged: `terraform state rm` broken resources and redeploy

### **BLOCK-003: Database Schema Not Applied**
- **Location:** Schema exists in `/lambda/db-init/schema.sql` but may not be deployed
- **Why it blocks:** Tables don't exist → API queries fail immediately
- **Severity:** CRITICAL
- **Root Cause:** Database initialization step skipped in CI/CD or failed silently
- **Fix:**
  1. Verify tables exist: 
     ```sql
     SELECT COUNT(*) FROM information_schema.tables 
     WHERE table_schema = 'public' AND table_name IN ('price_daily', 'algo_positions', 'stock_symbols');
     ```
  2. If empty: Apply schema manually (CI/CD should do this automatically)
  3. Verify GitHub Actions workflow `verify-and-init-db.yml` ran successfully

### **BLOCK-004: API Lambda Route Import Failures**
- **Location:** `lambda/api/api_router.py` lines 43-50
- **Pattern:** Critical routes (`health`, `algo`) may fail to import due to missing dependencies
- **Why it blocks:** API Lambda refuses to start if imports fail
- **Severity:** CRITICAL
- **Root Cause:** 
  - Missing Lambda layer with required packages (psycopg2, requests, jwt)
  - Incompatible Python version (Lambda uses 3.12, but dependencies compiled for 3.11)
  - Missing setup_imports.py in Lambda package
- **Fix:**
  1. Check Lambda logs: `aws logs tail /aws/lambda/algo-api-dev --follow`
  2. Look for `ImportError`, `ModuleNotFoundError`
  3. Verify Lambda layers attached: `aws lambda get-function --function-name algo-api-dev` → check `Layers`
  4. Rebuild layer: `cd terraform && bash build-layer.sh`

### **BLOCK-005: Cognito/JWT Authentication Broken**
- **Location:** `lambda/api/lambda_function.py` lines 200-250 (JWT verification)
- **Why it blocks:** Protected endpoints reject all requests
- **Severity:** CRITICAL (for authenticated endpoints)
- **Root Cause:**
  - COGNITO_USER_POOL_ID or COGNITO_CLIENT_ID not set in Lambda environment
  - Cognito pool not properly configured in AWS
  - JWKS endpoint unreachable or cached incorrectly
- **Fix:**
  1. Check Lambda env vars: `aws lambda get-function-configuration --function-name algo-api-dev | grep Cognito`
  2. Verify Cognito pool exists and is enabled
  3. Test JWKS fetch: Can Lambda reach `https://cognito-idp.us-east-1.amazonaws.com/<pool>/.well-known/jwks.json`?

### **BLOCK-006: Data Loaders Not Running (No Data)**
- **Location:** Morning and EOD pipelines via EventBridge/Step Functions
- **Why it blocks:** API returns stale/empty data; orchestrator halts on Phase 1
- **Severity:** CRITICAL
- **Root Cause:**
  - EventBridge rules disabled or not firing
  - Step Functions not configured
  - ECS tasks failing silently
  - Docker images not built/pushed
- **Fix:**
  1. Check EventBridge rules enabled: `aws events list-rules --state ENABLED | grep algo`
  2. Check Step Functions status: `aws stepfunctions list-state-machines | grep algo-eod`
  3. Check ECS task definitions: `aws ecs list-task-definitions | grep algo`
  4. If missing: Run GitHub Actions `build-push-ecr.yml` manually

---

## TIER 2: MAJOR INTEGRATION FAILURES (System partially works but data is wrong)

### **MAJOR-001: API Endpoints Return Empty Data Instead of Errors**
- **Location:** Multiple endpoints in `lambda/api/routes/algo.py`
- **Pattern:** When data is missing, returns `[]` or `{}` instead of 503/500 error
- **Why this is bad:** Frontend can't distinguish between "no data" and "error retrieving data"
- **Severity:** HIGH
- **Root Cause:** Recent commit removed fallback masking, but endpoints still have cases returning empty on error
- **Evidence:** Look for `return []` or `return {}` when catching exceptions
- **Fix:**
  - Scan all routes for error handling paths
  - Change all `return []` to proper error_response()
  - Ensure every exception path returns statusCode >= 400

### **MAJOR-002: Data Freshness Validation Too Lenient**
- **Location:** `tools/dashboard/fetchers.py` lines 120-265
- **Pattern:** Data thresholds vary (300s-3600s) depending on endpoint
- **Why this is bad:** Dashboard shows stale data without warning; traders make decisions on old data
- **Severity:** HIGH
- **Root Cause:** Thresholds set arbitrarily, not based on market impact
- **Fix:**
  - Define global thresholds in config:
    - Price data: <5 minutes (300s)
    - Performance metrics: <1 hour (3600s)
    - Market regime: <24 hours (86400s)
  - Validate freshness in all fetchers before returning data
  - Return error if data is stale

### **MAJOR-003: Missing Input Validation on POST Endpoints**
- **Location:** `/api/algo/preview`, `/api/algo/pre-trade-impact`
- **Pattern:** Body parameters not validated before processing
- **Why this is bad:** Invalid input can crash endpoints or return garbage data
- **Severity:** HIGH
- **Root Cause:** No schema validation (pydantic or jsonschema)
- **Fix:**
  1. Create request schemas for all POST endpoints
  2. Validate body parameters before processing
  3. Return 400 Bad Request with clear error message if validation fails

### **MAJOR-004: Database Transaction Errors Don't Rollback**
- **Location:** `algo/algo_daily_reconciliation.py` lines 300-600
- **Pattern:** INSERT/UPDATE statements without explicit rollback on error
- **Why this is bad:** Database gets inconsistent state if multi-statement operation fails partway through
- **Severity:** HIGH
- **Root Cause:** Not using transaction context managers consistently
- **Fix:**
  1. Wrap all multi-statement operations: `with connection.cursor() as cur: ... try: ... except: connection.rollback()`
  2. Verify every database operation uses DatabaseContext
  3. Test failure scenarios (simulate DB timeout, permission error, etc.)

### **MAJOR-005: Async Operations Have No Timeout**
- **Location:** Multiple loaders making external API calls without timeout
- **Evidence:** `requests.get()` calls without `timeout=` parameter
- **Why this is bad:** Hung requests can block Lambda indefinitely, causing timeouts
- **Severity:** HIGH
- **Root Cause:** External API calls (Alpaca, yfinance, FRED) not protected by timeout
- **Fix:**
  - Audit all `requests.get/post` calls
  - Add `timeout=<seconds>` to every one
  - Recommended: timeout=10s for external APIs

### **MAJOR-006: Frontend Error Handling Not Wired to CloudWatch**
- **Location:** `webapp/frontend/src/` - error logging implemented but incomplete
- **Pattern:** Some error paths don't trigger cloudWatchLogger
- **Why this is bad:** Production errors invisible to operators
- **Severity:** HIGH
- **Root Cause:** Not all error boundaries/promise rejections hooked up
- **Fix:**
  1. Global error handler in main.jsx should catch all unhandled errors
  2. Verify cloudWatchLogger called in all error paths
  3. Test: Open browser devtools, trigger error, verify shows in CloudWatch logs

---

## TIER 3: ARCHITECTURAL ISSUES (System works but poorly designed)

### **ARCH-001: SQL Injection Risk in Data Patrol**
- **Location:** `algo/algo_data_patrol.py` line 174
- **Pattern:** Table/column names concatenated into SQL string
- **Severity:** CRITICAL
- **Fix:** Use `psycopg2.sql.Identifier()` for identifiers

### **ARCH-002: No Rate Limiting on API Endpoints**
- **Location:** All public endpoints in `lambda/api/routes/`
- **Pattern:** No rate limit checks on expensive operations
- **Severity:** MEDIUM
- **Fix:** Add rate limiting decorator to all POST/expensive GET endpoints

### **ARCH-003: Configuration Split Between Multiple Sources**
- **Location:** Environment variables, algo_config table, terraform.tfvars
- **Pattern:** Same config exists in multiple places; no single source of truth
- **Severity:** MEDIUM
- **Fix:** Centralize all configuration in one place (recommend DynamoDB or Secrets Manager)

### **ARCH-004: Error Response Format Inconsistent**
- **Location:** Different routes return different error structures
- **Pattern:** Some include `_error`, some don't; some use `error_type`, others use `type`
- **Severity:** MEDIUM
- **Fix:** Enforce single error response format everywhere

### **ARCH-005: No Circuit Breaker for External API Calls**
- **Location:** All external API integrations (Alpaca, yfinance, FRED)
- **Pattern:** If external API fails, system hangs or crashes
- **Severity:** MEDIUM
- **Fix:** Implement circuit breaker pattern with exponential backoff

---

## TIER 4: DATA QUALITY ISSUES

### **DATA-001: Portfolio Data Stale (>1 hour)**
- **Location:** `tools/dashboard/fetchers.py` line 265
- **Pattern:** Freshness threshold is 3600s (1 hour) for portfolio data
- **Why this is bad:** Intraday trading strategy needs data <15 minutes old
- **Severity:** HIGH
- **Fix:** Reduce threshold to 900s (15 minutes) or add real-time pricing endpoint

### **DATA-002: Missing Validation on Market Metrics**
- **Location:** `tools/dashboard/fetchers.py` lines 120-184
- **Pattern:** Market metrics (breadth, momentum, yield curve) not validated
- **Severity:** MEDIUM
- **Fix:** Add null checks and range validation for all market metrics

### **DATA-003: Price Data Coverage Gaps**
- **Location:** Morning pipeline may not load all 5000+ symbols
- **Pattern:** Phase 1 checks coverage but doesn't force retry
- **Severity:** MEDIUM
- **Fix:** If coverage <70%, auto-retry loader or return error

### **DATA-004: Positions Data Can Get Out of Sync**
- **Location:** `algo/algo_daily_reconciliation.py`
- **Pattern:** Position reconciliation with Alpaca may fail, leaving positions inconsistent
- **Severity:** HIGH
- **Fix:** Add comprehensive sync validation, alert if discrepancies found

---

## TIER 5: TESTING & MONITORING GAPS

### **TEST-001: No Automated Integration Tests**
- **Location:** Integration tests exist but are marked manual/interactive
- **Pattern:** Can't run full end-to-end test in CI/CD
- **Severity:** MEDIUM
- **Fix:** Implement automated API contract tests, database state tests

### **MONITOR-001: Missing Metrics for Critical Operations**
- **Location:** No CloudWatch metrics for API endpoint latency, loader duration, data freshness
- **Severity:** MEDIUM
- **Fix:** Emit metrics for all critical operations

### **MONITOR-002: No Health Check for Circuit Breaker State**
- **Location:** `/api/health` endpoint doesn't verify circuit breaker functionality
- **Severity:** MEDIUM
- **Fix:** Add circuit breaker validation to health endpoint

---

## RECOMMENDED FIX SEQUENCE

1. **FIRST (Day 1):** Fix BLOCK-001, BLOCK-003, BLOCK-006
   - Verify database connection works
   - Verify schema applied
   - Verify loaders are running and producing data

2. **SECOND (Day 2):** Fix BLOCK-002, BLOCK-004, BLOCK-005
   - Fix terraform state issues
   - Fix Lambda layer issues
   - Fix Cognito configuration

3. **THIRD (Day 3):** Fix MAJOR-001 through MAJOR-006
   - Standardize error responses
   - Add input validation
   - Add transaction rollback
   - Add timeouts to external calls

4. **FOURTH (Week 2):** Fix ARCH and DATA issues
   - Fix SQL injection risk
   - Fix data freshness thresholds
   - Implement rate limiting

5. **FIFTH (Week 3):** Fix testing and monitoring gaps
   - Add automated tests
   - Add CloudWatch metrics
   - Improve observability

---

## QUICK DIAGNOSTICS COMMANDS

```bash
# Check database connectivity
aws lambda invoke --function-name algo-api-dev \
  --payload '{"httpMethod":"GET","path":"/api/health"}' \
  response.json && cat response.json | jq .

# Check Lambda layers
aws lambda get-function --function-name algo-api-dev | jq .Configuration.Layers

# Check EventBridge rules
aws events list-rules --state ENABLED | grep algo

# Check RDS Proxy
aws rds-proxy describe-db-proxies | grep -i status

# Check ECS tasks
aws ecs list-tasks --cluster algo-cluster-dev

# Check API Gateway
aws apigateway get-stage --rest-api-id <id> --stage-name dev
```

---

## NEXT STEPS

1. Run diagnostics above to identify which BLOCK issue is most critical
2. Start with fixing that specific issue
3. Test each fix before moving to next
4. After all BLOCK issues fixed, test API endpoints manually
5. After API working, test orchestrator and loaders
6. After system working, fix MAJOR/ARCH issues

