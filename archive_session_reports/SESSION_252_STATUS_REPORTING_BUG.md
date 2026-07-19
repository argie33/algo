# Session 252: Critical Status Reporting Bug + Stock Scores Coverage Issue

## Executive Summary

**FIXED:** Orchestrator was reporting "success" when phases 7-8 were actually degraded/skipped. Status logic didn't check for "degraded" or "skipped" states.

**ROOT CAUSE DISCOVERED:** Phase 7 degraded because momentum_score loader doesn't exist/run, causing stock_scores to have 0% momentum coverage. Phase 7 requires >= 70% data_completeness; all symbols fall below this.

## Issue 1: False Success Status Reporting (FIXED)

### The Bug
```
Run: LOCAL-AFTERNOON-20260718-191639-715098
Overall Status: SUCCESS
  Phase 7: degraded - no candidates pass >= 70% completeness filter
  Phase 8: skipped - can't run without Phase 7 signals
```

Status logic only checked for "error", "fail", "halted" — ignored "degraded" and "skipped".

### The Fix
- Added checks for `any_degraded` and `any_skipped` phase statuses
- Set `success = false` if ANY phase is not "ok" status
- Set `overall_status = "degraded"` if any phase is degraded/skipped
- Commit: 35067029d

### Impact
Now orchestrator honestly reports degraded/skipped phases, exposing underlying data quality issues.

---

## Issue 2: Stock Scores Data Completeness Crisis (NEW)

### The Metrics Coverage Problem

Stock Scores metric coverage by loader:
- **Momentum score:** 0% coverage ← **CRITICAL**
- **Value score:** 31.6% coverage
- **Quality score:** 53.3% coverage
- **Growth score:** 59.2% coverage
- **Positioning score:** 79.2% ✓ (good)
- **Stability score:** 99.7% ✓ (excellent)

### Why Phase 7 Degrades

1. Phase 7 requires `data_completeness >= 70%` for eligible signals
2. With momentum at 0%, NO symbol reaches 70% completeness
3. All 10 recent BUY signals have ~38% avg completeness
4. Zero candidates pass the filter → Phase 7 reports "degraded"

### Data Distribution
- 1,182 symbols (25.1%): 99.99% complete
- 731 symbols (15.5%): 80% complete  
- 1,174 symbols (24.9%): 60% complete
- 1,243 symbols (26.4%): 40% complete (← recent BUY signals here)
- 374 symbols (7.9%): 20% complete
- 7 symbols: 0% complete

**Bottom line:** 2,798 symbols (59%) have < 70% completeness due to missing momentum/quality/value scores.

---

## Investigation Findings

### Recent BUY Signals Analysis (Last 7 Days)

```sql
Unique symbols: 8
With >= 70% completeness: 0
Average completeness: 38%
```

Each signal symbol breaks down:
- APC, BAP, BOBS, BSAC, BTI, DCBO, DEO: 40% complete (missing quality, growth, value, momentum)
- APLM: 20% complete (worse coverage)

All have sufficient composite_score >= 30 and close > sma_50 (pass trend filter).
All fail the >= 70% completeness gate.

---

## Root Cause Chain

1. `load_momentum_indicators` does NOT exist or is NOT running
   - Momentum score is 0% across all 4,711 symbols
   - This alone guarantees completeness < 70% for all symbols

2. `load_value_quality_growth_metrics` is incomplete
   - Value score: 31.6% (broken for ~68% of symbols)
   - Quality score: 53.3% (broken for ~47% of symbols)
   - Growth score: 59.2% (broken for ~41% of symbols)

3. Phase 7's 70% threshold filter
   - Set conservatively for data quality
   - Now blocks nearly 100% of universe (including good signals)
   - Not actually a bug, but the 70% threshold is unachievable

---

## Options to Restore Signal Generation

### Option A: Fix Data Loaders (RECOMMENDED)
1. Implement or enable momentum indicator loader
2. Fix value/quality/growth metric loaders to improve coverage
3. Target >= 90% coverage for critical metrics
4. Keep 70% threshold (data quality gate)
5. Effort: 2-4 weeks for Phase 2 work

### Option B: Lower Completeness Threshold (SHORT-TERM)
1. Change Phase 7 threshold from 70% to 50%
2. Allows 1,913 symbols (40.6%) with >= 50% coverage
3. Maintains data quality gate, less strict
4. Recent BUY signals (38% avg) would still not qualify
5. Effort: 1 line change, but masks underlying issue
6. **Not recommended** — hides data quality problem

### Option C: Disable Completeness Gate (RISKY)
1. Remove `data_completeness >= 70` filter
2. Allows all symbols with composite_score > 0
3. Maximizes signal generation
4. **Risk:** Low-quality signals from incomplete data
5. **Not recommended** — violates fail-fast principle

### Option D: Hybrid - Phased Rollout
1. Phase 7a: Current (70%, ~0 signals for data quality)
2. Phase 7b: Fallback (50%, ~1,900+ signals if metrics improved)
3. Phase 7c: Future (90%, with Phase 2 work complete)
4. Dashboard shows "degraded_low_quality" vs "degraded_incomplete_data"
5. Effort: 3-5 days, positions for long-term improvement

---

## Session Work Done

### ✅ COMPLETED
1. Fixed orchestrator status reporting (commit 35067029d)
2. Investigated stock_scores completeness crisis
3. Identified momentum loader as critical blocker
4. Documented all root causes and options

### ⏭️ NEXT STEPS
1. Decide: Fix loaders (A) vs lower threshold (B) vs hybrid (D)?
2. If Option A: Priority rank metric loaders by impact
3. If Option B: Add clear "degraded_incomplete_data" reason to Phase 7
4. If Option D: Implement phased approach with explicit quality levels
5. Update dashboard to show data completeness % alongside signals

---

## Memory Update
- Added [[session_252_status_reporting_fix.md]] for orchestrator fix
- Added [[session_252_stock_scores_completeness_crisis.md]] for data issue
- Updated [[session_251_fallback_audit_complete.md]] with new findings

---

## Technical Details for Next Session

### Files Modified
- `algo/orchestration/orchestrator.py` - status reporting fix

### Files to Investigate
- `utils/loaders/` - check if momentum loader exists
- `utils/loaders/load_value_quality_growth_metrics.py` - why so incomplete
- `algo/orchestrator/phase7_signal_generation.py` line 372 - completeness gate

### Queries That Expose the Issue
```sql
-- Check metric coverage
SELECT 
    COUNT(DISTINCT CASE WHEN momentum_score IS NOT NULL THEN symbol END) as momentum_cnt,
    COUNT(*) as total
FROM stock_scores;

-- Check Phase 7 filterable universe
SELECT COUNT(*) FROM stock_scores WHERE data_completeness >= 70;

-- Check recent BUY signals eligibility
SELECT DISTINCT bsd.symbol, ss.data_completeness
FROM buy_sell_daily bsd
INNER JOIN stock_scores ss ON bsd.symbol = ss.symbol
WHERE bsd.signal_type = 'BUY' AND bsd.date >= CURRENT_DATE - INTERVAL '7 days'
AND ss.data_completeness >= 70;
```

---

## Conclusion

**The system is working correctly by reporting "degraded" Phase 7 now.** There IS a real problem: most metrics are incomplete. The orchestrator fix makes this visible. The challenge is deciding whether to:
- Invest in fixing metric loaders (best long-term)
- Lower the quality gate (quick fix, masks problem)
- Implement hybrid (progressive improvement)

The false-success bug is fixed. The data quality issue remains and needs deliberate action.
