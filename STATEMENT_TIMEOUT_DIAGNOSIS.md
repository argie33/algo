# Statement Timeout Diagnosis: 900s RDS Parameter vs 30s API Lambda

## Executive Summary

**Issue**: RDS `statement_timeout` is set to 900,000ms (15 minutes) at the parameter group level, but API Lambda has 30s timeout. This creates a **30x mismatch** allowing runaway queries to consume resources long after API clients have disconnected.

**Severity**: HIGH — Causes resource exhaustion, cascading failures, and unpredictable behavior.

---

## Root Cause Analysis

### 1. Current Configuration (Mismatched Timeouts)

| Component | Setting | Source | Value |
|-----------|---------|--------|-------|
| **API Lambda** | timeout | terraform/variables.tf:402 | **30 seconds** |
| **RDS statement_timeout** | Database-level | terraform/modules/database/main.tf:172 | **900,000ms (15 min)** |
| **Mismatch Ratio** | — | — | **30x** |

**Terraform configuration:**
```hcl
# terraform/modules/database/main.tf:170-174
parameter {
  name         = "statement_timeout"
  value        = "900000"  # 15 minutes in milliseconds
  apply_method = "immediate"
}
```

**Lambda configuration:**
```hcl
# terraform/variables.tf:399-403
variable "api_lambda_timeout" {
  description = "Timeout for API Lambda"
  type        = number
  default     = 30  # 30 seconds
}
```

### 2. Design Intent (Broken Assumption)

**Comment in main.tf (lines 163-168):**
```
# Increased from 30s → 900s (15 minutes) to support batch loaders processing 5000+ symbols.
# Batch loaders (signal_quality_scores, swing_trader_scores) with 5000+ symbols × DB joins
# can exceed 30s. API requests that need 30s strict timeout can override via SET statement in handler.
# apply_method = "immediate" is safe: this is a session-level parameter (no reboot required).
```

**The Problem**: The comment assumes "API requests can override via SET statement" but:
- ✗ API Lambda (`lambda/api/lambda_function.py:1362`) does NOT set per-request timeout
- ✗ Comment at line 1362 claims "statement_timeout is now set at RDS parameter group level (30s)" but it's actually 900s
- ✓ Some code paths DO override (see Data Flows below)

### 3. Zombie Query Scenario

**Timeline of a 45-second query through API:**

```
T=0s:      Client makes API request → Lambda cold-start begins
T=5s:      Lambda initialized, DatabaseContext opens connection
T=6s:      Query execution begins
T=30s:     API Lambda TIMEOUT → Lambda process killed, connection abandoned
T=30.1s:   PostgreSQL still executing query (statement_timeout = 900s)
T=45s:     Query completes after 39 seconds of being "orphaned"
```

**Impact**:
- Query held database connection for 45s despite client timeout at 30s
- Other queries queued behind it starve
- RDS reserved concurrency (25-30 connections) exhausted faster than expected
- Logs show slow queries that are actually blocking on the 30s-to-45s boundary

---

## Current Data Flow (Per-Request Timeouts)

### A. API Lambda (30s timeout)
**File**: `lambda/api/lambda_function.py:1358-1362`

```python
with DatabaseContext(db_mode) as cur:
    # statement_timeout is now set at RDS parameter group level (30s) — no per-request SET needed.
    params = parse_query_params(event)
    ...
```

**Issue**: Comment is WRONG — database timeout is 900s, not 30s.
**Result**: No override → queries can run up to 15 minutes before timeout.

### B. Orchestrator Process (Varies 10-60s)

1. **Health Monitor** (`algo/orchestration/database_health_monitor.py:76`):
   ```python
   cur.execute("SET statement_timeout = 10000")  # 10s timeout
   ```

2. **Phase 1 Freshness Check** (`algo/orchestrator/phase1_data_freshness.py:273`):
   ```python
   cur.execute("SET statement_timeout = 15000")  # 15s timeout for multi-table checks
   ```

3. **Risk Market Exposure** (`algo/risk/market_exposure.py:313`):
   ```python
   cur.execute("SET statement_timeout = 45000")  # 45s timeout
   ```

### C. Batch Loaders (0 = unlimited, problematic)

Files setting `statement_timeout = 0` (NO LIMIT):
- `loaders/load_buy_sell_daily.py:752`
- `utils/loader_infrastructure.py:166`
- `utils/optimal_loader.py:682`, `742`

**Issue**: These override to 0 (unlimited), causing queries to run indefinitely if hung.

### D. DB Initialization (2s probe)
**File**: `lambda/db-init/lambda_function.py:187`

```python
cur.execute("SET statement_timeout TO '2000'")  # 2 seconds
```

---

## Dependency Chain

```
API Request (30s timeout)
    ↓
Lambda function (cold-start ~5s + request processing)
    ↓
DatabaseContext (establishes RDS connection)
    ↓
Statement execution with RDS parameter timeout (900s) ← MISMATCH
    ↓
If query runs > 30s: API times out, connection abandoned (zombie)
    ↓
Query continues to 900s limit (15 min), consuming RDS slot
    ↓
Cascading: Other queries queue up, orchestrator phases blocked
```

### Components Affected

| Component | Timeout | Logic | Risk |
|-----------|---------|-------|------|
| API Lambda | 30s | No override → 900s timeout | **CRITICAL** |
| Batch loaders | 0 (unlimited) | Explicit disable | HIGH |
| Orchestrator phases | 10-60s | Per-phase override | MEDIUM |
| Health monitor | 10s | Per-check override | LOW |

---

## Fix Strategy

### Phase 1: Align Statement Timeout with API Lambda (CRITICAL)

**Change**: Set RDS `statement_timeout` to 35s (safe margin above 30s API timeout)

**Why 35s?**
- Matches API timeout within 5s buffer for RDS Proxy latency
- Prevents zombie queries from API
- Batch loaders must explicitly opt-out via `SET statement_timeout = 0`

**Files to modify**:
```hcl
# terraform/modules/database/main.tf:170-174
parameter {
  name         = "statement_timeout"
  value        = "35000"  # 35s = 30s API + 5s buffer
  apply_method = "immediate"
}
```

**Test verification**:
```bash
# Connect to RDS and verify:
SHOW statement_timeout;  # Should show 35000ms (35s)
```

### Phase 2: Explicit Batch Loader Timeout Override (REQUIRED)

**Problem**: Batch loaders setting `statement_timeout = 0` is dangerous (infinite queries).

**Change**: Set to explicit time limit (e.g., 600s = 10 minutes):

**Files to modify**:
1. `loaders/load_buy_sell_daily.py:752` → `"300000"` (5 min)
2. `utils/loader_infrastructure.py:166` → `"600000"` (10 min)
3. `utils/optimal_loader.py:682`, `742` → `"600000"` (10 min)

**Logic**:
```python
# Current (DANGEROUS):
cur.execute("SET statement_timeout = 0")  # No limit!

# Fixed (SAFE):
cur.execute("SET statement_timeout = '600000'")  # 10 min explicit limit
```

### Phase 3: API Lambda Per-Request Override (OPTIONAL HARDENING)

**Enhancement**: Explicit per-request timeout for defense-in-depth:

**File**: `lambda/api/lambda_function.py:1361-1364`

```python
with DatabaseContext(db_mode) as cur:
    # Enforce API timeout: 28s (2s buffer below Lambda 30s timeout)
    cur.execute("SET statement_timeout = '28000'")
    params = parse_query_params(event)
    ...
```

**Why 28s instead of 30s?**
- 2s buffer for connection close/cleanup
- Ensures statement kills before Lambda times out
- Cleaner error handling (statement timeout vs Lambda timeout)

---

## Test Verification Plan

### Test 1: Parameter Group Timeout (Post-Deploy)

```bash
# 1. Connect to RDS database
psql -h <rds-host> -U stocks -d stocks

# 2. Verify parameter (should be 35000 after fix)
SHOW statement_timeout;

# 3. Test timeout enforcement
SET statement_timeout = '3000';  -- 3 seconds
SELECT pg_sleep(5);  -- Should timeout with: ERROR: canceling statement due to statement timeout
```

### Test 2: API Request Timeout (Integration)

**Setup**: Deploy fix, point staging Lambda to modified RDS parameter.

**Test Case 1: Fast query (< 30s) should succeed**
```bash
curl -X GET https://api.staging/api/health
# Expected: 200 status, no timeout
```

**Test Case 2: Slow query (31-35s) should fail gracefully**
```bash
# Manually trigger a slow query via API (e.g., /api/scores with large watchlist)
# Expected: 
#   - At 35s: PostgreSQL kills query with statement_timeout error
#   - At 30s: Lambda times out (if statement hasn't killed yet)
#   - Client sees 503 or 504, not hanging
```

**Test Case 3: Batch loader with explicit timeout**
```bash
# Run a batch loader (e.g., load_buy_sell_daily.py)
# Verify in logs: 
#   - "SET statement_timeout = '300000'" logged
#   - Query completes or fails cleanly, doesn't hang
```

### Test 3: CloudWatch Logs Analysis

**Metrics to check (1 hour post-deploy)**:

1. **Statement timeout errors** (should increase initially as queries hit new limit):
   ```sql
   fields @timestamp, @message 
   | filter @message like /statement timeout/ 
   | stats count() by bin(5m)
   ```

2. **Query duration histogram** (should shift left, most queries < 35s):
   ```sql
   fields @duration 
   | stats avg(@duration), max(@duration), pct(@duration, 95) by @table
   ```

3. **RDS connection count** (should be lower as zombie queries eliminated):
   ```
   AWS CloudWatch → RDS Instance → DatabaseConnections metric
   ```

### Test 4: Dependency Verification

Ensure no code path breaks with the new 35s limit:

```bash
# Run existing tests:
pytest tests/ -k "timeout or database or orchestrator" -v

# Verify batch loaders start cleanly:
python -m loaders.load_buy_sell_daily --dry-run
python -m loaders.load_signal_quality_scores --dry-run
```

---

## Rollback Plan

If regression detected:

```bash
# 1. Revert Terraform change
git revert <commit-hash>

# 2. Redeploy
cd terraform
terraform apply -lock=false

# 3. Verify rollback
psql -h <rds-host> -U stocks -d stocks -c "SHOW statement_timeout;"
# Should show 900000ms (15 min)
```

---

## Dependency Chain Summary

### What breaks if NOT fixed:
1. ✗ Slow API queries hold connections > 30s (zombies)
2. ✗ Batch loaders with `timeout = 0` run indefinitely on hangs
3. ✗ Other loaders and orchestrator phases can't predict query lifetime
4. ✗ RDS connection pool exhaustion causes cascading failures

### What must be coordinated:
1. **Terraform deploy** (new parameter: 35s)
2. **Batch loader code changes** (explicit timeout instead of 0)
3. **API Lambda optional override** (hardening, not required)
4. **Test suite** (update timeouts if tests have hardcoded 900s assumptions)

---

## Code Locations Summary

| File | Line | Current | Issue | Fix |
|------|------|---------|-------|-----|
| `terraform/modules/database/main.tf` | 172 | 900000ms | 30x timeout mismatch | → 35000ms |
| `loaders/load_buy_sell_daily.py` | 752 | 0 (unlimited) | Dangerous | → 300000ms |
| `utils/loader_infrastructure.py` | 166 | 0 (unlimited) | Dangerous | → 600000ms |
| `utils/optimal_loader.py` | 682, 742 | 0 (unlimited) | Dangerous | → 600000ms |
| `lambda/api/lambda_function.py` | 1362 | (none) | Wrong comment, no override | → hardening override (optional) |
| `algo/orchestration/database_health_monitor.py` | 76 | 10000ms | ✓ OK | No change |
| `algo/orchestrator/phase1_data_freshness.py` | 273 | 15000ms | ✓ OK | No change |
| `algo/risk/market_exposure.py` | 313 | 45000ms | ✓ OK | No change |

---

## Success Criteria

After fix deployment:

- [ ] RDS parameter shows 35000ms (or configured value)
- [ ] No zombie queries in logs (statement_timeout properly kills at limit)
- [ ] API requests fail cleanly (500/503 not hanging)
- [ ] Batch loaders complete or fail with explicit timeout
- [ ] RDS connection count stable (not climbing with orphaned connections)
- [ ] Orchestrator phases execute within expected windows
