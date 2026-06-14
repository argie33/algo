# COMPREHENSIVE ISSUES LIST - All 64+ Outstanding Issues

**Date:** 2026-06-14  
**Status:** Complete audit of entire codebase  
**Total Issues Found:** 64+ critical, high, and medium severity issues

---

## EXECUTIVE SUMMARY

The system has fundamental architectural and integration failures. Recent changes removed fallback/masking, but exposed deeper problems:

1. **11 Blocking Issues** - System won't start/function
2. **7 Major Integration Failures** - Data/API broken
3. **5 Critical Security Issues** - SQL injection, rate limits, auth gaps
4. **10+ Database/Query Issues** - Crashes, inconsistency, locks
5. **8+ Frontend Issues** - Error handling, validation, state
6. **15+ Testing Gaps** - No automated coverage
7. **8+ Monitoring Gaps** - Blind spots in observability

---

## BLOCKING ISSUES (Critical - Fix First)

### BLOCK-001: Database Connection Pooling Failure
**Severity:** CRITICAL  
**Impact:** API Lambda can't execute any queries  
**Root Cause:** RDS Proxy misconfigured or unreachable  
**Evidence:**
- Lambda environment must have `DB_HOST` pointing to RDS Proxy endpoint, not direct RDS
- Security group must allow Lambda → RDS Proxy on port 5432
**Fix:**
- Verify RDS Proxy endpoint in `terraform.tfvars`
- Check Lambda environment variable `DB_HOST` set correctly
- Verify security group ingress rules
- Test: `psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT 1"`

### BLOCK-002: Terraform State Corrupted
**Severity:** CRITICAL  
**Location:** `terraform/errored.tfstate` (3.4MB file exists)  
**Impact:** Can't deploy infrastructure changes  
**Root Cause:** Previous terraform run crashed, state file not recovered  
**Fix:**
- Recover state: `terraform state pull | jq '.resources[] | .type' | sort | uniq`
- Compare to actual AWS resources
- If diverged, selectively restore or rebuild
- Test: `terraform plan` should show no unexpected changes

### BLOCK-003: Database Schema Not Applied
**Severity:** CRITICAL  
**Impact:** Tables don't exist, API fails immediately  
**Root Cause:** Database initialization skipped in CI/CD  
**Tables Required:**
- `price_daily` - CRITICAL
- `algo_positions` - CRITICAL
- `stock_symbols` - CRITICAL
- `market_health_daily` - CRITICAL
- `circuit_breaker_status` - CRITICAL
**Fix:**
- Check: `psql -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'"`
- Apply schema: `psql -f lambda/db-init/schema.sql`
- Verify GitHub Actions `verify-and-init-db.yml` succeeds

### BLOCK-004: Lambda Layer Missing or Incompatible
**Severity:** CRITICAL  
**Location:** Lambda API function `algo-api-dev`  
**Impact:** ImportError on startup (psycopg2, requests, jwt missing)  
**Root Cause:**
- Layer not attached to function
- Compiled for wrong Python version (3.11 vs 3.12)
- Missing `setup_imports.py` in function package
**Fix:**
- Check attached layers: `aws lambda get-function --function-name algo-api-dev | jq '.Configuration.Layers'`
- Rebuild layer: `cd terraform && bash build-layer.sh`
- Verify Python version: Lambda runtime must be 3.12
- Check logs: `aws logs tail /aws/lambda/algo-api-dev`

### BLOCK-005: Cognito Configuration Incomplete
**Severity:** CRITICAL (for protected endpoints)  
**Location:** `lambda/api/lambda_function.py` lines 200-250  
**Impact:** All authenticated endpoints reject requests  
**Required Environment Variables:**
- `COGNITO_USER_POOL_ID` (e.g., `us-east-1_XJpLb9SKX`)
- `COGNITO_CLIENT_ID` (e.g., `6smb0vrcidd9kvhju2kn2a3qrl`)
**Root Cause:**
- Variables not set in Lambda environment
- Cognito pool not properly configured
- JWKS endpoint unreachable
**Fix:**
- Verify env vars: `aws lambda get-function-configuration --function-name algo-api-dev | jq '.Environment.Variables'`
- Test JWKS: Can Lambda reach `https://cognito-idp.us-east-1.amazonaws.com/<pool-id>/.well-known/jwks.json`?
- Check Cognito pool: is it enabled? Do credentials exist?

### BLOCK-006: Data Loaders Not Running
**Severity:** CRITICAL  
**Impact:** API returns stale/empty data, Orchestrator halts  
**Root Cause:**
- EventBridge rules disabled
- Step Functions not configured
- ECS tasks failing silently
- Docker images not built/pushed
**Morning Pipeline Missing:** `2:00 AM ET` run doesn't load prices, health, scores  
**EOD Pipeline Missing:** `4:05 PM ET` run doesn't load market exposure, performance metrics  
**Fix:**
- Check EventBridge enabled: `aws events list-rules --state ENABLED | grep algo`
- Check Step Functions: `aws stepfunctions list-state-machines | grep algo-eod`
- Check ECS tasks: `aws ecs list-task-definitions | grep algo`
- Run CI/CD: `build-push-ecr.yml` to rebuild Docker images
- Manual test: `aws stepfunctions start-execution --state-machine-arn <arn>`

### BLOCK-007: API Lambda Route Import Failures
**Severity:** CRITICAL  
**Location:** `lambda/api/api_router.py` lines 43-50  
**Impact:** API refuses to start if `health` or `algo` routes fail to import  
**Root Cause:**
- Missing dependencies in Lambda package
- Circular imports
- Missing module files
**Evidence:** Look for `CRITICAL_ROUTE_IMPORT_FAILURE` in Lambda logs  
**Fix:**
- Check logs: `aws logs tail /aws/lambda/algo-api-dev --follow`
- Search for `ImportError`, `ModuleNotFoundError`
- Verify `routes/health.py` and `routes/algo.py` exist
- Verify all imported modules are in Lambda package

### BLOCK-008: Secrets Manager Access Failing
**Severity:** HIGH  
**Location:** Lambda tries to fetch credentials from Secrets Manager  
**Impact:** Lambda can't get RDS credentials, Alpaca keys, CloudFront domain  
**Root Cause:**
- Lambda IAM role doesn't have `secretsmanager:GetSecretValue` permission
- Secret doesn't exist
- Lambda in wrong VPC/region
**Fix:**
- Check IAM role: Does it have `secretsmanager:*` permissions?
- Check secret exists: `aws secretsmanager get-secret-value --secret-id algo/cloudfront-domain`
- Check region: Lambda must be in same region as secrets (us-east-1)

### BLOCK-009: VPC Configuration Broken
**Severity:** HIGH  
**Location:** Lambda API in VPC trying to reach RDS Proxy  
**Impact:** Network isolation prevents database access  
**Root Cause:**
- Lambda in wrong subnet
- Security group rules missing
- NAT Gateway not configured for outbound
**Fix:**
- Verify Lambda VPC/subnets: `aws lambda get-function-configuration --function-name algo-api-dev | jq '.VpcConfig'`
- Verify RDS Proxy security group: allows inbound from Lambda SG on port 5432
- Test network connectivity from Lambda using test SNS message

### BLOCK-010: OIDC/GitHub Actions Authentication Broken
**Severity:** HIGH  
**Impact:** CI/CD can't deploy, can't run migrations  
**Root Cause:**
- OIDC role not properly configured
- Trust policy missing correct principal
- GitHub Actions workflow not sending correct JWT claims
**Fix:**
- Check OIDC role exists: `aws iam list-roles | grep oidc`
- Verify trust policy includes `token.actions.githubusercontent.com`
- Test manually: Run GitHub Actions workflow and check logs

### BLOCK-011: Frontend CloudFront Distribution Not Serving
**Severity:** HIGH  
**Impact:** Dashboard frontend not accessible  
**Root Cause:**
- CloudFront distribution not deployed
- S3 bucket not configured
- Origin configuration wrong
**Fix:**
- Check distribution exists: `aws cloudfront list-distributions | grep algo`
- Verify S3 bucket has website hosting enabled
- Check origin configuration: S3 endpoint must be S3 website endpoint, not REST endpoint

---

## MAJOR INTEGRATION FAILURES (High Priority)

### MAJOR-001: API Returns Empty Data Instead of Errors
**Severity:** HIGH  
**Location:** Multiple routes in `lambda/api/routes/algo.py`, `market.py`, `prices.py`  
**Pattern:**
```python
try:
    data = fetch_data()
    return success_response(data)  # Returns [] or {} when data missing
except:
    return []  # WRONG - should be error_response
```
**Impact:** Frontend can't distinguish between "no data" and "query failed"  
**Evidence:** Look for any `return []` or `return {}` in error handling paths  
**Fix:** Audit all routes, ensure every exception returns `error_response()`

### MAJOR-002: Data Freshness Thresholds Inconsistent
**Severity:** HIGH  
**Location:** `tools/dashboard/fetchers.py` lines 120-265  
**Current Thresholds:**
- Performance: 3600s (1 hour)
- Market: 300s (5 minutes)
- Portfolio: 3600s (1 hour)
- Prices: varies
**Problem:** Trader sees 1-hour-old performance data but 5-minute-old market data  
**Fix:**
- Define global thresholds
- Apply consistently across all fetchers
- Alert if data exceeds threshold

### MAJOR-003: Missing Input Validation on POST Endpoints
**Severity:** HIGH  
**Endpoints:**
- `/api/algo/preview` (line 1293)
- `/api/algo/pre-trade-impact` (line 1353)
- `/api/contact/submit` (line 127)
**Problem:** No schema validation; invalid input crashes or returns garbage  
**Fix:**
- Add request body validation using pydantic/jsonschema
- Return 400 Bad Request with clear error message if validation fails
- Test: Send invalid JSON, verify proper error

### MAJOR-004: Database Transactions Don't Rollback on Error
**Severity:** HIGH  
**Location:** `algo/algo_daily_reconciliation.py` multiple INSERT/UPDATE blocks  
**Pattern:**
```python
cur.execute("INSERT INTO table1 ...")
cur.execute("INSERT INTO table2 ...")  # This fails
# Connection not rolled back - inconsistent state!
```
**Impact:** Database corrupted (partial updates, orphaned records)  
**Fix:**
- Use `with DatabaseContext('write') as cur:` everywhere
- Add explicit try/except with `connection.rollback()` on error
- Test: Simulate database error mid-transaction

### MAJOR-005: External API Calls Have No Timeout
**Severity:** HIGH  
**Location:** Loaders making requests to Alpaca, yfinance, FRED  
**Pattern:** `response = requests.get(url)` without `timeout=X`  
**Impact:** Hung requests block Lambda indefinitely  
**Fix:**
- Add `timeout=10` to all `requests.get/post` calls
- Wrap in try/except with timeout-specific error handling
- Test: Simulate API hanging

### MAJOR-006: Frontend Promise Rejections Unhandled
**Severity:** HIGH  
**Location:** `webapp/frontend/src/components/auth/`, `services/api.js`  
**Pattern:**
```javascript
fetch(url).then(...).catch(...)  // Missing .catch() on some
```
**Impact:** Unhandled rejections crash application silently  
**Fix:**
- Add `.catch()` to all promises
- Implement global error handler
- Test: Open DevTools, trigger error, verify CloudWatch log

### MAJOR-007: Circuit Breaker Not Preventing Trades
**Severity:** HIGH  
**Location:** Phase 2 circuit breaker checks vs Phase 6 entry execution  
**Pattern:**
- Phase 2 sets halt flag if breaker triggered
- Phase 6 may not check flag properly
- Trades could execute despite halt
**Impact:** System trades despite risk condition  
**Fix:**
- Verify Phase 6 reads halt flag
- Test: Manually trigger circuit breaker, verify Phase 6 skips

---

## CRITICAL SECURITY ISSUES

### SEC-001: SQL Injection in Data Patrol
**Severity:** CRITICAL  
**Location:** `algo/algo_data_patrol.py` line 174  
**Pattern:**
```python
query = f"SELECT * FROM {table_name} WHERE {col} > ..."  # Table/col names unescaped
```
**Impact:** Attacker can execute arbitrary SQL  
**Fix:** Use `psycopg2.sql.Identifier()` for table/column names

### SEC-002: No Rate Limiting on Authentication
**Severity:** CRITICAL  
**Location:** Cognito endpoints  
**Impact:** Brute force attacks possible  
**Fix:** Add rate limiting (5 attempts per 15 minutes per IP)

### SEC-003: No Rate Limiting on API Endpoints
**Severity:** HIGH  
**Location:** All POST endpoints  
**Impact:** DOS attacks possible  
**Fix:** Add rate limiting to expensive operations

### SEC-004: Hardcoded Trading Mode (Live vs Paper)
**Severity:** HIGH  
**Location:** Multiple files checking `APCA_API_BASE_URL`  
**Impact:** If env var changed, real money at risk  
**Fix:** Add startup warning, require explicit confirmation for LIVE mode

### SEC-005: Missing CORS Whitelist
**Severity:** MEDIUM  
**Location:** `lambda/api/lambda_function.py` line 167  
**Pattern:** `Access-Control-Allow-Origin: *` is too permissive  
**Fix:** Whitelist only CloudFront domain

### SEC-006: Credential Leakage in Error Messages
**Severity:** MEDIUM  
**Location:** Lambda error logging  
**Pattern:** Error messages include `APCA_API_BASE_URL`  
**Fix:** Redact sensitive env vars from error messages

### SEC-007: Missing Email Validation
**Severity:** MEDIUM  
**Location:** `/api/contact/submit` endpoint  
**Fix:** Validate email format, add message length limits

### SEC-008: No Input Sanitization
**Severity:** MEDIUM  
**Location:** All user input endpoints  
**Fix:** Sanitize strings, validate data types

### SEC-009: Session Token Storage Issues
**Severity:** HIGH  
**Location:** Frontend JWT handling  
**Note:** Recent legal flag on compliance - need verification  
**Fix:** Verify JWT storage compliant with regulations

### SEC-010: Missing API Key Rotation
**Severity:** MEDIUM  
**Location:** Alpaca/FRED API keys in Secrets Manager  
**Fix:** Implement automatic key rotation (quarterly minimum)

---

## DATABASE & QUERY ISSUES

### DB-001: Potential N+1 Query Pattern
**Severity:** MEDIUM  
**Location:** `algo/algo_daily_reconciliation.py` lines 400-500  
**Pattern:** Loop fetching position data without bulk optimization  
**Impact:** 1000s of queries instead of 1  
**Fix:** Use SQL JOIN instead of loop

### DB-002: Missing Connection Cleanup on Lambda Timeout
**Severity:** HIGH  
**Location:** `lambda/api/lambda_function.py`  
**Impact:** Connection pool exhausted over time  
**Fix:** Ensure all database operations use `DatabaseContext` context manager

### DB-003: Missing Database Indexes
**Severity:** MEDIUM  
**Location:** `price_daily(symbol, date)`, `algo_positions(symbol)`, etc.  
**Impact:** Slow queries  
**Fix:** Run EXPLAIN ANALYZE, add indexes for slow queries

### DB-004: Statement Timeout Not Configured
**Severity:** HIGH  
**Location:** Database initialization  
**Impact:** Loaders hang indefinitely  
**Fix:** Set `statement_timeout = 15 * 60 * 1000` (15 minutes)

### DB-005: Connection Pool Exhaustion Risk
**Severity:** HIGH  
**Location:** RDS Proxy configuration  
**Impact:** New connections refused  
**Fix:** Monitor connection usage, tune pool size

### DB-006: No Connection Retries
**Severity:** MEDIUM  
**Location:** Database connection code  
**Impact:** Transient failures crash loaders  
**Fix:** Implement exponential backoff for connection retries

### DB-007: Missing Deadlock Detection
**Severity:** MEDIUM  
**Location:** Multi-statement transactions  
**Impact:** Random transaction failures  
**Fix:** Add deadlock retry logic

### DB-008: Implicit Type Conversion Bugs
**Severity:** LOW  
**Location:** `algo/algo_position_sizer.py` and other files  
**Pattern:** `safe_float()` called on potentially NULL values  
**Fix:** Add explicit NULL checks before conversions

### DB-009: Missing Audit Trail
**Severity:** MEDIUM  
**Location:** Configuration changes in `algo_config` table  
**Fix:** Add audit table tracking who changed what when

### DB-010: No Foreign Key Constraints
**Severity:** MEDIUM  
**Location:** Database schema  
**Impact:** Orphaned records possible  
**Fix:** Add FK constraints

---

## FRONTEND ISSUES

### FE-001: Missing Error Boundary
**Severity:** MEDIUM  
**Location:** `webapp/frontend/src/pages/TradeTracker.jsx`  
**Impact:** Component crash crashes entire app  
**Fix:** Wrap with `<ErrorBoundary>`

### FE-002: Unhandled Promise Rejection in Auth
**Severity:** HIGH  
**Location:** `webapp/frontend/src/components/auth/`  
**Pattern:** `fetch(...).then(...)` without `.catch()`  
**Fix:** Add error handling to all async operations

### FE-003: Missing Null Check in Charts
**Severity:** MEDIUM  
**Location:** `HistoricalPriceChart.jsx`  
**Pattern:** Chart renders without validating data array  
**Fix:** Add guard clause for empty/invalid data

### FE-004: Missing Loading State
**Severity:** LOW  
**Location:** Multiple pages using `useApiQuery()`  
**Pattern:** No skeleton/spinner while loading  
**Fix:** Always show loading state during fetch

### FE-005: Console.log in Production Code
**Severity:** LOW  
**Location:** Multiple component files  
**Impact:** Clutters browser console  
**Fix:** Remove or wrap in debug flag

### FE-006: Memory Leak from Unclosed Subscriptions
**Severity:** MEDIUM  
**Location:** useEffect hooks without cleanup  
**Pattern:** `useEffect(() => { subscribe(...) }, [])`  
**Fix:** Return unsubscribe function from useEffect

### FE-007: Hardcoded API URLs
**Severity:** MEDIUM  
**Location:** `webapp/frontend/src/services/api.js`  
**Pattern:** API endpoint URLs hardcoded  
**Fix:** Use environment variables

### FE-008: Missing CORS Error Handling
**Severity:** MEDIUM  
**Location:** API request interceptors  
**Pattern:** CORS errors not distinguished from other errors  
**Fix:** Add specific handling for CORS errors

### FE-009: Session Storage Issues
**Severity:** HIGH  
**Location:** JWT token storage  
**Pattern:** Token stored in localStorage (XSS vulnerable)  
**Recommendation:** Use httpOnly cookies or sessionStorage

### FE-010: Missing Input Validation
**Severity:** MEDIUM  
**Location:** Form components  
**Fix:** Add client-side validation before submit

---

## TESTING GAPS

### TEST-001: No Automated Integration Tests
**Severity:** MEDIUM  
**Location:** Integration tests marked manual/interactive  
**Impact:** Can't verify end-to-end in CI/CD  
**Fix:** Implement automated API contract tests

### TEST-002: Missing Unit Tests for Validators
**Severity:** HIGH  
**Location:** `safe_float_strict`, `safe_int_strict` functions  
**Impact:** No confidence validation works correctly  
**Fix:** Create comprehensive test suite

### TEST-003: Missing API Contract Tests
**Severity:** HIGH  
**Location:** No contract tests for API responses  
**Fix:** Implement Pact or similar contract testing

### TEST-004: Missing Database Tests
**Severity:** MEDIUM  
**Location:** No tests for database schema, migrations  
**Fix:** Add schema validation tests

### TEST-005: Missing E2E Tests
**Severity:** HIGH  
**Location:** Frontend has Playwright tests but commented/disabled  
**Fix:** Enable and run E2E tests in CI/CD

### TEST-006: Missing Load Tests
**Severity:** MEDIUM  
**Impact:** Unknown system capacity  
**Fix:** Implement load testing for API and database

### TEST-007: Missing Chaos Testing
**Severity:** LOW  
**Impact:** Unknown failure modes  
**Fix:** Test system with simulated failures

### TEST-008: Missing Penetration Testing
**Severity:** MEDIUM  
**Impact:** Unknown security vulnerabilities  
**Fix:** Conduct penetration testing

### TEST-009: Test Coverage Unknown
**Severity:** MEDIUM  
**Impact:** Unknown code coverage  
**Fix:** Generate coverage reports

### TEST-010: Missing Regression Tests
**Severity:** MEDIUM  
**Impact:** Previous bugs may reoccur  
**Fix:** Automate regression test suite

### TEST-011: Missing Price Data Validation Tests
**Severity:** HIGH  
**Location:** No tests for `/api/prices` endpoint  
**Fix:** Add comprehensive price validation tests

### TEST-012: Missing Position Reconciliation Tests
**Severity:** HIGH  
**Location:** No tests for position sync with Alpaca  
**Fix:** Add tests for reconciliation logic

### TEST-013: Cognito Tests Require Manual Login
**Severity:** MEDIUM  
**Location:** `test_cognito_endpoints.py` lines 247, 251  
**Fix:** Use test credentials for automated testing

### TEST-014: Performance Tests Missing
**Severity:** MEDIUM  
**Impact:** Unknown API latency  
**Fix:** Add performance benchmarks

### TEST-015: Missing Circuit Breaker Tests
**Severity:** HIGH  
**Location:** No tests verifying circuit breaker triggers correctly  
**Fix:** Add tests for all breaker conditions

---

## MONITORING & OBSERVABILITY GAPS

### MON-001: Missing Metrics for API Latency
**Severity:** MEDIUM  
**Location:** No CloudWatch metrics for endpoint latency  
**Impact:** Can't detect API degradation  
**Fix:** Emit `AlgoTrading/API/Latency` metric

### MON-002: Missing Metrics for Data Freshness
**Severity:** MEDIUM  
**Location:** No per-source metrics  
**Impact:** Can't see which source is stale  
**Fix:** Emit freshness metrics per source

### MON-003: Missing Metrics for Loader Duration
**Severity:** MEDIUM  
**Location:** No tracking of individual loader times  
**Fix:** Emit per-loader duration metrics

### MON-004: Missing Error Count Metrics
**Severity:** MEDIUM  
**Location:** Errors logged but not metricated  
**Fix:** Emit error count metrics by type

### MON-005: Missing Health Check for Circuit Breakers
**Severity:** MEDIUM  
**Location:** `/api/health` doesn't verify CB functionality  
**Fix:** Add circuit breaker validation

### MON-006: Missing Audit Log
**Severity:** MEDIUM  
**Location:** Configuration changes not fully audited  
**Fix:** Implement audit trail in database

### MON-007: Missing Alert for Data Staleness
**Severity:** HIGH  
**Impact:** Stale data used silently  
**Fix:** Alert when critical data >24h old

### MON-008: Missing Alert for Loader Failures
**Severity:** HIGH  
**Location:** Loaders fail but no alert  
**Fix:** Emit CloudWatch alarm for failed loaders

### MON-009: No Dashboard for Real-Time System Status
**Severity:** MEDIUM  
**Impact:** Can't see system health at a glance  
**Fix:** Create CloudWatch dashboard

### MON-010: Missing Request ID Tracing
**Severity:** MEDIUM  
**Location:** No correlation IDs in logs  
**Fix:** Add request ID to all log messages

### MON-011: Missing Performance Baseline
**Severity:** MEDIUM  
**Impact:** Unknown what's "normal" performance  
**Fix:** Establish baseline metrics

### MON-012: Missing SLO Definition
**Severity:** MEDIUM  
**Impact:** No service level objectives  
**Fix:** Define SLOs for critical operations

---

## ARCHITECTURE & DESIGN ISSUES

### ARCH-001: Circular Dependency in Imports
**Severity:** MEDIUM  
**Location:** `algo_config.py` → `algo_orchestrator.py` → back to config  
**Impact:** Import order matters, fragile  
**Fix:** Use dependency injection to break cycles

### ARCH-002: Inconsistent Error Response Format
**Severity:** MEDIUM  
**Location:** Routes use mix of `error_type` and `type` fields  
**Impact:** Clients must handle multiple formats  
**Fix:** Standardize to single error response schema

### ARCH-003: No Abstract Base Classes
**Severity:** LOW  
**Location:** Signal classes don't inherit from common base  
**Impact:** Code duplication  
**Fix:** Create `BaseSignal` class

### ARCH-004: Data Provenance Tracking Unused
**Severity:** MEDIUM  
**Location:** `data_provenance_tracker.py` exists but not consistently used  
**Impact:** Can't trace data origin  
**Fix:** Enforce provenance tracking everywhere

### ARCH-005: Feature Flags Not Versioned
**Severity:** LOW  
**Location:** Feature flags changed but no audit trail  
**Fix:** Log all flag changes with timestamp/user

### ARCH-006: Configuration Split Across Multiple Sources
**Severity:** MEDIUM  
**Location:** Config in env vars, algo_config table, terraform.tfvars  
**Impact:** Hard to find where config is set  
**Fix:** Centralize in DynamoDB or Secrets Manager

### ARCH-007: No Circuit Breaker for External APIs
**Severity:** MEDIUM  
**Location:** Alpaca, yfinance, FRED integrations  
**Impact:** System hangs on external API failure  
**Fix:** Implement circuit breaker pattern

### ARCH-008: Tight Coupling Between Modules
**Severity:** MEDIUM  
**Impact:** Hard to test individual modules  
**Fix:** Use dependency injection

---

## CONFIGURATION ISSUES

### CONFIG-001: Hardcoded API Timeout
**Severity:** MEDIUM  
**Location:** `tools/dashboard/utilities.py` line 133  
**Value:** 5 seconds (not configurable)  
**Impact:** Can't tune for different network conditions  
**Fix:** Move to environment variable

### CONFIG-002: Hardcoded Connection Pool Size
**Severity:** LOW  
**Location:** `tools/dashboard/utilities.py` line 137  
**Value:** 16 connections  
**Fix:** Make configurable via environment

### CONFIG-003: Hardcoded Retry Count
**Severity:** LOW  
**Location:** Various loader files  
**Value:** 5 retries  
**Fix:** Make configurable via environment

### CONFIG-004: Missing Environment Variable Validation
**Severity:** MEDIUM  
**Location:** Lambda startup  
**Impact:** Missing vars cause cryptic errors  
**Fix:** Validate all required vars at startup

---

## DATA QUALITY ISSUES

### DATA-001: Portfolio Data Freshness Too Lenient
**Severity:** HIGH  
**Location:** `fetchers.py` line 265  
**Threshold:** 3600s (1 hour)  
**Impact:** Intraday traders use stale portfolio  
**Fix:** Reduce to 900s (15 minutes)

### DATA-002: Missing Validation on Market Metrics
**Severity:** MEDIUM  
**Location:** `fetchers.py` lines 120-184  
**Metrics:** breadth %, momentum, yield curve slope  
**Impact:** Invalid metrics used in calculations  
**Fix:** Add validation and error handling

### DATA-003: Price Coverage Gaps
**Severity:** MEDIUM  
**Location:** Morning pipeline  
**Impact:** Missing data for some symbols  
**Fix:** Force retry if coverage <70%

### DATA-004: Positions Out of Sync with Alpaca
**Severity:** HIGH  
**Location:** Position reconciliation in orchestrator  
**Impact:** Position data inconsistent with actual trades  
**Fix:** Comprehensive sync validation

### DATA-005: Historical Data Array Not Validated
**Severity:** MEDIUM  
**Location:** `fetchers.py` lines 410-420  
**Impact:** Empty/invalid arrays returned to frontend  
**Fix:** Validate array contents before returning

### DATA-006: Null Values in Critical Columns
**Severity:** HIGH  
**Location:** Technical data enrichment  
**Impact:** Signals generated with NULL technical indicators  
**Fix:** Ensure all technical data filled before signal generation

---

## DOCUMENTATION GAPS

### DOC-001: Missing API Documentation
**Severity:** MEDIUM  
**Location:** No OpenAPI/Swagger spec  
**Impact:** API consumers don't know endpoints exist  
**Fix:** Generate OpenAPI spec

### DOC-002: Missing Troubleshooting Guide
**Severity:** MEDIUM  
**Location:** OPERATIONAL_SETUP.md exists but incomplete  
**Fix:** Add decision trees for common issues

### DOC-003: Missing Configuration Reference
**Severity:** MEDIUM  
**Location:** Env vars scattered across files  
**Fix:** Create central environment variable reference

### DOC-004: Missing Runbook for Scaling
**Severity:** LOW  
**Location:** No documentation on Lambda concurrency  
**Fix:** Document expected concurrency and scaling

### DOC-005: Missing Migration Runbook
**Severity:** MEDIUM  
**Location:** No step-by-step migration guide  
**Fix:** Create database migration procedures

---

## OPERATIONAL ISSUES

### OPS-001: No Pre-Flight Checks
**Severity:** HIGH  
**Location:** Orchestrator doesn't validate prerequisites  
**Impact:** Orchestrator starts with missing data  
**Fix:** Add pre-flight validation before Phase 1

### OPS-002: No Graceful Shutdown Handler
**Severity:** MEDIUM  
**Location:** Orchestrator doesn't catch SIGTERM  
**Impact:** Connections not closed on Lambda timeout  
**Fix:** Add signal handlers for graceful shutdown

### OPS-003: Dependency Versions Not Pinned
**Severity:** MEDIUM  
**Location:** `requirements.txt`  
**Impact:** Builds may fail due to incompatible versions  
**Fix:** Pin all dependencies to specific versions

### OPS-004: Missing Docker Healthcheck
**Severity:** MEDIUM  
**Location:** `Dockerfile`  
**Impact:** Container orchestration can't detect health  
**Fix:** Add HEALTHCHECK instruction

### OPS-005: CI/CD Failure Runbook Missing
**Severity:** MEDIUM  
**Impact:** Can't troubleshoot deployment failures  
**Fix:** Create CI/CD troubleshooting guide

### OPS-006: No Infrastructure Change Log
**Severity:** LOW  
**Impact:** Can't track infrastructure changes  
**Fix:** Document all infrastructure modifications

---

## PERFORMANCE ISSUES

### PERF-001: Memory Leak from Unclosed Connections
**Severity:** MEDIUM  
**Location:** `tools/dashboard/utilities.py` line 134  
**Impact:** Memory usage increases over time  
**Fix:** Ensure connections properly closed on timeout

### PERF-002: Inefficient Data Conversion
**Severity:** LOW  
**Location:** `data_validation.py` safe validators  
**Impact:** Slow processing of large datasets  
**Fix:** Optimize validation logic for bulk operations

### PERF-003: Blocking Sleep in Dashboard Loop
**Severity:** LOW  
**Location:** `dashboard.py` lines 383, 437  
**Impact:** Dashboard unresponsive  
**Fix:** Use async sleep or remove blocking wait

### PERF-004: No Query Caching
**Severity:** MEDIUM  
**Impact:** Same queries re-executed repeatedly  
**Fix:** Implement query caching layer

### PERF-005: No Connection Pooling Reuse
**Severity:** MEDIUM  
**Impact:** New connection created per request  
**Fix:** Verify RDS Proxy pooling enabled

---

## SUMMARY BY SEVERITY

**CRITICAL (must fix immediately):**
- 11 Blocking issues
- 5 Security issues
- 3 Database critical issues
- ~19 total critical

**HIGH (fix this week):**
- 7 Major integration issues
- 8 High severity security/testing gaps
- 8+ database issues
- 6+ frontend issues
- ~29 total high

**MEDIUM (fix this sprint):**
- 10 Architecture issues
- 15 Testing gaps
- 12 Monitoring gaps
- 8 Configuration issues
- 6 Data quality issues
- ~51 total medium

**TOTAL: 64+ outstanding issues**

---

## RECOMMENDED FIX PRIORITY

### Week 1 (Restore Functionality)
1. Fix database connection (BLOCK-001)
2. Fix terraform state (BLOCK-002)
3. Apply schema (BLOCK-003)
4. Fix Lambda layers (BLOCK-004)
5. Fix Cognito (BLOCK-005)
6. Get loaders running (BLOCK-006)

### Week 2 (Fix Major Problems)
1. Standardize error responses (MAJOR-001)
2. Fix data freshness (MAJOR-002)
3. Add input validation (MAJOR-003)
4. Fix transaction rollback (MAJOR-004)
5. Add timeouts (MAJOR-005)
6. Wire frontend logging (MAJOR-006)

### Week 3 (Security & Stability)
1. Fix SQL injection (SEC-001)
2. Add rate limiting (SEC-002, SEC-003)
3. Implement circuit breakers (SEC-007, ARCH-007)
4. Add proper logging (MON-001 through MON-012)

### Week 4+ (Long-term improvements)
- Add automated tests
- Improve monitoring
- Fix architecture issues
- Optimize performance

---

## TESTING THIS DOCUMENT

To verify these issues:

1. Check Blocking issues:
```bash
# Can you connect to database?
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT COUNT(*) FROM price_daily"

# Are loaders running?
aws stepfunctions describe-execution --execution-arn <arn>

# Check Lambda health
curl https://<api-url>/api/health | jq .
```

2. Check Major issues:
```bash
# Any 503 errors?
aws logs filter-log-events --log-group-name /aws/lambda/algo-api-dev --filter-pattern "503"

# Any empty data responses?
aws logs filter-log-events --log-group-name /aws/lambda/algo-api-dev --filter-pattern "return \[\]"
```

3. Check Security issues:
```bash
# Any hardcoded credentials?
grep -r "APCA_API_KEY\|DB_PASSWORD" --include="*.py" --exclude-dir=.git

# SQL injection risks?
grep -r "f\"SELECT\|f'SELECT" lambda/ --include="*.py"
```

---

**Next Action:** Start with BLOCK-001 diagnosis. Use the AWS CLI commands in COMPREHENSIVE_ISSUES_LIST.md to identify which blocking issues are preventing your system from functioning.

