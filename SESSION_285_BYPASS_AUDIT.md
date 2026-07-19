# SESSION 285: CRITICAL BYPASS & STALENESS AUDIT

**Date:** 2026-07-19  
**Status:** 🔍 IN PROGRESS - Finding and fixing bypass patterns  
**User Concern:** "stages halted yet some completed afterwards" + "lot of stale tables"

---

## Investigation Summary

Targeted search for bypass patterns where:
1. Phases marked `halted=True` still persist data
2. Phases complete with fallback/degraded data instead of truly halting
3. Data marked `data_unavailable=TRUE` still gets used

---

## Critical Finding #1: Phase 9 Fallback Patterns ✅ ALREADY FIXED (b1cb7cb86)

**Commit:** b1cb7cb86 (July 19 18:04)  
**Status:** Fixed in latest code

**Problem Identified:**
- Phase 9 had TWO fallback patterns violating GOVERNANCE:

### Fallback Pattern A: Missing Alpaca Credentials (lines 733-842 REMOVED)
- If Alpaca credentials missing → Create snapshot from DATABASE state
- Allowed trading with ESTIMATED portfolio values instead of broker source-of-truth
- **Impact:** Data sync issues masked, position sizing incorrect

### Fallback Pattern B: Reconciliation Auth Failures (lines 911-978 REMOVED)
- If broker auth failed (401) in paper mode → Use database-cached portfolio state
- Treated 401 as "expected" and continued trading
- **Impact:** Used stale state instead of failing

**What Was Wrong:**
```
Phase 5 halts → Phase 6 marks halted=True
                BUT Phase 9 would see halted phase and create snapshot
                from DB state instead of truly halting → DATA PERSISTED
```

**Fix Applied:** Both fallback paths now raise RuntimeError (fail-fast)

---

## Critical Finding #2: Potential Similar Patterns

Searching other phases for comparable fallback logic...

### Phase 6 (Exit Execution) - NEEDS REVIEW
- Marked `always_run=True` for risk management
- Depends on Phase 3 only
- Phase 5 (exposure policy) is "optional"
- **Question:** Does Phase 6 write exit data even when Phase 5 halted?
- **Status:** Code review in progress

### Phase 7/8 Dependency Chain - VERIFIED SAFE
- Phase 7 checks Phase 5 halted status → properly returns halted
- Phase 8 checks Phase 7 halted status → properly returns halted
- Signal persistence only if Phase 7 succeeded
- **Status:** ✅ No bypass found

### Phase 4 (Reconciliation) - NEEDS REVIEW
- Depends on Phase 3
- Phase 3 always_run=True
- **Question:** Can Phase 4 fail silently or write partial data?
- **Status:** Code review in progress

---

## Stale Tables Investigation

**User Reported:** "lot of stale tables"  
**Root Cause (from Session 284 memory):** EventBridge Scheduler may not be running loaders

**Status:** EventBridge Scheduler correctly configured:
- Morning pipeline: `cron(0 2 ? * MON-FRI *)` - ENABLED  
- EOD pipeline: `cron(5 16 ? * MON-FRI *)` - ENABLED
- computed_metrics pipeline: configured - ENABLED

**Possible Issues:**
1. Loaders might be failing silently without marking `data_unavailable=TRUE`
2. Loaders might be stuck/hung
3. Database connections might be saturated
4. Loader timeouts might not be enforced

**Action:** Need to check actual loader execution and failure patterns

---

## Next Steps

1. ✅ Verified Phase 9 fallback patterns were fixed
2. 🔍 Review Phase 6 to ensure exits only run when safe
3. 🔍 Review Phase 4 reconciliation for silent failures
4. 🔍 Check all loaders for data_unavailable flag usage
5. 🔍 Monitor EventBridge Scheduler execution
6. 🔍 Check for hung loaders or timeouts

---

## Related Commits

- **b1cb7cb86** - Removed Phase 9 fallback patterns (COMPLETED)
- **eaa4dafcd** - Added data_unavailable checks (Session 284)
- **Session 283** - Loader GOVERNANCE compliance audit
- **Session 282** - Race condition elimination
- **Session 281** - Critical security and data integrity fixes
