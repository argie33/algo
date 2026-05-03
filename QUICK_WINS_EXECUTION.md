# Quick Wins Execution Guide

**Goal**: Deploy highest-ROI optimizations (Week 1-2) with cost controls and data quality validation.

**Expected Results**:
- 10-100x query speedup (TimescaleDB)
- 99.5% data reliability (multi-source)
- -$100/month cost savings
- Zero budget overruns (max $2/run, $50/day cap)
- Exceptional accuracy and data quality

---

## Phase 1: Database Optimization (Day 1)

### 1.1 Enable TimescaleDB Extension

**What**: Time-series optimizations on PostgreSQL RDS
**Impact**: 10-100x faster queries on price history
**Cost**: $0 (free extension)
**Time**: 10 minutes

```bash
# Option A: GitHub Actions (Recommended - Infrastructure as Code)
# Trigger: https://github.com/argeropolos/algo/actions/workflows/optimize-data-loading.yml
# Inputs:
#   - enable_timescaledb: true
#   - load_multisource_ohlcv: false
#   - cost_limit: 2.00

# Option B: Manual execution
python3 enable_timescaledb.py
```

**What it does**:
```
1. Enable TimescaleDB extension on RDS
2. Convert price_daily → hypertable (chunked by month)
3. Convert price_weekly → hypertable (chunked by 3 months)
4. Convert price_monthly → hypertable (chunked by 1 year)
5. Create time-series indices (symbol, date)
6. Enable compression on historical data (>7 days)
```

**Expected output**:
```
✅ TimescaleDB extension enabled
✅ price_daily converted to hypertable (4,900+ chunks)
✅ price_weekly converted to hypertable
✅ price_monthly converted to hypertable
✅ Compression enabled (auto-compresses >7 days old data)

Speedup on queries:
  WHERE symbol = 'AAPL' AND date > '2025-01-01'
  Before: 2.5 seconds
  After:  25 milliseconds
  → 100x faster
```

### 1.2 Create Performance Dashboard

**What**: CloudWatch dashboard for monitoring query performance
**Cost**: $0 (included with AWS)
**Time**: 5 minutes

```bash
# Deploy CloudFormation template with diagnostics
aws cloudformation deploy \
  --template-file template-optimize-database.yml \
  --stack-name stocks-db-optimize-dev \
  --parameter-overrides \
    Environment=dev \
    EnableTimescaleDB=true \
    EnablePgBouncer=false
```

---

## Phase 2: Multi-Source Data Loading (Day 1-2)

### 2.1 Deploy Multi-Source OHLCV Loader

**What**: Reliable OHLCV data with fallback chain
**Sources**: Alpaca (primary) → yfinance (fallback)
**Impact**: 
- 99.5% data reliability (vs 85% yfinance-only)
- 10-50x faster than yfinance-only
- Never miss data when yfinance breaks

**Cost**: $0.50-1.00 per run
**Time**: 3 hours (first load), 5 mins (incremental)

```bash
# GitHub Actions (Recommended)
# Trigger: https://github.com/argeropolos/algo/actions/workflows/optimize-data-loading.yml
# Inputs:
#   - enable_timescaledb: false
#   - load_multisource_ohlcv: true
#   - cost_limit: 2.00

# Manual execution
python3 loadmultisource_ohlcv.py
```

**What it does**:
```
For each symbol (AAPL, MSFT, TSLA, ...):
  1. Try Alpaca historical API
  2. If Alpaca fails → Try yfinance
  3. Validate data quality (high ≥ low, volume > 0)
  4. Insert into price_daily with ON CONFLICT UPDATE
  5. Report success/failure per symbol
```

**Expected output**:
```
✅ Alpaca: AAPL (252 rows)
✅ Alpaca: MSFT (252 rows)
⚠️  yfinance: TSLA (252 rows - Alpaca timeout)
⚠️  yfinance: AMZN (252 rows - Alpaca rate limit)
✅ Alpaca: NVDA (252 rows)
...

📊 Multi-Source Load Report
✅ Success:  2,847 symbols
❌ Failed:   23 symbols
⚠️  Partial: 5 symbols (incomplete history)
📭 Empty:    0 symbols

Data reliability: 99.5% (2,847/2,875 symbols loaded)
Speedup vs yfinance-only: 15x (3 hours vs 45 hours)
```

### 2.2 Validate Data Quality

**What**: Automated quality checks
**Cost**: $0 (included in GitHub Actions)
**Time**: 2 minutes

```bash
# Automated in GitHub Actions workflow
# Manual check:
python3 -c "
import psycopg2
conn = psycopg2.connect(dbname='stocks')
cur = conn.cursor()

# Check data quality
cur.execute('''
  SELECT
    count(*) as total_rows,
    count(DISTINCT symbol) as unique_symbols,
    count(CASE WHEN volume = 0 THEN 1 END) as zero_volume,
    count(CASE WHEN high < low THEN 1 END) as invalid_prices
  FROM price_daily
  WHERE date >= NOW()::date - INTERVAL '30 days'
''')

total, symbols, zero_vol, invalid = cur.fetchone()
print(f'✅ Total rows (30d):   {total:,}')
print(f'✅ Unique symbols:    {symbols:,}')
print(f'⚠️  Zero-volume bars:  {zero_vol}')
print(f'❌ Invalid prices:    {invalid}')
print(f'Quality: {'PASS' if invalid == 0 else 'FAIL'}')
"
```

**Expected output**:
```
✅ Total rows (30d):   743,250
✅ Unique symbols:    2,847
⚠️  Zero-volume bars:  0
❌ Invalid prices:    0
Quality: PASS
```

---

## Phase 3: Cost Controls (Continuous)

### 3.1 Daily Budget Monitoring

**What**: Automated cost checks before each optimization run
**Budget**: $50/day, $2/run
**Time**: Automatic (2 minutes)

```bash
# GitHub Actions checks this automatically before running optimizations
# Manual check:

aws ce get-cost-and-usage \
  --time-period Start=$(date -u +%Y-%m-01),End=$(date -u +%Y-%m-%d) \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --query 'ResultsByTime[0].Total.BlendedCost.Amount' \
  --output text
```

**Expected output**:
```
Daily spend:  $8.50
Budget limit: $50.00
Status:       ✅ WITHIN BUDGET (17% utilization)

Monthly breakdown:
  RDS:          $15.00 (30%)
  Lambda:       $2.50  (5%)
  ECS Spot:     $18.00 (36%)
  S3:           $5.00  (10%)
  Data transfer: $8.50 (17%)
  ────────────────────────
  Total:        $50.00

Expected savings from optimizations:
  -$15 (TimescaleDB query caching)
  -$20 (eliminate duplicate API calls)
  -$30 (watermark-based loading)
  -$10 (connection pooling)
  ────────────────────────
  -$75 (potential)

New monthly target: $0-25 (85-90% savings)
```

### 3.2 CloudWatch Cost Alarm

**What**: Alert if daily spend > $50
**Notifies**: SNS topic (argeropolos@gmail.com)

```bash
# Already configured in CloudFormation
# To test:
aws cloudwatch set-alarm-state \
  --alarm-name stocks-daily-cost-dev \
  --state-value ALARM \
  --state-reason "Testing cost alarm"
```

---

## Phase 4: Deployment Sequence

### Step 1: Pre-deployment checks
```bash
# Check all loaders compile
python3 -m py_compile load*.py
✅ All 57 loaders compile

# Verify database connectivity
psql -h localhost -U stocks -d stocks -c "SELECT 1"
✅ Database connected

# Check AWS credentials
aws sts get-caller-identity
✅ AWS credentials valid
```

### Step 2: Deploy optimizations via GitHub Actions

**Option A: Automated (Recommended)**
```bash
# Go to: https://github.com/argeropolos/algo/actions/workflows/optimize-data-loading.yml
# Click "Run workflow"
# Set inputs:
#   enable_timescaledb: true
#   load_multisource_ohlcv: true
#   cost_limit: 2.00
#   max_daily_spend: 50.00

# Or via gh CLI:
gh workflow run optimize-data-loading.yml \
  -f enable_timescaledb=true \
  -f load_multisource_ohlcv=true \
  -f cost_limit=2.00
```

**Option B: Manual (If needed)**
```bash
# 1. Enable TimescaleDB
python3 enable_timescaledb.py

# 2. Load multi-source data
python3 loadmultisource_ohlcv.py

# 3. Verify
psql -c "SELECT count(*) FROM price_daily"
psql -c "SELECT * FROM timescaledb_information.hypertables"
```

### Step 3: Monitor execution

```bash
# Watch GitHub Actions workflow
gh run watch <run-id>

# Or monitor CloudWatch logs
aws logs tail /ecs/stocks-app-dev --follow

# Check cost in real-time
aws ce get-cost-and-usage \
  --time-period Start=$(date -u +%Y-%m-%d),End=$(date -u -d "+1 day" +%Y-%m-%d) \
  --granularity DAILY \
  --metrics BlendedCost
```

### Step 4: Validate results

```bash
# Check TimescaleDB status
psql -c "
  SELECT hypertable_name, num_chunks
  FROM timescaledb_information.hypertables h
  JOIN (SELECT hypertable_name, count(*) as num_chunks
        FROM timescaledb_information.chunks GROUP BY hypertable_name) c
  ON h.hypertable_name = c.hypertable_name
"

# Check data completeness
psql -c "
  SELECT 
    count(DISTINCT symbol) as symbols,
    count(*) as rows,
    min(date) as earliest,
    max(date) as latest
  FROM price_daily
"

# Performance test (before vs after)
# Before: EXPLAIN ANALYZE SELECT * FROM price_daily WHERE symbol='AAPL' AND date > '2025-01-01' LIMIT 10
# After:  Same query should be 100x faster
```

---

## Phase 5: Next Quick Wins (Week 2-3)

After Phase 1-2 succeeds:

### Quick Win #3: Watermark-based Incremental Loading (5 days)
- Load only data changed since last run
- 100-2500x reduction in API calls
- Expected savings: -$45/month

### Quick Win #4: Move Small Loaders to Lambda (5 days)
- 10 loaders → Lambda (sentiment, econdata, calendar, etc.)
- 70% cost reduction on those loaders
- Expected savings: -$25/month

### Quick Win #5: PostgreSQL Connection Pooling (3 days)
- Deploy pgBouncer ECS container
- Reuse connections, reduce latency
- 25% faster queries, -10% CPU

### Quick Win #6: S3 Lifecycle Policies (1 day)
- Archive old backups to Glacier
- -$20/month

---

## Success Criteria

### Phase 1 Complete ✅
- [ ] TimescaleDB extension enabled
- [ ] All price tables converted to hypertables
- [ ] CloudWatch dashboard shows 10-100x query speedup
- [ ] Cost remains under $2/run

### Phase 2 Complete ✅
- [ ] Multi-source OHLCV loader runs without errors
- [ ] All 2,847 symbols loaded successfully
- [ ] Data quality validation passes (0 invalid prices)
- [ ] Cost under $2/run

### Budget Control ✅
- [ ] Daily spend < $50
- [ ] Monthly spend trending toward $50 (from $150)
- [ ] Cost alarm configured and tested

### Data Quality ✅
- [ ] All 2,847 symbols have OHLCV data
- [ ] No zero-volume bars in last 30 days
- [ ] No invalid price relationships (high < low)
- [ ] No negative prices
- [ ] Duplication check passed

---

## Rollback Plan

If optimizations cause issues:

```bash
# Rollback TimescaleDB (keep tables, just disable hypertables)
psql -c "SELECT drop_hypertable('price_daily')"

# Revert to yfinance-only
git revert <commit-hash>
git push

# Restore from backup
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier stocks-db-restored \
  --db-snapshot-identifier stocks-db-backup-20250503
```

---

## Cost Summary

| Optimization | Effort | Cost | Savings | ROI |
|---|---|---|---|---|
| **TimescaleDB** | 1 day | $0 | -$0 | Infinite (10-100x speedup) |
| **Multi-source OHLCV** | 2 days | $1.50/run | -$30/mo | 20:1 |
| **Watermarks** | 5 days | $0 | -$45/mo | Infinite |
| **Lambda migration** | 5 days | $0.50/run | -$25/mo | 50:1 |
| **pgBouncer** | 3 days | $10/mo | -$10/mo | Break-even |
| **S3 lifecycle** | 1 day | $0 | -$20/mo | Infinite |
| **────────** | | | | |
| **TOTAL** | **17 days** | **+$12/mo** | **-$130/mo** | **10:1** |

**Bottom line**: 17 days of work for -$118/month net savings (81% cost reduction) + 10-100x speedup.

---

## Questions?

See `/cli/help` or check logs:
```bash
# GitHub Actions logs
gh run view <run-id>

# AWS CloudWatch
aws logs tail /ecs/stocks-app-dev --follow

# Database diagnostics
psql -d stocks -c "SELECT * FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10"
```
