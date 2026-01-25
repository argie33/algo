# 🔴 CRITICAL ISSUES - Loader Roadmap & Missing Data

## Frontend Error: No Trading Signals

**Error**: `TradingSignals.jsx:62 - Failed to fetch`
```
API: https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev/api/signals/stocks
Response: NO SIGNALS FOUND FOR DAILY - Database is empty
```

**Root Cause**: Buy/sell signal loaders never completed
- `loadbuyselldaily` - OFFLINE (needs to run)
- `loadbuysellweekly` - OFFLINE (needs to run)  
- `loadbuysellmonthly` - OFFLINE (needs to run)

---

## Data Dependency Chain - What Needs to Run

### TIER 1: FOUNDATION (MUST RUN FIRST)
```
❌ loadstocksymbols.py
   └─ Populates: stock_symbols table
   └─ Required by: ALL other loaders

❌ loadbenchmark.py
   └─ Populates: benchmark prices (SPY, QQQ, etc)
   └─ Required by: Beta calculations in stock scores
```

### TIER 2: PRICE DATA (CRITICAL)
```
❌ loadpricedaily.py
   └─ Populates: price_daily table
   └─ Required by: Technical analysis, scoring, signals
   └─ Issue: Missing stock_splits column in database

❌ loadlatestpricedaily.py
   └─ Populates: latest_prices snapshot
   └─ Required by: API endpoints showing current prices
```

### TIER 3: FINANCIAL DATA
```
❌ loadannualbalancesheet.py
❌ loadannualcashflow.py
❌ loadannualincomestatement.py
❌ loadquarterlybalancesheet.py
❌ loadquarterlycashflow.py
❌ loadquarterlyincomestatement.py
❌ loadttmincomestatement.py
❌ loadttmcashflow.py
   └─ Populate: Financial statement tables
   └─ Required by: Quality metrics, fundamental analysis
```

### TIER 4: EARNINGS & SENTIMENT
```
❌ loadearningshistory.py
   └─ Populates: earnings table
   └─ Required by: Stock scores (earnings yield component)

❌ loadanalystsentiment.py
❌ loadanalystupgradedowngrade.py
   └─ Issue: Missing columns in database
   └─ Required by: Stock scores (sentiment component)

❌ loadaaiidata.py
❌ loadnaaim.py
❌ loadfeargreed.py
   └─ Populate: Sentiment/alternative data
   └─ Required by: Risk assessment components
```

### TIER 5: METRICS CALCULATION
```
❌ loadfundamentalmetrics.py
   └─ Populates: fundamental_metrics table
   └─ Requires: Tier 3 data

❌ loadpositioningmetrics.py
❌ loadfactormetrics.py
   └─ Populate: Specialized metrics
   └─ Requires: Price data + fundamentals
```

### TIER 6: STOCK SCORES (CRITICAL)
```
❌ loadstockscores.py
   └─ Populates: stock_scores table
   └─ Requires: ALL of Tier 1-5
   └─ Status: Has critical missing columns blocking it
   └─ Impact: Powers entire dashboard
```

### TIER 7: TRADING SIGNALS (BLOCKING FRONTEND)
```
❌ loadbuysellweekly.py
❌ loadbuyselldaily.py
❌ loadbuysellmonthly.py
   └─ Populates: buy_sell_signals table
   └─ Requires: Stock scores from Tier 6
   └─ Status: OFFLINE - causing "NO SIGNALS FOUND" errors
   └─ Impact: TradingSignals component fails
```

---

## Critical Database Issues Blocking Loaders

### Issue 1: Missing `stock_splits` Column
```
Table: price_daily
Error: psycopg2.errors.UndefinedColumn: column "stock_splits" does not exist
Loader: loadpricedaily.py
Status: FAILED
Fix: ALTER TABLE price_daily ADD COLUMN stock_splits DECIMAL(10,6);
```

### Issue 2: Missing Columns in analyst_recommendations
```
Table: analyst_recommendations
Missing: bullish_count, bearish_count, neutral_count
Loader: loadanalystsentiment.py, loadanalystupgradedowngrade.py
Status: BLOCKED
Fix: Add columns to analyst_recommendations table
```

### Issue 3: Missing Columns in sector_performance
```
Table: sector_performance
Missing: sector column
Loader: loadsectorranking.py
Status: BLOCKED
```

---

## APIs Currently Failing

### 1. Trading Signals API ❌
```
Endpoint: GET /api/signals/stocks?timeframe=daily|weekly|monthly
Status: Returns empty
Reason: loadbuysellweekly/daily/monthly never ran
Fix: Run signal loaders after stock scores complete
```

### 2. Stock Scores API ❌
```
Endpoint: GET /api/stocks/scores
Status: Incomplete/partial data
Reason: Missing analyst recommendation columns
Fix: Add missing columns + run loadanalystsentiment
```

### 3. Price Data APIs ❌
```
Endpoint: GET /api/prices/daily, /api/prices/latest
Status: Failed with UndefinedColumn error
Reason: stock_splits column missing
Fix: Add column to price_daily table
```

### 4. Financial Data APIs ❌
```
Endpoint: GET /api/fundamentals/*
Status: Empty/missing data
Reason: Financial statement loaders offline
Fix: Run Tier 3 loaders
```

---

## AWS ECS vs Local Loaders

### AWS ECS (OFFLINE ❌)
```
Status: CloudFormation ROLLBACK_COMPLETE
Running: 0 services, 0 tasks
Logs: 0 entries (45+ log groups empty)
Issue: Stack deployment failed, rolled back
Fix: Delete stack and redeploy via GitHub Actions
```

### Local Python Loaders (PARTIALLY RUNNING ✅)
```
Status: 11 processes running
Issue: Missing database column (stock_splits)
Running: loadpricedaily, loadpriceweekly, etc
Fix: Add stock_splits column, restart loaders
```

---

## Execution Plan - Priority Order

### IMMEDIATE (Do Now - 30 min)
```
1. Fix database schema:
   ALTER TABLE price_daily ADD COLUMN stock_splits DECIMAL(10,6);
   
2. Fix analyst_recommendations table:
   ALTER TABLE analyst_recommendations 
   ADD COLUMN bullish_count INTEGER,
   ADD COLUMN bearish_count INTEGER,
   ADD COLUMN neutral_count INTEGER;

3. Restart local loaders:
   bash start_loaders.sh
```

### SHORT-TERM (1-2 hours)
```
4. Wait for local loaders to complete:
   - loadpricedaily
   - loadpriceweekly
   - loadpricemonthly
   
5. Run foundational loaders:
   - loadstocksymbols
   - loadbenchmark
   
6. Run financial statement loaders:
   - loadannualbalancesheet
   - loadannualcashflow
   - loadannualincomestatement
   - quarterly versions
```

### MEDIUM-TERM (2-4 hours)
```
7. Run sentiment/earnings loaders:
   - loadearningshistory
   - loadanalystsentiment
   - loadanalystupgradedowngrade
   - loadaaiidata, loadnaaim, loadfeargreed

8. Run metrics loaders:
   - loadfundamentalmetrics
   - loadfactormetrics
   - loadpositioningmetrics

9. Run master scoring:
   - loadstockscores
```

### FINAL (After all above complete)
```
10. Run trading signal loaders:
    - loadbuysellweekly
    - loadbuyselldaily
    - loadbuysellmonthly
    
    Result: TradingSignals component will show data
```

### LONG-TERM (Parallel with above)
```
11. Deploy AWS ECS stack:
    - Delete failed CloudFormation stack
    - Redeploy via GitHub Actions
    - Configure all 59 loaders as ECS services
```

---

## Current Blocking Issues Summary

| Issue | Impact | Severity | Fix |
|-------|--------|----------|-----|
| Missing stock_splits column | Price loaders fail | 🔴 CRITICAL | ALTER TABLE |
| Missing analyst columns | Stock scores incomplete | 🔴 CRITICAL | ALTER TABLE |
| AWS ECS stack ROLLBACK | No production loaders | 🔴 CRITICAL | Delete & redeploy |
| Local loaders stalled | Data not updating | 🟠 HIGH | Restart + schema fix |
| TradingSignals empty | Frontend broken | 🔴 CRITICAL | Run signal loaders |

---

## Monitoring Commands

```bash
# Check local loaders
ps aux | grep "load.*\.py" | grep python3 | wc -l

# Check loader progress
tail -20 /home/stocks/algo/loadpricedaily.log

# Check database data
psql -U stocks -d stocks -h stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com << 'SQL'
SELECT 
  'price_daily' as table_name, COUNT(*) as row_count FROM price_daily
UNION ALL
SELECT 'stock_scores', COUNT(*) FROM stock_scores
UNION ALL
SELECT 'buy_sell_signals', COUNT(*) FROM buy_sell_signals;
SQL

# Test APIs
curl https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev/api/signals/stocks?timeframe=daily | jq '.[] | length'
```

---

**Status**: 🔴 **CRITICAL - Multiple blockers preventing data flow**
**Next Step**: Fix database schema + restart loaders
**Timeline**: Full recovery ~4-6 hours after fixes applied

