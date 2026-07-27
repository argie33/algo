# Data Freshness Panel Enhancements

## Overview

The freshness panel now goes beyond simple "recency" metrics to provide comprehensive **operational health** visibility. Four new metric categories help traders and operators distinguish between:
- Data that is fresh but invalid (NULL columns, duplicates)
- Complete universe of data vs. missing symbols/dates
- Transient failures (retry) vs. systemic issues (auth/rate-limit/service down)
- Performance degradation (throughput trending)

## Implementation

### 1. Data Quality Metrics
**File**: `dashboard/freshness_enhancements.py` → `enrich_health_item_with_data_quality()`

Detects and surfaces:
- **NULL ratios** in critical columns (threshold: >5% flags as warning)
- **Duplicate rows** using exact deduplication check
- **Value constraint violations** (negative prices, RSI out of range, VIX > 150, etc.)

**Display**: "price_daily: 3.2% NULL in close (threshold 5%)" in red error panel if critical

**Schema**: Added to `data_loader_status_history` table (migration 1164)

**Example usage in loaders**:
```python
# After loading complete, run validation
from dashboard.freshness_enhancements import enrich_health_item_with_data_quality
health_item = {...}  # from API
health_item = enrich_health_item_with_data_quality(health_item)
# Returns: health_item["data_quality_issues"] = [issue1, issue2]
#          health_item["quality_status"] = "ok" | "warning" | "error"
```

---

### 2. Coverage Completeness
**File**: `dashboard/freshness_enhancements.py` → `enrich_health_item_with_coverage()`

Detects gaps in expected data:
- **Symbol coverage %** (e.g., 2995/3000 = 99.8%)
- **Missing symbol list** (top 5 missing, prioritized by market cap)
- **Coverage status** classification (complete ≥95%, partial 80-95%, sparse <80%)

**Why it matters**: 
- All 3000 symbols loaded ✓ but top-10 holdings in that 0.2%? 
- Risk calc proceeds on incomplete universe
- Portfolio exposure misjudged

**Display**: 
```
├─ Coverage: 2995/3000 symbols (99.8%)
├─ Missing: NFLX, ROKU, DASH, LYFT, COIN
└─ Gap impact: top-10 tech holdings 40% uncovered
```

**Supported tables**: Any table with symbol column (price_daily, technical_data_daily, stock_scores, algo_positions, etc.)

---

### 3. Failure Pattern Analysis
**File**: `dashboard/freshness_enhancements.py` → `enrich_health_item_with_failure_pattern()`

Distinguishes transient failures from systemic issues:
- **Failure rate (30d)** — % of last 30 runs that failed
  - 10% = occasional blips (normal)
  - 50% = systemic problem (investigate)
- **Failure pattern** — time-of-day clustering
  - "Mondays 5am only" → scheduler conflict
  - "Random times" → transient network issues
- **MTTR (Mean Time To Recovery)** — avg hours from failure to next success
  - 2h MTTR = consistent issue, 5 hours to fix
  - 0.5h MTTR = quick auto-recovery
- **Recovery trend** — improving/stable/degrading over last 30 days
- **Last 5 runs** — visual summary (✓ ✗ ✓ ✓ ✓)

**Storage**: `data_loader_status_history` table (migration 1164)
- Auto-retains 100 most recent runs per table
- Older entries purged automatically
- Indexed for fast rolling-window queries

**Display**:
```
├─ Failure rate: 10% (3/30)
├─ MTTR: 2.3 hours avg
├─ Pattern: Monday mornings 3/3 times
├─ Last 5 runs: ✗ ✗ ✓ ✗ ✓
└─ Recommendation: Check scheduler conflict Monday 5-6am
```

---

### 4. API Diagnostics
**File**: `dashboard/freshness_enhancements.py` → `enrich_health_item_with_api_diagnostics()`

Surfaces API-specific failure modes from error messages:
- **Rate limiting** (HTTP 429)
  - Display: "Rate limit (98/100 calls used, reset 9am)"
  - Action: "Retry after quota reset"
- **Authentication failures** (HTTP 401)
  - Display: "Auth failed"
  - Action: "Credentials need rotation"
- **Service unavailable** (HTTP 503)
  - Display: "Service down"
  - Action: "Retry after 5 minutes"

**Schema**: Added to `data_loader_status` (migration 1164)
- `http_status_code` (INTEGER) — HTTP response status
- `rate_limit_quota` (TEXT) — quota status string for display
- `retry_count` (INTEGER) — number of retries performed
- `rate_limit_resets` (TIMESTAMP) — when quota resets

**Display**:
```
[⚡] API DIAGNOSTICS
├─ Last failure: 2026-07-27 14:35:22 EST
├─ Status: Rate limit (98/100 calls used)
├─ Next quota reset: 2026-07-28 09:00 EST (18.5 hours)
├─ Retry strategy: exponential backoff, next attempt 3:35pm
└─ Action: Can retry after reset or increase quota
```

---

## Panel Display Sections (In Order)

1. **Freshness Table** (existing) — Last updated, row count, age vs threshold
2. **Data Quality Issues** (new) — NULLs, duplicates, constraint violations
3. **Coverage Gaps** (new) — Missing symbols, dates, sectors
4. **Failure Patterns** (new) — Rate, windows, MTTR, trends
5. **API Diagnostics** (new) — Rate limits, auth, service status
6. **Loader Errors** (existing) — Error messages for stale tables
7. **Never-Started Loaders** (existing) — Loaders never invoked
8. **In-Progress Loaders** (existing) — Currently loading
9. **Stale Detail** (existing) — Age vs. own threshold
10. **Repeated Failures** (existing) — Migration 1163 streaks
11. **Inventory Gaps** (existing) — Untracked/missing tables

---

## Database Schema Changes (Migration 1164)

### New `data_loader_status` Columns
```sql
ALTER TABLE data_loader_status
    ADD COLUMN http_status_code INTEGER NULL;
    ADD COLUMN rate_limit_quota TEXT NULL;
    ADD COLUMN retry_count INTEGER DEFAULT 0;
    ADD COLUMN execution_duration_sec DECIMAL(10, 2) NULL;
    ADD COLUMN symbols_per_second DECIMAL(10, 2) NULL;
```

### New `data_loader_status_history` Table
```sql
CREATE TABLE data_loader_status_history (
    id SERIAL PRIMARY KEY,
    table_name VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,  -- NOT_STARTED, RUNNING, COMPLETED, FAILED, TIMEOUT
    execution_started TIMESTAMP NULL,
    execution_completed TIMESTAMP NULL,
    error_message TEXT NULL,
    http_status_code INTEGER NULL,
    row_count BIGINT NULL,
    completion_pct DECIMAL(5, 2) NULL,
    symbols_loaded INTEGER NULL,
    symbol_count INTEGER NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

- **Retention policy**: Last 100 runs per table (auto-purged)
- **Indexes**: By (table, completion_date DESC) for fast lookups
- **Used for**: Failure rate, pattern analysis, MTTR calculation

---

## Integration Points

### API Layer (`lambda/api/routes/algo_handlers/market.py`)
```python
# Automatically enriches health items after fetching
for source in sources:
    source = enrich_health_item_with_data_quality(source, cur)
    source = enrich_health_item_with_coverage(source, cur)
    source = enrich_health_item_with_failure_pattern(source, cur)
    source = enrich_health_item_with_api_diagnostics(source)
```

### Dashboard Panel (`dashboard/panels/health.py`)
```python
# Display enhancements called from _build_freshness_panel()
quality_section = _build_data_quality_section(hlth_items)
coverage_section = _build_coverage_section(hlth_items)
failure_section = _build_failure_pattern_section(hlth_items)
api_section = _build_api_diagnostics_section(hlth_items)

left_rows.extend([quality_section, coverage_section, failure_section, api_section])
```

### Loader Status Manager (`utils/loaders/status_manager.py`)
```python
# Updated to pass diagnostics
manager.mark_completed(
    execution_duration_sec=42.5,
    http_status=200,
    rate_limit_quota="98/100 calls"
)
manager.mark_failed(
    error_message="Rate limit hit",
    http_status=429,
    retry_count=3
)
```

---

## Usage Example: Operator Decision Making

### Before Enhancement
```
OPERATOR SEES:
  price_daily: ✓ OK [2h ago] [2.8M rows]
  market_health_daily: ~ STALE [26h ago] [1.2M rows]

OPERATOR QUESTION: "Should I wait for market health or skip Phase 2?"
PANEL ANSWER: "It's stale."
STILL UNKNOWN: Why? Will it fix? How long? Is it a one-off?
```

### After Enhancement
```
OPERATOR SEES:
  price_daily: ✓ OK [2h ago] [2.8M rows]
    └─ Coverage: 2995/3000 symbols
    └─ Quality: 99.2% clean
    └─ Duration: 32 sec (normal)
  
  market_health_daily: ⚠ STALE [26h ago]
    └─ Issue: Rate limit (100/100 calls used)
    └─ Reset: 2026-07-28 09:00 EST (18.5h remaining)
    └─ Pattern: Not recurring (1/30 failure)
    └─ Action: Safe to wait for reset
    └─ Blocks: Phase 2 until fixed

OPERATOR DECISION: "Price data complete & trustworthy. 
Market health temporarily rate-limited (expected).
Proceed with Phase 1, delay Phase 2 until 9am. ETA clear."
```

---

## Rollout Checklist

- [ ] Apply migration 1164 to database
- [ ] Deploy `dashboard/freshness_enhancements.py` module
- [ ] Update `lambda/api/routes/algo_handlers/market.py` with enrichment calls
- [ ] Update `dashboard/panels/health.py` with new display functions
- [ ] Update `utils/loaders/status_manager.py` with diagnostics parameters
- [ ] Test with 3+ loaders (check data quality, coverage, failures)
- [ ] Verify panel displays all sections without errors
- [ ] Monitor logs for any enrichment warnings/failures (should be DEBUG level)
- [ ] Confirm dashboard loads without lag (enrichments are async fail-safe)

---

## Performance Considerations

### Query Timing
- **Data quality checks**: bounded to a 200k-row sample per column/table (was an unbounded
  full-table scan pre-fix - confirmed live at ~0.35s/column on price_daily's 8.7M rows;
  the duplicate-row check additionally never ran at all due to invalid SQL, see fix notes
  in `freshness_enhancements.py`)
- **Coverage calculation**: was 100% broken pre-fix (referenced a nonexistent
  `universe_stocks` table/`is_active` column - the real table is `stock_symbols`/`active`)
- **Failure pattern analysis**: ~10-50ms per table (index lookup on history)
- **API diagnostics**: <1ms per table (string parsing only)

**Runs synchronously inline in the `/api/algo/data-status` request handler** (`_get_data_status`
in `lambda/api/routes/algo_handlers/market.py`), not async - it directly adds to that request's
latency. The dashboard client caches the response for 60s (`fetchers_config.py`), which limits
how often it re-runs, but does not make the work itself async or non-blocking.

### Storage Impact
- `data_loader_status_history`: ~2-5 KB per run × 100 runs/table × 30-50 tables = ~6-15 MB
- Auto-purged (keeps only last 100 per table)
- Negligible impact on total DB size

---

## Troubleshooting

**Panel shows "unknown" status for all metrics**
→ Enrichment module not imported or disabled
→ Check logs for `[DATA_STATUS] Freshness enhancements module not available`
→ Falls back to basic freshness display (safe)

**Coverage section missing for specific table**
→ Table not in symbol-based table list
→ Edit `symbol_tables` set in `enrich_health_item_with_coverage()`

**Failure patterns show "unknown"**
→ `data_loader_status_history` table missing
→ Apply migration 1164
→ Patterns appear after 5+ runs of a loader

**API diagnostics always show "ok"**
→ Loader not passing HTTP status to `mark_failed()`
→ Update loader code to pass `http_status` parameter
→ Currently optional (graceful fallback)

---

## Future Enhancements

1. **Dependency cascade visualization** — show impact if table stays stale
2. **ML anomaly detection** — flag unusual execution patterns automatically
3. **Credential expiry countdown** — days until API keys/auth tokens expire
4. **Cross-table reconciliation** — P&L validation, position sync audit
5. **Data lineage tracking** — which tables feed into which phases
