# Dashboard Architectural Issues — Additional Findings (Beyond Documented)

**Date:** 2026-06-12  
**Scope:** Python terminal dashboard (`tools/dashboard/dashboard.py`)  
**Architecture Goal:** Dashboard = pure display layer, all computation in API/database

---

## Summary

Found **6 additional architectural issues** not captured in previous audits. These involve:
- Business logic overrides in fetch functions
- Validation/filtering logic in display layer
- Metric computations in panel rendering
- Data aggregation in UI functions

**Impact:** Dashboard violates single-responsibility principle; contains computation that should happen in API/database layer.

---

## ISSUE GROUP A: Computation in Fetch Functions

### Issue A1: Win Rate Confidence Override (CONTRADICTS DOCUMENTED FIX)
**Severity:** 🔴 CRITICAL — Two sources of truth for confidence  
**Location:** `dashboard.py` lines 1847-1852 in `fetch_perf()`  
**Status:** ❌ **NOT FIXED** (documented as C1-4 FIXED, but code still present)

**Problem:**
```python
wr_confidence = perf.get("win_rate_confidence", "medium")  # API provides this
be_pct = (breakeven_trades / total_trades * 100) if total_trades > 0 else 0
if be_pct > 15:
    wr_confidence = "low"  # DASHBOARD OVERRIDES API VALUE
elif be_pct > 5:
    wr_confidence = "medium"
```

Dashboard receives `win_rate_confidence` from API but then **recalculates** it based on breakeven percentage:
- API says confidence = "high" 
- Dashboard checks: "if breakeven > 5%, set to medium"
- UI displays dashboard-computed value, not API value

**Architecture Violation:**
- API is single source of truth for confidence metrics
- Dashboard should display, not recalculate
- Breakeven → confidence mapping is business logic

**Recommendation:**
- Remove lines 1848-1852
- Trust API value: `wr_confidence = perf.get("win_rate_confidence", "medium")`
- If API needs to improve confidence calculation, fix it in API layer, not dashboard

**Related Issues:** C1-4 in CALCULATION_ARCHITECTURE_ISSUES.md

---

### Issue A2: SPY Price Change Calculation in Fetch Function
**Severity:** 🟠 HIGH — Computation in data layer  
**Location:** `dashboard.py` lines 1490-1508 in `fetch_market()`  
**Pattern:** Fallback calculation when pre-computed missing

**Problem:**
```python
# Fallback: calculate SPY change if not in database
if spy_chg is None and len(spy_rows) >= 2:
    close0 = spy_rows[0].get("close")
    close1 = spy_rows[1].get("close")
    if close0 is not None and close1 is not None:
        cur_spy  = safe_float(close0)
        prev_spy = safe_float(close1)
        if cur_spy is not None and prev_spy is not None:
            if spy_v is None: spy_v = cur_spy
            if prev_spy > 0: spy_chg = round((cur_spy - prev_spy) / prev_spy * 100, 2)
```

Dashboard is calculating SPY percentage change from price_daily raw data:
- Gets two rows from `price_daily` table
- Computes: `(cur - prev) / prev * 100`
- This is **pre-computation work that should live in database or API**

**Architecture Violation:**
- Calculation (`(price0 - price1) / price1 * 100`) belongs in API or view
- Dashboard should receive pre-computed `spy_pct_change` field
- "Fallback" pattern suggests this is hiding missing pre-computed data

**Recommendation:**
- Create database view or API endpoint that returns pre-computed SPY change
- Dashboard receives `spy_change_pct` field, not raw prices
- Remove the fallback calculation

**Related:** Category C2 (Data Filtering & Transformation) in CALCULATION_ARCHITECTURE_ISSUES.md

---

## ISSUE GROUP B: Validation/Filtering Logic in Fetch Functions

### Issue B1: Signal Quality Threshold Validation
**Severity:** 🟡 MEDIUM — Business rule validation in display layer  
**Location:** `dashboard.py` lines 2088-2096 in `fetch_signals()`

**Problem:**
```python
# Signal quality filtering validation
sq = safe_float(s.get("signal_quality_score"), 0)
eq = safe_float(s.get("entry_quality_score"), 0)
if max(sq, eq) < min_quality_threshold:
    signals_below_threshold += 1

if signals_below_threshold > 0:
    logger.warning(f"VALIDATION: Received {signals_below_threshold} signals below quality threshold {min_quality_threshold} from API — API should pre-filter these")

quality_filtered = 0  # Dashboard does not filter; count is 0
```

Dashboard is:
1. Validating signal quality against threshold (business logic)
2. Counting violations
3. Logging warnings when API returns data that should be filtered

**Architecture Violation:**
- API should pre-filter signals before returning them
- Dashboard should NOT check quality thresholds
- "API should pre-filter" comment in the warning itself acknowledges this is wrong

**Recommendation:**
- Move signal quality filtering to API layer (`/api/algo/signals` endpoint)
- Dashboard removes this validation
- If API returns a signal, dashboard displays it (trust API)

**Related:** C1-2 (Signal Quality Filtering) in CALCULATION_ARCHITECTURE_ISSUES.md

---

### Issue B2: Grade Threshold Loading in Signal Fetch
**Severity:** 🟡 MEDIUM — Configuration-dependent filtering in display layer  
**Location:** `dashboard.py` lines 2140-2147 in `fetch_signals()`

**Problem:**
```python
# M1 FIX: Use config threshold instead of hardcoded 80
grade_cfg = load_grade_thresholds(cfg)
thr_a = grade_cfg.get('a', 80)
top_a = q(c, f"""
    SELECT s.symbol, s.score
    FROM swing_trader_scores s
    WHERE s.date=%s
      AND s.score >= {thr_a}
    ORDER BY s.score DESC LIMIT 20""", (grades_date,)) if grades_date else []
```

Dashboard is:
1. Loading grade thresholds from config
2. Using them to filter database queries (score >= thr_a)
3. This is **filtering/querying logic in the dashboard**

**Architecture Violation:**
- Grade-based filtering should happen in API or database view
- API endpoint should return "top A-grade stocks"
- Dashboard should receive pre-filtered data

**Recommendation:**
- Create API endpoint: `/api/algo/signals/top-grades`
- API handles threshold loading and filtering
- Dashboard receives pre-filtered result

---

## ISSUE GROUP C: Metric Computation in Panel Functions

### Issue C1: Position Metrics Computed in Panel
**Severity:** 🔴 CRITICAL — Complex calculations in display function  
**Location:** `dashboard.py` lines 4048-4052 in `panel_positions()`

**Problem:**
```python
denom = (entry - stop) if (stop is not None and entry is not None and entry != stop) else None
rmul  = (price - entry) / denom if (denom is not None and entry is not None and price is not None) else None
dist  = (price - stop) / price * 100 if (stop is not None and price is not None and price > 0) else None
t1pct = (t1 - price) / price * 100 if (t1 is not None and price is not None and price > 0) else None
```

Panel rendering function is computing:
- **R-multiple:** `(price - entry) / (entry - stop)`
- **Distance to stop:** `(price - stop) / price * 100`
- **Distance to T1:** `(t1 - price) / price * 100`

These happen **every time the panel renders** (not memoized).

**Architecture Violation:**
- These are core position metrics, should come from API
- Panel should display pre-computed values
- Same computation logic appears in multiple panels → code duplication

**Recommendation:**
- API endpoint returns pre-computed: `r_multiple`, `distance_to_stop_pct`, `distance_to_t1_pct`
- Panel receives these fields
- Remove all calculation logic from panel function
- Total: ~20 lines of calculation removed from panel

---

### Issue C2: Sector Aggregation in Panel
**Severity:** 🟠 HIGH — Data aggregation in display layer  
**Location:** `dashboard.py` lines 4410-4445 in `panel_sector_compact()`

**Problem:**
```python
sd: dict = {}
for p in positions_list:
    sec = p.get("sector") or "[No Sector]"
    val = float(p.get("position_value")) if p.get("position_value") is not None else 0.0
    pnl_raw = p.get("unrealized_pnl_pct")
    pnl = safe_float(pnl_raw)
    if sec not in sd:
        sd[sec] = {"val": 0.0, "n": 0, "pnls": []}
    sd[sec]["val"] += val
    sd[sec]["n"]   += 1
    if pnl is not None:
        sd[sec]["pnls"].append(pnl)
sorted_secs = sorted(sd.items(), key=lambda x: -x[1]["val"])

def fmt_sec_item(sec, dv):
    pct     = dv["val"] / pv * 100 if pv else 0
    avg_pnl = sum(dv["pnls"]) / len(dv["pnls"]) if dv["pnls"] else 0
    # ... more computation
```

Panel is performing:
1. **Aggregation:** Grouping positions by sector
2. **Summation:** Summing position values per sector
3. **Averaging:** Computing average P&L per sector
4. **Sorting:** Sorting sectors by value
5. **Computation:** Computing percentage allocation, average P&L

**Architecture Violation:**
- This aggregation should come from API endpoint
- `/api/algo/portfolio/sectors` should return pre-aggregated sector data
- Panel should iterate over API response, not aggregate raw positions

**Computation Cost:**
- O(n) aggregation on every render cycle
- 6+ sectors × 20+ positions = ~120 operations per panel render
- With refresh every 30 seconds = 4 renders/min × 120 ops = 480 ops/min just for this panel

**Recommendation:**
- API endpoint: `/api/algo/portfolio/sectors`
  - Returns: `[{sector: "Tech", total_value: 50000, positions: 5, avg_pnl: 2.5}, ...]`
  - Pre-aggregated and sorted
- Panel receives aggregated data
- Remove 35 lines of aggregation logic from panel
- Reduce render time by ~10-20ms

---

### Issue C3: Recent Trades List Building
**Severity:** 🟡 MEDIUM — Data transformation in panel  
**Location:** `dashboard.py` lines 4297+ in `panel_recent_trades()`

**Note:** Requires detailed review of this function to identify specific computation patterns.

---

## ISSUE GROUP D: Fallback to Database Pattern

### Issue D1: Database Fallback in Fetch Functions
**Severity:** 🟠 HIGH — Wrong architecture for data sourcing  
**Location:** `dashboard.py` lines 1822-1918 in `fetch_perf()` (and other fetch_* functions)

**Problem:**
```python
def fetch_perf(c=None):
    """Fetch performance metrics from API with database fallback.
    Falls back to database if API unavailable.
    """
    try:
        api_resp = api_call("/api/algo/performance")
        if "_error" not in api_resp:
            # Use API
        else:
            # API failed, try database fallback
            logger.info("fetch_perf: API unavailable, falling back to database")
            # Query database directly
```

Dashboard is:
1. Attempting API call first
2. If API fails, directly querying database
3. This creates **two separate code paths** for the same data

**Architecture Violation:**
- Dashboard should NOT query database directly
- Dashboard should ONLY use API
- If API fails, dashboard should fail (not silently use degraded data)
- Database querying in dashboard violates separation of concerns

**Current State vs. Desired:**
```
Current (WRONG):
Dashboard → API (try) → DB (fallback)

Desired:
Dashboard → API (always)
API → DB (with retry/fallback logic)
```

**Recommendation:**
- Remove all database fallback code from dashboard
- Dashboard only calls API endpoints
- Move fallback logic to API/middleware layer
- If API is unavailable, dashboard shows error (not degraded data)

**Impact:**
- Simplifies dashboard code by ~100 lines
- Makes data sourcing explicit
- Centralizes fault handling in API layer

---

## Summary Table

| Issue | Category | Severity | Location | Type | Impact |
|-------|----------|----------|----------|------|--------|
| A1 | Computation | 🔴 CRIT | fetch_perf:1847-1852 | Confidence override | Two sources of truth |
| A2 | Computation | 🟠 HIGH | fetch_market:1490-1508 | SPY change calc | Hidden missing data |
| B1 | Validation | 🟡 MED | fetch_signals:2088-2096 | Quality threshold | Duplicate validation |
| B2 | Filtering | 🟡 MED | fetch_signals:2140-2147 | Grade threshold filtering | Query logic in dashboard |
| C1 | Computation | 🔴 CRIT | panel_positions:4048-4052 | Position metrics | Re-computed per render |
| C2 | Aggregation | 🟠 HIGH | panel_sector_compact:4410-4445 | Sector aggregation | O(n) on every render |
| D1 | Architecture | 🟠 HIGH | fetch_*:throughout | DB fallback pattern | Wrong data sourcing |

---

## Remediation Priority

### Phase 1: Critical Issues (blocks architecture goal)
- **A1:** Remove confidence override — API is source of truth
- **C1:** Move position metrics to API — panel displays only

### Phase 2: High Priority (performance + separation of concerns)
- **A2:** Pre-compute SPY change — remove fallback logic
- **C2:** Add sector aggregation endpoint — move computation to API
- **D1:** Remove database fallback — dashboard uses API only

### Phase 3: Medium Priority (data integrity)
- **B1:** Move signal quality filtering to API — dashboard validates format only
- **B2:** Add grades endpoint — API returns pre-filtered by grade

---

## Architecture Debt Assessment

**Total computation lines in dashboard:** ~200 lines
**Should be in API:** ~150 lines
**Fallback/retry logic:** ~50 lines
**Filtering/validation:** ~30 lines

**Removal saves:**
- **Code complexity:** 20% reduction in dashboard.py
- **Render time:** ~30-50ms per refresh cycle
- **Testing burden:** Move to API layer (centralized)
- **Operational clarity:** Single source of truth for each metric

---

## Next Steps

1. **Create API issues** for missing endpoints (sector aggregation, position metrics, SPY change)
2. **Refactor fetch_perf()** — remove confidence override
3. **Refactor panel_positions()** — receive pre-computed metrics
4. **Remove database fallback pattern** — centralize in API middleware
5. **Add integration tests** — verify dashboard only uses API, not DB

