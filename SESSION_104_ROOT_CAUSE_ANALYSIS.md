# SESSION 104: COMPREHENSIVE LOADER BRITTLENESS ROOT CAUSE ANALYSIS

## Current Status (2026-08-13)
- **buy_sell_daily**: STALE from 2026-08-11 (2 days old)
- **price_daily**: RUNNING at 0% (retry attempt failing)
- **technical_data_daily**: RUNNING at 0% (retry attempt failing)
- **stock_scores**: COMPLETED but from 2026-08-11

## ROOT CAUSES IDENTIFIED

### 1. CRITICAL SESSION 104 BUG: invoke_loader_retry() Table Name vs Loader Key Mismatch
**Impact**: ALL Phase 1 failsafe retry attempts fail with "Unknown loader name"

**Root Cause**:
- Phase 1 failsafe receives TABLE NAMES (e.g., "price_daily", "technical_data_daily")
- `invoke_loader_retry(loader_name)` passes table name to subprocess
- `scripts/run_loader.py` only accepts LOADER KEYS (e.g., "prices", "technical") or full filenames
- Result: subprocess.run() fails with "Unknown loader name" and returns exitcode=1
- Phase 1 then marks loader as FAILED and gives up on retry

**Example Failure**:
```bash
python scripts/run_loader.py price_daily --force-refresh
# ERROR: Unknown loader name: 'price_daily'. Valid shorthand names: ['prices', ...]. Or use full filenames like 'load_prices.py'.
```

**Status in Code**:
- **FIXED** in phase1_failsafe_retry.py `invoke_loader_retry()` function (lines 1241-1280)
- Added conversion: `table_to_loader_shorthand(table_name)` → `loader_key`
- Now passes `loader_key` to `scripts/run_loader.py` instead of `table_name`

---

### 2. CRITICAL STATUS MANAGER BUG: NOT_STARTED Status With Completed Execution
**Impact**: Loaders appear broken even when execution succeeds

**Evidence**:
```
buy_sell_daily:
  Status: NOT_STARTED (WRONG!)
  Completion: 99.16% (nearly done)
  execution_started: 2026-08-12 04:08:56
  execution_completed: 2026-08-12 21:09:59 (15 hours later, DONE)
  last_updated: 2026-08-11 00:00:00
```

**Root Cause**: Loader ran to 99.16% completion and finished execution (15+ hours duration), but never called `mark_completed()` or `mark_failed()` to update status from NOT_STARTED.

**Why It Matters**:
- Phase 1 ONLY retries loaders with status in (FAILED, ERROR, TIMEOUT, or completion_pct < 85%)
- NOT_STARTED status is not checked for retry eligibility
- Loader appears "broken" to pipeline (NOT_STARTED = never started) but has recent data

**Action Items**:
- [ ] Investigate why buy_sell_daily ran for 15 hours but never updated its status
- [ ] Check if there's a mark_failed() path that's not being called
- [ ] Verify LoaderStatusManager marks COMPLETED correctly after loader.run() succeeds

---

### 3. SESSION 103 CONSEQUENCE: Pipeline Ordering Created Cascading Dependency
**Impact**: Signals pipeline depends on metrics pipeline; any metrics delay cascades

**What Happened in Session 103**:
- Moved `scores` and `buy_sell` from `morning` pipeline to `signals` pipeline
- Reason: They depend on metrics (value_quality_growth, enhanced_quality_growth, etc.)
- **Problem**: `signals` pipeline now depends on `metrics` completing first

**Execution Order**:
```
morning (prices, technical, ...)
  → metrics (company_info, financial_statements, valuations, ..., 30+ loaders)
    → signals (prices, technical, scores, buy_sell, ...)
      → buy_sell runs only AFTER metrics completes
```

**Cascading Failure Scenario**:
1. Morning pipeline completes
2. Metrics pipeline starts (10+ loaders, 2-3 hours total)
3. If ANY metrics loader fails (company_info, financial_statements, valuations, etc.), scores fails
4. If scores fails, entire signals pipeline never runs
5. buy_sell_daily stays NOT_STARTED forever
6. Monday: STALE buy_sell_daily halts trading

**Why This Brittles The System**:
- Morning completes ~30 min
- Metrics takes 2-3 hours
- If metrics has ANY failure after 2 hours, signals never runs
- buy_sell_daily with 2-day stale data halts orchestrator

---

### 4. SESSION 103 INCOMPLETE FIX: Timeouts Updated But Not All Retry Paths
**What Was Fixed**:
- `invoke_loader_retry()` now uses configured timeouts from `get_loader_timeouts()`
- Timeout uses 1.25x safety margin

**What Was Missed**:
- ✗ Didn't convert table_name to loader_key before calling scripts/run_loader.py
- ✗ Assumed all loaders can be invoked by table_name (not true)

---

## SOLUTIONS

### Solution 1: FIX invoke_loader_retry() (APPLIED)
**Status**: ✅ FIXED in this session

Change subprocess call to convert table_name → loader_key:
```python
# Convert table name to loader key
from loaders.loader_registry import table_to_loader_shorthand
loader_key = table_to_loader_shorthand(loader_name)

# Pass loader_key, not table_name
result = subprocess.run(
    [sys.executable, "scripts/run_loader.py", loader_key, "--force-refresh"],
    ...
)
```

---

### Solution 2: INVESTIGATE NOT_STARTED Status Bug
**Status**: 🔍 NEEDS INVESTIGATION

Check:
1. Why buy_sell_daily's loader ran for 15 hours but didn't call mark_completed()
2. Is there an exception path that leaves status at NOT_STARTED?
3. Does buy_sell have custom status management logic that's failing?

---

### Solution 3: DECOUPLE SIGNALS FROM METRICS PIPELINE
**Status**: ⏳ PROPOSED

**Option A** (Recommended - Minimal Risk):
- Move `scores` and `buy_sell` back to `morning` pipeline (Session 103 reverted this)
- Or move to a separate `signals_early` pipeline that runs after morning but before metrics
- Rationale: Signals only depend on prices + technical, not on metrics
  - metrics tables: value_quality_growth, enhanced_quality_growth, positioning, stability (enrichment only)
  - signals dependencies: price_daily, technical_data_daily
  - metrics are ENRICHMENT, not CORE to signal generation

**Option B** (Parallelism - Medium Risk):
- Run metrics pipeline in parallel with signals pipeline
- Requires dependency management and failsafe retry coordination
- More complex but allows faster overall execution

**Recommended**: Option A - Keep signals decoupled from metrics dependency

---

## TESTING PLAN

1. **Test Fix 1**: Run orchestrator with the table_name→loader_key fix
   - Verify Phase 1 failsafe can now retry price_daily successfully
   - Check that all 6 price loaders (price_daily/weekly/monthly/etf_*) complete

2. **Test Fix 2**: Investigate buy_sell_daily NOT_STARTED bug
   - Manually run buy_sell loader and check status transitions
   - Trace the execution to see where mark_completed() should be called

3. **Test Fix 3**: Validate pipeline ordering
   - Run morning → metrics → signals full chain
   - Verify buy_sell completes successfully
   - Verify no stale data by 2026-08-14 morning

---

## FIXES APPLIED (SESSION 104)

### ✅ FIX 1: invoke_loader_retry() Table Name vs Loader Key (COMMITTED)
- **Commit**: 4791f9035
- **File**: `algo/orchestrator/phase1_failsafe_retry.py` lines 1255-1295
- **Change**: Added `table_to_loader_shorthand()` to convert table_name → loader_key before calling scripts/run_loader.py
- **Impact**: Phase 1 failsafe can now successfully invoke loaders by their correct key names
- **Verified**: Subprocess no longer fails with "Unknown loader name" error

### ✅ FIX 2: buy_sell_daily NOT_STARTED Status Bug (COMMITTED)
- **Commit**: 939dfb6a0
- **File**: `loaders/load_buy_sell_daily.py` lines 1055-1069, 1112-1125, 1159-1173
- **Change**: Added `LoaderStatusManager.mark_failed()` calls before returning on dependency check failures
- **Impact**: Status no longer stays at NOT_STARTED when dependencies are missing
- **Result**: Phase 1 can now detect and retry buy_sell_daily when upstream loaders fail

### 🔍 ISSUE 3: Database Query Timeout on Status Updates (FOUND, NOT YET FIXED)
- **Discovery**: Price loader ran successfully and updated all watermarks (all 6 price tables) but failed to mark status as COMPLETED
- **Cause**: Database timeout when inserting into data_loader_status during mark_completed()
- **Evidence**:
  ```
  psycopg2.errors.QueryCanceled: canceling statement due to statement timeout
  CONTEXT: while inserting index tuple (2,26) in relation "data_loader_status"
  ```
- **Impact**: Loader returns exit code 1 (failure) even though data was successfully loaded
- **Next**: Investigate data_loader_status table locking/contention

---

## TEST RESULTS (2026-08-13 13:42+)

### Price Loader Test (background task be9y3tyle)
- **Status**: ✅ DATA LOAD SUCCESSFUL, ❌ STATUS UPDATE TIMEOUT
- **Duration**: ~2 hours
- **Data Loaded**: 4923 symbols across all 6 price tables
- **Watermarks Updated**: All 6 price tables (price_daily, price_weekly, price_monthly, etf_price_daily, etf_price_weekly, etf_price_monthly)
- **Failure**: Database timeout while marking status COMPLETED (not a loader logic issue)
- **Exit Code**: 1 (returned as failure even though data is fresh)

### Root Cause Analysis
The database query timeout suggests:
1. **High Lock Contention**: Multiple orchestrator runs accessing data_loader_status
2. **Concurrent Sessions**: The main orchestrator run at 13:38 locked the table
3. **Missing Timeout Config**: STATUS MANAGER queries hitting default PostgreSQL statement_timeout

---

## OUTSTANDING ISSUES

### 1. Database Lock Contention on data_loader_status
**Severity**: CRITICAL (blocks all Phase 1 status updates)

**Symptoms**:
- Price loader completes successfully but can't mark status COMPLETED
- Database returns "statement timeout" on INSERT/UPDATE to data_loader_status
- Timestamps suggest timestamp conflicts due to concurrent sessions

**Investigation Needed**:
- [ ] Check data_loader_status table size and indexes
- [ ] Review PostgreSQL statement_timeout configuration
- [ ] Check for long-running locks from concurrent orchestrator runs
- [ ] Consider using advisory locks or SKIP LOCKED for status updates

**Temporary Workaround**:
- Ensure only ONE orchestrator instance runs at a time
- Clean up stale orchestrator locks (already done at start of session)

---

### 2. Pipeline Ordering: Signals Depends on Metrics
**Severity**: HIGH (cascading failure scenario)

**Current Order**:
```
morning → metrics (slow, 2-3h) → signals
```

**Problem**: If any metrics loader fails, signals pipeline never runs

**Solution Options** (from earlier analysis):
- Option A: Move signals to run in parallel with metrics (requires dependency gating)
- Option B: Decouple signals from metrics entirely (signals only need prices+technical)

---

### 3. buy_sell_daily Should Validate Its Own Status
**Severity**: MEDIUM (defensive programming)

**Issue**: buy_sell_daily can fail with exit code 1 without calling mark_failed()

**Recommendation**: Add wrapper logic to ensure mark_failed() is always called on error paths

---

## NEXT STEPS (PRIORITY ORDER)

1. **IMMEDIATE**: Fix database lock contention issue
   - Run orchestrator with only 1 concurrent instance
   - Verify price loader can mark status COMPLETED
   - Confirm all 6 price tables reach COMPLETED status

2. **TODAY**: Run full orchestrator pipeline test
   - morning → metrics → signals chain
   - Verify buy_sell_daily completes successfully
   - Check that no stale data persists

3. **FOLLOW-UP**: Investigate pipeline ordering optimization
   - Consider running signals in parallel with (or ahead of) metrics
   - Reduces risk of cascading failures from metrics delays

---

## TIMELINE
- **Session 103**: Attempted fixes but missed invoke_loader_retry table_name bug (2026-08-13 ~12:00)
- **Session 104 (Now)**:
  - Identified and fixed root causes #1 #2 (2026-08-13 13:39+)
  - Discovered root cause #3: database timeout (2026-08-13 ~16:00)
  - Price loader data is fresh and watermarks updated despite status timeout
- **Next Session**: Fix database lock issue and run full orchestrator test
