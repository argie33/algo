# Dashboard 5xx Error Diagnostic Report

**Date**: 2026-07-06  
**Status**: 8/26 endpoints failing with 5xx errors  

---

## EXECUTIVE SUMMARY

The dashboard is showing 5xx errors for 8 API endpoints. Root cause analysis:

1. **Fixed**: Activity/audit endpoint response schemas (committed)
2. **Unfixed**: Lambda API returning 500 errors for 3 endpoints  
3. **Circuit Breaker**: Opened after 3 consecutive failures, blocking all subsequent calls
4. **Data Staleness**: Circuit breaker endpoint returns 503 (data older than 1 hour)

---

## FAILING ENDPOINTS (8 TOTAL)

### Group A: 500 Server Errors (3)
- **activity** → `/api/algo/audit-log` (500 after 4 retries)
- **audit** → `/api/algo/audit-log` (500 after 4 retries)
- **exec_hist** → `/api/algo/execution/recent` (500 after 4 retries)

### Group B: 503 Service Unavailable (5)
- **sentiment** → `/api/algo/sentiment` (circuit breaker open)
- **sec_rot** → `/api/algo/sector-rotation` (circuit breaker open)
- **srank** → `/api/sectors` (circuit breaker open)
- **cb** → `/api/algo/circuit-breakers` (circuit breaker open)
- **sig_eval** → `/api/algo/rejection-funnel` (circuit breaker open)

---

## ROOT CAUSE ANALYSIS

### Immediate Cause
1. Group A endpoints throw 500 errors in Lambda
2. After 3 failures, dashboard's circuit breaker opens (fail-safe)
3. Group B endpoints blocked by circuit breaker (transient 503s)

### Why Endpoints Throw 500
Possible causes in AWS Lambda environment:

1. **Database Connectivity**
   - Lambda → RDS Proxy connection failing
   - Verify: RDS security groups, VPC endpoints, credentials
   
2. **Schema Mismatch**
   - Columns renamed or removed in migrations
   - Example: Earlier fix was `check_date` vs `computed_at`
   - Verify: Run migrations on AWS RDS

3. **Response Validation**
   - API handlers returning unexpected field types
   - Fixed: Activity/audit contracts now match handler output (see commit 21120d031)
   
4. **Missing Data / Stale Cache**
   - Circuit breaker endpoint explicitly checks data freshness
   - Returns 503 if data >1 hour old (correct fail-closed behavior)
   - Verify: Data loaders have executed recently

---

## DATABASE STATUS (Local)

```
[OK] Database connection successful

Table Status:
  algo_audit_log: [EXISTS] - 9,807 rows
  orchestrator_execution_log: [EXISTS] - 2 rows
  circuit_breaker_status: [EXISTS] - 2 rows
```

**Note**: These tables exist and have data locally, but Lambda API still returns 500.
This suggests Lambda deployment or AWS connectivity issues, not database schema problems.

---

## CHANGES MADE THIS SESSION

### Commit 21120d031: Fixed Response Schemas
```
- activity endpoint: Removed fields only computed by fetcher (run_id, run_at, phases, recent_actions)
- audit endpoint: Added pagination fields (total, limit, offset) to optional_fields
- exec_hist endpoint: Added pagination fields (total, limit) to optional_fields
```

**Impact**: Eliminates response validation errors. If 500 continues after redeployment,
issue is in Lambda handler logic, not response schema mismatch.

---

## OTHER ISSUES IDENTIFIED

### Data Metric Thresholds Lowered (load_stock_scores.py)
```
BEFORE: value_metrics=80%, growth_metrics=70%, positioning_metrics=70%, stability_metrics=85%
NOW:    all metrics=50% (marked "TEMPORARILY LOWERED FOR DEMO")
```

**Impact**: Stock scoring coverage reduced, may affect signal generation quality.
**Action**: Restore thresholds to intended values or make demo mode permanent.

---

## NEXT STEPS (PRIORITY ORDER)

### 1. CHECK LAMBDA LOGS (IMMEDIATE)
```bash
# View Lambda execution errors in CloudWatch
aws logs tail /aws/lambda/algo-api-dev --follow

# Or: Check recent Lambda errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/algo-api-dev \
  --start-time $(($(date +%s%N) - 3600000000000)) \
  --filter-pattern "ERROR" \
  | jq '.events[] | {timestamp, message: .message[:200]}'
```

### 2. VERIFY AWS DEPLOYMENT
```bash
# Confirm current Lambda code was deployed after commit 21120d031
aws lambda get-function-code-location --function-name algo-api-dev

# Redeploy if needed
cd terraform && terraform apply -lock=false
```

### 3. CHECK DATABASE MIGRATIONS (AWS)
```bash
# Connect to RDS and verify tables
psql -h <rds-proxy-endpoint> -U algo -d algo

# List recent migrations
SELECT * FROM alembic_version ORDER BY version_num DESC LIMIT 10;
```

### 4. VERIFY RDS CONNECTIVITY FROM LAMBDA
```bash
# Check security group allows 5432 from Lambda security group
# Verify VPC endpoints for RDS Proxy
# Test Lambda → RDS connection with simple query

# Add to Lambda handler for debugging:
import psycopg2
try:
    conn = psycopg2.connect(...)
    print("RDS connection successful")
except Exception as e:
    logger.error(f"RDS connection failed: {e}")
```

### 5. CHECK CIRCUIT BREAKER RESET
The circuit breaker automatically tries half-open state after 60 seconds.
To manually reset:

```python
from dashboard.api_data_layer import _circuit_breaker_lock, _circuit_breaker_state, _circuit_breaker_failures
with _circuit_breaker_lock:
    # Force closed state
    _circuit_breaker_state = "closed"
    _circuit_breaker_failures = 0
    print("Circuit breaker reset")
```

### 6. RESTORE DATA METRIC THRESHOLDS
Decide if demo mode is intentional:
- If demo: Add explicit demo mode flag to load_stock_scores.py
- If not: Restore thresholds in loaders/load_stock_scores.py lines 87-90

---

## TESTING RESULTS

### Local Database
✓ algo_audit_log: 9,807 rows  
✓ orchestrator_execution_log: 2 rows  
✓ circuit_breaker_status: 2 rows  

### API Endpoints (via AWS endpoint)
✗ activity: 500 after 4 retries  
✗ audit: 500 after 4 retries  
✗ exec_hist: 500 after 4 retries  
✗ sentiment: Circuit breaker open  
✗ sec_rot: Circuit breaker open  
✗ srank: Circuit breaker open  
✗ cb: Circuit breaker open (correct: data stale >1h)  
✗ sig_eval: Circuit breaker open  

### Working Endpoints (18/26)
✓ algo_metrics, cfg, eco, econ_cal, exp_factors, health, irank, mkt, notifs, perf,
perf_anl, port, pos, risk, run, scores, sig, trades

---

## KEY INSIGHT

The fact that local database works but AWS Lambda returns 500 suggests:
1. Code deployed to Lambda is catching an exception
2. Most likely: RDS connectivity, SQL error, or missing dependency
3. Response schema fix (commit 21120d031) addresses validation, not server errors

Check CloudWatch logs for actual error messages before proceeding.
