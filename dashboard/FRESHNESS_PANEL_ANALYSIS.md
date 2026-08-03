# Data Freshness Panel - Comprehensive Analysis & Enhancement Recommendations

**Goal**: Expand the Python dashboard's data freshness panel to surface all tracked loader and data metrics for complete operational visibility.

---

## Current Status: What's Already Tracked & Displayed

### ✅ Currently Displayed in Python Dashboard

**1. Basic Table Health**
- Table name, age (hours/days), row count, status badge
- Ready-to-trade indicator (global, not per-table)
- Critical stale table highlights

**2. Loader Infrastructure**
- Loader error messages with table name
- Never-started loaders (status = NOT_STARTED)
- In-progress loaders with completion % and symbol load progress
- Stale detail: age vs. own threshold (per-table)
- Repeated failures: consecutive_failures count and last success time

**3. Data Quality Metrics** (NEW - already implemented)
- NULL ratios in critical columns (with threshold: >5% flags as warning)
- Duplicate rows detected
- Value constraint violations (negative prices, RSI out of range, VIX > 150, etc.)

**4. Coverage Completeness** (NEW - already implemented)
- Symbol coverage % and gap analysis
- Missing symbol list (top gaps prioritized by market cap)
- Coverage status classification (complete/partial/sparse)

**5. Failure Patterns** (NEW - already implemented via data_loader_status_history)
- Failure rate over 30 days
- Failure pattern detection (time-of-day clustering, random, etc.)
- MTTR (Mean Time To Recovery) in hours
- Recovery trend (improving/stable/degrading)
- Last 5 runs visual summary

**6. API Diagnostics** (NEW - already implemented)
- Rate limiting details (quota used/remaining, reset time)
- Authentication failures (401)
- Service unavailable (503)
- Retry strategy and exponential backoff info

**7. Table Inventory**
- Untracked tables (exist in DB, no monitoring)
- Missing tables (tracked but dropped from schema)

---

## ❌ Available But NOT Currently Displayed

### Database Fields Available for Display
All these fields exist in `data_loader_status` table but aren't shown in the panel:

1. **Loader Performance Metrics**
   - `execution_duration_sec` — How long the loader took to complete
   - `symbols_per_second` — Calculated throughput (symbols_loaded / execution_duration_sec)
   - `http_status_code` — HTTP response status (200, 429, 401, 503, etc.)
   - `rate_limit_quota` — Rate limit status string (e.g., "98/100 calls used")
   - `retry_count` — Number of retries performed on that run
   - `completion_pct` — Percentage complete during execution (0-100)

2. **Data Freshness Precision**
   - `last_success_at` — Last successful completion (distinct from last_execution)
   - `execution_started` — When loader started (to detect hangs)
   - `execution_completed` — When loader finished
   - Execution duration trend (is it getting slower?)

3. **Symbol Load Progress**
   - `symbols_loaded` — Actual count of symbols loaded
   - `symbol_count` — Expected/target symbol count
   - Completion % during mid-run (currently shown for in-progress only, not for completed)

### React Dashboard Features (Not in Python)
From `webapp/frontend/src/components/`:

1. **SystemHealthIndicator**
   - Degraded mode status (position sizes at 50%)
   - Signal freshness status (OK/STALE)
   - Signal age in hours (more precise than days)

2. **DataAgeBadge**
   - Precise data age in days (0 = today, 1 = yesterday, etc.)
   - "No Data" indicator
   - Visual warning when age > 3 days

3. **LoaderHealthPanel**
   - Categorical grouping: CRITICAL, ERROR, STALE, EMPTY, HEALTHY
   - Summary badges showing counts per category
   - Collapsed/expanded view for healthy tables
   - Consecutive failures count inline with table status

---

## 📊 Recommended Enhancements (Priority Order)

### TIER 1: High-Impact, Low-Risk (Easy Wins)

#### 1.1 Execution Duration & Throughput Display
**Impact**: Detect performance degradation, identify slow loaders
```
Example display:
  price_daily: ✓ OK [2h ago] [2.8M rows] [35 sec / 95 sym/sec]
  technical_daily: ~ STALE [26h ago] [1.2M rows] [timeout after 180 sec]
```
**Where**: In the freshness table, add columns after row count
**Data source**: `execution_duration_sec`, `symbols_per_second`
**Effort**: Add 2 columns to table display

#### 1.2 Signal Freshness & Degraded Mode Status  
**Impact**: Alerts user when system is running at reduced capacity
```
Example display:
  [bold yellow]⚠ SYSTEM STATUS:[/]
  [dim]├─ Signals: STALE (18 hours old)[/]
  [dim]├─ Degraded mode: [red]ACTIVE[/] - position sizes at 50%[/]
  [dim]└─ Action: Wait for fresh data, or reduce position sizes manually[/]
```
**Where**: At top of freshness panel, before the table
**Data source**: Call `/api/health` endpoint (already done in React)
**Effort**: One new section with 3-4 status lines

#### 1.3 Data Age Precision (Days Instead of Hours)
**Impact**: Operators see "today", "yesterday", "2 days ago" vs. vague "old"
```
Example: "1d ago" instead of "23h ago" for Monday data checked Tuesday
```
**Where**: Age column, existing table
**Data source**: Slight formatting change to `fmt_age()`
**Effort**: Change 1 formatting function

#### 1.4 Last Success vs. Last Execution  
**Impact**: Distinguish "loader never succeeded" from "succeeded once, failed 5x in a row"
```
Example display:
  failed_loader_xyz: ✗ FAILED [never succeeded]
  degraded_loader_abc: ✗ FAILED [6 failures, last success 3d ago]
```
**Where**: In the "Repeated Failures" section
**Data source**: `last_success_at` already available
**Effort**: Enhance existing repeated failures section

---

### TIER 2: Medium-Impact, Medium-Effort

#### 2.1 HTTP Status Code Breakdown
**Impact**: Quickly identify why a loader failed (auth vs. rate limit vs. service down)
```
Example display:
  market_data: ~ STALE [18h ago]
    └─ Failure reason: HTTP 429 (Rate Limited)
    └─ Quota used: 98/100 calls
    └─ Reset time: 2026-07-28 09:00 EST (18.5h remaining)
    └─ Retry strategy: Exponential backoff, next at 14:35
```
**Where**: Enhance existing API Diagnostics section
**Data source**: `http_status_code` already in DB
**Effort**: Parse status code and add conditional display

#### 2.2 Loader Throughput Trend
**Impact**: Detect if loaders are slowing down (data volume growth, infrastructure issues)
```
Example display:
  price_daily: [green]↗ [/] 95 sym/sec (up from avg 87 sym/sec)
  signal_data: [red]↘ [/] 12 sym/sec (down from avg 45 sym/sec - DEGRADING)
```
**Where**: Next to execution duration, optional mini-sparkline
**Data source**: Use `data_loader_status_history` rolling average
**Effort**: Query last 10 runs, calculate trend

#### 2.3 Execution Timeline (When Did This Start/Finish?)
**Impact**: Diagnose hangs (loader started but never completed)
```
Example display:
  In-Progress Loaders:
    ├─ price_daily: 45% complete [started 12:30, running 8m] ETA 2m
    └─ signal_data: 0% complete [started 14:15, running 45m] ⚠ TIMEOUT RISK
```
**Where**: New section in freshness panel
**Data source**: `execution_started`, `execution_completed`, duration trend
**Effort**: New display section

---

### TIER 3: Nice-to-Have Enhancements

#### 3.1 Coverage Completion Progress
**Impact**: Shows if a loader is loading data progressively (partial coverage acceptable)
```
Example: "price_daily: 2850/3000 symbols (95%)"
```
**Where**: Inline with in-progress loader info
**Data source**: `symbols_loaded` / `symbol_count`
**Effort**: Low

#### 3.2 Cross-Table Dependency Visualization
**Impact**: Show which phases depend on which freshness status
```
Example:
  ├─ price_daily [stale] → BLOCKS Phase 1
  ├─ technical_daily [ok] → Phase 2-3 ready
  └─ buy_sell_daily [ok] → Phase 7-8 ready
```
**Where**: Separate section at bottom
**Data source**: GOVERNANCE.md's phase dependency map
**Effort**: Medium (requires phase mapping)

#### 3.3 Loader SLA Compliance
**Impact**: Track if a loader meets its target cadence
```
Example: "price_daily: [green]✓[/] Within SLA (updates every 1h, last was 55m ago)"
```
**Where**: Summary line per loader
**Data source**: `stale_threshold_days` (proxy for SLA)
**Effort**: Low

---

## 🔧 Implementation Plan

### Phase 1 (This Week) - TIER 1 Quick Wins
1. Add `execution_duration_sec` and `symbols_per_second` columns to freshness table
2. Add system status section (signal freshness + degraded mode from `/api/health`)
3. Format age as day/hour hybrid ("1d ago", "23h ago")
4. Show `last_success_at` in repeated failures section

**Files to modify:**
- `dashboard/panels/health.py` → `_build_freshness_panel()`, `build_column_table()`
- `dashboard/panels/health.py` → New function `_build_system_status_section()`
- `dashboard/formatters.py` → Update `fmt_age()` or create `fmt_age_precise()`

### Phase 2 (Next Week) - TIER 2 Medium Enhancements
1. Expand API Diagnostics with HTTP status code details
2. Add loader throughput trend (up/down arrows)
3. Add execution timeline for in-progress loaders

**Files to modify:**
- `dashboard/panels/health.py` → Enhance `_build_api_diagnostics_section()`
- `dashboard/panels/health.py` → New function `_build_loader_timeline_section()`
- `dashboard/fetchers_market.py` → Query `data_loader_status_history` for trends

---

## 💾 Database Schema Check

Verify all needed columns exist (they should from migration 1164):
```sql
SELECT column_name FROM information_schema.columns
WHERE table_name = 'data_loader_status'
  AND column_name IN (
    'execution_duration_sec',
    'symbols_per_second',
    'http_status_code',
    'rate_limit_quota',
    'retry_count',
    'symbols_loaded',
    'symbol_count',
    'last_success_at',
    'consecutive_failures'
  );
```

All should return results. If not, apply migration 1164.

---

## 🧪 Testing Checklist

- [ ] Freshness table displays execution duration for 5+ loaders
- [ ] Throughput displays correctly (symbols/second)
- [ ] Signal freshness section appears when `/api/health` has freshness data
- [ ] Degraded mode status displays accurately
- [ ] Last success vs. last execution shows distinct info
- [ ] HTTP status codes (429, 401, 503) render with appropriate colors/messages
- [ ] In-progress loaders show execution timeline
- [ ] Table refreshes without lag when querying execution history

---

## 📈 Success Metrics

Once implemented, the operator should be able to:
1. ✅ See why a loader failed (auth? rate limit? timeout?) without reading logs
2. ✅ Spot performance degradation (slower throughput) at a glance
3. ✅ Know if system is in degraded mode (position sizes reduced)
4. ✅ Distinguish "never ran" from "ran once, broken for days"
5. ✅ Understand signal freshness status clearly
6. ✅ Get ETA on in-progress loaders without polling logs
