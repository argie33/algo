# 🔴 CRITICAL BLOCKERS - EXECUTION PLAN

**Status**: Multiple cascading failures found  
**Need to fix before data loads**

---

## Issue #1: Windows Encoding - AFFECTS 40+ LOADERS

**Problem**: Emoji characters in logging crash on Windows  
**Error**: `UnicodeEncodeError: 'charmap' codec can't encode character '✅'`

**Affected Loaders** (confirmed):
- loadfactormetrics.py
- loadbuyselldaily.py
- loadbuyselldaily.py (buy_sell loaders)
- And likely 40+ others

**Solution**: Remove or escape emoji characters in logging

**Quick Fix**: 
```python
# Change: logging.info(f"✅ Done")
# To: logging.info("DONE")
```

**Scope**: Need to scan all loaders for emoji characters

---

## Issue #2: Missing Dependent Tables

**Problem**: Loaders expect tables that don't exist or aren't populated

| Loader | Expects | Status | Needs to Run First |
|--------|---------|--------|---|
| loadfactormetrics.py | key_metrics | NOT EXISTS | ❓ |
| loadfactormetrics.py | annual_income_statement | EMPTY | loadannualincomestatement.py |
| loadfactormetrics.py | annual_cash_flow | EMPTY | loadannualcashflow.py |
| loadstockscores.py | quality_metrics | EMPTY | loadfactormetrics.py |
| loadstockscores.py | growth_metrics | EMPTY | loadfactormetrics.py |
| loadstockscores.py | value_metrics | EMPTY | loadfactormetrics.py |
| loadstockscores.py | stability_metrics | EMPTY | loadfactormetrics.py |

**Dependency Chain**:
```
price_daily (need to expand)
    ↓
annual_income_statement (load)
annual_cash_flow (load)
quarterly_income_statement (load)
quarterly_balance_sheet (load)
quarterly_cash_flow (load)
    ↓
loadfactormetrics.py (calculate quality/growth/value/stability)
    ↓
loadstockscores.py (calculate composite scores)
    ↓
loadbuyselldaily.py (calculate signals)
```

---

## Issue #3: key_metrics Table Missing

**Problem**: loadfactormetrics.py references `key_metrics` table that doesn't exist

**Options**:
1. Table was renamed - need to find new name
2. Table needs to be created - schema/data source unknown
3. Loader is outdated - needs updating

**Impact**: Quality metrics can't load without this

---

## EXECUTION PLAN (Priority Order)

### PHASE 1: Fix Immediate Crashes (30 min)
- [ ] Remove emoji characters from all loaders
- [ ] Fix Windows path issues ✅ (already done)
- [ ] Fix schema mismatches ✅ (already done)

### PHASE 2: Find key_metrics (15 min)
- [ ] Search for key_metrics in code
- [ ] Check what data it should contain
- [ ] Find/create/load correct source

### PHASE 3: Load Financial Statements (2 hours)
```bash
python3 loadannualincomestatement.py
python3 loadannualcashflow.py
python3 loadquarterlyincomestatement.py
python3 loadquarterlybalancesheet.py
python3 loadquarterlycashflow.py
```

### PHASE 4: Load Factor Metrics (1 hour)
```bash
python3 loadfactormetrics.py
```

### PHASE 5: Load Stock Scores (30 min)
```bash
python3 loadstockscores.py
```

### PHASE 6: Load Signals (3-4 hours)
```bash
python3 loadbuyselldaily.py
python3 loadbuysellweekly.py
python3 loadbuysellmonthly.py
python3 loadbuysell_etf_daily.py
python3 loadbuysell_etf_weekly.py
python3 loadbuysell_etf_monthly.py
```

---

## IMMEDIATE NEXT STEP

**Should I**:
1. Fix emoji encoding issue in ALL loaders (global search/replace)?
2. Find key_metrics table and understand what it should be?
3. Start loading financial statements?

**Recommendation**: Do ALL THREE in parallel:
- Use grep to find all emoji characters
- Search code for key_metrics definition
- Start loadannualincomestatement.py (takes time, can happen in background)

What should we do first?
