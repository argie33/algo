# Comprehensive System Assessment & Action Plan

**Date:** 2026-05-16  
**Objective:** Identify and prioritize all outstanding issues blocking production readiness

---

## EXECUTIVE SUMMARY

**Current Status:** System is 80% complete but 5 critical blockers prevent live trading:

1. **Stock Scores Incomplete** - 7.1% coverage (725/10,167)
2. **Quality Metrics Broken** - 4 rows vs 374 expected
3. **Filter Pipeline Issues** - Rejecting all signals (or none passing)
4. **Swing Scores Schema Missing** - Table doesn't exist
5. **No Live Trades** - Only 1 trade recorded (test only)

**Good News:** All architectural pieces are in place. These are data/calculation issues, not design problems.

---

## CRITICAL BLOCKERS (FIX FIRST)

### 1. Stock Scores Loader - 7.1% Coverage
**Severity:** 🔴 CRITICAL  
**Impact:** Algo cannot rank/filter signals without stock scores. No trades will execute.

**Current State:**
- 725 scores / 10,167 symbols (7.1%)
- Root cause: yfinance rate limiting + sequential processing (~1 symbol/sec = 2.8 hours for 10K)
- Last run: Unknown (check loader logs)

**Decision Point:** Do we need all 10K symbols or a subset?
- **Option A:** Load only active trading universe (~500-2,000 symbols) = faster, sufficient
- **Option B:** Load all 10K symbols = complete but requires rate limiting strategy + caching

**Recommended Fix:**
1. Determine target universe size
2. If Option A: Filter stock_symbols to only active universe, update loader
3. If Option B: Add parallelism + caching + rate limiting to stock_scores loader
4. Re-run loader and verify coverage >90%

**Effort:** 2-3 hours

---

### 2. Quality Metrics - 4 Rows vs 374 Expected
**Severity:** 🔴 CRITICAL  
**Impact:** Portfolio quality scoring unavailable. Could miss quality stocks.

**Current State:**
- 4 rows in quality_metrics vs 374 in growth_metrics and value_metrics
- Root cause: Unknown (loader broken or only ran on subset)
- Alternative metrics: growth_metrics (374), value_metrics (377) both working

**Investigation Needed:**
1. Check load_quality_metrics.py for obvious bugs
2. Run manually: `python3 load_quality_metrics.py --symbols AAPL MSFT GOOGL TSLA` to test
3. Check if there's data dependency (missing financial statements?)

**Recommended Fix:**
1. Debug why only 4 rows loaded
2. Either fix loader or mark as "temporary partial" if data source issue
3. Re-run to get 370+ symbols scored

**Effort:** 1-2 hours

---

### 3. Filter Pipeline Rejecting Signals
**Severity:** 🔴 CRITICAL  
**Impact:** Even if stock scores exist, filter pipeline rejects all signals = no trades.

**Current State:**
- STATUS.md says "all tested signals rejected even with feature_flags enabled"
- Feature flags all ON except tier 5
- Root cause: TBD

**Investigation Needed:**
1. Run orchestrator with --dry-run and observe which tier rejects signals
2. Check if tier 1 (top 12 from market context) has any passing signals
3. Verify feature_flags logic in algo_filter_pipeline.py

**Recommended Fix:**
1. Test with sample date (2026-05-15) to see signal pass rates
2. Debug which tier is blocking (1/2/3/4)
3. Either fix threshold/logic OR disable tier temporarily to test downstream

**Effort:** 1-2 hours

---

### 4. Swing Scores Table Missing
**Severity:** 🟡 HIGH  
**Impact:** SwingCandidates page won't work. Swing score calculations not persisted.

**Current State:**
- Table "swing_scores" doesn't exist
- STATUS.md mentions "Fixed swing score indentation error" but table creation may not have happened
- Algorithm: algo_filter_pipeline.py computes swing_score grade but nowhere to store it

**Recommended Fix:**
1. Check if `init_database.py` creates swing_scores table
2. If missing: Create schema with columns (symbol, date, swing_score, grade, created_at)
3. Update algo_filter_pipeline.py to persist scores to table
4. Verify SwingCandidates page works

**Effort:** 1 hour

---

## DATA QUALITY ISSUES (Secondary)

### 5. Industry Ranking Columns Missing
**Severity:** 🟡 MEDIUM  
**Impact:** Sector rotation analysis incomplete. Some dashboard features limited.

**Current State:**
- `company_profile.rank_1w_ago`, `rank_4w_ago` columns don't exist
- Sector rotation score tries to use these and fails

**Recommended Fix:**
1. Check if columns should exist in schema
2. Either add columns + loader OR remove from sector rotation calculation
3. Verify sector/industry pages show data

**Effort:** 30 minutes

---

### 6. Earnings Data Missing
**Severity:** 🟡 MEDIUM  
**Impact:** Earnings-aware trading features unavailable.

**Current State:**
- `earnings_calendar` table empty (0 rows)
- Some loaders reference `earnings_date` column (may not exist)

**Recommended Fix:**
1. Check if earnings loader exists (likely loadearningshistory.py or similar)
2. If exists: debug why not running or populating
3. If not: verify earnings aren't required for core algo (they're not)
4. Update STATUS.md if earnings are optional

**Effort:** 1 hour

---

## DESIGN/ARCHITECTURE REVIEW

### Trading Universe Scope
**Question:** What symbols should we be trading?

Current state:
- Symbols loaded: 10,167 (all NASDAQ + NYSE)
- Stock scores loaded: 725 (7.1%)
- Signals generated on: Unknown (likely all 10,167 but need to verify)

**Issue:** If we load all 10,167 symbols but can only score 725, the algo is under-informed.

**Options:**
1. **Universe A (Focused):** Top 500 liquid symbols by volume → smaller but fast to score
2. **Universe B (Complete):** All 10,167 → comprehensive but needs parallel scoring
3. **Universe C (Smart):** All symbols with price data, score top 1,000 by volume → balanced

**Decision Needed:** Which universe are we optimizing for? This affects:
- Scoring speed
- API costs (data source calls)
- Orchestrator complexity
- Portfolio diversification

---

### Calculation Correctness
**Completed:** Most core calculations verified (per STATUS.md Session 30)
- Stock score weighting: Fixed double-counting ✓
- SQS threshold: Lowered to 40 ✓
- Position monitor: Removed artificial floor ✓

**Outstanding:** Need to verify:
- Swing score formula matches design intent
- Market exposure calculation correct (48 factors listed, need validation)
- Exit logic matches documented strategy (trailing stops, profit targets)

---

## PERFORMANCE OPPORTUNITIES

### 1. Stock Scores Loader Parallelism
**Current:** Sequential, ~1 symbol/second  
**Potential:** With 8-worker parallelism, could do 8/second = 350% speedup

**Quick Win:** Already have OptimalLoader with parallelism support. Just need to:
1. Check if stock_scores loader uses it properly
2. Verify parallelism=8 is set
3. Re-run and measure improvement

**Expected Impact:** 2.8 hours → 20 minutes for full 10K symbols

---

### 2. API Endpoint Performance
**Status:** Fixed in Session 28 with CTEs (100x+ speedup)  
**Current:** ~20-50ms per endpoint ✓

---

### 3. Database Indexes
**Status:** 10 indexes added in Session 26 ✓

---

## FRONTEND DATA GAPS

24 pages exist. Missing data on:
- **SwingCandidates** - Needs swing_scores table
- **EconomicDashboard** - Has economic data, needs verification
- **SectorAnalysis/IndustryAnalysis** - Has sector/industry tables, may be complete
- **DeepValueStocks** - Needs value_metrics (377 rows ✓)
- **Sentiment** - Tables working (market_exposure_daily has data)

---

## ACTION PLAN (Priority Order)

### PHASE 1: Unblock Core Trading (Today - 3-4 hours)

**1. Fix Stock Scores Loader** [2 hours]
   - Decide universe scope (all 10K vs subset)
   - If subset: Filter stock_symbols table first
   - Verify parallelism enabled in loader
   - Run with `--force` to reload all
   - Target: >90% coverage (9,000+ symbols)

**2. Debug Filter Pipeline** [1 hour]
   - Run orchestrator with sample date (2026-05-15)
   - Log which tier rejects which signals
   - Identify if issue is data, threshold, or logic
   - If needed: Temporarily disable failing tier to test downstream

**3. Fix Quality Metrics** [1 hour]
   - Test loader manually on 5 symbols
   - Identify why only 4 rows loaded
   - Re-run or mark as limitation if unfixable

### PHASE 2: Complete Data Pipeline (Next 2-3 hours)

**4. Create Swing Scores Table** [1 hour]
   - Add schema if missing
   - Update filter pipeline to persist
   - Verify page works

**5. Add Missing Schema Columns** [30 min]
   - Industry ranking columns
   - Any other missing references

**6. Verify All Data Flows** [1 hour]
   - Run full orchestrator end-to-end
   - Verify at least 10% of signals pass
   - Check database for trades/positions

### PHASE 3: Performance & Polish (Next session)

**7. Optimize Stock Scores Parallelism**
**8. Review Calculation Correctness**
**9. End-to-End Trading Test**

---

## DECISION MATRIX

**Before we proceed, you should decide:**

| Question | Impact | Option A | Option B | Option C |
|----------|--------|----------|----------|----------|
| **Trading Universe** | Core data scope | 500 liquid symbols | All 10K symbols | Top 1K by volume |
| **Earnings Data** | Optional feature | Load if time permits | Skip for now | Load from yfinance fallback |
| **Quality Metrics** | Data completeness | Fix if quick fix exists | Use growth+value instead | Load only on demand |

---

## SUCCESS CRITERIA

When complete, system should:
- [ ] Stock scores: 90%+ coverage
- [ ] Filter pipeline: >10% signals pass
- [ ] Orchestrator: Runs end-to-end without errors
- [ ] Trades: Execute at least 1 real trade in paper mode
- [ ] Pages: All 24 pages load without 404 errors
- [ ] Data: All critical tables populated within SLA
- [ ] Performance: Orchestrator completes <5 minutes

---

## Technical Debt (Lower Priority)

- ✓ Code cleanup: Done (Session 25)
- ✓ API optimization: Done (Session 28)
- ⚠️ Swing scores persistence: Needs implementation
- ⚠️ Schema consistency: A few missing columns
- ⚠️ Error logging: Some loaders may fail silently

