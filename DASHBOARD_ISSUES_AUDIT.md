# Algo Dashboard: Comprehensive Issues Audit
**Date:** 2026-06-13  
**Scope:** Full system audit - Architecture, Data Sources, Performance, Security  
**Status:** CRITICAL - Multiple missing endpoints, data integrity issues, and architectural concerns  

## Executive Summary

The algo dashboard has **4 critical missing endpoints** that will cause complete rendering failures, plus significant architectural issues. The system is not ready for market open without addressing critical path items.

---

## CRITICAL ISSUES (Block Market Open)

### Issue #1: Missing Dashboard API Endpoints
**Severity:** CRITICAL - Causes 404 errors and dashboard failures  
**Impact:** Frontend cannot load required data visualizations  

The PortfolioDashboard component requests these endpoints that have NO handlers implemented:

#### 1.1 GET /api/algo/daily-return-histogram
- **Called by:** `PortfolioDashboard.jsx` line 180
- **Purpose:** Display distribution of daily returns as histogram
- **Data source:** `algo_portfolio_snapshots` table (daily_return_pct column)
- **Current status:** Handler does not exist
- **Response format needed:**
  ```json
  {
    "statusCode": 200,
    "items": [
      {"bucket": "-5% to -2%", "count": 12, "pct": 8.5},
      {"bucket": "-2% to 0%", "count": 25, "pct": 17.8},
      ...
    ],
    "total": 141
  }
  ```

#### 1.2 GET /api/algo/trade-distribution  
- **Called by:** `PortfolioDashboard.jsx` line 182
- **Purpose:** Show distribution of trade outcomes by return buckets
- **Data source:** `algo_trades` (pnl_total, status) joined with entry/exit analysis
- **Current status:** Handler does not exist
- **Response format needed:**
  ```json
  {
    "statusCode": 200,
    "items": [
      {"bucket": "-20% to -10%", "count": 2, "pct": 3.2},
      {"bucket": "-10% to 0%", "count": 8, "pct": 12.9},
      ...
    ],
    "win_count": 45,
    "loss_count": 28,
    "total": 73
  }
  ```

#### 1.3 GET /api/algo/holding-period-distribution
- **Called by:** `PortfolioDashboard.jsx` line 186
- **Purpose:** Show distribution of days positions held
- **Data source:** `algo_trades` (entry_date, exit_date) or positions with age calculation
- **Current status:** Handler does not exist
- **Response format needed:**
  ```json
  {
    "statusCode": 200,
    "items": [
      {"days": "1-3", "count": 15, "pct": 20.5},
      {"days": "4-7", "count": 22, "pct": 30.1},
      ...
    ],
    "avg_holding_days": 12.3,
    "total": 73
  }
  ```

#### 1.4 GET /api/algo/stage-distribution
- **Called by:** `PortfolioDashboard.jsx` line 190
- **Purpose:** Show distribution of chart stages at entry
- **Data source:** `algo_signals` table (entry_stage column) or computed from trades
- **Current status:** Handler does not exist
- **Response format needed:**
  ```json
  {
    "statusCode": 200,
    "items": [
      {"stage": "Stage 2", "count": 28, "pct": 38.4},
      {"stage": "Stage 1", "count": 18, "pct": 24.7},
      ...
    ],
    "total": 73
  }
  ```

**Action Items:**
- [ ] Add route handlers for all 4 endpoints in `lambda/api/routes/algo.py`
- [ ] Implement SQL queries to compute histograms
- [ ] Add input validation (limit result size, date ranges)
- [ ] Test response format matches frontend expectations
- [ ] Add error handling for missing/incomplete data

---

### Issue #2: Test Files Still in Production Source
**Severity:** HIGH - Blocks CI/CD and violates project standards  

**Files to delete:**
1. `lambda/api/routes/test_critical_endpoints.py` (52 lines) — Incomplete test stubs
2. `lambda/api/routes/test_endpoints_verification.py` (65+ lines) — Placeholder tests  
3. `lambda/api/routes/TEST_ERROR_HANDLING.md` (6.3 KB) — Documentation that belongs elsewhere

**Why they're problems:**
- These are not real tests, just empty stubs
- Will be included in Lambda layer deployment
- Violate project structure (tests belong in `tests/`, not `lambda/api/routes/`)
- Confuse maintainers ("is this actually tested?")
- Block pre-commit hooks if configured to reject test files outside `tests/`

**Action Items:**
- [ ] Delete all 3 files immediately
- [ ] Verify no other imports reference these files
- [ ] If any real test content exists, move to `tests/integration/` or `tests/e2e/`

---

## HIGH-PRIORITY ISSUES

### Issue #3: Data Source Dependencies Not Documented or Validated
**Severity:** HIGH - Causes silent data gaps without errors  

**Problem:** Dashboard endpoints depend on data from loaders, but:
1. No validation that prerequisite data exists before returning response
2. No documentation of which loaders feed which endpoints
3. Endpoints return empty arrays with no warning

**Examples:**
- `/api/algo/daily-return-histogram` requires `algo_portfolio_snapshots` with recent daily_return_pct values
- `/api/algo/stage-distribution` requires `algo_signals` populated with entry_stage values
- `/api/algo/trades` requires both `algo_trades` AND reconciliation from Alpaca

**Current behavior:** If prerequisite data missing, endpoint returns `{"statusCode": 200, "items": []}` — looks successful but is actually incomplete

**Action Items:**
- [ ] Add data freshness checks using existing `check_data_freshness()` function
- [ ] Return `statusCode: 202` (Accepted, partial data) if data is stale
- [ ] Include metadata fields: `_is_stale`, `_data_age_hours`, `_warning`
- [ ] Document data dependencies in code comments
- [ ] Add CloudWatch metrics: `dashboard_endpoint_missing_data`

---

### Issue #4: Loaders Don't Populate All Required Columns
**Severity:** HIGH - Causes endpoint failures and data gaps  

**Specific issues:**

#### 4.1 `algo_signals` table missing `entry_stage` column
- **Required by:** `stage-distribution` endpoint
- **Current status:** Column may not exist or not populated
- **Fix needed:** Add column, modify `load_algo_signals.py` to capture entry_stage from trade entry

#### 4.2 `algo_portfolio_snapshots` missing distribution metrics
- **Required by:** `daily-return-histogram` needs daily_return_pct populated
- **Current status:** May only compute on-demand, not stored
- **Fix needed:** Ensure daily snapshots populate all required fields

#### 4.3 `algo_trades` missing entry_stage tracking
- **Required by:** `trade-distribution` and `stage-distribution` endpoints
- **Current status:** Trades don't capture chart stage at entry
- **Fix needed:** Modify trade entry logic to save entry_stage from signal

**Action Items:**
- [ ] Audit schema: `SELECT column_name FROM information_schema.columns WHERE table_name='algo_signals'`
- [ ] Add missing columns to schema with migration
- [ ] Modify loaders to populate all required fields
- [ ] Add pre-load validation: count NULL values in critical columns

---

## MEDIUM-PRIORITY ISSUES

### Issue #5: Response Format Inconsistency
**Severity:** MEDIUM - Causes client parsing errors and tech debt  

**Problem:** Different endpoints return different JSON structures:
- Some endpoints: `{ statusCode: 200, items: [...], total, limit, offset }` (list format)
- Some endpoints: `{ statusCode: 200, data: {...} }` (data format)
- Some endpoints: `{ statusCode: 200, ...fields directly }` (flat format)

**Examples from codebase:**
- `/api/algo/positions` returns flat format
- `/api/algo/trades` returns list format
- `/api/algo/performance` returns data format

**Frontend workaround:** `extractArray()` helper (line 94-98 in PortfolioDashboard.jsx) masks the inconsistency by trying multiple extraction patterns

**Action Items:**
- [ ] Standardize all `/api/algo/*` endpoints to consistent format
- [ ] Recommendation: Use list format for all: `{ statusCode, items, total, limit, offset, _is_stale, _cached_at }`
- [ ] Update existing endpoints to match new standard
- [ ] Document format in comments at top of `lambda/api/routes/algo.py`
- [ ] Add response format validation tests

---

### Issue #6: Missing Input Validation on New Endpoints
**Severity:** MEDIUM - Opens DoS and resource exhaustion vectors  

**Validation gaps in new endpoints:**
1. `/api/algo/daily-return-histogram` — no date range validation (could request years of data)
2. `/api/algo/trade-distribution` — no result size limits (could try to fetch 1M rows)
3. `/api/algo/holding-period-distribution` — no aggregation size limits
4. `/api/algo/stage-distribution` — no filtering on stage type

**Existing validation patterns to follow:**
- `safe_limit(value, max_val=1000, default=100)` — cap list sizes
- `safe_days(value, max_val=365, default=180)` — cap date ranges
- `safe_offset(value)` — validate pagination offset
- Rate limiting via `check_admin_rate_limit()`

**Action Items:**
- [ ] Add `safe_limit()` calls: all histogram endpoints max_val=1000 (buckets)
- [ ] Add `safe_days()` calls for temporal endpoints: max_val=365, default=90
- [ ] Add rate limiting from `ADMIN_RATE_LIMITS` dict
- [ ] Return HTTP 400 with descriptive error for invalid inputs
- [ ] Document validation assumptions

---

### Issue #7: Performance: No Query Optimization for Distribution Endpoints
**Severity:** MEDIUM - Will cause slow dashboard loads and RDS CPU spikes  

**Risk analysis:**

#### 7.1 Daily Return Histogram
- Query: Scan all `algo_portfolio_snapshots` rows (10,000+), group by return bucket
- Without optimization: O(n) full table scan on every request
- Solution: Pre-compute in `compute_performance_metrics.py` nightly, store in dedicated table

#### 7.2 Trade Distribution
- Query: For each trade in `algo_trades`, compute return %, group by bucket
- Risk: Expensive calculation repeated on every dashboard refresh
- Solution: Add computed column or pre-compute nightly

#### 7.3 Stage Distribution
- Query: Aggregate `algo_signals` by entry_stage
- Issue: May scan large signals table without proper indexing
- Solution: Add index on `(entry_stage)`, limit to last 90 days

**Current state:** No pre-computation, no caching, no query optimization

**Action Items:**
- [ ] Create pre-computed tables: `dashboard_daily_return_histogram`, `dashboard_trade_distribution`, etc.
- [ ] Modify `loaders/compute_performance_metrics.py` to populate these tables
- [ ] Add database indexes: `CREATE INDEX idx_signals_entry_stage ON algo_signals(entry_stage)`
- [ ] Cache results with 1-hour TTL in endpoint handlers
- [ ] Limit aggregations to last 90 days of data
- [ ] Add CloudWatch metric: `dashboard_histogram_query_duration_ms`

---

### Issue #8: Data Integrity: Silent Fallbacks After Cleanup
**Severity:** MEDIUM - Hidden data quality issues  

**Background:** `ISSUES_IDENTIFIED.md` documents fallback cleanup from critical paths, but gaps remain

**Remaining problems:**

#### 8.1 Sentiment data in `_get_sentiment()` endpoint
- May still have `or 0` fallbacks for missing sentiment scores
- Should validate sentiment columns exist + have recent data

#### 8.2 Economic calendar data
- Returns sparse data if economic events missing from loaders
- No validation that calendar data is actually populated

#### 8.3 Grade distribution
- Marked as "HIGH-SEVERITY ISSUE: not pre-calculated" in `load_grade_distribution_daily.py` comment
- Endpoint returns empty results with no warning

**Action Items:**
- [ ] Grep for remaining fallback patterns: `or 0`, `or False`, `or []`, `or None`
- [ ] Add explicit `_is_fallback_data: true` flag to responses using fallbacks
- [ ] Log warnings when using fallback (not silently)
- [ ] Add metrics: `dashboard_endpoint_using_fallback` counter

---

## ARCHITECTURAL ISSUES

### Issue #9: No Monitoring for Dashboard Endpoints
**Severity:** MEDIUM - Operations team can't detect failures until users complain  

**Missing visibility:**
1. No CloudWatch metrics when endpoints return empty/stale data
2. No alarms when histogram computation times out
3. No metrics on data freshness per endpoint
4. Dashboard shows no indication of data staleness to users

**What should be tracked:**
- Endpoint latency: `dashboard_endpoint_latency_ms` (target: <500ms)
- Data freshness: `dashboard_data_freshness_hours` (target: <24h)
- Error rates: `dashboard_endpoint_errors` (target: <1%)
- Fallback usage: `dashboard_using_fallback_data` (should be rare)

**Action Items:**
- [ ] Wrap new endpoint handlers with `TimeBlock()` context manager for metrics
- [ ] Add response metadata fields: `_latency_ms`, `_cached_at`, `_data_age_hours`
- [ ] Create CloudWatch dashboard: `algo-dashboard-health`
- [ ] Set alarms: endpoint >1s, data >24h old, error rate >5%
- [ ] Frontend displays freshness indicator (green/yellow/red badge)

---

### Issue #10: Frontend Component Structure Too Monolithic
**Severity:** MEDIUM - Tech debt accumulating, hard to maintain  

**Problems in `PortfolioDashboard.jsx` (>500 lines):**

1. **Over-fetching of endpoints** (lines 150-193)
   - Fetches 11 endpoints sequentially
   - Each endpoint blocks others from starting
   - Could batch related queries

2. **Error state handling scattered**
   - Each endpoint has separate `error` variable
   - No unified error display strategy
   - Difficult to show partial success

3. **Skeleton loading complex** (line 197)
   - `isPrimaryLoading` = OR of 11 boolean flags
   - If one endpoint is slow, entire skeleton shows
   - Should implement progressive loading

4. **Component is too large**
   - Single file handles too many concerns
   - Hard to test individual sections
   - Performance: all data must load before rendering

**Required refactoring:**
- Break into sub-components: PerformanceMetrics, PositionHealth, EquityCurveChart, DistributionCharts
- Create bulk `/api/algo/dashboard` endpoint for top 5 critical queries
- Implement progressive rendering (show KPIs while charts load)
- Add request deduplication (don't refetch if data <30s old)

**Action Items:**
- [ ] Create sub-components in `webapp/frontend/src/components/dashboard/`
- [ ] Implement bulk endpoint: `/api/algo/dashboard` combining status + positions + performance + markets
- [ ] Add progressive loading: render KPIs immediately, show skeleton for charts
- [ ] Reduce main component to <300 lines

---

### Issue #11: Missing Database Columns for Distribution Endpoints
**Severity:** MEDIUM - Silently blocks calculations  

**Schema gaps:**

| Table | Column | Status | Impact |
|-------|--------|--------|--------|
| `algo_signals` | `entry_stage` | Missing | stage-distribution endpoint can't function |
| `algo_trades` | `entry_stage` | Missing | Need to look up from signal history |
| `algo_portfolio_snapshots` | `daily_return_bucket` | Missing | Histogram must compute on-the-fly |
| `algo_signals` | `win_loss_bucket` | Missing | Trade-distribution must calculate per trade |

**Action Items:**
- [ ] Add column to schema: `ALTER TABLE algo_signals ADD COLUMN entry_stage VARCHAR(20)`
- [ ] Backfill from trade history: `UPDATE algo_signals SET entry_stage='Stage 2' WHERE ...`
- [ ] Add index: `CREATE INDEX idx_signals_stage ON algo_signals(entry_stage)`
- [ ] Document schema additions in migration file
- [ ] Update loaders to populate on future trades

---

## PERFORMANCE & MONITORING

### Issue #12: No Performance Baseline Documentation
**Severity:** MEDIUM - Can't detect regressions, no SLA visibility  

**Missing documentation:**
- No documented latency SLAs for dashboard endpoints
- No baseline performance metrics for existing endpoints
- No synthetic monitoring tests
- No performance regression detection

**Recommended SLAs:**
- `/api/algo/status` — <100ms (critical path)
- `/api/algo/positions` — <200ms (critical path)
- `/api/algo/performance` — <300ms (critical path)
- `/api/algo/daily-return-histogram` — <500ms (can cache)
- `/api/algo/trades` — <300ms with limit=200

**Action Items:**
- [ ] Run baseline performance tests for all endpoints
- [ ] Document SLAs in `steering/algo.md`
- [ ] Set CloudWatch alarms: endpoint latency >2x SLA
- [ ] Add synthetic test: monthly performance regression test
- [ ] Add dashboard: `algo-api-performance` showing latency trends

---

### Issue #13: No Data Freshness Indicators for Users
**Severity:** MEDIUM - Users don't know if displayed data is stale  

**Current state:** Dashboard displays data without indicating age

**Example problem:** If loaders fail at 2:30 AM, users at 9:30 AM don't know they're seeing day-old data

**Required improvements:**
- [ ] Every endpoint response includes `_cached_at: "2026-06-13T14:32:00Z"`
- [ ] Frontend calculates data age: `Date.now() - cached_at`
- [ ] Display indicator: Green (fresh <1h), Yellow (stale 1-24h), Red (very stale >24h)
- [ ] Show tooltip: "Data as of 2:15 PM ET"
- [ ] Alert if data >24h old: "Dashboard showing day-old data due to data loading issue"

**Action Items:**
- [ ] Add timestamp to all endpoint responses
- [ ] Create `<DataFreshnessIndicator />` component
- [ ] Add visual badge to dashboard header
- [ ] Show warning modal if data >24h old

---

## SUMMARY TABLE: All Issues by Priority

| # | Issue | Files | Effort | Risk | Blocker |
|---|-------|-------|--------|------|---------|
| 1 | Missing endpoints (4) | `lambda/api/routes/algo.py` | 4-5h | Low | **YES** |
| 2 | Delete test files | Multiple | 0.5h | Low | **YES** |
| 3 | Data dependencies | Multiple | 3-4h | Med | **YES** |
| 4 | Column populations | Loaders + schema | 2-3h | Low | **YES** |
| 5 | Response format | `lambda/api/routes/algo.py` | 2-3h | Med | No |
| 6 | Input validation | `lambda/api/routes/algo.py` | 2-3h | Low | No |
| 7 | Query optimization | DB + loaders | 4-5h | Med | No |
| 8 | Silent fallbacks | Multiple | 2-3h | Low | No |
| 9 | Monitoring | CloudWatch + code | 2-3h | Low | No |
| 10 | Frontend refactor | `webapp/frontend/src/` | 6-8h | Med | No |
| 11 | DB schema | Migration + loaders | 2-3h | Low | No |
| 12 | Performance baseline | Docs + testing | 2h | Low | No |
| 13 | Data freshness UI | Frontend + API | 2-3h | Low | No |

**Critical Path (must complete for market open):** Issues #1-4 = ~10 hours  
**Full Stabilization:** All issues = ~30-35 hours

---

## RECOMMENDED RESOLUTION SEQUENCE

### Phase 1: Unblock Dashboard (3-4 hours) — BEFORE MARKET OPEN
1. Delete test files (Issue #2)
2. Implement 4 missing endpoints (Issue #1)
3. Verify schema has required columns (Issue #4)
4. Manual test in browser
5. **Verification:** Dashboard loads without 404 errors

### Phase 2: Data Integrity (3-4 hours) — TODAY
1. Add data dependency validation (Issue #3)
2. Verify all loaders populate required columns (Issue #4)
3. Test with real data end-to-end
4. **Verification:** All dashboard metrics show correct values

### Phase 3: Performance & Observability (4-5 hours) — THIS WEEK
1. Add input validation (Issue #6)
2. Optimize queries (Issue #7)
3. Add CloudWatch monitoring (Issue #9)
4. Document SLAs (Issue #12)

### Phase 4: Tech Debt & Refactoring (6-8 hours) — THIS SPRINT
1. Fix response format inconsistency (Issue #5)
2. Refactor frontend component (Issue #10)
3. Add data freshness UI (Issue #13)
4. Clean up fallback usage (Issue #8)

---

## Files Requiring Changes

**Critical (must change):**
- `lambda/api/routes/algo.py` — add 4 endpoint handlers
- `lambda/db-init/schema.sql` — add missing columns
- `loaders/load_algo_signals.py` — populate entry_stage
- `loaders/load_algo_trades.py` — capture entry_stage at trade entry
- Delete: `lambda/api/routes/test_*.py` and `TEST_ERROR_HANDLING.md`

**High Priority (should change):**
- `loaders/compute_performance_metrics.py` — pre-compute histograms
- `lambda/api/routes/algo.py` — add data freshness checks
- `webapp/frontend/src/pages/PortfolioDashboard.jsx` — progressive loading

**Medium Priority (improve):**
- `steering/algo.md` — document SLAs and data dependencies
- `lambda/api/routes/utils.py` — standardize response formats
- Multiple loaders — add column population validation

---

## Testing Checklist

Before market open:
- [ ] All 4 missing endpoints return HTTP 200 (not 404)
- [ ] Dashboard loads in browser without console errors
- [ ] Histogram endpoints return valid JSON with data
- [ ] Trade distribution shows correct win/loss split
- [ ] Holding period distribution shows reasonable values
- [ ] Stage distribution matches actual trade entry stages
- [ ] No test files present in `lambda/api/routes/`
- [ ] All data appears in correct decimal precision
- [ ] No "undefined" or "NaN" values in UI

---

## Success Criteria

✅ Dashboard fully renders at market open without 404 errors  
✅ All data displays with correct values (no placeholder/fallback data)  
✅ No console errors or warnings in browser DevTools  
✅ Data freshness visible to user (shows last update time)  
✅ CloudWatch metrics show healthy endpoint latencies  
✅ Test files removed from codebase  
✅ Schema audit confirms all required columns exist  
✅ Loaders populate all required fields end-to-end  

---

**Prepared:** 2026-06-13  
**Target Market Open:** 2026-06-13 09:30 AM ET  
**Status:** Requires immediate action on critical path items
