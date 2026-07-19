# SESSION 283: CRITICAL FINDINGS - BYPASS AUDIT

**Date:** 2026-07-19  
**Status:** Audit Complete - 6 Critical Issues Found  
**Severity:** HIGH - System still contains silent fallbacks despite Session 282 claims of elimination

---

## Issue #1: CRITICAL - Silent Halt Flag Fallback (STILL PRESENT)

**File:** `algo/orchestration/halt_flag_manager.py:167-169`  
**Severity:** CRITICAL  
**Impact:** Trading proceeds when halt flag cannot be checked (DynamoDB unavailable)

### The Problem
```python
except Exception as e:
    if "UnrecognizedClientException" in str(e) or "InvalidCredentials" in str(e):
        logger.info(f"[HALT_FLAG] DynamoDB unavailable (local dev mode?). Allowing execution to continue. {e}")
        return False  # <-- SILENT FALLBACK: NO HALT CHECK
```

### Why This Is Dangerous
- DynamoDB unavailability is **production-silent** - could happen in AWS too (temp network issue, credential rotation)
- Log says "allowing execution to continue" - this contradicts governance mandate "fail-fast on missing safety checks"
- Comment claims "local dev mode" but code allows ANY DynamoDB error to bypass halt check
- Session 282 memory claims this was fixed in commit `e2718fd97` - **CLAIM IS FALSE**, code still present

### Correct Behavior (Per GOVERNANCE.md)
Halt flag check is CRITICAL infrastructure. Must:
- ❌ NOT silently continue on DynamoDB failure
- ✅ FAIL-FAST with explicit error: "HALT_CHECK_UNAVAILABLE → treating as halt condition"
- ✅ Line 171-192 already has the correct fail-closed logic - need to NOT CATCH the UnrecognizedClientException

---

## Issue #2: DESIGN FLAW - Phase 6 Always-Run Bypass

**File:** `algo/orchestrator/phase_registry.py:142-147`  
**File:** `algo/orchestrator/phase1_reconciliation.py:1002`  
**Severity:** HIGH  
**Impact:** Phase 6 (exit execution) can run and complete while Phase 5 (exposure policy) is halted

### The Problem
```python
# Phase 6: EXIT EXECUTION
PhaseRegistryEntry(
    phase_num=6,
    phase_name="EXIT EXECUTION",
    dependencies=[3],  # Only depends on Phase 3, not Phase 5
    skip_if_halted=False,
    always_run=True,   # <-- Runs even when Phase 5 halted
),
```

Session 282 audit VERIFIED this is "SAFE DESIGN" but **never tested the implication**:
- Phase 5 halts → exposure_actions NOT computed
- Phase 6 runs (always_run=True) → executes exits based on incomplete position data
- **Result:** Exits proceed without exposure policy constraints during circuit breaker halt

### Current Workaround (Line 1002)
```python
# Degrade gracefully if reconciliation failed (e.g., broker unavailable in dry-run)
# Phase 9 is always_run, so it should not cause a halt even if broker is unavailable
if reconciliation_succeeded:
    # ... normal flow
else:
    # Returns degraded data → dashboard gets partial data marked as complete
```

This is a **SILENT DEGRADATION** (contradicts GOVERNANCE fail-fast mandate).

---

## Issue #3: GOVERNANCE VIOLATION - Dashboard Silent Preservation of Stale Data

**File:** `dashboard/dashboard.py:581-592` (UNCOMMITTED CHANGES)  
**Severity:** HIGH  
**Impact:** Dashboard can display 20+ second old data as fresh without warning

### The Problem (Original Code Before Changes)
```python
elif current_result is None:
    # Timeout: load_all() didn't complete in 20 seconds
    logger.warning("load_all() returned None (timeout) - preserving previous state and marking stale")
    if state.result is None:
        state.result = {}  # Silent empty return
    else:
        # Preserve stale state indefinitely
        if isinstance(state.result, dict):
            state.result["_stale_refresh"] = True
```

**GOVERNANCE VIOLATION:** Line 37-68 explicitly forbids "silent fallbacks" and "silent data loss".  
This pattern violated that by preserving arbitrarily old cached data.

### Fix Applied (Uncommitted)
Good: Changed to fail-fast by marking data unavailable instead of preserving stale state.

---

## Issue #4: DATA SCHEMA CORRUPTION - earnings_calendar Missing Date Column

**Database Error:** `column "date" does not exist`  
**Severity:** HIGH  
**Impact:** Phase 1 freshness check cannot validate earnings_calendar staleness

### Discovery
Query: `SELECT COUNT(*), MAX(date) FROM earnings_calendar`  
Error: `UndefinedColumn: column "date" does not exist`

**Root Cause:** earnings_calendar schema mismatch. Likely renamed or never created correctly.

---

## Issue #5: DATA TRANSACTION ABORT CASCADE

**Database Error:** `InFailedSqlTransaction: current transaction is aborted`  
**Severity:** HIGH  
**Impact:** After earnings_calendar query fails, all subsequent queries in same transaction fail

**Root Cause:** PostgreSQL transaction abort on first error. Any missing column causes cascade failure.

---

## Issue #6: PHASE REGISTRY DESIGN FLAW - Circular Phase Dependencies

**File:** `algo/orchestrator/phase_registry.py:154-156`  
**Severity:** MEDIUM  
**Impact:** Phase 7 depends on Phase 5, but Phase 5 can fail while Phase 6 (always_run) succeeds

**The Scenario:**
1. Phase 5 fails (market regime data missing) → Phase 5 HALTS pipeline
2. Phase 6 executes anyway (always_run=True) → exits executed
3. Phase 7 tries to run → depends on Phase 5 which failed
4. Phase 7 skipped due to halt
5. **Result:** Portfolio state is modified (exits) but no new signals generated

**Question:** Is this by design (halt prevents new entries while allowing exits) or a bypass?

---

## Memory Claims vs Reality

| Commit | Claim | Reality |
|--------|-------|---------|
| `e2718fd97` | "Remove all LOCAL_MODE bypasses from halt flag" | ❌ Silent fallback still at line 168-169 |
| `33af4ed86` | "Eliminate all unsafe fallbacks" | ❌ Phase 6 always-run bypass still present |
| `d413866b7` | "Update audit findings with FileLockManager fixes" | ❌ Halt flag fallback not fixed |
| Session 282 | "System safety: HIGH (95%)" | ❌ Still contains multiple silent fallbacks |
| Session 282 | "Phase 6 designed correctly" | ⚠️ Design never stress-tested |

---

## Governance Violations

### GOVERNANCE.md §2: Code Cleanliness
- ❌ Blocks commits: Type errors + "silent fallbacks"
- ✅ Violations present: Silent fallback in halt_flag_manager.py line 168

### GOVERNANCE.md §3: Data Quality (PRINCIPLE: Fail-fast on missing data)
- ❌ "No silent fallbacks"
- ✓ Violations: (a) Dashboard preserves stale data; (b) Phase 6 exits without exposure policy

---

## Recommendations (Priority Order)

### 1. FIX IMMEDIATELY (Blocks Production)
1. **halt_flag_manager.py:167-169** - Remove silent fallback, fail-closed on DynamoDB error
2. **earnings_calendar schema** - Fix missing date column or determine correct column name
3. **dashboard.py** - Merge uncommitted changes (fail-fast on data timeout)

### 2. FIX SOON (Design Issues)
4. **Phase 5/6/7 dependency graph** - Clarify: is exposure policy bypass during halts intentional?
5. **Phase 9 degradation** - Fail-fast on reconciliation failure instead of returning partial data

### 3. TESTING REQUIRED
6. Stress-test Phase 6 always-run behavior when Phase 5 fails
7. Verify Phase 7 dependency validation actually halts on Phase 5 failure

---

## Testing To Verify

**Test 1: Halt Flag DynamoDB Unavailable**
```python
# Mock DynamoDB failure
# Verify: Orchestrator fails-fast with RuntimeError
# Not: Orchestrator continues with warning
```

**Test 2: Phase 5 Fails → Phase 6 Exits → Phase 7 Halts**
```python
# Scenario: Phase 5 (market regime) unavailable
# Expected: Phase 6 executes exits-only, Phase 7 halted
# Verify: No new entries created, only exits
```

**Test 3: Dashboard Load Timeout**
```python
# Mock 21-second load_all timeout
# Expected: Data marked unavailable, not stale cached state
```

---
