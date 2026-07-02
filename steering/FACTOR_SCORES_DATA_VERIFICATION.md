# Factor Scores Data Verification Guide

**Purpose**: Ensure data flows correctly through metric loaders into stock_scores without gaps or silent failures.  
**Audience**: Ops engineers monitoring the pipeline  
**Last Updated**: 2026-07-01  
**Key Issue**: SEC EDGAR parallelism constraint fix (parallelism=1-2) deployed to prevent rate limiting

---

## Quick Status Check (5 minutes)

Run this to verify everything is working:

```bash
python3 scripts/verify_factor_scores_data.py
```

Output should show:
- ✓ Connected to AWS (if running in prod environment)
- ✓ SEC EDGAR loaders at 70%+ completion
- ✓ Metric coverage within thresholds
- ✓ Stock scores at 90%+ coverage

If any checks fail → see "Troubleshooting" section below.

---

## What to Monitor During Pipeline Execution

The factor scores pipeline has multiple stages. Here's what happens at each stage and what to watch for:

### Stage 1: Financial Data Loading (SEC EDGAR) — 10-30 minutes

**Expected behavior:**
- `income_statements` loader runs with parallelism=1-2 (rate-limited by SEC API)
- `balance_sheets` loader runs with parallelism=1-2
- `cash_flow_statements` loader runs with parallelism=1-2
- Data flows into `annual_income_statement`, `annual_balance_sheet` tables
- Completion: 80%+ coverage (80% of stocks have SEC data available)

**Critical fix (2026-07-01):**
- OLD: parallelism defaulted to 32 → SEC API 429 Too Many Requests → infinite retries → 5-8 hour hangs
- NEW: parallelism constrained to 1-2 → keeps under SEC's 10 req/sec limit → completes in 10-30 min

**Data to verify:**
```sql
-- Check income statement data is flowing
SELECT COUNT(*) as total, COUNT(DISTINCT symbol) as symbols
FROM annual_income_statement
WHERE fiscal_year >= 2023 AND revenue > 0;
-- Expected: total > 2000, symbols > 1000

-- Check balance sheet data
SELECT COUNT(*) as total, COUNT(DISTINCT symbol) as symbols
FROM annual_balance_sheet
WHERE fiscal_year >= 2023 AND total_assets > 0;
-- Expected: total > 2000, symbols > 1000
```

**Signs of problems:**
- ✗ Stage taking > 45 minutes → SEC API throttling (check logs for 429 errors)
- ✗ income_statements completion stuck at 0% → loader may not have started
- ✗ income_statements completion at 50% after 20 min → parallelism may be too high

---

### Stage 2: Metric Loader Execution — 20-40 minutes

**Expected behavior:**

| Loader | Parallelism | Duration | Upstream Dependency | Coverage Goal |
|--------|-------------|----------|---------------------|---------------|
| quality_metrics | 2-3 | 15-25 min | annual_income_statement | 65% |
| growth_metrics | 2-3 | 15-25 min | annual_income_statement | 80% |
| value_metrics | 3-4 | 13-20 min | stock_prices_daily | 80% |
| positioning_metrics | 3-4 | 13-28 min | stock_prices_daily | 70% |
| stability_metrics | 2-3 | 10-20 min | stock_prices_daily | 85% |

**Data to verify:**
```sql
-- Check metric coverage after stage 2
SELECT table_name,
    COUNT(*) as total_rows,
    COUNT(CASE WHEN data_unavailable = false OR data_unavailable IS NULL THEN 1 END) as available_rows,
    ROUND(100.0 * COUNT(CASE WHEN data_unavailable = false OR data_unavailable IS NULL THEN 1 END) / COUNT(*), 1) as coverage_pct
FROM quality_metrics
GROUP BY table_name
UNION ALL
SELECT 'quality_metrics',
    COUNT(*),
    COUNT(CASE WHEN data_unavailable = false OR data_unavailable IS NULL THEN 1 END),
    ROUND(100.0 * COUNT(CASE WHEN data_unavailable = false OR data_unavailable IS NULL THEN 1 END) / COUNT(*), 1)
FROM quality_metrics;
-- Expected: all >= threshold
```

**Signs of problems:**
- ✗ positioning_metrics stuck at 0% after 10 min → yfinance timeout or API issue
- ✗ quality_metrics stuck at 0% after 5 min → may be waiting for upstream financial data
- ✗ Any loader with 0% "available" rows → may not be actually running, just marking everything data_unavailable

**Key distinction: Incomplete vs. Silent Failure**
```sql
-- GOOD: Incomplete but explicit (marking unavailable)
SELECT COUNT(*) FROM quality_metrics WHERE data_unavailable = TRUE;
-- Returns: 1000+ (explicit marking, system knows these are unavailable)

-- BAD: Incomplete and silent (rows exist but are NULL/default)
SELECT COUNT(*) FROM quality_metrics WHERE quality_score IS NULL AND data_unavailable IS NULL;
-- Returns: > 0 (gap in data — neither marked available nor unavailable)
```

---

### Stage 3: Stock Scores Computation — 5-10 minutes

**Expected behavior:**
- Orchestrator waits for metric loaders to reach minimum coverage thresholds
- stock_scores loader runs, computing composite scores
- Each symbol gets factors aggregated into signal_score, etc.
- Completion: 90%+ coverage (4500+ of 5000 symbols have scores)

**Data to verify:**
```sql
-- Check stock scores completeness
SELECT
    COUNT(*) as total_scores,
    COUNT(CASE WHEN composite_score IS NOT NULL THEN 1 END) as with_score,
    ROUND(100.0 * COUNT(CASE WHEN composite_score IS NOT NULL THEN 1 END) / COUNT(*), 1) as coverage_pct,
    ROUND(AVG(composite_score), 2) as avg_score,
    ROUND(STDDEV(composite_score), 2) as stddev_score
FROM stock_scores;
-- Expected: coverage_pct >= 90, avg_score ~50-70, stddev ~15-25

-- Check factor score distribution
SELECT
    ROUND((
        (CASE WHEN quality_score IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN growth_score IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN value_score IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN momentum_score IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN positioning_score IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN stability_score IS NOT NULL THEN 1 ELSE 0 END) / 6.0
    ) * 100 / 20) * 20 as completeness_bucket,
    COUNT(*) as count
FROM stock_scores
WHERE composite_score IS NOT NULL
GROUP BY completeness_bucket
ORDER BY completeness_bucket DESC;
-- Expected: histogram skewed toward 80-100% completeness
```

**Signs of problems:**
- ✗ stock_scores coverage < 50% → upstream metrics incomplete
- ✗ All scores == 50.0 exactly → scoring function may be returning default value
- ✗ Max score == 100.0 for many symbols → normalization may be broken
- ✗ All factors NULL (showing 0% in distribution) → metrics weren't loaded, stock_scores skipped those symbols

---

## Known Data Gaps (Expected)

These gaps are normal and documented:

### 1. REITs and Exotic Securities (~13.6% of universe)
- **Why**: Real Estate Investment Trusts lack traditional balance sheet structure
- **Impact**: quality_score, growth_score marked data_unavailable
- **Example**: OPI (Realty Income REIT)
  - Has positioning_score ✓, value_score ✓, stability_score ✓
  - Missing quality_score ✗ (no operating margin calculation), growth_score ✗
  - Composite score computed with 4/6 factors (weight redistribution)

### 2. Micro-caps, OTC Stocks (~7% of universe)
- **Why**: No SEC EDGAR filings or limited yfinance data
- **Impact**: quality_score, growth_score marked data_unavailable
- **Expected**: ~350 stocks per screening day

### 3. ETFs (~2% of covered universe)
- **Why**: Excluded from metric loaders by design (exclude_etfs_from_symbols=True)
- **Impact**: No scores computed (architectural decision — would require synthetic data)
- **Example**: XHS (China 100 ETF) won't appear in stock_scores

### 4. Positioning Metrics for some stocks (<3%)
- **Why**: yfinance doesn't provide insider/institutional data for some symbols
- **Impact**: positioning_score marked data_unavailable
- **Example**: Some obscure OTC symbols

### Allowed Data Gaps
- quality_metrics: 682-750 securities with data_unavailable=TRUE (known gap, expected)
- positioning_metrics: 40-200 securities with data_unavailable=TRUE
- **Do NOT escalate** if gaps are within these ranges

### Unallowed Data Gaps (Investigate Immediately)
- stock_scores: > 10% NULL composite_scores
- value_metrics: < 70% coverage (indicates yfinance outage)
- positioning_metrics: < 60% coverage
- quality_metrics: 0 rows in table (loader never ran)

---

## Troubleshooting Decision Tree

### Problem: Pipeline taking > 2 hours

**Step 1: Check SEC EDGAR loaders**
```sql
SELECT table_name, completion_pct, status
FROM data_loader_status
WHERE table_name IN ('income_statements', 'balance_sheets', 'cash_flow_statements');
```

- If stuck at 50% for > 30 min → SEC API rate limiting
  - Check CloudWatch logs: `/ecs/algo-financials_annual_income-loader`
  - Look for: "429 Too Many Requests", "rate limit exceeded"
  - **Fix**: Verify parallelism=1-2 is set in utils/loaders/config.py
  - If still > 2, check DynamoDB loader-config table for override

- If stuck at 0% → loader may not have started
  - Check ECS task logs: Are tasks running?
  - Check orchestrator logs: Did it trigger metric loaders?

**Step 2: Check metric loader status**
```sql
SELECT table_name, completion_pct, status
FROM data_loader_status
WHERE table_name IN ('positioning_metrics', 'value_metrics', 'quality_metrics', 'growth_metrics', 'stability_metrics');
```

- If any < 20% after 15 min → upstream dependency issue
  - Check: Does upstream table have data?
  - For quality_metrics: Check annual_income_statement has revenue data
  - For value_metrics: Check stock_prices_daily is complete

**Step 3: Check stock_scores status**
```sql
SELECT completion_pct, status FROM data_loader_status WHERE table_name = 'stock_scores';
```

- If 0% but metrics are > 80% → stock_scores loader may not have started
  - Check orchestrator logs for validation errors
  - May be waiting for metrics to reach thresholds

---

### Problem: stock_scores shows 60% coverage (low)

**Step 1: Check metric completeness**
```sql
-- Check which metrics are missing
SELECT
    COUNT(*) as total,
    COUNT(CASE WHEN quality_score IS NOT NULL THEN 1 END) as q,
    COUNT(CASE WHEN growth_score IS NOT NULL THEN 1 END) as g,
    COUNT(CASE WHEN value_score IS NOT NULL THEN 1 END) as v,
    COUNT(CASE WHEN positioning_score IS NOT NULL THEN 1 END) as p,
    COUNT(CASE WHEN stability_score IS NOT NULL THEN 1 END) as s,
    COUNT(CASE WHEN momentum_score IS NOT NULL THEN 1 END) as m
FROM stock_scores;
```

**Step 2: Check if metrics were loaded**
```sql
SELECT table_name, COUNT(*) as rows, 
    COUNT(CASE WHEN data_unavailable = FALSE OR data_unavailable IS NULL THEN 1 END) as available
FROM quality_metrics
GROUP BY table_name;
```

- If quality_metrics has 0 rows → loader didn't run
- If all rows have data_unavailable=TRUE → upstream SEC data missing (expected for ~13.6% of stocks)

---

### Problem: Data shows big holes (random missing scores)

**Check for silent failures:**
```sql
-- Find scores with all factors NULL but no error flag
SELECT symbol, composite_score, quality_score, growth_score
FROM stock_scores
WHERE composite_score IS NULL 
  AND quality_score IS NULL 
  AND growth_score IS NULL
  AND value_score IS NULL
  AND positioning_score IS NULL
  AND stability_score IS NULL
  AND data_unavailable IS NULL  -- <-- This is the problem
LIMIT 20;
```

**If any exist:**
1. This indicates a scoring failure that wasn't marked
2. Check orchestrator logs for errors during stock_scores computation
3. Likely root cause: Metric loaders returned corrupted data (NaN, invalid types)

---

## Automated Verification (Post-Pipeline)

Run after pipeline completes:

```bash
# Full verification
python3 scripts/verify_factor_scores_data.py

# Expected output:
# ✓ Connected to AWS
# ✓ Data Loader Status [all >= 70%]
# ✓ Financial Data Flow [income/balance sheet rows > 2000]
# ✓ Metric Table Coverage [all >= threshold]
# ✓ Stock Scores Completeness [>= 90%]
# ✓ ALL CHECKS PASSED
```

Exit code 0 = all checks passed, 1 = gaps detected

---

## Manual Verification (Spot Checks)

**After each pipeline run**, spot-check a few specific symbols:

```sql
-- Check OPI (REIT example — should have positioning, value, stability but not quality/growth)
SELECT symbol, composite_score, quality_score, growth_score, 
       value_score, momentum_score, positioning_score, stability_score
FROM stock_scores
WHERE symbol = 'OPI';

-- Check AAPL (should have all factors)
SELECT symbol, composite_score, quality_score, growth_score,
       value_score, momentum_score, positioning_score, stability_score
FROM stock_scores
WHERE symbol = 'AAPL';

-- Check for any all-NULL scores
SELECT COUNT(*) as null_composite_scores
FROM stock_scores
WHERE composite_score IS NULL AND data_unavailable IS NULL;
-- Expected: 0 (all NULLs should be marked data_unavailable)
```

---

## Operational Runbook

### Daily Health Check (5 min)
```sql
-- Pipeline freshness
SELECT MAX(updated_at), NOW() - MAX(updated_at) as age
FROM stock_scores;
-- Expected: age < 24 hours

-- Scoring coverage
SELECT COUNT(*) FILTER (WHERE composite_score IS NOT NULL) * 100.0 / COUNT(*) as pct
FROM stock_scores;
-- Expected: >= 90%

-- Data unavailable count
SELECT COUNT(*) FROM stock_scores WHERE data_unavailable = TRUE;
-- Expected: 680-750 (REITs, micro-caps) — alert if > 1000 or < 500
```

### Weekly Deep Dive (30 min)
- Run full verification: `python3 scripts/verify_factor_scores_data.py`
- Spot-check 5-10 symbols across market caps
- Review CloudWatch logs for exceptions
- Check for any new unknown data gaps (investigate before deploying changes)

---

## Related Documentation

- [[FACTOR_SCORES_DATA_FLOW.md]] — Data flow architecture and dependencies
- [[GOVERNANCE.md]] — Data quality rules and fail-fast principles
- [[OPERATIONS.md]] — Monitoring and alerting setup

