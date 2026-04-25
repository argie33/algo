# Data Loader Issues Summary - April 25, 2026

## Root Cause Analysis

### The "Holes Galore" Problem
Users see blank/empty data because data loaders are failing or producing incomplete results. When loaders fail partway through, data gets partially loaded:

```
Positioning: ✅ Inserted successfully for AA, AAL, AAME, AAON...
Key Metrics: ❌ FAILED - column "book_value" does not exist
Earnings: ⚠️ Partial - only 7 records in earnings_estimates table
```

This creates "holes" where some stocks have data and others don't.

---

## Critical Loader Issues

### 1. loaddailycompanydata.py - SCHEMA MISMATCH

**Problem:**
```
ERROR: column "book_value" of relation "key_metrics" does not exist
```

**What's Happening:**
- Loader successfully inserts positioning data ✅
- Loader successfully inserts insider transactions ✅
- Loader successfully inserts earnings history ✅
- Loader FAILS to insert key_metrics ❌

**Root Cause:**
The SQL INSERT statement tries to insert into columns that don't exist in key_metrics:
```python
# WRONG - trying to use columns that don't exist:
cur.execute("""
    INSERT INTO key_metrics (..., book_value, peg_ratio, ...)
    VALUES (...)
""")
```

**Actual key_metrics columns:**
- price_to_book (not book_value)
- peg_ratio ✓
- price_to_sales_ttm
- dividend_yield
- beta
- earnings_growth
- trailing_pe
- forward_pe
- etc.

**Impact:**
- Positioning data IS loaded (explains why we have 209/515)
- But other metrics from same loader incomplete

**Fix:**
Update SQL to use correct column names

---

### 2. loadoptionschains.py - MISSING DEPENDENCY

**Problem:**
```
Error importing greeks_calculator: No module named 'greeks_calculator'
```

**Root Cause:**
Script imports missing module for options Greeks calculation:
```python
from greeks_calculator import calculate_greeks  # ← MODULE NOT FOUND
```

**Impact:**
- Options chains loader fails completely
- Zero options data loaded (1/515 stocks)

**Fix:**
Either:
a) Install missing module: `pip install greeks_calculator`
b) Remove dependency and calculate Greeks differently
c) Skip Greeks calculation for now

---

### 3. loadanalystupgradedowngrade.py - BAD CREDENTIALS

**Problem:**
```
ERROR - Failed to connect to database: FATAL: password authentication failed
```

**Root Cause:**
Script uses hardcoded localhost credentials instead of environment:
```python
# WRONG - hardcoded credentials
conn = psycopg2.connect(
    host="localhost",
    user="stocks",
    password="hardcoded_password",
    database="stocks"
)

# Should use environment variables like other loaders
```

**Impact:**
- Analyst upgrade loader can't connect to DB
- Only 193/515 analyst recommendations loaded (from other sources?)

**Fix:**
Update to read from environment variables like `loaddailycompanydata.py` does

---

### 4. loadoptionsgreeks.py / loadoptionsdata.py - MISSING/INCOMPLETE

**Problem:**
Options data critically incomplete (1/515 stocks)

**Root Cause:**
Either loader doesn't exist, or fails silently

**Fix:**
Create or debug options data loader

---

## Loader Status Matrix

| Loader | Status | Coverage | Issue | Fix Priority |
|--------|--------|----------|-------|--------------|
| loaddailycompanydata.py | ⚠️ PARTIAL | Positioning: 209/515 | Schema mismatch on key_metrics | 🔴 P0 |
| loadoptionschains.py | ❌ FAILED | 1/515 | Missing greeks_calculator module | 🔴 P0 |
| loadanalystupgradedowngrade.py | ❌ FAILED | 193/515 | Bad database credentials | 🔴 P0 |
| loadearningsmetrics.py | ✅ PARTIAL | 7/515 | Limited data from API | 🟡 P1 |
| loadanalystsentiment.py | ✅ PARTIAL | 359/515 | Unknown - 30% gap | 🟡 P1 |
| loadstockscores.py | ✅ COMPLETE | 515/515 | - | - |
| loadtechnicalindicators.py | ✅ COMPLETE | 515/515 | - | - |

---

## Why This Causes "Blank" Frontend Fields

When user opens a stock detail page for AAPL, they expect to see:
- Earnings estimates → ❌ BLANK (API only has 7 stocks)
- Options chains → ❌ BLANK (only 1 stock loaded)
- Analyst upgrades → ❌ BLANK (missing for AAPL)
- Positioning → ❌ BLANK (if not in the 209 loaded)

The loaders are **failing silently** and the frontend shows empty objects.

---

## Action Plan (Priority Order)

### IMMEDIATE (FIX TODAY)
1. Fix loaddailycompanydata.py - Update SQL to use correct column names
2. Fix loadanalystupgradedowngrade.py - Update to use environment credentials  
3. Fix loadoptionschains.py - Install missing dependency or remove it

### SHORT TERM
4. Investigate earnings API - why only 604 records available?
5. Debug analyst sentiment loader - why 30% gap?

### After Fixes
6. Re-run all three critical loaders against S&P 500 stocks
7. Verify data now shows up on frontend
8. Create loader health monitoring/alerting

---

## Testing After Fixes

Run in this order:
```bash
# 1. Fix and test loaddailycompanydata.py
python3 loaddailycompanydata.py | tail -50

# 2. Fix and test loadanalystupgradedowngrade.py
python3 loadanalystupgradedowngrade.py | tail -50

# 3. Fix and test loadoptionschains.py
python3 loadoptionschains.py | tail -50

# 4. Verify new data coverage
curl http://localhost:3001/api/diagnostics
```

Expected results after fixes:
- Institutional Positioning: 209 → 515 stocks
- Analyst Upgrades: 193 → 515 stocks
- Options Chains: 1 → 400+ stocks (most liquid)
- Key Metrics: Should have all fields populated
