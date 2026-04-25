# Data Loading Status Report - 2026-04-24

## Executive Summary
The database has **64 tables** with significant data, but **critical gaps exist** in:
1. Tables that APIs are calling don't match actual schema names
2. Empty/sparse tables (10+ expected data tables missing data)
3. Loader errors blocking Windows Python processes
4. Partial symbol coverage due to signal/SIGALRM incompatibility

---

## Tables Currently Populated (Row Counts)

### ✅ Solid Data (10k+ rows)
- **price_daily**: 322,213 rows (core price data across symbols)
- **etf_price_daily**: 277,943 rows (ETF price history)
- **technical_data_monthly**: 118,521 rows (monthly technical indicators)
- **quarterly_cash_flow**: 64,909 rows
- **quarterly_balance_sheet**: 64,796 rows  
- **quarterly_income_statement**: 64,702 rows
- **technical_data_weekly**: 49,378 rows
- **annual_income_statement**: 17,478 rows
- **annual_cash_flow**: 17,433 rows
- **annual_balance_sheet**: 17,365 rows
- **earnings_history**: 19,999 rows

### ⚠️ Partially Loaded (100-5k rows)
- **stock_symbols**: 4,969 rows (all 4,969 stocks loaded)
- **company_profile**: 4,969 rows (has sector/industry data)
- **sector_ranking**: 3,566 rows (has 11 columns - missing performance metric)
- **industry_ranking**: 2,188 rows
- **earnings_estimates**: **4 rows** ← CRITICAL: Nearly empty
- **analyst_sentiment_analysis**: 3,459 rows
- **institutional_positioning**: 3,320 rows
- **economic_data**: 3,060 rows
- **sector_technical_data**: 2,678 rows
- **analyst_upgrade_downgrade**: 1,961 rows

### 🔴 Empty Tables (0 rows - APIs call these!)
- **earnings_data** ← Called by API, doesn't exist
- **company_stats** ← Called by API, doesn't exist  
- **daily_prices** ← Called by API, actually named `price_daily`
- **weekly_prices** ← Called by API, actually named `price_weekly`
- **stock_scores** (0 rows)
- **quality_metrics** (0 rows)
- **stability_metrics** (0 rows)
- **value_metrics** (0 rows)

### ❌ Database Schema Mismatch
- `stability_metrics`, `sector_performance`, `commodity_correlations`, `social_sentiment_analysis` → estimated **-1 rows** (schema inconsistency)

---

## Root Cause Analysis

### Issue #1: API Routes Call Wrong Table Names
**File**: `webapp/lambda/routes/earnings.js` (and others)
```javascript
// APIs call these:
SELECT * FROM earnings_data     // ← DOESN'T EXIST
SELECT * FROM daily_prices      // ← Actually "price_daily"
SELECT * FROM company_stats     // ← DOESN'T EXIST
```

**What actually exists**:
- `earnings_history` (19,999 rows)
- `price_daily` (322,213 rows)
- `company_profile` (4,969 rows)

---

### Issue #2: Loader Script Errors on Windows
**File**: `loaddailycompanydata.py`

#### Error 1: Database Connection Failed Initially
```
psycopg2.OperationalError: connection to server at "localhost" (::1), port 5432 failed
Is the server running on that host and accepting TCP/IP connections?
```
**Status**: Resolved - database now running, connections work

#### Error 2: signal.SIGALRM Not Available on Windows
```python
# In fetch_yfinance_data():
signal.signal(signal.SIGALRM, timeout_handler)  # ← Unix only!
```
**Impact**: ~1000+ symbols (CTRM, CTRN, CTS, CTSH, CTVA...) have NO stats loaded
**Result**: 
- All company stats data missing
- Earnings estimates mostly empty (only 4 rows)
- yfinance timeout protection completely broken

---

### Issue #3: Missing Data Tables

| Expected | Actually In DB | Row Count | Status |
|----------|---|---|---|
| earnings_data | earnings_history | 19,999 | ✅ Loaded but wrong schema |
| daily_prices | price_daily | 322,213 | ✅ Loaded but APIs use wrong name |
| company_stats | None | 0 | 🔴 Loader failed due to SIGALRM |
| earnings_estimates | earnings_estimates | 4 | 🔴 Loader didn't finish |

---

## Critical Data Gaps

### 1. **Company Stats Completely Missing** (0 rows)
- **Expected from**: `loaddailycompanydata.py`
- **Why failing**: Python's `signal.SIGALRM` doesn't exist on Windows
- **Impact**: No PE ratios, dividend yields, market cap, beta — metrics APIs need
- **Affected symbols**: ~1,000+ (any symbol that needed timeout handling)

### 2. **Earnings Estimates Nearly Empty** (4 rows instead of 5000+)
- **Expected from**: Earnings loader (likely stopped early)
- **Why**: Likely upstream dependency (company_stats needed first?)
- **Impact**: All EPS forecasts, revenue estimates missing

### 3. **Sector Ranking Incomplete** (3,566 rows)
- **Schema mismatch**: APIs expect `performance`, `change_pct`, but actual columns are:
  - `daily_strength_score`, `momentum_score`, `trend`
  - No `performance` or `change_pct` columns
- **Data quality**: Only 3,566 sector records across all dates/sectors

### 4. **Technical Data Sparse for Daily** (28,914 rows)
- Need to verify: how many distinct symbols? date range?
- Only ~1.4% of `price_daily` rows (322k) have technical data

---

## Loader Log Findings

**File**: `./loader_logs/04-company-data_loaddailycompanydata.log` (750 KB)

### Errors Found
```
ERROR - Non-retriable error in fetch_yfinance_data: module 'signal' has no attribute 'SIGALRM'
WARNING - All fetch attempts failed for CTRM: module 'signal' has no attribute 'SIGALRM'
WARNING - Could not fetch any data for CTRM after 3 retries - skipping
WARNING - CTRM: No stats returned
```

### Impacted Symbols
- CTRM, CTRN, CTS, CTSH, CTVA, (and many more starting with C, D, E...)
- **Estimate**: ~1,000+ symbols skipped

### Loader Status
- `loadstocksymbols.py`: ✅ COMPLETED
- Other loaders: 🔴 PARTIALLY FAILED (symbol loading worked, stats/estimates didn't)

---

## What This Means for Your APIs

### Current Situation
1. **Frontend calls** `/api/earnings` → queries `earnings_data` → 404/empty result
2. **Frontend calls** `/api/company-stats` → queries `company_stats` → 404/empty result
3. **Frontend calls** `/api/stocks/AAPL/stats` → might work if price_daily has it, but company_stats is missing

### What Actually Works
- Price data endpoints (has 322k rows of daily prices)
- Sector/industry rankings (has ~3.5k records)
- Earnings history (has 20k records but wrong name in some APIs)

### What's Broken
- All endpoints querying `earnings_data`, `company_stats`, `daily_prices` (wrong names)
- Any stock fundamental metrics (PE, yield, beta, etc.)
- Earnings projections (4 rows vs thousands needed)

---

## Recommended Actions (Priority Order)

### 🔴 CRITICAL (Do First)
1. **Fix table name mismatches** in API routes
   - `earnings_data` → use `earnings_history` OR reload with correct target
   - `daily_prices` → rename to `price_daily` OR update all API calls
   - `company_stats` → needs to be created/loaded

2. **Fix Python loader SIGALRM error**
   - Replace Unix signal handling with threading timeout
   - Re-run loaddailycompanydata.py to populate company_stats

3. **Verify earnings_estimates data flow**
   - Check why only 4 rows loaded
   - Re-run earnings loader

### ⚠️ IMPORTANT (Do Second)
4. **Verify sector_ranking schema**
   - APIs expect `performance`, `change_pct`
   - DB has `daily_strength_score`, `momentum_score`
   - Either update API queries or reload with correct schema

5. **Add logging to loaders**
   - Each loader should log: symbols processed, errors encountered, row counts
   - Make it visible in frontend health dashboard

### 📊 NICE-TO-HAVE (Do Third)
6. **Create data quality dashboard**
   - Show table row counts and date ranges
   - Alert when expected data is missing
   - Track loader success/failure rates

7. **Document data schema**
   - What does each column mean?
   - Where does it come from?
   - How often is it updated?

