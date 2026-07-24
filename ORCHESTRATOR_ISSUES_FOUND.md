# Orchestrator Issues - Session Current

## Status: BLOCKING ALL ENTRIES

### Issue #1: Signal Quality Scores Pipeline Broken
**Severity**: CRITICAL - Prevents all entries

**Problem**:
- Phase 7 generates 37 candidate signals
- Only 6/37 have signal_quality_scores data in database
- Phase 7 invokes SignalQualityScoresLoader to compute missing 31 scores
- Loader fails silently, returns success but doesn't insert data
- Phase 8 rejects all 31 NULL-score signals per fail-closed policy

**Evidence**:
```
algo_signals: 37 total, only 6 with matching signal_quality_scores
signal_quality_scores has 1803 rows but none for these 31 symbols
Phase 8 rejection at line 1299: "Signal quality score unavailable (NULL)"
```

**Missing Symbols** (31 total):
CP, EAT, EMA, EPR, ESEA, FMS, FRT, FVCB, GAIN, HG, HIW, INCY, ING, JCAP, KARO, KRC, KRG, LTC, LTH, LXP, NLY, NVDA, ORRF, PDLB, RLX, RY, TD, TRNO, TRP, V, XNET

### Issue #2: Quality Threshold Too Conservative
**Severity**: HIGH - Rejects even computed signals

**Problem**:
- Configured threshold: 75 (line 1298 in phase8_entry_execution.py)
- Actual signal quality range: 60-72
- Average composite: 64.3/100
- Result: Even the 6 signals with computed scores rejected

### Issue #3: Exit Engine 404 Handling
**Severity**: MEDIUM - Fixed, prevents position exits on delisted symbols

**Status**: FIXED in commit bf0af9e0c
- Changed from raising RuntimeError to returning None
- Allows fallback to database pricing
- Delisted positions (15 total) previously force-closed, now handled gracefully

## Actions Required

### Immediate (Next Orchestrator Run):
1. Fix SignalQualityScoresLoader - ensure it computes and inserts scores
2. Verify all 37 signals get quality scores computed
3. Validate Phase 8 receives proper scores

### Short-term:
1. Review signal quality formula - why is average only 64.3?
2. Consider if threshold of 75 is appropriate
3. Add logging to track loader completion

### Verification:
- After fix, re-run Phase 7-8 to verify signals pass quality gate
- Check Phase 8 logs show entries being executed
- Monitor first 3-5 entries for performance
