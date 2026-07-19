# Session 271: Targeted Audit - Issues Found

**Date:** 2026-07-19  
**Goal:** Find bypasses, cheats, and unsafe patterns in algo system  
**Status:** Issues identified - fixes required

## Critical Issues Found

### 1. **API Default Masking Data Unavailability** ⚠️ HIGH
**File:** `lambda/api/routes/algo_handlers/market.py:1002`  
**Issue:** Silent default when `fed_rate_data_unavailable` field missing from database

```python
# Line 1002 - UNSAFE DEFAULT
"fed_rate_data_unavailable": market_health.get("fed_rate_data_unavailable", False),
```

**Problem:**
- If market_health row doesn't have `fed_rate_data_unavailable` column (e.g., stale schema, NULL corruption), defaults to False
- Lies to dashboard: "data is available" when it might actually be missing
- Other fields (put_call_ratio, yield_curve) use explicit None checks instead of defaults

**Impact:** Dashboard can show stale/missing data as "available", traders make decisions on false information

**Fix Required:**
- Explicit None check: `market_health.get("fed_rate_data_unavailable") is True` (not False default)
- Or: Raise error if field missing rather than assume

---

### 2. **Inconsistent Data Unavailability Pattern in API** ⚠️ MEDIUM  
**File:** `lambda/api/routes/algo_handlers/market.py:993-1002`  
**Issue:** Three different patterns used for same purpose

```python
# Line 993 - GOOD: Explicit logic
"put_call_ratio_data_unavailable": pcr_val is None,

# Line 997 - GOOD: Explicit logic  
"yield_curve_data_unavailable": ycs_val is None,

# Line 1002 - BAD: Silent default
"fed_rate_data_unavailable": market_health.get("fed_rate_data_unavailable", False),
```

**Problem:** Inconsistent error handling makes it hard to reason about data reliability. put_call_ratio/yield_curve use null-check pattern, but fed_rate uses default pattern.

**Fix Required:** Standardize all three to same pattern

---

### 3. **Phase 3 Always Runs Despite Halt** ℹ️ DESIGN
**File:** `algo/orchestrator/phase_registry.py:104`  
**Status:** By design (not a bug, but worth confirming intent)

```python
PhaseDefinition(
    phase_num=3,
    phase_name="position_monitor",
    ...
    always_run=True,  # Position monitoring is essential risk management
)
```

**Analysis:** 
- Phase 3 has `always_run=True`, so it executes even when Phase 1/2 halt
- Comment says "Position monitoring is essential risk management" - this is legitimate
- Similar pattern for Phase 6 (exit execution) and Phase 9 (reconciliation)
- This explains why user saw "stages halted yet others completed"

**Status:** CORRECT - These phases SHOULD run during halt to manage risk

---

### 4. **Explicit Phase Dependency Documentation Missing** ⚠️ MEDIUM
**File:** `algo/orchestration/orchestrator.py` (phase registration)  
**Issue:** Phase dependencies are implicit in code, not explicit in comments

**Current Behavior:**
- Phase 3 always runs (position monitoring)
- Phase 6 always runs (exit execution)  
- Phase 9 always runs (reconciliation)
- Other phases skip if halted

**Problem:** When user sees phases halted but later phases complete, it's not obvious why. No clear documentation of "these phases always run" intent.

**Fix Required:** Add explicit docstring to orchestrator explaining:
```
## Phase Execution Rules During Halt

If any phase 1-5 halts (Phase 1 staleness, Phase 2 CB, etc):
- Phases 1-5: SKIP (fail-closed)
- Phases 6, 9: CONTINUE (risk management: close positions, final snapshot)
- Phase 7-8: Depend on Phase 5 data, may skip if deps unavailable

This is intentional - exits and reconciliation must run to close positions during emergencies.
```

---

## Non-Critical Issues (Design Validation Needed)

### 5. **Phase Executor Skip Data Defaults**
**File:** `algo/orchestrator/phase_executor.py:145-172`  
**Status:** CORRECT (defensive programming)

When a phase is skipped due to halt, it returns default data:
```python
defaults = {
    1: {"status": "skipped"},
    2: {"status": "skipped"},
    3: {"recommendations": []},
    ...
}
```

**Analysis:** This is intentional - allows downstream phases to check `if phase_result.ok` without null-checking. Proper defensive programming.

---

### 6. **Dashboard Local Server Fallback** ℹ️ CONFIG
**File:** `dashboard/local_api_server.py`  
**Status:** Intentional, properly logged

Dashboard auto-connects to localhost if AWS config unavailable - this is expected for dev mode.

---

## Summary of Findings

| Issue | Severity | Type | Status |
|-------|----------|------|--------|
| fed_rate_data_unavailable silent default | HIGH | Bug | **NEEDS FIX** |
| Inconsistent data unavailability patterns | MEDIUM | Code Quality | **NEEDS FIX** |
| Phase 3 always runs (halt bypass) | MEDIUM | Documentation | **By Design** - needs clarity |
| Missing phase execution docs | MEDIUM | Documentation | **NEEDS FIX** |
| Phase executor skip defaults | LOW | Code Quality | **CORRECT** |
| Dashboard localhost fallback | LOW | Config | **CORRECT** |

---

## What Was NOT Found (Good News)

✅ No COALESCE fabricating fake data (removed in Session 265)  
✅ No env var bypasses (SKIP_PHASE3_MONITOR removed in Session 269)  
✅ No hardcoded test data in production loaders  
✅ No silent fallbacks to zero/empty in critical paths  
✅ No unhandled exceptions in phase execution  
✅ No mock data in production code  

---

## Recommended Actions

### Immediate (High Priority)
1. **Fix fed_rate_data_unavailable default** - Replace `.get("fed_rate_data_unavailable", False)` with explicit None check
2. **Standardize all data_unavailable patterns** - Make put_call_ratio, yield_curve, fed_rate use same logic
3. **Add phase execution documentation** - Explain why Phase 3/6/9 always run

### Follow-up (Medium Priority)
4. **Add test for Phase 3 halt behavior** - Verify position monitoring always runs regardless of halt
5. **Code review Phase 6/9** - Confirm exit execution and reconciliation also properly always-run
6. **Dashboard data quality panel** - Add warnings when data_unavailable fields are present

---

## Questions for User

1. **Is Phase 3 always-running intentional?** Should position monitoring be blocked during halt? (Probably not, but confirming)
2. **Should fed_rate default to False or raise error?** What's the intended behavior if field missing?
3. **Any other "always_run" phases we missed?** Should reconciliation (Phase 9) always run?

