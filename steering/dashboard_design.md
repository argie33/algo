# Dashboard Architecture Audit: Misaligned Calculations & Data Flow Issues

**Date:** 2026-06-11  
**Scope:** Frontend dashboard (PortfolioDashboard.jsx) vs. API endpoints (routes/algo.js)  
**Goal:** Identify places where we're calculating locally when data should be pre-computed in the backend

---

## Executive Summary

The dashboard has **8 major architectural inefficiencies** where expensive calculations happen in the frontend on every render, when they should either be:
1. **Pre-computed and stored** in database tables during daily loader runs
2. **Computed once** in the backend API and cached
3. **Computed on demand** in the backend (not on every page load)

This creates:
- **Poor performance**: Histograms bin 200 trades on every render
- **Inconsistency**: Frontend and backend calculate metrics differently
- **Maintenance burden**: Logic lives in two places (hard to debug, easy to diverge)

---

## Issue #1: Drawdown Calculation (DrawdownChart, line 808)

**Current flow:**
```
API: /api/algo/equity-curve
  └─ Returns: [{ snapshot_date, total_portfolio_value }]
     
Frontend: DrawdownChart (useMemo)
  └─ Calculates: peak = max(value), dd = (peak - value) / peak
  └─ Groups into 12 bins for rendering
```

**Problem:**
- Drawdown % is computed **client-side** on every render from raw equity curve
- 180+ snapshots × 4 hours = 720 computations per day (wasteful)
- No caching between page reloads

**Should be:**
```
Loader: load_algo_performance_daily.py
  └─ Computes: peak, current_drawdown_pct once per day
  
Database: algo_performance_daily (or new table)
  └─ Stores: drawdown_pct, max_drawdown_pct

API: /api/algo/equity-curve
  └─ Returns: [{ snapshot_date, total_portfolio_value, drawdown_pct }]
  
Frontend: EquityCurve
  └─ Just renders: (data) => <AreaChart data={data} />
```

**Effort:** Low. Migration: add `drawdown_pct` column. Loader: compute in SQL window function.

---

## Issue #2: Daily Return Histogram (DailyReturnHistogram, line 862)

**Current flow:**
```
API: /api/algo/equity-curve
  └─ Returns: [{ snapshot_date, daily_return_pct }]  ← Raw daily %'s

Frontend: DailyReturnHistogram (useMemo)
  └─ Bins into 12 buckets: lo/hi, step, buckets[idx]
  └─ Computes: mean, std of last 90 days
  └─ Renders BarChart
```

**Problem:**
- **Binning logic is frontend-only.** If we want to change bin count, update threshold, or show different periods, frontend must change.
- Statistics (mean, std) recalculated on every render
- Hard to test (lives in JSX, not a pure function)

**Should be:**
```
Option A: Pre-computed bins
  Database: daily_return_histogram (daily)
    └─ Stores: bucket_mid, bucket_count (computed once per day)
    
  API: /api/algo/daily-return-histogram
    └─ Returns: [{ bucket_mid, count }]
    
  Frontend: 
    └─ Just renders: (data) => <BarChart data={data} />

Option B: Backend-computed stats (lightweight)
  API: /api/algo/equity-curve?include_stats=true
    └─ Returns: [{ ... }], stats: { mean: X, std: Y }
    
  Frontend:
    └─ Renders with stats passed in
```

**Why it matters:**
- The stats (mean, σ) are **quantitative insights** that should be logged for audit trails
- Binning strategy should be **configurable by the user**, not hardcoded

**Effort:** Medium. Loader: compute bins + stats. Database: new table. API: new endpoint.

---

## Issue #3: Trade Outcome Distribution (TradeDistribution, line 937)

**Current flow:**
```
API: /api/algo/trades?limit=200
  └─ Returns: [{ exit_r_multiple, ... }]

Frontend: TradeDistribution (useMemo)
  └─ Bins by R-multiple: < -2R, -2 to -1R, ..., > 3R
  └─ Counts trades in each bin
  └─ Renders BarChart
```

**Problem:**
- Binning happens **locally every render**, even if trades haven't changed
- 200 trades × 4 hours = 800 binning operations per day
- No way to drill down: "which trades were in the 1-2R bucket?"

**Should be:**
```
Database: trade_outcome_distribution (daily)
  └─ Stores: r_bucket (enum or range), trade_count, example_trades
  
API: /api/algo/trade-distribution
  └─ Returns: [{ bucket: "0-1R", count: 23, examples: [symbol, ...] }]
  
Frontend:
  └─ Renders: (data) => <BarChart data={data} />
  
Bonus: Add drill-down route:
  API: /api/algo/trades?r_bucket=0-1R
    └─ Returns: all trades in that bucket (for analysis)
```

**Effort:** Medium. Loader: compute bins. Database: new table. API: new endpoint + filter.

---

## Issue #4: Holding Period Histogram (HoldingPeriodHistogram, line 997)

**Current flow:**
```
API: /api/algo/trades
  └─ Returns: [{ trade_duration_days, ... }]

Frontend: HoldingPeriodHistogram (useMemo)
  └─ Bins by days: 0-3d, 4-7d, ..., 60d+
  └─ Counts trades in each bin
  └─ Renders BarChart
```

**Problem:**
- Same as Issue #3: binning happens client-side every render
- Hard-coded bins (0-3, 4-7, etc.). What if we want 1-day bins?

**Should be:**
```
Database: holding_period_distribution (daily)
  └─ Stores: period_bucket, trade_count, avg_return_pct_in_bucket

API: /api/algo/holding-period-distribution
  └─ Returns: [{ bucket: "4-7d", count: 15, avg_return: 1.2 }]
  
Frontend:
  └─ Renders: (data) => <BarChart data={data} />
```

**Effort:** Low-Medium. Same pattern as Issue #3.

---

## Issue #5: R-Multiple Ladder (RLadderPanel, line 1047)

**Current flow:**
```
API: /api/algo/positions
  └─ Returns: [{
       symbol, avg_entry_price, current_price, stop_loss_price,
       target_1_price, target_2_price, target_3_price
     }]

Frontend: RLadderPanel (useMemo)
  └─ For each position:
       1. Compute lo = min(stop, entry, cur)
       2. Compute hi = max(t3, cur)
       3. For each price: pct = (price - lo) / (hi - lo) * 100
       4. Map stop, entry, targets to percentages
  └─ Renders: <Marker pct={pX} />
```

**Problem:**
- **Layout logic (percentages) is computed client-side.** If we want to change the scale (e.g., "show prices from stop to 2×T3"), frontend must change.
- 200 renders of this component = 200 × 5 positions = 1000 calculations
- No reusability: other pages can't use this ladder view

**Should be:**
```
API: /api/algo/positions
  └─ Returns: [{
       symbol, 
       avg_entry_price, current_price, stop_loss_price,
       target_1_price, target_2_price, target_3_price,
       
       // Add these:
       ladder_pct_stop, ladder_pct_entry, ladder_pct_current,
       ladder_pct_t1, ladder_pct_t2, ladder_pct_t3,
       ladder_scale_min, ladder_scale_max
     }]

Frontend:
  └─ Renders: <Marker pct={item.ladder_pct_current} />
```

**Effort:** Low. API change: compute percentages in SELECT. Frontend: less logic.

---

## Issue #6: Sector Concentration (SectorConcentration, line 1230)

**Current flow:**
```
API: /api/algo/positions
  └─ Returns: [{ sector, position_value }]

Frontend: SectorConcentration (useMemo)
  └─ Grouping: byS = {}; for (p of positions) byS[s] += value
  └─ Compute: totalValue, pct = (value / total) * 100
  └─ Render: BarChart(pct)
```

**Problem:**
- Grouping & percentage math happens **on every render**
- No reusability: hard to embed this logic in other components
- No way to query: "give me all positions in Technology"

**Should be:**
```
Database: sector_concentration (daily)
  └─ Stores: sector, position_count, total_value_pct, is_overweight

API: /api/algo/positions
  OR: /api/algo/sector-allocation (new)
  └─ Returns: [{
       sector, position_count, total_value_dollars, allocation_pct,
       is_overweight, overweight_threshold
     }]

Frontend:
  └─ Renders: (data) => <BarChart data={data} />
  
Bonus routes:
  /api/algo/sector/:name/positions
    └─ Get all positions in a sector (drill-down)
```

**Effort:** Low-Medium. API: grouping in SQL. Database: optional (could just return from positions query).

---

## Issue #7: Stage Phase Distribution (StagePhaseDonut, line 1287)

**Current flow:**
```
API: /api/algo/positions
  └─ Returns: [{ symbol, weinstein_stage, minervini_trend_score }]

Frontend: StagePhaseDonut (useMemo)
  └─ Labeling logic:
       if (stage === 1) return 'Stage 1 (base)'
       if (stage === 2) {
         if (score >= 8) return 'Late Stage-2'
         else if (score >= 6) return 'Mid Stage-2'
         else return 'Early Stage-2'
       }
  └─ Grouping: counts[k] = (counts[k] || 0) + 1
  └─ Render: PieChart(counts)
```

**Problem:**
- **Stage categorization logic (score >= 8 = "Late") is hardcoded in frontend**
- If we change the thresholds for "Early/Mid/Late", frontend must be redeployed
- No versioning: what if we want to compare "old categorization" vs "new"?

**Should be:**
```
Database: algo_config or new table
  └─ Stores: stage_2_early_min_score, stage_2_mid_min_score, stage_2_late_min_score

Loader: compute_stage_labels.py
  └─ For each position: determine label based on stage + score + config
  
API: /api/algo/positions
  └─ Returns: [{
       symbol,
       weinstein_stage,
       minervini_trend_score,
       stage_label,  // ← "Early Stage-2", "Late Stage-2", etc.
       stage_label_version  // ← for audit
     }]

Frontend:
  └─ Grouping: counts[p.stage_label] = (counts[...] || 0) + 1
  └─ Render: PieChart(counts)
```

**Effort:** Medium. API: add computed fields. Loader: compute labels.

---

## Issue #8: Risk Allocation Pie (RiskAllocationPie, line 1174)

**Current flow:**
```
API: /api/algo/positions
  └─ Returns: [{ symbol, open_risk_dollars }]

Frontend: RiskAllocationPie (useMemo)
  └─ Compute: totalRisk = sum(risk)
  └─ Filter: d.risk > 0
  └─ Sort: by risk desc
  └─ Compute: riskPct = (totalRisk / totalValue) * 100
  └─ Render: PieChart(risk)
```

**Problem:**
- **Filtering, sorting, and percentage math happen locally**
- No reusability: other components can't get "sorted positions by risk"
- No way to query: "what's the total open risk?"

**Should be:**
```
API: /api/algo/positions
  └─ Returns: [{
       symbol,
       open_risk_dollars,
       risk_pct_of_portfolio,
       risk_rank  // ← 1 = highest risk, N = lowest
     }]
  
Bonus: new endpoint
  /api/algo/risk-summary
    └─ Returns: {
         total_risk_dollars,
         total_risk_pct,
         highest_risk_position: "AAPL",
         num_positions_with_risk: 5
       }
```

**Effort:** Low. API: compute in SELECT.

---

## Summary Table: What's Client-Side vs. Backend

| Issue | Component | Current | Should Be | Effort |
|-------|-----------|---------|-----------|--------|
| #1 | Drawdown | Client-side calc | Pre-computed daily | Low |
| #2 | Daily Returns | Client-side bins | Pre-computed bins + stats | Medium |
| #3 | Trade Outcomes | Client-side bins | Pre-computed daily | Medium |
| #4 | Holding Periods | Client-side bins | Pre-computed daily | Low-Med |
| #5 | R-Ladder | Client-side percentages | API computes pct | Low |
| #6 | Sector Concentration | Client-side grouping | API groups in SQL | Low-Med |
| #7 | Stage Distribution | Client-side labels + grouping | Config-driven labels | Medium |
| #8 | Risk Allocation | Client-side sorting + pct | API sorts + computes | Low |

---

## Implementation Roadmap

### Phase 1 (Quick Wins, 1-2 days)
- **#5 R-Ladder**: Add 6 columns to positions response (pct_stop, pct_entry, etc.)
- **#8 Risk Allocation**: Add risk_pct, risk_rank to positions response
- **#6 Sector Concentration**: Return sector allocation from positions (group in API)

### Phase 2 (Data Layer, 2-3 days)
- **#1 Drawdown**: Add daily_drawdown_pct to equity curve response
- **#2 Daily Returns**: Compute histogram bins in loader, return via API
- **#3 Trade Outcomes**: Compute R-multiple buckets in loader

### Phase 3 (Configuration, 1-2 days)
- **#7 Stage Distribution**: Move hardcoded thresholds to algo_config
- **#4 Holding Periods**: Add bins table (if needed) or compute on demand

---

## Key Principles for Going Forward

1. **Calculations belong in the database or backend**, not the frontend
   - The frontend should be **dumb rendering**, not data transformation
   - Frontend computes = harder to test, debug, and audit

2. **Pre-computed metrics should be stored** if they're used in dashboards
   - Drawdown, histogram buckets, risk %, etc. should live in tables
   - Loaders compute once; API serves; frontend renders

3. **Dynamic/user-input calculations go in the backend**
   - If a user filters by date range or threshold, that's an API endpoint
   - Not computed on the client

4. **Configuration belongs in the database or .env, not the code**
   - Hardcoded thresholds (score >= 8 for "Late Stage-2") should be in algo_config
   - Allows A/B testing, quick iterations, and audit trails

---

## Open Questions

1. **Equity curve caching**: We fetch 180 snapshots every page load. Should we:
   - Paginate? (50 at a time)
   - Cache in localStorage?
   - Return 60/90 days by default, allow user to expand?

2. **Performance metrics freshness**: The perf endpoint uses `algo_performance_daily` with `report_date = CURRENT_DATE`. What if it's 2 PM and today's metrics aren't computed yet? Should we fall back to yesterday?

3. **Trade history**: We fetch 200 recent trades. Should we paginate this or lazy-load on scroll?

4. **Histogram granularity**: Daily bins (1 new histogram per day) or real-time? If daily, should we store multiple "versions" (12 bins, 20 bins, etc.)?

---

## Files Affected

**Frontend:**
- `webapp/frontend/src/pages/PortfolioDashboard.jsx` (all 8 issues)

**Backend:**
- `webapp/lambda/routes/algo.js` (endpoints: /positions, /trades, /performance, /equity-curve)
- `loaders/load_algo_performance_daily.py` (add drawdown, histogram metrics)
- Migrations: Add columns to `algo_performance_daily`, `algo_positions`, `algo_portfolio_snapshots`

**Configuration:**
- `algo_config` table: Add stage thresholds if not already there
