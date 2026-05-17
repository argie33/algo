# Production Readiness Roadmap

**Last Updated:** 2026-05-17  
**Status:** ✅ Core safety fixes complete | 🔴 26 issues identified | ⏳ Remaining: 37-48 hours

---

## Executive Summary

### What's Done ✅
- **Algo Safety:** Halt mechanism, fail-closed phases, circuit breaker for batch failures
- **Data Quality:** Dynamic score weighting, data completeness tracking, GDP regime detection
- **AWS:** OIDC role name fixed, deployment unblocked
- **Security:** Exposed credentials removed, API error handling for DB errors, CORS validation
- **7 Commits:** 6 critical fixes + 1 CORS validation

### Critical Path to Production
**Estimated:** 8-10 hours of work remaining before safe deployment

```
✅ Safety fixes (DONE)
✅ Data accuracy (DONE)
✅ AWS deployment (DONE)
🔴 Error disclosure (CRITICAL - 2 hrs)
🔴 Input validation (CRITICAL - 1.5 hrs)
🔴 Connection pooling (HIGH - 3 hrs)
🔴 Env var validation (HIGH - 1 hr)
→ Deploy to staging
→ 24-48 hr paper trading test
→ Production deploy
```

---

## Complete Issue List (26 Issues)

### CRITICAL (Blocks Production) - 4 Issues, ~6 hours

#### C-1: Error Message Disclosure (2 hours)
**Impact:** Security vulnerability, leaks internal details  
**Locations:** 29 places in lambda/api/lambda_function.py return raw `str(e)`  
**Lines:** 337, 452, 475, 497, 590, 646, 682, 742, 773, 795, 815, 834, 857, 875, 901, 931, 956, 974, 984, 994, 1230, 1256, 1289, 1306, 1355, 1402, 1519, 1635, 1756, 1815, 1843, 1957, 2021, 2092, 2120, 2217, 2237, 2257, 2306, 2336, 2380

**Current Code:**
```python
except Exception as e:
    logger.error(...)
    return error_response(500, 'internal_error', str(e))  # ❌ Exposes raw error
```

**Fix:**
```python
except psycopg2.errors.UndefinedTable as e:
    return error_response(503, 'data_not_loaded', 'Financial data not loaded')
except psycopg2.DatabaseError as e:
    logger.error(..., exc_info=True)
    return error_response(503, 'database_error', 'Database unavailable')
except Exception as e:
    logger.error(..., exc_info=True)
    return error_response(500, 'internal_error', 'Server error')  # ❌ No str(e)
```

**Action:** Grep for `str(e)` and replace with safe message

---

#### C-2: Missing Limit Validation (1.5 hours)
**Impact:** DoS vulnerability, client can request huge result sets  
**Locations:** 
- Line 2125: default limit 5000 (should be 100-500)
- Line 1153: default 500 (OK, but no pre-validation)
- Line 1157: default 500 (OK)
- Line 1262: default 600 (should max 100)

**Current Code:**
```python
limit = int(params.get('limit', [5000])[0])  # ❌ No cap before query
```

**Fix:**
```python
def _safe_limit(limit_str, min_val=1, max_val=500, default=100):
    try:
        limit = int(limit_str)
        return max(min_val, min(limit, max_val))
    except (ValueError, TypeError):
        return default

# Then use:
limit = _safe_limit(params.get('limit', [None])[0])
```

**Action:** Add `_safe_limit()` helper, apply to all endpoints

---

#### C-3: CORS Origin Blank (30 minutes) ✅ FIXED
**Status:** ✅ Already fixed in commit 80f8c6b77

---

#### C-4: Exposed AWS Errors (1 hour)
**Impact:** Internal AWS ARN details exposed when ECS task fails  
**Locations:** Line 742, 774, other ECS invoke sites

**Fix:** Catch boto3 ClientError and return generic message

---

### HIGH (Feature Breaking) - 5 Issues, ~8 hours

#### H-1: Unvalidated Sort Parameter (30 min)
**Impact:** SQL injection vector (mitigated but not defense-in-depth)  
**Location:** Line 2127, sort_by not validated at parameter extraction

**Fix:** Add validation at parameter extraction (line 2127):
```python
allowed_sorts = ['composite_score', 'value_score', 'quality_score', ...]
sort_by = params.get('sortBy', ['composite_score'])[0]
if sort_by not in allowed_sorts:
    return error_response(400, 'invalid_sort', f'Sort must be one of: {allowed_sorts}')
```

---

#### H-2: Connection Pooling Missing (3 hours)
**Impact:** Connection limit exhaustion under load  
**Location:** Line 37-38, only single cached connection

**Fix:** Implement psycopg2.pool.ThreadedConnectionPool
```python
from psycopg2 import pool

_db_pool = psycopg2_pool.ThreadedConnectionPool(
    minconn=2, maxconn=10, **db_config
)

def get_conn():
    return _db_pool.getconn()

def put_conn(conn):
    _db_pool.putconn(conn)
```

---

#### H-3: Console.logs in Production (1 hour)
**Impact:** Performance degradation, info disclosure  
**Locations:** 
- AuthContext.jsx: lines 218, 231, 264, 268, 275, 298, 302, 405, 441, 495 (10+ logs)
- errorLogger.js: 20+ logs
- apiService.jsx: logs every call

**Fix:** Wrap in `if (process.env.VITE_DEBUG === 'true')`

---

#### H-4: Missing Indexes (30 min)
**Impact:** Query performance degradation  
**Tables:** sector_rotation_signal, buy_sell_daily, data_patrol_log

**Add to init_database.py:**
```sql
CREATE INDEX idx_sector_rotation_date ON sector_rotation_signal(date DESC, sector);
CREATE INDEX idx_buy_sell_daily_date ON buy_sell_daily(date DESC);
CREATE INDEX idx_patrol_log_created_at ON data_patrol_log(created_at DESC);
```

---

#### H-5: Unvalidated Integer (notif_id) (30 min)
**Impact:** Crashes if non-numeric ID passed  
**Location:** Lines 347, 358

**Fix:**
```python
try:
    notif_id_int = int(notif_id)
except ValueError:
    return error_response(400, 'invalid_id', 'ID must be numeric')
```

---

### MEDIUM (Degrades Experience) - 6 Issues, ~10 hours

#### M-1: Bare Exception Handlers (2 hours)
**Impact:** Swallows unexpected errors  
**Locations:** 55+ places catch generic Exception

**Fix:** Be specific (psycopg2.DatabaseError, ValueError, etc.)

---

#### M-2: Missing Symbol Validation (1 hour)
**Impact:** DB errors on invalid symbols  
**Locations:** Lines 1026, 1292, 2075

**Fix:**
```python
if not re.match(r'^[A-Z0-9.\-]{1,20}$', symbol):
    return error_response(400, 'invalid_symbol', 'Symbol format invalid')
```

---

#### M-3: No Pagination on Large Sets (2 hours)
**Impact:** Timeout/memory issues with millions of rows  
**Locations:** Lines 1196, 1226, 1286

**Fix:** Add offset parameter, document pagination in API

---

#### M-4: Console.logs in Utils (1 hour)
**Impact:** Performance, log spam  
**Files:** errorLogger.js, apiService.jsx

**Fix:** Wrap in debug flag

---

#### M-5: JSON Parsing Error Handling (45 min)
**Impact:** Crashes on non-JSON response  
**Location:** responseNormalizer.js line 18-57

**Fix:** Validate content-type, wrap in try/catch

---

#### M-6: No Query Timeout (30 min)
**Impact:** Slow queries hang Lambda  
**Location:** Line 88, connection string

**Fix:** Set `statement_timeout=15000` in connection options

---

### LOW (Polish) - 7 Issues, ~15 hours

- L-1: Hardcoded container names (15 min)
- L-2: No API documentation (4 hrs)
- L-3: Rate limiting not enforced (1 hr)
- L-4: Inconsistent timezone handling (1 hr)
- L-5: Unused imports (1 hr)
- L-6: No frontend config fallback (30 min)
- L-7: No monitoring/metrics (3 hrs)

---

### CONFIG & DEPLOYMENT - 2 Issues, ~2 hours

#### CONFIG-1: Missing Env Var Validation (1 hour)
**Locations:** lambda_handler startup

**Required vars:**
- `FRONTEND_ORIGIN` ✅ Fixed with validation
- `DB_SECRET_ARN` or `DATABASE_SECRET_ARN`
- `ECS_CLUSTER_ARN`
- `PATROL_TASK_DEFINITION_ARN`
- `ENVIRONMENT` (prod/dev/staging)

**Fix:** Add startup check in lambda_handler before processing:
```python
required_envs = ['DB_SECRET_ARN', 'FRONTEND_ORIGIN', 'ECS_CLUSTER_ARN']
for env in required_envs:
    if not os.getenv(env):
        logger.critical(f"Required env var {env} not set")
        return error_response(503, 'misconfiguration', 'API not configured')
```

---

#### CONFIG-2: No Health Check Validation (1 hour)
**Ensure:** `/api/health` endpoint actually tests DB connection

---

### TESTING - 2 Issues, ~5 hours

- T-1: No API integration tests for error cases (3 hrs)
- T-2: Frontend tests missing for auth failures (2 hrs)

---

## Recommended Fix Order

### Phase 1: Unblock Production (6-8 hours)
**Do These First:**

1. **C-1: Error Disclosure** (2 hrs)
   - Find/replace `str(e)` → safe messages
   - Test with invalid requests

2. **C-2: Input Validation** (1.5 hrs)
   - Add `_safe_limit()`, `_safe_offset()`, symbol validation
   - Apply to all endpoints

3. **H-1: Env Var Validation** (1 hr)
   - Add startup checks in lambda_handler
   - Test with missing vars

4. **H-4: Connection Pooling** (3 hrs)
   - Implement ThreadedConnectionPool
   - Test connection exhaustion scenario

5. **H-4b: Missing Indexes** (30 min)
   - Add to init_database.py
   - Run on local DB

**Result:** API is secure, validated, and can scale

---

### Phase 2: Polish & Testing (10-15 hours)
- Remove console.logs from production code
- Add integration tests for error paths
- Add rate limiting enforcement
- Complete remaining HIGH/MEDIUM items

---

### Phase 3: Polish (5+ hours)
- API documentation
- Monitoring/metrics
- Timezone consistency
- Code cleanup

---

## Testing Strategy

**After fixing CRITICAL items:**
```bash
# 1. Local validation
python3 lambda/api/lambda_function.py --test-errors
python3 lambda/api/lambda_function.py --test-limits
python3 lambda/api/lambda_function.py --test-auth

# 2. Integration tests
pytest tests/integration/test_api_errors.py -v

# 3. Staging deployment
gh workflow run deploy-webapp.yml --ref main

# 4. Paper trading validation
python3 algo_orchestrator.py --mode paper --days 2

# 5. Load test
ab -n 10000 -c 100 http://api.stage/api/health
```

---

## Deployment Checklist

**Before Production:**
- [ ] All CRITICAL issues fixed
- [ ] CORS origin env var set
- [ ] Required env vars validated
- [ ] Error messages sanitized (no str(e))
- [ ] Input validation on all user inputs
- [ ] Connection pooling tested
- [ ] 24-48 hr paper trading test passed
- [ ] Rate limiting enforced
- [ ] Indexes added

**During Deployment:**
- [ ] Set FRONTEND_ORIGIN to actual domain
- [ ] Set ENVIRONMENT=production
- [ ] Enable CloudWatch monitoring
- [ ] Set up alert for error rate > 1%

---

## Risk Assessment

**If deployed without fixes:**
- 🔴 **Critical:** Error disclosure (security), CORS broken (users can't access), input validation gaps (DoS)
- 🟠 **High:** Unvalidated sorts, connection exhaustion, console.logs
- 🟡 **Medium:** Missing indexes (slow), poor error handling

**Recommended:** Fix CRITICAL items (6-8 hrs) before staging deployment

---

## Summary

- ✅ **7 commits, major fixes done:** Algo safety, data quality, AWS deployment
- 🔴 **26 issues remaining:** 4 critical, 5 high, 6 medium, 7 low, 2 config, 2 testing
- ⏳ **37-48 hours of work:** Focus on CRITICAL first (6-8 hrs to production-ready)
- 📋 **Clear roadmap:** Each issue has specific location, root cause, and fix
