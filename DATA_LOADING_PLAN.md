# Data Loading Plan - Complete Database Population

**Date**: 2026-01-01
**Issue**: Critical tables missing data (earnings table is EMPTY, stock_scores incomplete)

---

## Current Database State

| Table | Rows | Status | Last Updated |
|-------|------|--------|--------------|
| **stock_symbols** | 5,300 | ✅ Complete | - |
| **company_profile** | 5,359 | ✅ Complete | - |
| **price_daily** | 23,401,005 | ✅ Complete | 2025-12-31 |
| **technical_data_daily** | 23,503,549 | ✅ Complete | - |
| **value_metrics** | 78,727 | ✅ Complete | - |
| **quality_metrics** | 57,857 | ✅ Complete | - |
| **growth_metrics** | 73,062 | ✅ Complete | - |
| **stability_metrics** | 55,814 | ✅ Complete | - |
| **earnings** | **0** | ❌ EMPTY | Never loaded |
| **stock_scores** | **46** | ❌ Incomplete | Should be ~5,300 |

---

## Critical Issues Identified

### 🚨 **Priority 1: earnings Table is EMPTY**

**Impact:**
- loadstockscores.py **CANNOT** calculate accurate scores without earnings data
- Missing: P/E ratios, earnings growth, earnings consistency
- Your custom scoring script also depends on earnings data

**Root Cause:**
- `loaddailycompanydata.py` populates earnings table
- Last run: **2025-12-19** (13 days ago)
- Needs to be re-run

### 🚨 **Priority 2: stock_scores Incomplete**

**Current:** 46 rows
**Expected:** ~5,300 rows (one per stock)

**Root Cause:**
- `loadstockscores.py` depends on earnings data
- Since earnings is empty, scores can't be calculated

---

## Data Loader Dependencies

```
┌─────────────────────────┐
│ 1. loadstocksymbols.py  │  ← Foundation (5,300 symbols)
└────────────┬────────────┘
             │
             ├──────────────────────────────────────┬─────────────────────────────┐
             │                                      │                             │
             ▼                                      ▼                             ▼
┌────────────────────────┐       ┌──────────────────────────┐   ┌──────────────────────┐
│ 2. loadpricedaily.py   │       │ 3. loaddailycompanydata  │   │ loadannual*.py       │
│    (price_daily)       │       │    (company_profile,     │   │ loadquarterly*.py    │
│    23M+ rows ✅        │       │     earnings ❌ EMPTY,   │   │ loadttm*.py          │
└────────────┬───────────┘       │     positioning,         │   └──────────────────────┘
             │                   │     estimates)           │
             │                   └────────────┬─────────────┘
             │                                │
             ▼                                │
┌────────────────────────┐                    │
│ technical_data_daily   │                    │
│ 23M+ rows ✅           │                    │
└────────────────────────┘                    │
                                              │
                    ┌─────────────────────────┴────────────┐
                    │                                      │
                    ▼                                      ▼
        ┌───────────────────────┐           ┌──────────────────────┐
        │ 4. loadfactormetrics  │           │ Other loaders        │
        │    (value_metrics,    │           │ (sentiment, news,    │
        │     quality_metrics,  │           │  calendar, etc.)     │
        │     growth_metrics,   │           └──────────────────────┘
        │     stability_metrics)│
        │    ALL ✅             │
        └───────────┬───────────┘
                    │
                    ▼
        ┌───────────────────────┐
        │ 5. loadstockscores.py │
        │    (stock_scores)     │
        │    46 rows ❌         │
        │    DEPENDS ON:        │
        │    - earnings ❌      │
        │    - factor_metrics ✅│
        │    - price_daily ✅   │
        └───────────────────────┘
```

---

## Execution Plan

### Phase 1: Load Core Company Data (CRITICAL)

**Order matters - follow exactly:**

```bash
# 1. Ensure stock symbols are current
python3 loadstocksymbols.py

# 2. Load company data INCLUDING EARNINGS (CRITICAL!)
python3 loaddailycompanydata.py
# This populates:
# - company_profile ✅ (already has data)
# - earnings ❌ (EMPTY - needs this run)
# - institutional_positioning
# - positioning_metrics
# - earnings estimates
# - insider transactions

# Verify earnings loaded:
psql -h localhost -U stocks -d stocks -c "SELECT COUNT(*) FROM earnings;"
# Expected: > 50,000 rows (multiple quarters per stock)
```

### Phase 2: Load Financial Statements (if needed)

```bash
# Annual statements
python3 loadannualincomestatement.py
python3 loadannualbalancesheet.py
python3 loadannualcashflow.py

# Quarterly statements (more current)
python3 loadquarterlyincomestatement.py
python3 loadquarterlybalancesheet.py
python3 loadquarterlycashflow.py

# TTM (trailing twelve months) - most recent
python3 loadttmincomestatement.py
python3 loadttmcashflow.py
```

### Phase 3: Calculate Stock Scores

```bash
# NOW we can run stock scores with complete data
python3 loadstockscores.py

# Verify stock scores calculated:
psql -h localhost -U stocks -d stocks -c "SELECT COUNT(*) FROM stock_scores;"
# Expected: ~5,300 rows

# Check score distribution:
psql -h localhost -U stocks -d stocks -c "
SELECT
  COUNT(*) as stocks,
  ROUND(AVG(composite_score), 2) as avg_composite,
  ROUND(AVG(value_score), 2) as avg_value,
  ROUND(AVG(quality_score), 2) as avg_quality,
  ROUND(AVG(momentum_score), 2) as avg_momentum
FROM stock_scores
WHERE composite_score IS NOT NULL;
"
```

### Phase 4: Your Custom Scoring Script

After Phase 3 completes, you can run your custom MySQL-based scoring script.

**Required changes for your script:**

1. **Change database from MySQL to PostgreSQL:**
```python
# OLD (MySQL):
import pymysql
conn = pymysql.connect(host='localhost', user='stocks', password='bed0elAn', db='stocks')

# NEW (PostgreSQL):
import psycopg2
conn = psycopg2.connect(host='localhost', user='stocks', password='bed0elAn', dbname='stocks')
```

2. **Update table/column references** (if needed)
3. **Add scipy dependency:**
```bash
pip install scipy scikit-learn
```

---

## Verification Queries

After each phase, run these checks:

```sql
-- Check earnings data loaded
SELECT COUNT(*) as total_earnings,
       COUNT(DISTINCT symbol) as unique_stocks,
       MIN(date) as earliest,
       MAX(date) as latest
FROM earnings;
-- Expected: 50,000+ rows, ~5,300 stocks, dates going back 2+ years

-- Check stock_scores populated
SELECT COUNT(*) as total_scores,
       COUNT(*) FILTER (WHERE composite_score IS NOT NULL) as with_composite,
       COUNT(*) FILTER (WHERE value_score IS NOT NULL) as with_value
FROM stock_scores;
-- Expected: ~5,300 total, most with non-null scores

-- Check score distributions (should look reasonable)
SELECT
  ROUND(composite_score, 0) as score_bucket,
  COUNT(*) as count
FROM stock_scores
WHERE composite_score IS NOT NULL
GROUP BY score_bucket
ORDER BY score_bucket;
-- Should show bell curve distribution

-- Find stocks missing scores
SELECT symbol,
       composite_score IS NULL as missing_composite,
       value_score IS NULL as missing_value,
       quality_score IS NULL as missing_quality
FROM stock_scores
WHERE composite_score IS NULL OR value_score IS NULL
LIMIT 20;
```

---

## Quick Start: Run Critical Loaders NOW

```bash
# Navigate to project directory
cd /home/stocks/algo

# Run the critical loaders in order
echo "=== Loading Company Data + Earnings ==="
python3 loaddailycompanydata.py

echo "=== Calculating Stock Scores ==="
python3 loadstockscores.py

echo "=== Verifying Data ==="
psql -h localhost -U stocks -d stocks -c "
SELECT
  'earnings' as table, COUNT(*) as rows FROM earnings
UNION ALL
SELECT 'stock_scores', COUNT(*) FROM stock_scores
UNION ALL
SELECT 'company_profile', COUNT(*) FROM company_profile;
"
```

---

## Expected Runtime

| Loader | Runtime | API Calls |
|--------|---------|-----------|
| loaddailycompanydata.py | ~45-90 min | 5,300 (one per stock) |
| loadstockscores.py | ~10-20 min | None (uses DB data) |

**Total estimated time:** ~1-2 hours for complete data load

---

## Next Steps

1. ✅ Run `loaddailycompanydata.py` to populate earnings
2. ✅ Run `loadstockscores.py` to calculate scores
3. ✅ Verify all tables have expected row counts
4. ✅ Adapt your custom scoring script for PostgreSQL
5. ✅ Run your custom scoring with full dataset

---

## Notes

- **Earnings data is CRITICAL** - without it, P/E ratios, growth metrics, and value scores are meaningless
- loaddailycompanydata.py should be run **daily** or **weekly** to keep data current
- loadstockscores.py should run **after** loaddailycompanydata.py completes
- Your custom scoring script adds technical indicators not in production system (good addition!)
