# SESSION 285: CRITICAL BYPASS & STALENESS AUDIT

**Date:** 2026-07-19  
**Status:** ✅ TWO CRITICAL BYPASSES FIXED - Audit findings documented  
**User Concern:** "stages halted yet some completed afterwards" + "lot of stale tables"

## Quick Summary

Found and fixed **2 CRITICAL GOVERNANCE violations** where "stages halted yet completed afterwards":
1. **Phase 9 fallback patterns** (fixed in b1cb7cb86) - Using database state when broker unavailable
2. **buy_sell_daily universe filter** (fixed in 4b8f3372e) - Proceeding with all symbols when filter fails

Both violated GOVERNANCE: "Fail-fast on missing data. No silent fallbacks."

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

## Critical Finding #3: Universe Filter Fallback in buy_sell_daily ✅ FIXED

**File:** `loaders/load_buy_sell_daily.py:54-77`  
**Commit:** 4b8f3372e (Session 285)  
**Status:** FIXED

**Problem:**
When filtering signals to only scored symbols failed (stock_scores query error), loader:
```python
except Exception as e:
    logger.error("Failed to filter... Proceeding with all {len(symbols)} symbols")
    # NO RAISE - silently continues!
```

**Bypass Details:**
- stock_scores unavailable → filter query fails
- Should fail-fast, but catches exception and proceeds
- Generates signals for ~10k symbols instead of ~4.7k scored symbols
- Results in ~99.5% signal rejection in Phase 7 (inefficient)
- Violates GOVERNANCE: "Fail-fast on missing data"

**Real-World Impact:**
```
Phase 7 halts (no signals with scores) 
BUT buy_sell_daily completed anyway
  → Phase 8 sees empty signals list
  → Dashboard shows no trading opportunities
  → Operator sees "halted" phase but data was written
```

**Fix Applied:**
Changed from try/except-continue to fail-fast:
- Stock_scores query fails → raise RuntimeError
- No scored symbols → raise RuntimeError
- No symbols remain after filter → raise RuntimeError

---

## Next Steps

1. ✅ Verified Phase 9 fallback patterns were fixed (b1cb7cb86)
2. ✅ Found and fixed buy_sell_daily universe filter fallback (4b8f3372e)
3. 🔍 Search for similar fallback patterns in other loaders
4. 🔍 Review Phase 6 to ensure exits only run when safe
5. 🔍 Check data_loader_status table for stuck/pending loaders
6. 🔍 Monitor EventBridge Scheduler execution

---

## Related Commits

- **4b8f3372e** - Removed buy_sell_daily universe filter fallback (Session 285 - THIS SESSION)
- **b1cb7cb86** - Removed Phase 9 fallback patterns (Session 285)
- **eaa4dafcd** - Added data_unavailable checks (Session 284)
- **Session 283** - Loader GOVERNANCE compliance audit
- **Session 282** - Race condition elimination
- **Session 281** - Critical security and data integrity fixes
