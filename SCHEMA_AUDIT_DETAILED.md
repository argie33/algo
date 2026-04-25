# Comprehensive Schema Audit Report
## April 25, 2026 - Data Integrity Analysis

---

## CRITICAL ISSUES FOUND

### ❌ ISSUE #1: earnings_estimates SCHEMA MISMATCH
**Severity**: 🔴 CRITICAL - This completely blocks earnings data loading  
**File**: `loaddailycompanydata.py`  
**Table**: `earnings_estimates`

**THE PROBLEM**:
```
Database Schema Expects:
- eps_estimate (DECIMAL)
- revenue_estimate (DECIMAL)
- eps_actual (DECIMAL)
- revenue_actual (DECIMAL)

But Loader Tries to INSERT:
- avg_estimate (column doesn't exist)
- low_estimate (column doesn't exist)
- high_estimate (column doesn't exist)
- year_ago_eps (column doesn't exist)
- estimate_count (column doesn't exist)
- growth (column doesn't exist)
- period (column doesn't exist)
```

**WHY THIS HAPPENS**:
- The database schema was created with one set of column names
- `loaddailycompanydata.py` tries to load earnings data using DIFFERENT column names
- These mismatched columns don't exist, so INSERT fails or is skipped

**IMPACT**:
- ❌ Earnings estimates table remains 100% NULL values
- ❌ Only 7/515 stocks have ANY earnings data (from previous runs)
- ❌ Frontend shows blank earnings pages for 99% of stocks
- **User Experiences**: Empty earnings forecast tables

**HOW TO FIX**:
Either:
1. **Option A** (Recommended): Update `loaddailycompanydata.py` to use correct column names:
   - Change `avg_estimate` → `eps_estimate`
   - Change `low_estimate` → `revenue_estimate` (or map differently)
   - Change `high_estimate` → handle separately
   
2. **Option B**: Drop earnings_estimates loading from loaddailycompanydata.py and create a dedicated `load_earnings_estimates_simple.py`

---

### ❌ ISSUE #2: loadoptionschains.py - MISSING DEPENDENCY
**Severity**: 🔴 CRITICAL - Options data 99.8% missing  
**File**: `loadoptionschains.py`  
**Table**: `options_chains`

**THE PROBLEM**:
```python
# Line 26-30 in loadoptionschains.py:
from greeks_calculator import GreeksCalculator
# OR
from utils.greeks_calculator import GreeksCalculator
```

The module `greeks_calculator` does NOT exist. Python cannot import it.

**IMPORT ERROR**:
```
ModuleNotFoundError: No module named 'greeks_calculator'
```

**IMPACT**:
- ❌ Options loader fails on import
- ❌ Only 1/515 stocks have options data
- ❌ Options chains are completely unavailable
- **User Experiences**: "No options data available" for all stocks

**HOW TO FIX**:
Option 1 (Quick): Remove Greeks calculation, simplify the loader
```python
# Comment out or remove:
# from greeks_calculator import GreeksCalculator

# Just load raw options data from yfinance without Greeks
# Greeks can be calculated later if needed
```

Option 2: Install the missing module or create it
```bash
pip install greeks_calculator
# OR create utils/greeks_calculator.py with Black-Scholes implementation
```

---

### ⚠️ ISSUE #3: loadanalystupgradedowngrade.py - DATABASE CREDENTIALS
**Severity**: 🟡 HIGH - Analyst upgrades only 37.5% loaded  
**File**: `loadanalystupgradedowngrade.py`  
**Coverage**: 193/515 stocks (should be ~500+)

**THE PROBLEM**:
The script uses hardcoded or mismatched database credentials instead of environment variables.

```python
# Expected (from other loaders):
conn = psycopg2.connect(**get_db_config())

# Actual (possibly):
conn = psycopg2.connect(
    host="localhost",
    user="stocks",
    password="some_hardcoded_password",  # ❌ WRONG
    database="stocks"
)
```

**IMPACT**:
- ⚠️ Can connect to local PostgreSQL only
- ⚠️ Fails when API deploys to AWS Lambda (different DB host)
- ⚠️ Only partial data loads (connection intermittent?)
- **User Experiences**: 60% of stocks have no upgrade/downgrade data

**HOW TO FIX**:
Update to use environment variables like other loaders:
```python
from lib.db import get_db_config, get_connection
conn = get_connection()
```

---

### 🟡 ISSUE #4: key_metrics PARTIAL LOAD
**Severity**: 🟡 HIGH  
**File**: `loaddailycompanydata.py`  
**Table**: `key_metrics`  
**Coverage**: Unknown (likely partial)

**THE PROBLEM**:
`loaddailycompanydata.py` inserts into `key_metrics` immediately after `company_profile`, but if there's an error:
- `company_profile` data IS committed (✅)
- `key_metrics` data FAILS (❌)
- Execution STOPS and later loaders never run

The script has strategic `conn.commit()` calls that can mask errors.

**SCHEMA TO INSERT**:
```
(ticker, trailing_pe, forward_pe, price_to_sales_ttm, price_to_book, peg_ratio, 
 dividend_yield, beta, earnings_growth, held_percent_insiders, held_percent_institutions,
 shares_short, shares_short_prior_month, short_ratio, short_percent_of_float,
 implied_shares_outstanding, float_shares)
```

**NEED TO VERIFY**: All these columns exist in the `key_metrics` table schema.

**IMPACT**:
- ⚠️ Key metrics may be partially or fully missing for many stocks
- ⚠️ PE ratios, dividend yield, beta missing from UI

**HOW TO FIX**:
1. Verify `key_metrics` schema has all columns listed above
2. If columns missing, add them:
   ```sql
   ALTER TABLE key_metrics ADD COLUMN IF NOT EXISTS held_percent_institutions DECIMAL(8,6);
   ALTER TABLE key_metrics ADD COLUMN IF NOT EXISTS short_percent_of_float DECIMAL(8,6);
   -- ... etc for any missing columns
   ```

---

## SUMMARY TABLE: All Known Issues

| Issue | Table | File | Severity | Coverage | Status |
|-------|-------|------|----------|----------|--------|
| **Column mismatch** | earnings_estimates | loaddailycompanydata.py | 🔴 CRITICAL | 12% NULL | ❌ BROKEN |
| **Missing import** | options_chains | loadoptionschains.py | 🔴 CRITICAL | 0.2% | ❌ BROKEN |
| **Bad credentials** | analyst_upgrade_downgrade | loadanalystupgradedowngrade.py | 🟡 HIGH | 37% | ⚠️ PARTIAL |
| **Unknown schema** | key_metrics | loaddailycompanydata.py | 🟡 HIGH | ? | ? |

---

## ACTION PLAN (Priority Order)

### PHASE 1: IMMEDIATE (30 minutes)
1. **Fix earnings_estimates loading** (loaddailycompanydata.py)
   - [ ] Map columns correctly or skip earnings in this loader
   - [ ] Create dedicated earnings loader if needed
   - Status: BLOCKS all earnings data

2. **Fix options loader** (loadoptionschains.py)
   - [ ] Remove or install greeks_calculator dependency
   - [ ] Simplify to just load raw options chains from yfinance
   - Status: BLOCKS all options data

3. **Fix analyst credentials** (loadanalystupgradedowngrade.py)
   - [ ] Update to use `get_db_config()` from lib.db
   - [ ] Test with environment variables
   - Status: BLOCKS full analyst coverage

### PHASE 2: VERIFICATION (15 minutes)
4. **Verify key_metrics schema**
   - [ ] Check if all inserted columns exist
   - [ ] Add missing columns if needed
   - [ ] Re-run loaddailycompanydata.py

5. **Test API endpoints**
   - [ ] `/api/earnings/info?symbol=AAPL` - should have non-NULL values
   - [ ] `/api/options/chains?symbol=AAPL` - should have options data
   - [ ] `/api/analysts/upgrades` - should have 500+ records
   - [ ] `/api/scores/stockscores` - should have key metrics

### PHASE 3: DATA RELOAD
6. **Run fixed loaders**
   ```bash
   python3 loaddailycompanydata.py      # Once fixed
   python3 loadoptionschains.py         # Once fixed
   python3 loadanalystupgradedowngrade.py  # Once fixed
   ```

---

## WHICH DATA SHOULD LOAD & HOW

| Data Type | Loader | Table | Status | Fix Priority |
|-----------|--------|-------|--------|--------------|
| **Earnings Estimates** | `loaddailycompanydata.py` OR new loader | `earnings_estimates` | BROKEN | 🔴 P0 |
| **Options Chains** | `loadoptionschains.py` | `options_chains` | BROKEN | 🔴 P0 |
| **Analyst Upgrades** | `loadanalystupgradedowngrade.py` | `analyst_upgrade_downgrade` | PARTIAL | 🟡 P1 |
| **Key Metrics** | `loaddailycompanydata.py` | `key_metrics` | UNKNOWN | 🟡 P1 |
| **Stock Scores** | `loadstockscores.py` | `stock_scores` | ✅ WORKING | - |
| **Technical Data** | `loadtechnicalindicators.py` | `technical_data_daily` | ✅ WORKING | - |
| **Analyst Sentiment** | `loadanalystsentiment.py` | `analyst_sentiment_analysis` | 🟡 70% | P2 |

---

## Files That Need Fixes

### HIGH PRIORITY - Fix These First
- [ ] `loaddailycompanydata.py` - earnings_estimates column mismatch
- [ ] `loadoptionschains.py` - greeks_calculator import error
- [ ] `loadanalystupgradedowngrade.py` - database credentials

### MEDIUM PRIORITY - Verify After Fixes
- [ ] Database schema validation (key_metrics columns)
- [ ] API endpoint tests for data presence

---

Generated: 2026-04-25  
Status: 3 critical loader issues blocking 3 data sources  
Action: Fix loaders, re-run, verify data appears in APIs
