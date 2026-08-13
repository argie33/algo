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

## TIMELINE
- **Session 103**: Attempted fixes but missed the table_name/loader_key conversion bug
- **Session 104 (Now)**: Identified and fixed root cause #1, identified root causes #2 and #3
- **Next**: Apply remaining fixes and test
