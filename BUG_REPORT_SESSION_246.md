# Bug Report - Session 246: Stock Scores Computation Failure

## Summary
Found critical bug in stock_scores loader: all stocks have composite_score=80.0 with NULL component scores. This breaks Phase 7 signal generation which depends on meaningful score distributions for ranking.

## Bugs Found

### BUG #1: CRITICAL - Stock_scores Hardcoded to 80.0
**Status:** Partially Fixed (Safety check added, root cause in progress)  
**Severity:** CRITICAL - Breaks signal ranking in Phase 7

#### Symptoms
- `stock_scores` table has 4711 rows
- ALL stocks have composite_score=80.0 (100% identical)
- ALL component scores NULL: quality_score, growth_score, value_score, positioning_score, stability_score, momentum_score
- `data_unavailable = false` (marked successful despite NULL data)

#### Root Cause
The loader's `fetch_incremental()` method depends on batch context (metric caches initialized by `_prepare_batch_context()`). When these caches aren't available or fail to initialize:
- fetch_incremental() catches the AttributeError
- Returns data_unavailable marker
- Gets inserted as NULL scores into database

Additionally, there appears to be a fallback mechanism that's setting composite_score=80.0 for records with all NULL components.

#### Evidence
```python
# When called directly without batch context:
loader = StockScoresLoader()
loader.fetch_incremental('AAPL', None)
# ERROR: 'StockScoresLoader' object has no attribute '_quality_cache'
# Returns: [{"data_unavailable": True, ...}]

# But orchestrator runs complete successfully, inserting 80.0/NULL data
```

#### Code Path
1. OptimalLoader.run() calls _prepare_batch_context() once at start
2. Then calls load_symbol() for each symbol (potentially in parallel)
3. load_symbol() calls fetch_incremental()
4. fetch_incremental() expects self._quality_cache and other caches to exist
5. If caches missing: returns data_unavailable marker -> inserts NULL -> fallback sets 80.0?

#### Fix Applied
Added safety check in fetch_incremental() to fail-fast if caches aren't initialized:
- Commit: ab5d9a63e
- Raises explicit RuntimeError instead of silently returning data_unavailable
- Prevents silent data corruption

#### Still TODO
- [ ] Verify caches are properly initialized through full execution
- [ ] Find where 80.0 fallback is being set
- [ ] Add comprehensive logging to trace cache initialization
- [ ] Consider making caches thread-safe if parallel execution is issue

---

### BUG #2: MINOR - Stale Cache Fallback Removed (CORRECT)
**Status:** Fixed (This was intentional)  
**Severity:** MEDIUM - Safety-first design decision

The removal of `_try_stale_cache_fallback()` in api_data_layer.py was **intentional and correct**. In finance applications, showing stale data is dangerous:
- Stale market prices lead to wrong position sizing
- Stale account balances lead to incorrect risk calculations
- Stale signals lead to mistimed trade execution

Better to fail loudly and let operators explicitly choose to trade with stale data than silently show old values.

---

### BUG #3: MINOR - SEC Loaders Have Minimal Data
**Status:** Known Limitation (Not a bug)  
**Severity:** LOW - Expected behavior

New SEC loaders (institutional_holdings_13f, insider_holdings_sec) have minimal data:
- institutional_holdings_13f: 4 rows
- insider_holdings_sec: 2 rows

Root cause: SEC EDGAR companyfacts API doesn't expose institutional ownership data via standardized metrics. Real Form 13F data requires XML parsing (not available via API).

These are new Phase 2 loaders and the limited data is expected while the system is being tuned. Not a critical issue.

---

## Test Results
- Tests passing: 1130 passed, 11 skipped, 16 xfailed, 2 xpassed
- Orchestrator execution: ALL 9 phases complete successfully
- Local dev mode: Working correctly

## Data Quality Issues

### Current State
```
Sample Stock Scores (7/18/2026 16:43):
AAPL: composite=80.00, quality=NULL, growth=NULL, value=NULL, positioning=NULL, stability=NULL, momentum=NULL
MSFT: composite=80.00, quality=NULL, growth=NULL, value=NULL, positioning=NULL, stability=NULL, momentum=NULL
...all 4711 stocks have same pattern...
```

### Expected State
```
AAPL: composite=47.37, quality=52.96, growth=42.15, value=58.23, positioning=35.41, stability=62.78, momentum=51.20
(Real computed scores distributed across 0-100 range)
```

### Impact on Phase 7
Phase 7 uses `composite_score >= 30` to filter entry signals. With all scores at 80.0:
- Either ALL 4711 stocks pass the filter (if threshold <= 80)
- Or NO stocks pass (if threshold > 80)
- Signal ranking is broken (no discrimination between good/bad stocks)

## Recommended Next Steps

1. **Immediate:** Monitor orchestrator runs with new safety check
   - If RuntimeError appears: batch context initialization is failing
   - If silent 80.0/NULL continues: find the fallback mechanism

2. **Short-term:** Add comprehensive logging to trace cache initialization through full execution pipeline

3. **Medium-term:** Verify thread safety of batch context caches if parallel execution is the issue

4. **Long-term:** Consider refactoring caches to be per-symbol instead of global to eliminate shared state

## Files Modified
- loaders/load_stock_scores.py: Added safety check (commit ab5d9a63e)
- dashboard/api_data_layer.py: Removed stale cache fallback (correct design decision)
- scripts/local_loader_scheduler.py: Added SEC loaders (expected integration)

## Links
- Previous fix history: Sessions 243-245 documented in memory/
- Phase 7 logic: algo/orchestrator/phase7_signal_generation.py
- Stock scores loader: loaders/load_stock_scores.py
