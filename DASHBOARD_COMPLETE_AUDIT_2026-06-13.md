# Complete Dashboard Audit — All Issues Identified
**Date:** 2026-06-13  
**Status:** COMPREHENSIVE ANALYSIS — 94+ issues across all severity tiers  
**Market Open:** < 9 hours away (estimated 8:00 AM ET today)  
**Readiness:** ❌ NOT READY — Critical architectural issues must be fixed first

---

## Executive Summary

The dashboard has **94 documented issues** spanning:
- **10 Critical (E-tier)** architectural issues
- **17 High severity (H-tier)** issues
- **20 Medium severity (M-tier)** issues  
- **47 Medium-low (T-tier)** issues

**Current state:** 1 complete, 1 in-progress (staged but not committed), 92 remaining

**Time to stabilize (critical path only):** 4-6 hours
**Time to fully fix all issues:** 25-30 hours

---

## TIER 0: CRITICAL — BLOCKS MARKET OPEN (10 Issues)

### 🔴 E1: Database Fallback Pattern Still Exists (IN PROGRESS)
**Severity:** CRITICAL  
**Status:** Partially converted, 176 lines staged but not committed  
**Impact:** Dual data sources enable silent failures, violates single-source-of-truth architecture

**What's converted:**
- ✅ `fetch_algo_config()` → API-only
- ✅ `fetch_market()` → API-only
- ✅ AWS boto3 integration added (working tree only)

**What remains (MUST FIX):**
- ❌ `fetch_perf()` — still has DB fallback
- ❌ `fetch_positions()` — still has DB fallback  
- ❌ `fetch_signals()` — still has DB fallback
- ❌ `fetch_portfolio()` — still has DB fallback
- ❌ `fetch_sector_ranking()` — still has DB fallback
- ❌ `fetch_recent_trades()` — still has DB fallback
- ❌ `fetch_health()` — still has DB fallback
- ❌ `fetch_economic_pulse()` — still has DB fallback
- ❌ `fetch_algo_metrics()` — still has DB fallback
- ❌ `fetch_notifications()` — still has DB fallback
- ❌ `fetch_sentiment()` — still has DB fallback
- ❌ `fetch_economic_calendar()` — still has DB fallback
- ❌ `fetch_risk_metrics()` — still has DB fallback
- ❌ `fetch_perf_analytics()` — still has DB fallback
- ❌ `fetch_signal_eval()` — still has DB fallback
- ❌ `fetch_sector_rotation()` — still has DB fallback
- ❌ `fetch_industry_ranking()` — still has DB fallback
- ❌ `fetch_exec_history()` — still has DB fallback
- ❌ `fetch_audit_log()` — still has DB fallback
- ❌ `fetch_circuit()` — still has DB fallback
- ❌ `fetch_activity()` — still has DB fallback

**Code location:** `tools/dashboard/fetchers.py` lines 38-2100+

**Blocking fixes:** E2, E4, E6, E7 cannot be addressed until E1 is complete

**Time to fix:** 1-2 hours

---

### 🔴 E2: Confidence Override Calculation in Dashboard (TODO)
**Severity:** CRITICAL  
**Status:** Not yet fixed

**Problem:** Dashboard recalculates `confidence` override based on signal metadata, duplicating business logic that should be in API

**Code location:** `panels.py` — multiple signal panel rendering functions

**Expected behavior:** API returns final confidence; dashboard displays it as-is, no recalculation

**Current behavior:** Dashboard modifies confidence value with panel-level logic

**Time to fix:** 30 minutes (depends on E1 completion)

---

### 🔴 E3: Position Metrics Pre-computation (✅ COMPLETE)
**Status:** ✅ DONE in commit f2747f850
- Position metrics (ladder, distance to stops/targets) pre-computed in API
- Dashboard displays pre-computed values without recalculation

---

### 🔴 E4: SPY Change Pre-computation (✅ COMPLETE)
**Status:** ✅ DONE
- Loader computes `spy_change_pct`
- API returns pre-computed value
- Dashboard displays it

---

### 🔴 E5: Sector Aggregation Recomputed O(n) Per Render (PARTIAL)
**Severity:** CRITICAL  
**Status:** Partially addressed with caching, needs API endpoint

**Problem:** `compute_sector_agg()` recalculates sector allocation stats on every 30-second refresh
- Current implementation uses in-memory OrderedDict cache
- Cache key uses `id(pos)` (Python object identity) — breaks if positions list recreated
- Better approach: Hash positions data or track actual changes
- Ideal: Move aggregation to API endpoint so dashboard just displays

**Code location:** `utilities.py:197-250`, `panels.py` sector aggregation

**Current cache:**
```python
_sector_agg_cache = OrderedDict()
_sector_cache_maxsize = 100
```

**Problem with current approach:**
- `id(pos)` assumes same Python object = same data (false if list recreated)
- No invalidation logic if positions change

**Time to fix:** 2 hours (to fix cache logic or move to API)

---

### 🔴 E6: Signal Quality Validation Duplication (TODO)
**Severity:** CRITICAL  
**Status:** Not yet fixed

**Problem:** Dashboard validates signal quality scores, duplicating API-side validation

**Impact:** Two sources of truth for signal filtering; silent failures if thresholds differ

**Code location:** `fetchers.py` signal validation, `panels.py` signal filtering

**Time to fix:** 1 hour (depends on E1 completion)

---

### 🔴 E7: Grade Threshold Filtering in Panel (TODO)
**Severity:** CRITICAL  
**Status:** Not yet fixed

**Problem:** Dashboard filters swing scores by grade threshold instead of letting API handle it

**Code location:** `panels.py` swing score filtering

**Time to fix:** 1 hour (depends on E1 completion)

---

### 🔴 E8: MIN_QUALITY_SCORE Hardcoded (TODO)
**Severity:** CRITICAL  
**Status:** Not yet fixed

**Location:** Line 2026 in `fetchers.py` or `panels.py`
```python
MIN_QUALITY_SCORE = 70  # Hardcoded
```

**Problem:**
- Can't tune without code redeploy
- Configuration locked in code, not database

**Solution:** Move to `algo_config` table
- Add entry: `min_signal_quality_score` with value `70`
- Load dynamically in `fetch_signals()`
- Dashboard fetches from API config endpoint

**Time to fix:** 30 minutes

---

### 🔴 E9: METRICS_MAX_AGE Hardcoded (TODO)
**Severity:** CRITICAL  
**Status:** Not yet fixed

**Location:** Line 36 in `utilities.py`
```python
METRICS_MAX_AGE = 3  # Hardcoded to 3 seconds
```

**Problem:**
- Can't adjust timeout without code redeploy
- API calls fail if response takes > 3 seconds (too aggressive)

**Solution:** Move to environment variable or `algo_config`
- Set `API_TIMEOUT = 20` (already done in line 116)
- But also need dynamic `METRICS_MAX_AGE` for stale data detection

**Time to fix:** 30 minutes

---

### 🔴 E10: Win Rate Excludes Open Trades (TODO)
**Severity:** CRITICAL  
**Status:** Not yet fixed

**Problem:** Win rate calculation only counts closed trades, ignoring unrealized losses in open positions

**Example:**
- 10 closed trades: 10 wins = 100% win rate ✓
- 5 open positions with -$50k unrealized loss ✗
- Dashboard shows: "100% win rate" (misleading — hides risk)

**Impact:** Operator can't see true performance; metric becomes meaningless

**Where calculated:** `fetchers.py` `fetch_perf()` or API `/algo/performance` endpoint

**Fix:** Include open positions in win rate calculation
```python
closed_wins = count of closed profitable trades
open_wins = count of open positions with positive unrealized P&L
open_losses = count of open positions with negative unrealized P&L

win_rate = closed_wins / (closed_wins + closed_losses + open_positions)
# or better: only count closed trades separately, flag open losses explicitly
```

**Time to fix:** 1 hour

---

## TIER 1: HIGH SEVERITY (17 Issues)

### ⚠️ Status: Verification Needed
MASTER_ISSUE_AUDIT.md marks all 17 as "✅ COMPLETE" but HIGH_MEDIUM_ISSUES.md shows many as "❌ NOT FIXED".
**Action needed:** Manually verify H1-H11 against current code (30 min)

### H1: Port Hardcoded to 5432 (⚠️ VERIFY)
**Location:** `utilities.py` line 242 or credential loading code
```python
port = int(os.environ.get("DB_PORT", 5432))
```

**Problem:** Fails silently if database on non-standard port (5433, 5434, etc.)

**Status:** ⚠️ Check if this code path is still used post-E1

---

### H2: No Test Connection Validation (⚠️ VERIFY)
**Location:** Credential validation function

**Problem:** Validates credentials format only, never tests actual DB connectivity

**Status:** ⚠️ Check if this is still needed (E1 removes DB calls entirely)

---

### H3 & H4: VIX None → 0 Coloring Bug (⚠️ VERIFY)
**Location:** Two places in `panels.py` (lines ~3151, ~3158)

**Problem:** 
```python
vc = R if (mkt.get("vix") or 0) >= 30 else (Y if (mkt.get("vix") or 0) >= 20 else G)
# If vix = None: (None or 0) >= 30 → 0 >= 30 → False → G (GREEN)
# But missing VIX should be YELLOW (unknown), not GREEN (calm)
```

**Status:** ⚠️ May be fixed in recent commits

---

### H5: Market Breadth Hides Missing Data (⚠️ VERIFY)
**Location:** Line ~3173

**Problem:**
```python
nhnl = (nh or 0) - (nl or 0)  # Shows 0 when both are None (missing)
hbar(nhnl, ...)  # Displays as neutral bar
# Should show "--" for missing
```

**Status:** ⚠️ Verify fix exists

---

### H6: Schema Validation Missing Column Types (⚠️ VERIFY)
**Problem:** Validates columns exist, not their types

**Status:** ⚠️ Check if validation is complete

---

### H7: Sector Ranking Missing Data Validation (LIKELY FIXED)
**Status:** ✅ LIKELY FIXED — code shows filtered_count returned

---

### H8: Trade Status Not Validated Against Enum (⚠️ VERIFY)
**Problem:** Invalid status values display without warning

**Status:** ⚠️ Check if validation exists

---

### H9: Position Entry Price Validation (✅ VERIFIED FIXED)
**Location:** Database constraint
```sql
WHEN ot.entry_price IS NULL OR ot.entry_price <= 0 THEN NULL
```

**Status:** ✅ Database prevents invalid prices

---

### H10: Signal Quality Score Missing Validation (✅ VERIFIED FIXED)
**Lines:** 1887-1904, 1998, 3832-3833

**Status:** ✅ Filtered count returned to panel

---

### H11: Exposure Factor Data Presence Not Checked (✅ VERIFIED FIXED)
**Lines:** 1354-1432, 4254-4266

**Status:** ✅ Missing factors flagged with warning indicator

---

### H12: Load_all() Timeout Doesn't Show Failed Fetchers (LIKELY FIXED)
**Lines:** 3007-3020

**Status:** ✅ LIKELY FIXED — still_running list tracked

---

### H13: Partial Fetch Failures Not Surfaced in UI (LIKELY FIXED)
**Status:** ✅ LIKELY FIXED — multiple panels show degraded data

---

### H14: No Failure Threshold (LIKELY FIXED)
**Status:** ✅ Error handling appears standardized

---

### H15 & H16: Win Rate Excludes Open / Ignores Open Risk (= E10)
**Status:** = E10 (CRITICAL, not yet fixed)

---

### H17: Sharpe Closed-Only (Related to E10)
**Status:** Related to E10 — needs open positions included

---

## TIER 2: MEDIUM SEVERITY (20 Issues)

### Status Summary
- ✅ 12 complete
- 🟡 5 partial (need completion)
- 🔄 1 in progress
- ❌ 2 not fixed

### ✅ Complete (12 issues)
- M1: Hardcoded grade thresholds
- M2: Hardcoded market thresholds
- M3: Hardcoded risk thresholds
- M5: Sector visibility missing
- M6: Risk calculation status missing
- M7: Economic data state unclear
- M8: Swing score inconsistent
- M9: Confidence not explained
- M10: Calculation staleness unknown
- M11: Circuit breaker defaults
- M14: Market health no thresholds
- M19: No operator runbook

### 🟡 Partial (Need Completion)

#### M4: Fallback Prices Not Flagged
**Problem:** When price source is fallback, no indicator shown

**Status:** Partial — need price source indicator

**Time to fix:** 1 hour

---

#### M12: Risk Source Not Indicated
**Problem:** Operator can't see if risk data is current or stale

**Status:** Partial — need risk data source visibility

**Time to fix:** 1 hour

---

#### M13: Filtered Signal Count Not Shown
**Problem:** Operator doesn't see how many signals were filtered

**Status:** Partial — need to show filtered count in panel

**Time to fix:** 1 hour

---

#### M16: Halt Reasons Cryptic
**Problem:** Halt reason codes not human-readable

**Example:** `"DRAWDOWN_DEFENSE"` should display as `"Drawdown Defense Triggered"`

**Status:** Partial — need human-readable labels

**Time to fix:** 1 hour

---

#### M18: Price Source Not Indicated
**Problem:** Can't distinguish current vs fallback prices in display

**Status:** Partial — need current vs fallback flag

**Time to fix:** 1 hour

---

### 🔄 In Progress (1 issue)

#### M15: Stale Alerts Not Returned
**Problem:** Staleness indicator not standardized across fetchers

**Status:** In progress — need staleness indicator schema

**Time to fix:** 1-2 hours

---

### ❌ Not Fixed (2 issues)

#### M17: No Unified Health Panel
**Problem:** Data quality metrics scattered across panels, not aggregated

**Time to fix:** 2 hours (architectural)

---

#### M20: NULL Handling Inconsistent
**Problem:** Some code silently filters NULLs, other code handles explicitly

**Time to fix:** 2 hours (widespread)

---

## TIER 3: MEDIUM-LOW (47 Issues)

**Status:** Identified but not addressed  
**Time to fix:** 12-15 hours total

### Category Breakdown

1. **Fallback Calculation Logic (8 issues)**
   - When to use fallback vs error
   - Silent fallback scenarios
   
2. **Data Filtering & Transformation (10 issues)**
   - Inconsistent filtering thresholds
   - Transformation logic in wrong layer
   
3. **Hardcoded Configuration (8 issues)**
   - Thresholds hardcoded in multiple places
   - Can't tune without code changes
   
4. **Data Quality Issues (7 issues)**
   - Stale data not flagged
   - Missing data marked as 0
   - Partial loads not indicated
   
5. **Business Logic in Display Layer (8 issues)**
   - Calculations that should be in API
   - Risk metrics computed on render
   - Grade filtering in panel
   
6. **Missing Pre-Computed Fields (6 issues)**
   - Fields that should be in API response
   - Currently computed in panel
   
7. **Error Handling Issues (4 issues)**
   - Inconsistent error propagation
   - Timeouts not handled uniformly
   
8. **Inconsistent APIs (3 issues)**
   - Response shapes differ between endpoints
   - Field naming inconsistencies

---

## GIT STATE ISSUES

### Git Conflict: Staged vs Working Tree
**Status:** Conflict exists (MM = modified in both index and working tree)

**Staged changes:** 176 lines
- E1 partial: `fetch_algo_config()`, `fetch_market()` API conversion
- Missing: AWS boto3 import, E5 sector caching

**Working tree changes:** Additional fixes
- AWS boto3 integration
- E5 sector caching

**Before committing:** Must reconcile which version is correct

**Recommendation:** Use working tree version (has more fixes)

**Time to fix:** 30 minutes

---

## NEW ISSUES DISCOVERED

### NEW 1: AWS Secrets Manager Integration Incomplete
**Status:** Partially implemented (boto3 import in working tree only)

**Action:** Complete integration or document as not-yet-used

---

### NEW 2: Sector Aggregation Cache Using Object Identity
**Status:** Cache key uses `id(pos)` — breaks on list recreation

**Better approach:** Hash positions data or track actual changes

**Time to fix:** 30 minutes

---

### NEW 3: fetch_market() API Migration Incomplete  
**Status:** Staged version doesn't handle all response fields

**Risk:** May lose fields if API response structure differs from DB query

**Action:** Verify response field mapping complete

**Time to fix:** 30 minutes

---

## CRITICAL PATH TO MARKET OPEN

**Time available:** < 9 hours (estimated 8:00 AM ET)

### Option A: Minimal Viable Stabilization (2-3 hours)
1. Resolve git conflict
2. Complete E1 (finish fetch_* API conversions)
3. Quick fix E8, E9 (config externalization)
4. Test dashboard starts
5. Deploy

**Result:** Dashboard functional but data integrity issues remain

---

### Option B: Critical Fixes (4-6 hours) — RECOMMENDED
1. Resolve git conflict (30 min)
2. Complete E1 (1-2 hours)
3. E8, E9 config externalization (1 hour)
4. E10 win rate includes open trades (1 hour)
5. M15-M18 operator visibility (1-2 hours)
6. Test and deploy (30 min)

**Result:** Dashboard stable, operator sees data quality warnings, single source of truth

---

## READINESS CHECKLIST

### Must Complete Before Market Open
- [ ] Resolve git conflict (staged vs working)
- [ ] Complete E1 (all fetch_* functions API-only)
- [ ] Complete E8, E9 (config externalization)
- [ ] Complete E10 (win rate includes open)
- [ ] Verify H1-H11 status against current code
- [ ] Verify M4, M12, M15, M16, M18 are acceptable partial state
- [ ] Test dashboard loads without errors
- [ ] All critical panels populate
- [ ] No silent failures
- [ ] Configuration loads from external source

### Can Defer to Next Session
- H-tier verification (if not already fixed)
- M17 (unified health panel)
- M20 (NULL handling consistency)
- All T-tier issues (47 items, lower priority)

---

## SUCCESS CRITERIA

✅ **REQUIRED for market open:**
1. Dashboard starts without errors
2. All critical panels display data (market, portfolio, positions, signals)
3. No silent failures (errors logged/visible)
4. API is sole data source (no DB fallback queries)
5. Configuration loaded from external source (algo_config table)
6. Operator sees data quality warnings
7. Git history clean (no staged/working conflicts)

⚠️ **Nice-to-have (can defer 1 week):**
1. Unified health panel (M17)
2. NULL handling consistency (M20)
3. All H-tier verification complete
4. All T-tier fixes

---

## RECOMMENDATIONS

### Immediate (Next 30 minutes)
1. ✅ Acknowledge this audit
2. Resolve git conflict (staged vs working tree)
3. Verify H1-H11 status in current code
4. Decide: Option A (minimal) or Option B (critical fixes)?

### If Option B Selected (Execute in order)
1. Complete E1 (1-2 hours)
   - Finish converting all fetch_* functions to API-only
   - Remove all database fallback code
   
2. E8, E9 (1 hour)
   - Move MIN_QUALITY_SCORE to algo_config
   - Move METRICS_MAX_AGE to config or env
   
3. E10 (1 hour)
   - Include open positions in win rate calculation
   - Update sharpe ratio calculation
   
4. M15-M18 (1-2 hours)
   - Add stale data indicators
   - Add price source indicators
   - Add human-readable halt labels
   
5. Test (30 min)
   - Dashboard starts
   - All panels load
   - No errors in log
   - Configuration tunable
   
6. Commit and deploy

### Total Time: 4-6 hours

---

## DECISION POINT

**Current time:** ~6:00 AM ET (estimated 3.5 hours before market open)  
**Time needed:** 4-6 hours for Option B

**Recommendation:**
- If market open can slip 2 hours: Execute Option B (full critical fixes)
- If must open at 9:30 AM: Execute Option A (minimal) and patch E10 immediately after open
- If less than 3 hours: Deploy on staging, paper trading only until E1 verified

**Risk assessment:**
- Option A: Dashboard works but has data integrity issues (win rate misleading, configuration not tunable)
- Option B: Dashboard stable, fully transparent, production-ready

---

## NEXT STEPS

1. **Read this document completely** (5 minutes)
2. **Resolve git conflict** (30 minutes)
3. **Verify H1-H11 status** (30 minutes)
4. **Decide Option A or B** (5 minutes)
5. **Execute remediation** (2-6 hours depending on option)
6. **Test and deploy** (30 minutes)

**Total time from now:** 3-7 hours

---

**Generated:** 2026-06-13 @ 06:00 ET  
**For:** Market open readiness decision  
**Status:** Action required — audit complete, decision awaited
