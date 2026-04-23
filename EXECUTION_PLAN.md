# 🚀 COMPLETE EXECUTION PLAN - Data to Display to Deployment

**Status**: All critical blockers fixed. Ready to load data.  
**Timeline**: ~10-12 hours for full completion  
**Approach**: Sequential loading with validation at each stage

---

## Phase 0: DONE ✅

- [x] Fix Windows path compatibility (6 loaders)
- [x] Fix emoji encoding (44 loaders)
- [x] Fix schema mismatches
- [x] Commit all fixes

---

## Phase 1: FOUNDATION DATA (2-3 hours)

**Objective**: Load minimal viable dataset to make stock scores work

### Step 1.1: Load Daily Prices (60-90 min)
```bash
python3 loadpricedaily.py
```
**Expected**: 22.2M price records in `price_daily`  
**Validates**: Basic price data pipeline works  
**Blocker**: Everything else depends on this

### Step 1.2: Expand price data (30 min parallel)
```bash
# Parallel (can run all 3 together)
python3 loadpriceweekly.py  # ~4M records
python3 loadpricemonthly.py # ~600K records
python3 loadlatestpricedaily.py  # Latest prices
```

### Step 1.3: Load Company Data (45-60 min)
```bash
python3 loaddailycompanydata.py
```
**Expected**: Creates `key_metrics` table (required by factor metrics)  
**Validates**: yfinance API integration works  
**Critical**: Blocks factor metrics loading

### Validation After Phase 1:
```python
import psycopg2, os
conn = psycopg2.connect(host='localhost', database='stocks', user='stocks', 
                        password=os.getenv('DB_PASSWORD', 'bed0elAn'))
cur = conn.cursor()

# Check counts
tables = [
    ('price_daily', 22000000),      # Should be ~22M
    ('key_metrics', 5000),          # Should be ~5K
    ('stock_symbols', 4900),        # Should be ~4.9K
]

for table, expected in tables:
    cur.execute(f'SELECT COUNT(*) FROM {table}')
    actual = cur.fetchone()[0]
    pct = (actual / expected * 100) if expected else 0
    print(f"{table:25} {actual:>12,} / {expected:>12,} ({pct:>5.1f}%)")
```

---

## Phase 2: FINANCIAL STATEMENTS (2-3 hours)

**Objective**: Load fundamental data needed for quality/growth metrics

### Step 2.1: Annual Financials (45 min - 2 hours parallel)
```bash
# Can run in parallel - independent data sources
python3 loadannualincomestatement.py    # ~20K records
python3 loadannualbalancesheet.py       # ~7K records
python3 loadannualcashflow.py           # ~20K records
```

### Step 2.2: Quarterly Financials (60 min - parallel)
```bash
python3 loadquarterlyincomestatement.py # ~27K records
python3 loadquarterlybalancesheet.py    # ~10K records
python3 loadquarterlycashflow.py        # ~11K records
```

### Step 2.3: Earnings Data (30 min - parallel)
```bash
python3 loadearningshistory.py
python3 loadearningsmetrics.py
python3 loadearningssurprise.py
```

### Validation After Phase 2:
```python
financial_tables = [
    'annual_income_statement',
    'annual_balance_sheet', 
    'annual_cash_flow',
    'quarterly_income_statement',
    'quarterly_balance_sheet',
    'quarterly_cash_flow',
]

for table in financial_tables:
    cur.execute(f'SELECT COUNT(*) FROM {table}')
    count = cur.fetchone()[0]
    print(f"{table:40} {count:>12,} rows")
    
# Should see: 20K+, 7K+, 20K+, 27K+, 10K+, 11K+ respectively
```

---

## Phase 3: FACTOR METRICS (1-2 hours)

**Objective**: Calculate all intermediate metrics (quality, growth, value, stability)

### Step 3.1: Load All Factor Metrics
```bash
python3 loadfactormetrics.py
```

**Expected Output**:
- `quality_metrics`: ~5K records
- `growth_metrics`: ~5K records  
- `value_metrics`: ~5K records
- `stability_metrics`: ~5K records
- `momentum_metrics`: Already loaded (4,943 rows)
- `positioning_metrics`: 0 rows (no data source yet)

**Validates**: All intermediate metrics calculated correctly

### Validation After Phase 3:
```python
factor_tables = [
    'quality_metrics',
    'growth_metrics',
    'value_metrics',
    'stability_metrics',
    'momentum_metrics',
]

for table in factor_tables:
    cur.execute(f'SELECT COUNT(*) FROM {table}')
    count = cur.fetchone()[0]
    expected = 4943 if table == 'momentum_metrics' else 5000
    pct = count / expected * 100 if expected else 0
    status = "OK" if count > expected * 0.9 else "PROBLEM"
    print(f"[{status}] {table:30} {count:>12,} ({pct:>5.1f}%)")
```

---

## Phase 4: STOCK SCORES (30 minutes)

**Objective**: Calculate composite scores for all stocks

### Step 4.1: Load Stock Scores
```bash
python3 loadstockscores.py
```

**Expected**: 4,996 stock scores  
**Depends on**: All factor metrics from Phase 3

### Validation After Phase 4:
```python
cur.execute('SELECT COUNT(*) FROM stock_scores')
count = cur.fetchone()[0]
print(f"stock_scores: {count} (expected: 4996)")

# Sample a few scores to verify calculation
cur.execute('SELECT symbol, quality_score, growth_score, value_score, stability_score FROM stock_scores LIMIT 5')
for row in cur.fetchall():
    print(row)
```

---

## Phase 5: TRADING SIGNALS (4-6 hours)

**Objective**: Calculate daily/weekly/monthly buy/sell signals

### Step 5.1: Daily Signals (2-3 hours)
```bash
python3 loadbuyselldaily.py
```
**Expected**: 133K+ daily signals

### Step 5.2: Weekly Signals (1-2 hours - parallel)
```bash
python3 loadbuysellweekly.py
```
**Expected**: 24K+ weekly signals

### Step 5.3: Monthly Signals (1-2 hours - parallel)
```bash
python3 loadbuysellmonthly.py
```
**Expected**: 7K+ monthly signals

### Step 5.4: ETF Signals (3-4 hours - parallel if you have ETF data)
```bash
python3 loadbuysell_etf_daily.py
python3 loadbuysell_etf_weekly.py
python3 loadbuysell_etf_monthly.py
```

### Validation After Phase 5:
```python
signal_tables = [
    ('buy_sell_daily', 133000),
    ('buy_sell_weekly', 24000),
    ('buy_sell_monthly', 7000),
]

for table, expected in signal_tables:
    cur.execute(f'SELECT COUNT(*) FROM {table}')
    count = cur.fetchone()[0]
    pct = count / expected * 100 if expected else 0
    print(f"{table:25} {count:>12,} ({pct:>5.1f}%)")
```

---

## Phase 6: MARKET CONTEXT DATA (1-2 hours - parallel)

**Objective**: Load sector, industry, and economic context

### Step 6.1: Sector & Industry (30 min - parallel)
```bash
python3 loadsectorranking.py         # Sector performance
python3 loadindustryranking.py       # Industry performance
python3 loadsectors.py               # Sector definitions
```

### Step 6.2: Market Indices & Economic (30 min - parallel)
```bash
python3 loadmarketindices.py         # Market indices
python3 loadecondata.py              # Economic indicators
python3 loadbenchmark.py             # Benchmark comparisons
```

### Step 6.3: Analyst Data (30 min)
```bash
python3 loadanalystupgradedowngrade.py  # Analyst ratings (1.3M records)
python3 loadanalystsentiment.py         # Analyst sentiment
python3 loadsentiment.py                # General sentiment
```

---

## Phase 7: OPTIONAL ENHANCEMENT DATA (2-3 hours)

These are nice-to-have but not required for UI to work:

```bash
python3 loadnews.py                    # Stock news (API-limited)
python3 loadcalendar.py               # Economic calendar
python3 loadoptionschains.py          # Options data (sparse)
python3 loadcommodities.py            # Commodity prices
python3 loadfeargreed.py              # Fear & Greed index
python3 loadnaaim.py                  # AAII sentiment
```

---

## VALIDATION AFTER ALL LOADING

### Database Completeness Check
```python
import psycopg2, os

conn = psycopg2.connect(host='localhost', database='stocks', user='stocks',
                        password=os.getenv('DB_PASSWORD', 'bed0elAn'))
cur = conn.cursor()

# Get all tables and row counts
cur.execute("""
    SELECT table_name FROM information_schema.tables 
    WHERE table_schema='public' ORDER BY table_name
""")

print("DATABASE COMPLETENESS CHECK")
print("=" * 70)

total_records = 0
for (table,) in cur.fetchall():
    cur.execute(f'SELECT COUNT(*) FROM {table}')
    count = cur.fetchone()[0]
    total_records += count
    status = "FULL" if count > 100 else "SPARSE" if count > 0 else "EMPTY"
    print(f"[{status:7}] {table:40} {count:>12,} rows")

print("=" * 70)
print(f"TOTAL: {total_records:,} records across all tables")
```

---

## API & FRONTEND TESTING

### Start Local Backend
```bash
# In webapp directory
node app.js  # or whatever your server is

# Verify API is running
curl http://localhost:3001/api/stocks | head -100
```

### Test Frontend
```bash
# Open browser
http://localhost:3001
```

### Verify Key Features
- [ ] Stock list displays with scores
- [ ] Filtering by metrics works
- [ ] Stock detail page shows all data
- [ ] Trading signals display correctly
- [ ] Sector/industry rankings show
- [ ] No broken links or 404s

---

## DEPLOYMENT TO AWS

Once local testing passes:

### Step 1: Create AWS Infrastructure
```bash
# CloudFormation or manual setup
aws rds create-db-instance \
  --db-instance-identifier stocks-prod \
  --db-instance-class db.t3.medium \
  --engine postgres \
  --master-username stocks \
  --master-user-password [SECURE-PASSWORD]
```

### Step 2: Migrate Database
```bash
# Dump from local
pg_dump -U stocks stocks > stocks-$(date +%Y%m%d).sql

# Restore to RDS (use AWS DMS for large databases)
psql -h [RDS-ENDPOINT] -U stocks < stocks-20260423.sql
```

### Step 3: Deploy Lambda Functions
```bash
# Package loaders as Lambda layers
zip -r loader-layer.zip python_packages/

# Deploy API Gateway + Lambda
aws lambda create-function --function-name stocks-api ...
```

### Step 4: Deploy Frontend
```bash
# Build and upload to S3/CloudFront
npm run build
aws s3 sync dist/ s3://[BUCKET]/
```

### Step 5: Setup Monitoring
```bash
# CloudWatch alarms
aws cloudwatch put-metric-alarm --alarm-name loader-failures ...

# Log groups
aws logs create-log-group --log-group-name /aws/lambda/stocks-api
```

---

## SUCCESS CRITERIA

✅ All database tables populated (Phase 1-7)  
✅ Stock list displays with scores  
✅ Filtering works across all metrics  
✅ Trading signals showing buy/sell dates  
✅ Zero 404 errors  
✅ API response time < 500ms  
✅ Frontend loads without console errors  
✅ AWS deployed and accessible  
✅ All data matches local database

---

## ESTIMATED TIMELINE

| Phase | Task | Duration | Status |
|-------|------|----------|--------|
| 0 | Fix blockers | 30 min | ✅ DONE |
| 1 | Foundation data | 2-3 hrs | ⏳ NEXT |
| 2 | Financial statements | 2-3 hrs | ⏳ |
| 3 | Factor metrics | 1-2 hrs | ⏳ |
| 4 | Stock scores | 30 min | ⏳ |
| 5 | Trading signals | 4-6 hrs | ⏳ |
| 6 | Market context | 1-2 hrs | ⏳ |
| 7 | Enhancements | 2-3 hrs | ⏳ |
| | **TOTAL (Core)** | **~12-16 hrs** | |
| | **API & Frontend** | 1-2 hrs | ⏳ |
| | **AWS Deployment** | 2-3 hrs | ⏳ |
| | **TOTAL (All)** | **~15-21 hrs** | |

---

## NEXT IMMEDIATE STEP

**Run Phase 1.1 NOW:**
```bash
python3 loadpricedaily.py
```

Monitor the output. Once complete, validate, then continue with Phase 1.2.

Should I start Phase 1.1 now?
