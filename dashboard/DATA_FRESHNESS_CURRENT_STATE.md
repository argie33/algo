# Data Freshness Panel - Current State & Capabilities

**Last Updated**: 2026-08-02 after TIER 1 Enhancements

---

## Overview

The Python dashboard's **DATA FRESHNESS - EXPANDED** panel is a comprehensive operational health display combining:
1. **Real-time loader status** (what's running/failed/stale)
2. **Data quality metrics** (NULLs, duplicates, constraint violations)
3. **Coverage analysis** (symbol/date/sector gaps)
4. **Failure pattern detection** (30-day trends, MTTR, recovery analysis)
5. **API diagnostics** (rate limits, auth failures, retry strategies)
6. **System health status** (signal freshness, degraded mode)

---

## Panel Sections (In Display Order)

### 1. **System Status** (NEW with TIER 1)
Shows critical system-wide conditions:
- **Signal Freshness**: OK / STALE with age in hours
- **Degraded Mode**: ACTIVE / INACTIVE with indicator
- **Action Items**: Clear guidance when system is compromised

**Example**:
```
System Status:
  Signal Freshness: STALE (18 hours old)
  Degraded Mode: ACTIVE - position sizes at 50%
```

---

### 2. **Trading Halt Status**
Shows if trading is halted globally and why:
```
→ Trading halted: Circuit breaker triggered (VIX > 40)
Expected data date: 2026-08-01
```

---

### 3. **Freshness Summary Line**
High-level overview:
```
Freshness: 28/30 fresh  2 stale  1 loader(s) with errors (3 total failures)  ✓ READY TO TRADE
```

Shows:
- Count of fresh vs. stale tables
- Loader error count (NEW: from error count propagation)
- Ready-to-trade status

---

### 4. **Main Freshness Table** (NEW columns in TIER 1)
Two-column layout with all tracked tables:

| Table | Age | Rows | Duration | Throughput | Status |
|-------|-----|------|----------|-----------|--------|
| price_daily | 2h ago | 2.8M | 35 sec | 95 sym/sec | ok |
| technical_daily | 2h ago | 1.2M | 42 sec | 87 sym/sec | ok |
| buy_sell_daily | STALE | 450K | timeout | -- | stale |
| market_health_daily | -- | -- | -- | -- | EMPTY |

**Columns**:
- **Table**: Data source name
- **Age**: Hours since last update (colored: green if fresh, yellow if aging, red if stale)
- **Rows**: Record count (formatted with commas)
- **Duration**: How long loader took (e.g., "35 sec", "--" if failed)
- **Throughput**: Symbols loaded per second (e.g., "95 sym/sec", "--" if failed/not applicable)
- **Status**: ok / stale / empty / error / timeout

---

### 5. **Loader Errors**
Detailed error messages for failed loaders:
```
Loader errors:
  [RED]market_health_daily:[/] [TIMEOUT] HTTP 429: Rate limited (98/100 calls used)
  [RED]economic_data:[/] [FAILED] Connection timeout after 30s
  ...and 3 more
```

Shows:
- Table name
- Error status (TIMEOUT vs FAILED)
- Actual error message from loader

---

### 6. **Never-Run Loaders**
Loaders that have never executed (distinct from "empty result"):
```
Never run:  earnings_calendar_sec  insider_transactions  commodity_correlations
```

---

### 7. **Loading Now**
In-progress loaders with progress:
```
Loading now:
  ⟳ price_daily: 45% (2850/3000 symbols)
  ⟳ technical_daily: 78% (2340/3000 symbols)
```

Shows:
- Table name
- Completion percentage (0-100%)
- Symbols loaded / total expected

---

### 8. **Stale Detail**
Why a table is stale (age vs. its own threshold):
```
Stale detail (age vs. own threshold):
  [YELLOW]market_health_daily:[/] 26d old, threshold 7d
  [YELLOW]economic_data:[/] 12d old, threshold 3d
```

---

### 9. **Repeated Failures**
Loaders with consecutive failures (2+):
```
Repeated failures:
  [RED]market_health_daily:[/] 6x in a row, last ok 3d ago
  [RED]economic_data:[/] 4x in a row, last ok 1d ago
  [RED]earnings_calendar_sec:[/] never succeeded
```

Shows:
- Number of consecutive failures
- When it last succeeded (or "never")

---

### 10. **Data Quality Issues** (NEW feature)
Quality problems that make data unusable:
```
Data Quality Issues:
  [RED]price_daily:[/] 3.2% NULL in close price (threshold 5%)
  [RED]technical_daily:[/] 12 duplicate rows detected
  [YELLOW]market_health_daily:[/] VIX value 156 (out of range 0-150)
```

Shows:
- NULL ratios in critical columns
- Duplicate row counts
- Constraint violations (out-of-range values)

---

### 11. **Coverage Gaps** (NEW feature)
Missing symbols, dates, or sectors:
```
Coverage Gaps:
  [RED]stock_symbols:[/] 2850/3000 symbols (95.0% coverage) (missing: NFLX, ROKU, DASH, LYFT, COIN)
  [YELLOW]sector_analysis:[/] 8/11 sectors (72.7% coverage) (missing: Energy, Materials)
```

Shows:
- Symbol/date/sector coverage percentage
- Missing items (prioritized by importance)
- Coverage status: complete (≥95%) / partial (80-95%) / sparse (<80%)

---

### 12. **Failure Patterns** (NEW feature - 30-day rolling analysis)
Systemic vs. transient failures:
```
Failure Patterns (30-day):
  [YELLOW]market_health_daily:[/] 20% failures
    Pattern: Monday mornings 3/3 times
    MTTR: 2.3 hours avg
    Last 5: ✗ ✗ ✓ ✗ ✓
    Trend: [YELLOW]stable[/]

  [RED]economic_data:[/] 50% failures
    Pattern: Random times
    MTTR: 5.2 hours avg
    Last 5: ✗ ✗ ✗ ✗ ✓
    Trend: [RED]degrading[/]
```

Shows:
- Failure rate over 30 days
- When failures occur (time-of-day patterns, random, etc.)
- MTTR (Mean Time To Recovery) in hours
- Last 5 runs summary (✓ success, ✗ failure)
- Recovery trend: improving / stable / degrading

**What This Tells You**:
- "Monday mornings" → Scheduler conflict (fix once, done)
- "Random times" → Transient network issues (wait/retry)
- "Degrading trend" → Investigate urgently (growing problem)
- "50% failures" → Systemic issue (not transient)

---

### 13. **API Diagnostics** (NEW feature)
API-specific failure modes:
```
API Diagnostics:
  [YELLOW]market_health_daily:[/] Rate Limited
    Quota: 98/100 calls used
    Action: Retry after quota reset (2026-08-03 09:00 EST)

  [RED]economic_data:[/] Auth Failed
    Quota: No auth token
    Action: Credentials need rotation

  [RED]commodity_data:[/] Service Down
    Quota: Service unavailable
    Action: Retry after 5 minutes
```

Shows:
- Specific API failure type (Rate Limit / Auth / Service Down)
- Quota status and reset time
- Recommended action

---

### 14. **Untracked Tables**
Tables in database with no monitoring:
```
Untracked tables (47):  earnings_data  insider_data  ...and 45 more
```

---

### 15. **Missing Tables**
Tables tracked in monitoring but dropped from schema:
```
Tracked but missing from DB (2):  old_config  legacy_data
```

---

## Data Tracked But Not Displayed (Yet)

The following metrics are recorded in the database and available via the API, but not yet displayed in the dashboard. These are candidates for TIER 2 & 3 enhancements:

### Available at Database Level
- `http_status_code` (200, 429, 401, 503, etc.)
- `rate_limit_quota` (full quota status string)
- `retry_count` (number of retries performed)
- `execution_started` / `execution_completed` (exact timestamps)
- `last_success_at` (distinct from last execution)

### Enhancement Opportunities
1. **HTTP Status Breakdown** (TIER 2)
   - Show exact HTTP status codes alongside error messages
   - Color-code by severity (401 auth / 429 rate limit / 503 service down)
   - Include reset times for rate limits

2. **Loader Throughput Trend** (TIER 2)
   - Visual indicators: ↗ improving, → stable, ↘ degrading
   - Compare to rolling average
   - Detect performance issues early

3. **Execution Timeline** (TIER 2)
   - Show started/running duration for in-progress loaders
   - ETA for completion
   - Warn on timeout risk

4. **Cross-Table Dependency Map** (TIER 3)
   - Show which phases depend on which data
   - Cascade impact: "if X stale → blocks Y, Z"
   - Visual dependency graph

5. **Loader SLA Compliance** (TIER 3)
   - Track adherence to configured update cadence
   - Historical compliance trend
   - Escalation alerts

---

## Performance Notes

**Query Timing**:
- Freshness table: ~50ms (single query)
- Data quality checks: ~0.35s per column on 8.7M rows (bounded sample)
- Coverage calculation: ~100ms per table
- Failure pattern analysis: ~10-50ms per table (index lookup)
- API diagnostics: <1ms per table (string parsing)

**Total Dashboard Load Time**: ~2-3 seconds (includes all 20+ fetchers)

**Caching**: Health data cached for 60 seconds (fetchers_config.py)

---

## Known Limitations

1. **Data Age Precision**: Shows hours/days, not minutes (adequate for daily cadence)
2. **Coverage Missing Thresholds**: Only shows missing items, not weighted by importance (future: market cap weighting)
3. **Failure Pattern Detection**: Requires 5+ runs to generate meaningful patterns (new loaders won't show pattern data)
4. **API Diagnostics**: Requires loaders to pass http_status explicitly (some legacy loaders may not)
5. **System Status Section**: Only displays if API response includes signal_freshness data (requires /api/health integration)

---

## How to Use This Panel

### Quick Scan (30 seconds)
1. Look at **Freshness Summary** line
   - All green? → Data is ready
   - Yellow/Red? → Something needs attention

2. Check **System Status** section
   - Signals stale? → Wait for fresh data
   - Degraded mode active? → Reduced position sizes

3. Scan **Loader Errors** section
   - Any errors? → Investigation needed

### Deep Dive (2 minutes)
1. Look at **Failure Patterns** for struggling loaders
   - Degrading trend? → Escalate
   - Monday-only failures? → Scheduler issue
   
2. Check **Data Quality Issues**
   - NULLs too high? → Data trust problem
   - Duplicates? → Data integrity issue

3. Review **Coverage Gaps**
   - Missing key symbols? → Risk calculation affected
   - Sparse coverage (<80%)? → Use with caution

### Troubleshooting Specific Table
1. Find table in **Freshness Table**
   - Duration/Throughput columns show performance
   
2. Check **Loader Errors** for specific error message

3. Look at **Repeated Failures** section
   - How many times failed? Systemic or transient?

4. Review **Failure Patterns** section
   - When does it fail? Pattern or random?

5. Check **API Diagnostics**
   - Rate limit? Auth issue? Service down?

---

## Success Metrics

The freshness panel is working well when it enables operators to:

✅ See what data is available without reading logs  
✅ Understand why a loader failed (specific reason, not just "STALE")  
✅ Know if the system is trading at full capacity or degraded  
✅ Spot performance trends (slower loading, recurring failures)  
✅ Distinguish transient failures from systemic issues  
✅ Understand impact of missing data on trading logic  

---

## Related Components

- **React Dashboard** (`webapp/`): LoaderHealthPanel, SystemHealthIndicator show same data in web UI
- **API** (`lambda/api/routes/`): `/api/algo/data-status` endpoint serves all freshness data
- **Loaders** (`loaders/`, `utils/loaders/`): Populate data_loader_status via LoaderStatusManager
- **Database** (`data_loader_status`, `data_loader_status_history` tables): Store all metrics

---

## References

- `FRESHNESS_PANEL_ANALYSIS.md` — Full enhancement recommendations (TIER 1, 2, 3)
- `IMPLEMENTATION_SUMMARY.md` — What was added in this release
- `dashboard/FRESHNESS_ENHANCEMENTS.md` — Original enhancement design doc
- `CLAUDE.md` → Memory system for load-bearing rules
