# Data Loading Improvements - Comprehensive Strategy

## Current State

- **30 active loaders** across 8 categories (prices, technicals, fundamentals, sentiments, earnings, etc.)
- **Scheduled via EventBridge** (26 rules) + **Step Functions** (13 EOD-critical loaders)
- **Structured logging** in place with trace IDs for debugging
- **Data patrol system** for comprehensive validation (15+ checks)
- **Data freshness checks** in orchestrator Phase 1
- **Tables**: 30+ core data tables, all with schema defined

## Identified Issues & Gaps

### 1. **Silent Loader Failures** 🚨
- Loaders may fail without visible alerting
- No automated retry mechanism for transient failures
- Failed loaders not immediately visible in operational dashboards
- **Impact**: Incomplete data for some symbols/dates

### 2. **Incomplete Symbol Coverage**
- Not all S&P 500 symbols may have complete data for all loaders
- Some metrics might fail for certain stock types (micro-caps, new IPOs, etc.)
- No coverage auditing per loader
- **Impact**: Technical indicators missing for some symbols

### 3. **Data Quality Issues**
- NULL values in indicators (RSI, EMA, ATR) not tracked or alerted
- Zero-volume entries treated as valid data
- API rate limiting not gracefully handled
- **Impact**: Trading on incomplete technical picture

### 4. **Technical Indicator Gaps**
- Weekly/monthly prices need more historical depth
- Some indicators require 100+ days of history
- Initial backfill limited to 100 days instead of 1+ years
- **Impact**: Seasonal patterns and long-term trends not captured

### 5. **Loader Parallelism Issues**
- Multiple loaders may hit same APIs concurrently
- No rate-limit coordination between loaders
- Resource contention on RDS during peak load times
- **Impact**: Timeouts, partial data loads, or failed batches

### 6. **Monitoring Blind Spots**
- No real-time alerting for stale data
- Data patrol runs manually, not scheduled automatically
- CloudWatch metrics not published for data quality
- **Impact**: Issues discovered late or not at all

---

## Priority 1: Immediate Fixes (This Week)

### P1.1: Add Loader Health Dashboard
Create `/api/data-coverage` endpoint (DONE in code) that returns:
- Price data freshness and coverage %
- Technical indicator completeness per indicator
- Symbol universe vs actual coverage
- Recent loader failures
- Market health status

**Action**: 
```bash
# Deploy new endpoint
git add lambda/api/routes/data_coverage.py
# Test: curl http://localhost:3000/api/data-coverage
```

### P1.2: Enable Automatic Data Patrol Scheduling
Add EventBridge rule to run data patrol daily:

```python
# In terraform/modules/loaders/main.tf, add:
"data_patrol_daily" = {
  schedule    = "cron(15 9 ? * MON-FRI *)"  # 4:15am ET, after prices loaded
  description = "Daily data quality validation - P1,P3,P7,P9,P12 checks"
}
```

Run `data_patrol --quick` (critical checks only) for speed.

### P1.3: Add Loader Retry Logic
Enhance ECS task definitions with exponential backoff:

```python
# In loaders/base_loader.py
MAX_RETRIES = 3
BASE_WAIT = 2
for attempt in range(MAX_RETRIES):
    try:
        return fetch_data()
    except RateLimitError:
        wait = BASE_WAIT * (2 ** attempt)  # 2s, 4s, 8s
        logger.warning(f"Rate limited, retrying in {wait}s...")
        time.sleep(wait)
```

---

## Priority 2: Data Completeness (Week 2-3)

### P2.1: Price Data Backfill Script
Create loader for historical price data (1+ years per symbol):

```python
# loaders/load_price_history_backfill.py
"""
Backfill price_daily with 3+ years of history for technical indicator stability.
Runs once per new symbol, then incremental updates only.
"""
```

**Why**: Technical indicators like SMA, EMA, Bollinger Bands need 60-100 days minimum.
Seasonal patterns require 1+ year history for reliable backtests.

### P2.2: Technical Indicator Completeness Audit
Query and identify missing indicators:

```sql
SELECT symbol, date, COUNT(CASE WHEN rsi IS NULL THEN 1 END) as missing_rsi
FROM technical_data_daily
WHERE date > NOW() - INTERVAL '7 days'
GROUP BY symbol, date
HAVING COUNT(*) > 0
ORDER BY missing_rsi DESC
LIMIT 20
```

Rerun `load_technical_data_daily` for problematic symbols.

### P2.3: Symbol Universe Validation
Ensure all loaders cover all S&P 500 stocks:

```sql
-- Check which symbols are missing from quality_metrics
SELECT s.symbol
FROM stock_symbols s
LEFT JOIN quality_metrics q ON s.symbol = q.symbol AND q.date = CURRENT_DATE
WHERE s.is_sp500 = TRUE AND q.symbol IS NULL
ORDER BY s.symbol
LIMIT 50
```

Run batch re-computation for missing symbols.

---

## Priority 3: Resilience & Monitoring (Week 3-4)

### P3.1: CloudWatch Metrics for Data Quality
Publish custom metrics every loader run:

```python
cloudwatch.put_metric_data(
    Namespace='Algo/DataQuality',
    MetricData=[
        {'MetricName': 'LoaderRunTime', 'Value': runtime_seconds},
        {'MetricName': 'SymbolsCovered', 'Value': symbol_count},
        {'MetricName': 'NullRate', 'Value': null_pct},
        {'MetricName': 'RowsLoaded', 'Value': row_count},
    ]
)
```

Set CloudWatch alarms:
- Alert if any loader hasn't run in 24+ hours
- Alert if NULL rate exceeds 5%
- Alert if symbol coverage drops below 95%

### P3.2: Loader Status Tracking Table
Use existing `data_loader_status` table more comprehensively:

After each loader run:
```sql
INSERT INTO data_loader_status 
  (loader_name, status, executed_at, rows_loaded, error_message)
VALUES 
  ('load_stock_prices_daily', 'SUCCESS', NOW(), 504, NULL)
```

Query in orchestrator Phase 1 to fail-close on recent failures.

### P3.3: Data Freshness Dashboard
Create Lambda function that publishes:
- Age of each critical table
- Loader execution timeline
- Data gaps (symbols with no recent data)
- Coverage metrics per loader

Expose via `/api/health/data` endpoint.

---

## Priority 4: Optimization (Week 4+)

### P4.1: Loader Parallelism Tuning
- **Batch 1** (prices): Run single large task with parallelism=4
- **Batch 2** (technicals): Run after prices, parallelism=2
- **Batch 3** (fundamentals): Run separately, parallelism=1 (SEC rate limits)
- **Batch 4** (sentiment): Run concurrently with fundamentals, parallelism=2

Stagger batches by 30 minutes to avoid RDS contention.

### P4.2: Incremental Loading with Watermarks
Extend `loader_watermarks` table:

```sql
CREATE TABLE IF NOT EXISTS loader_watermarks (
    loader VARCHAR(80) PRIMARY KEY,
    symbol VARCHAR(20),
    granularity VARCHAR(20),  -- 'daily', 'weekly', 'symbol', 'global'
    watermark TEXT,            -- last processed date or ID
    rows_loaded INTEGER,
    last_run_at TIMESTAMP,
    UNIQUE (loader, symbol, granularity)
);
```

Every loader:
1. Reads watermark (last processed date)
2. Fetches only NEW data since then
3. Updates watermark after successful load

**Benefit**: 90%+ reduction in redundant API calls.

### P4.3: Metric Pre-aggregation
Cache expensive calculations:

```sql
-- Instead of computing quality_metrics every night,
-- cache per 500-symbol batch with partial results
CREATE TABLE quality_metrics_staging (
    batch_id INTEGER,
    symbol VARCHAR(20),
    computed_fields JSONB,
    status VARCHAR(20),  -- 'processing', 'ready', 'failed'
    created_at TIMESTAMP
);
```

On success, merge to main table. On failure, retry just that batch.

---

## Testing & Validation

### Before Deploying:
1. Run all 30 loaders against test symbol universe (50 stocks)
2. Verify data_patrol passes all checks
3. Check /api/data-coverage reports 100% coverage for test universe
4. Monitor loader execution times and memory usage
5. Test retry logic with manual API throttling

### After Deploying:
1. Monitor data freshness daily for 1 week
2. Set up CloudWatch dashboard showing:
   - Loader success rates
   - Data freshness timeline
   - Symbol coverage heatmap
3. Create runbook for responding to data gaps
4. Alert team to any coverage drops

---

## Success Metrics

| Metric | Target | Current |
|--------|--------|---------|
| Symbol coverage | 99%+ | TBD |
| Price data freshness | < 1 day | TBD |
| Technical indicators complete | 98%+ | TBD |
| Loader success rate | 99.5%+ | TBD |
| NULL rates in indicators | < 1% | TBD |
| Data patrol pass rate | 99%+ | TBD |
| Orchestrator Phase 1 success | 99.9%+ | TBD |

---

## Implementation Checklist

- [ ] Deploy `/api/data-coverage` endpoint
- [ ] Add daily data patrol EventBridge rule
- [ ] Implement loader retry logic
- [ ] Create price history backfill loader
- [ ] Audit and fix missing technical indicators
- [ ] Validate symbol universe completeness
- [ ] Publish CloudWatch metrics
- [ ] Set up CloudWatch alarms
- [ ] Create data freshness dashboard
- [ ] Optimize loader parallelism
- [ ] Implement watermark-based incremental loading
- [ ] Set up pre-aggregation for metrics
- [ ] Test all changes with sample data
- [ ] Deploy to production
- [ ] Monitor for 1 week
- [ ] Update runbooks and documentation

---

## Questions for Review

1. **Which data is currently most problematic?** (Run `/diagnostic` to find out)
2. **Which API sources have rate limit issues?** (Check CloudWatch logs for 429 errors)
3. **Are there symbols that consistently fail to load?** (Query data_patrol_log for P7 findings)
4. **What's the current orchestrator failure rate in Phase 1?** (Check algo_audit_log)

Run diagnostic:
```bash
python diagnostic_data_coverage.py
```

Then prioritize fixes based on actual gaps found.
