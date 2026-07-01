# Factor Scores Data Flow & Troubleshooting Guide

**Purpose**: Understand how data flows from market data through metric loaders into factor scores  
**Target Audience**: Ops, developers debugging missing scores  
**Last Updated**: 2026-07-01

---

## Data Flow Architecture

```
MARKET DATA (Real-time via yfinance, SEC EDGAR, etc.)
    ↓
    ├─ stock_prices_daily
    │   ├─ Price, volume, returns
    │   └─→ Feeds: momentum_metrics, technical_data_daily
    │
    ├─ technical_data_daily
    │   ├─ RSI, MACD, Bollinger Bands
    │   └─→ Feeds: signal_quality_scores, swing_trader_scores
    │
    ├─ positioning_metrics ★ CRITICAL
    │   ├─ Sources: insider_ownership, institutional_ownership, short_interest
    │   ├─ yfinance API calls (0.5-1s each × 5000 symbols)
    │   ├─ Parallelism: 3-4 (min 3)
    │   ├─ Expected time: 13-28 minutes
    │   └─→ Feeds: stock_scores
    │
    ├─ value_metrics ★ CRITICAL
    │   ├─ Sources: P/E, P/B, P/S, dividend yield from yfinance
    │   ├─ Parallelism: 3-4 (min 3)
    │   ├─ Expected time: 13-28 minutes
    │   └─→ Feeds: stock_scores
    │
    ├─ stability_metrics ★ CRITICAL
    │   ├─ Sources: volatility, beta from yfinance
    │   ├─ Parallelism: 2-3 (min 2)
    │   ├─ Expected time: 10-20 minutes
    │   └─→ Feeds: stock_scores
    │
    ├─ quality_metrics ⚠ SEC-dependent
    │   ├─ Sources: SEC annual financials (10-K filings)
    │   ├─ ROE, debt_to_equity, margins from annual_income_statement
    │   ├─ Parallelism: 2-3 (min 2)
    │   ├─ Expected time: 15-30 minutes (blocked on financial_data_pipeline)
    │   └─→ Feeds: stock_scores
    │
    ├─ growth_metrics ⚠ SEC-dependent
    │   ├─ Sources: SEC annual financials (YoY revenue growth, EPS growth)
    │   ├─ Parallelism: 2-3 (min 2)
    │   ├─ Expected time: 15-30 minutes (blocked on financial_data_pipeline)
    │   └─→ Feeds: stock_scores
    │
    └─ momentum_metrics
        ├─ Sources: stock_prices_daily (1m, 3m, 6m, 12m returns)
        ├─ Parallelism: 1 (fast, depends only on prices)
        └─→ Feeds: stock_scores

                        ↓ ORCHESTRATOR GATE ↓
                   (Validates ≥70% coverage)
                        
                stock_scores ★★ OUTPUT
                    ├─ Requires: positioning, value, stability (REQUIRED)
                    ├─ Requires: quality, growth (OPTIONAL if SEC data sparse)
                    ├─ Validates: Data completeness ≥ 70%
                    ├─ Pre-flight: Fails fast if upstream incomplete
                    ├─ Computation: 5-10 minutes for 5000 symbols
                    └─ Output: Table with composite_score + factor scores
                              (or NULL if insufficient data)
```

---

## Pipeline Execution Timeline

### EOD Pipeline (4:05 PM ET)

```
4:05 PM - Pipeline Start
  ├─ T+0 min: Orchestrator Phase 1 starts
  │   ├─ stock_prices_daily fetch (∼2-5 min)
  │   ├─ technical_data_daily compute (∼1-3 min)
  │   ├─ positioning_metrics, value_metrics, stability_metrics START (parallelism 3-4)
  │   │   └─ Expected: Complete by T+30 min
  │   ├─ momentum_metrics compute (∼2-3 min)
  │   └─ data_loader_status updated every 2 min
  │
  ├─ T+20-30 min: Metric loaders completing
  │   ├─ positioning_metrics: 98% complete, 4900+ stocks loaded
  │   ├─ value_metrics: 95% complete
  │   ├─ stability_metrics: 99% complete
  │   └─ [CRITICAL GATE] Orchestrator checks coverage:
  │       - If < 70% in any table: WAIT (continue loaders)
  │       - If ≥ 70% in all: PROCEED to stock_scores
  │
  ├─ T+30-35 min: Orchestrator Phase 2 starts
  │   ├─ Dependency check: Compare MAX(updated_at) upstream vs stock_scores
  │   ├─ If upstream newer: Retrigger stock_scores
  │   ├─ stock_scores pre-flight validation runs
  │   │   └─ Verifies positioning ≥80%, value ≥80%, stability ≥85% coverage
  │   ├─ If validation fails: EXIT with error (see troubleshooting)
  │   ├─ stock_scores computation: 5-10 min
  │   └─ Result written to stock_scores table
  │
  └─ T+40-50 min: Pipeline Complete
      ├─ stock_scores.updated_at = now
      ├─ Dashboard can read factor scores
      └─ All stocks with ≥50% data completeness have numeric scores
```

### Computed Metrics Pipeline (7:00 PM ET)

```
7:00 PM - Pipeline Start (After Financial Data Pipeline 4:05 PM)
  ├─ Waits for financial_data_pipeline (4:05 PM) to complete
  ├─ T+0 min (7:00 PM): Compute quality/growth metrics FROM financial data
  │   ├─ quality_metrics (parallelism 2-3): 15-30 min
  │   ├─ growth_metrics (parallelism 2-3): 15-30 min
  │   ├─ [SEC Filing Gap] If SEC data sparse → data_unavailable=True (expected)
  │   └─ Result: 50-85% coverage (OK, not all companies have complete SEC data)
  │
  ├─ T+30-35 min (7:30 PM): Re-run stock_scores
  │   ├─ Now has fresh quality/growth data
  │   ├─ Pre-flight validation: All upstream metrics ≥70%+
  │   ├─ Recompute with quality/growth scores
  │   └─ Update composite scores (may change from phase 1)
  │
  └─ T+40-45 min (7:40 PM): Pipeline Complete
      └─ stock_scores now includes quality + growth factors
```

---

## Expected Output State After Successful Run

### Metric Tables (all should exist and be populated)

```sql
-- positioning_metrics should have:
SELECT COUNT(*) as total,
       COUNT(*) FILTER (WHERE data_unavailable = false) as with_real_data,
       COUNT(*) FILTER (WHERE insider_ownership IS NOT NULL) as with_insider,
       COUNT(*) FILTER (WHERE institutional_ownership IS NOT NULL) as with_institutional
FROM positioning_metrics;

-- Expected: total ~5000, with_real_data ~4800+ (98%+), all have insider/institutional
```

```sql
-- stock_scores should have:
SELECT COUNT(*) as total,
       COUNT(*) FILTER (WHERE composite_score IS NOT NULL) as with_scores,
       COUNT(*) FILTER (WHERE positioning_score IS NOT NULL) as with_positioning,
       COUNT(*) FILTER (WHERE value_score IS NOT NULL) as with_value,
       COUNT(*) FILTER (WHERE quality_score IS NOT NULL) as with_quality,
       COUNT(*) FILTER (WHERE growth_score IS NOT NULL) as with_growth
FROM stock_scores;

-- Expected after EOD: total ~5000, with_scores ~4800+, positioning/value/stability ~4800+
-- Expected after Computed Metrics: quality/growth populated for ~50-85% (SEC data may be sparse)
```

---

## Troubleshooting Decision Tree

### Symptom: Factor Scores Show "--" (Missing Values)

```
Start: OPI (or other stock) showing "--" for factor scores

├─ YES: Is stock_scores table empty (0 rows)?
│   ├─ YES
│   │   └─→ Issue: stock_scores loader never ran
│   │       └─ Check: Is EOD pipeline executing?
│   │           ├─ Check Step Functions: algo-eod-pipeline-dev
│   │           ├─ Check logs: /aws/states/algo-eod-pipeline-dev
│   │           └─ Fix: Manually trigger or check scheduler rule enabled
│   │
│   └─ NO: stock_scores exists, but OPI has NULL composite_score
│       └─→ Issue: stock_scores computed but OPI excluded
│           └─ Reason: Insufficient upstream metrics (< 50% data completeness)
│               ├─ Check: positioning_metrics for OPI
│               │   └─ SQL: SELECT * FROM positioning_metrics WHERE symbol='OPI'
│               ├─ Check: value_metrics for OPI
│               │   └─ SQL: SELECT * FROM value_metrics WHERE symbol='OPI'
│               ├─ Check: stock_scores validation in logs
│               │   └─ grep "[STOCK_SCORES] Pre-flight validation" CloudWatch logs
│               └─ Fix: Wait for metric loaders to complete
│                   └─ Check timeout: Did loaders time out?
│
└─ stock_scores has OPI, but some factor scores are NULL
    └─→ Issue: Partial data for OPI (missing specific upstream metric)
        ├─ NULL positioning_score?
        │   └─ Check: positioning_metrics coverage < 50% overall
        │       └─ Fix: positioning_metrics might still be running
        │           └─ Expected: Takes 13-28 min with parallelism=3
        │
        ├─ NULL quality_score?
        │   └─ Check: quality_metrics coverage < 50%
        │       └─ Reason: SEC filing data sparse (expected for some stocks)
        │       └─ Not an error — quality_score unavailable is normal
        │
        └─ NULL growth_score?
            └─ Check: growth_metrics coverage < 50%
                └─ Reason: growth_metrics blocked on financial_data_pipeline
                └─ Fix: Wait for Computed Metrics Pipeline (7 PM)
                    └─ Retry after 7:45 PM ET
```

---

## Root Cause Analysis: Why Do Scores Go Missing?

### Issue #1: Orchestrator Timeout (Before Infrastructure Fix)

**Symptom**: All factor scores missing (all NULL)

**Timeline**:
```
4:05 PM: Orchestrator starts, metric loaders BEGIN with parallelism=1-2
4:10 PM: positioning_metrics at 10% (2-41 min remaining)
4:15 PM: value_metrics at 8% (2-41 min remaining)
4:30 PM: Orchestrator TIMEOUT at 15-minute mark
        └─ positioning_metrics only 36% complete
        └─ value_metrics only 34% complete
4:30 PM: Pre-flight validation FAILS (need ≥70% coverage)
4:30 PM: stock_scores skipped, no output
```

**Root Cause**: Metric loaders too slow due to:
- yfinance API: 0.5-1.0 seconds per symbol × 5000 symbols = 41-83 minutes
- Parallelism too low (1-2) → sequential or slow parallel
- Orchestrator timeout too tight (15 min)

**Fix Applied** (2026-06-30):
- ✅ Increased parallelism: 1-2 → 3-4
- ✅ Increased timeout: 15 min → 25 min
- ✅ Result: positioning_metrics now completes in 13-28 min

---

### Issue #2: Stale Data (Before Granular Timestamp Fix)

**Symptom**: Scores updated once per day only, missing intraday updates

**Timeline**:
```
2026-06-30 00:00: stock_scores computed, updated_at = date(2026-06-30)
2026-07-01 07:56: positioning_metrics loader runs, finds new data, updates table
2026-07-01 11:00: Dashboard loads OPI scores
                 └─ stock_scores still has updated_at = date(2026-06-30)
                 └─ Displaying old scores (momentum=None, positioning=None)
                 └─ New positioning data never picked up!
```

**Root Cause**: stock_scores used `date.today()` (once per day granularity)
- Only recomputes if forced or next day

**Fix Applied** (2026-06-30):
- ✅ Changed to `datetime.now(timezone.utc)` (per-second granularity)
- ✅ Orchestrator now detects upstream newer than downstream → retriggers stock_scores
- ✅ Result: Intraday updates possible, stale data fixed automatically

---

### Issue #3: Insufficient Upstream Coverage

**Symptom**: stock_scores computes but some OPI factor scores NULL

**Timeline**:
```
4:05 PM: Metric loaders START
4:20 PM: positioning_metrics 85% complete
4:25 PM: stock_scores PRE-FLIGHT validation runs
        └─ Checks: positioning ≥80% ✓ (85%)
        └─ Checks: value ≥80% ✗ (45% — still loading!)
4:25 PM: PRE-FLIGHT FAILS, stock_scores skipped
4:30 PM: value_metrics finally 100% complete
4:30 PM: Orchestrator retries stock_scores (dependency check)
4:35 PM: NOW all metrics ready, stock_scores succeeds
```

**Root Cause**: Uneven loader completion times
- Some metrics ready at T+15, others at T+30
- Pre-flight check runs too early
- Was mitigated by increasing all loader parallelism

**Monitoring**: Check data_loader_status table:
```sql
SELECT loader_name, completion_pct, updated_at 
FROM data_loader_status 
ORDER BY completion_pct;
```

---

## Critical Thresholds (Don't Change Without Discussion)

### Pre-Flight Validation Thresholds

**File**: `loaders/load_stock_scores.py` lines 86-116

```python
required_metric_tables = {
    "value_metrics": 0.80,          # ← Need 80% coverage for value scores
    "positioning_metrics": 0.70,    # ← Need 70% coverage (was 50, fixed 2026-06-30)
    "stability_metrics": 0.85,      # ← Need 85% coverage for stability scores
}
```

**Why These Thresholds?**
- value_metrics ≥80%: Most stocks have P/E, P/B ratios available
- positioning_metrics ≥70%: Institutional data missing for small-cap stocks (expected)
- stability_metrics ≥85%: Volatility/beta available for most stocks

**If thresholds too high:**
- stock_scores doesn't run → users see NULL
- But ensures quality data only

**If thresholds too low:**
- stock_scores runs with incomplete data
- Might compute scores with missing key factors
- Data quality suffers

### Data Completeness Threshold

**File**: `loaders/load_stock_scores.py` lines 229-240

```python
completeness_threshold = 0.50  # ← Need ≥50% of 6 factors to compute valid score
```

**Meaning**: If stock has < 3 of 6 factors (quality, growth, value, momentum, positioning, stability):
- Return empty (don't write score)
- User sees stock as not-scored (correct behavior)

---

## Verification Checklist (Quick)

After pipeline runs, verify in this order:

```bash
# 1. Check metric table coverage
python3 scripts/verify_metric_loaders.py

# Expected: All tables ✓ OK with coverage shown
```

```bash
# 2. Check factor scores populated
python3 scripts/check_opi_scores.py

# Expected: OPI row with numeric composite_score (not NULL)
```

```bash
# 3. Check for any data gaps
sqlite3 algodb.db << EOF
SELECT COUNT(*) FILTER (WHERE composite_score IS NULL) as null_scores
FROM stock_scores;
EOF

# Expected: Should be small number (< 5% of 5000 = < 250 NULL scores)
```

If all 3 pass: ✅ **Data flowing correctly**

If any fail: 🔴 **Troubleshoot** using decision tree above

---

## Key Metrics to Monitor (Ongoing)

Add these to dashboards:

```sql
-- Metric table freshness (should update daily)
SELECT 'positioning_metrics' as table_name,
       MAX(updated_at) as latest_update,
       NOW() - MAX(updated_at) as staleness
FROM positioning_metrics;

-- factor_scores completeness
SELECT 
    COUNT(*) as total_stocks,
    COUNT(*) FILTER (WHERE composite_score IS NOT NULL) as with_scores,
    COUNT(*) FILTER (WHERE composite_score IS NOT NULL) * 100.0 / COUNT(*) as score_coverage_pct
FROM stock_scores;

-- Average factor scores (sanity check)
SELECT 
    ROUND(AVG(composite_score), 1) as avg_composite,
    ROUND(AVG(momentum_score), 1) as avg_momentum,
    ROUND(AVG(quality_score), 1) as avg_quality,
    ROUND(AVG(growth_score), 1) as avg_growth,
    ROUND(AVG(value_score), 1) as avg_value,
    ROUND(AVG(positioning_score), 1) as avg_positioning,
    ROUND(AVG(stability_score), 1) as avg_stability
FROM stock_scores
WHERE composite_score IS NOT NULL;
```

**Expected**: 
- All table updates within 24 hours
- score_coverage_pct ≥ 95%
- avg_composite around 50-70 range (normal distribution)

---

## Related Documentation

- [[METRIC_LOADER_FIX_VERIFICATION.md]] — Parallelism increase details
- [[factor_scores_stale_data_fix.md]] — Granular timestamp & dependency fix
- [[FACTOR_SCORES_DATA_VERIFICATION.md]] — Comprehensive verification checklist
- [[GOVERNANCE.md]] — Data quality rules and safety thresholds
