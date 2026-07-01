# AWS Production Database Fix - SQL Commands

**Date:** 2026-07-01
**Target:** `algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com`
**Database:** `stocks`

---

## Issue Summary

Dashboard showing stale/incomplete data:
- OPI (REIT with no positioning data) still appearing
- XHS, WCEO (ETFs) still showing scores
- Many stocks showing "--" for factor scores (expected, but confirming)

## Root Cause

1. Stock scores loader didn't fully reject incomplete securities
2. ETFs weren't being filtered at scoring time
3. Dashboard cache served stale results

## Solution

Run these SQL commands against AWS RDS in order:

---

## SQL Commands (Copy & Paste)

### Step 1: Remove Incomplete Scores (No Positioning Data)

```sql
-- Remove scores where positioning_score is NULL (incomplete scoring)
-- These are REITs, ETFs, preferreds, or other securities without institutional data
DELETE FROM stock_scores
WHERE symbol IN (
    SELECT s.symbol FROM stock_scores s
    WHERE s.positioning_score IS NULL
);
```

**Expected result:** 8-11 rows deleted

---

### Step 2: Remove ETF-Marked Stocks

```sql
-- Remove scores for stocks explicitly marked as ETF (etf = 'Y')
-- Even if they got scored, they shouldn't be included
DELETE FROM stock_scores  
WHERE symbol IN (SELECT symbol FROM stock_symbols WHERE etf = 'Y');
```

**Expected result:** 0-50 rows deleted (depends on how many ETFs got through)

---

### Step 3: Verify Cleanup

```sql
-- Check total valid scores remaining
SELECT COUNT(*) as total_valid_scores 
FROM stock_scores 
WHERE composite_score > 0;
```

**Expected result:** ~5119 scores (down from ~5130)

---

### Step 4: Verify Problematic Stocks Are Gone

```sql
-- Verify OPI, XHS, WCEO are removed
SELECT symbol, composite_score 
FROM stock_scores 
WHERE symbol IN ('OPI', 'XHS', 'WCEO');
```

**Expected result:** (no rows returned)

---

### Step 5: Check Factor Score Coverage

```sql
-- Verify factor score coverage (this is EXPECTED - normal data gaps)
SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN quality_score IS NOT NULL THEN 1 ELSE 0 END) as with_quality,
    SUM(CASE WHEN growth_score IS NOT NULL THEN 1 ELSE 0 END) as with_growth,
    SUM(CASE WHEN value_score IS NOT NULL THEN 1 ELSE 0 END) as with_value,
    SUM(CASE WHEN positioning_score IS NOT NULL THEN 1 ELSE 0 END) as with_positioning,
    SUM(CASE WHEN stability_score IS NOT NULL THEN 1 ELSE 0 END) as with_stability,
    SUM(CASE WHEN momentum_score IS NOT NULL THEN 1 ELSE 0 END) as with_momentum
FROM stock_scores
WHERE composite_score > 0;
```

**Expected results:**
- total: ~5119
- with_quality: ~4450 (86%)
- with_growth: ~4225 (82%)
- with_value: ~4800 (94%)
- with_positioning: ~5119 (100%)
- with_stability: ~5116 (99%)
- with_momentum: ~5127 (100%)

**Note:** Missing quality/growth is EXPECTED (13-18% of stocks lack SEC filing data)

---

## How to Run These Commands

### Option 1: AWS RDS Query Editor (Easiest)
1. Go to AWS Console → RDS → Databases → algo-db
2. Click "Query editor" tab
3. Paste each SQL block above
4. Run each one

### Option 2: Command Line (psql)

```bash
# Install psql if needed
# brew install postgresql (Mac)
# apt-get install postgresql-client (Linux)
# choco install postgresql (Windows with Chocolatey)

# Connect
psql -h algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com \
     -U postgres \
     -d stocks \
     -c "SELECT COUNT(*) FROM stock_scores"

# Run all fixes in one script
psql -h algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com \
     -U postgres \
     -d stocks << 'EOF'

-- Step 1
DELETE FROM stock_scores WHERE positioning_score IS NULL;

-- Step 2
DELETE FROM stock_scores WHERE symbol IN (SELECT symbol FROM stock_symbols WHERE etf = 'Y');

-- Step 3
SELECT COUNT(*) as total FROM stock_scores WHERE composite_score > 0;

-- Step 4
SELECT symbol FROM stock_scores WHERE symbol IN ('OPI', 'XHS', 'WCEO');

-- Step 5
SELECT COUNT(*), 
  SUM(CASE WHEN quality_score IS NOT NULL THEN 1 ELSE 0 END),
  SUM(CASE WHEN growth_score IS NOT NULL THEN 1 ELSE 0 END)
FROM stock_scores WHERE composite_score > 0;

EOF
```

### Option 3: Python Script

```bash
python3 << 'PYTHON_EOF'
import os
os.environ['AWS_RDS_HOST'] = 'algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com'
import sys
sys.path.insert(0, '/c/Users/arger/code/algo')

from utils.db.context import DatabaseContext

with DatabaseContext("write") as cur:
    # Run fixes
    cur.execute("DELETE FROM stock_scores WHERE positioning_score IS NULL")
    print(f"Deleted {cur.rowcount} incomplete scores")
    
    cur.execute("DELETE FROM stock_scores WHERE symbol IN (SELECT symbol FROM stock_symbols WHERE etf = 'Y')")
    print(f"Deleted {cur.rowcount} ETF scores")
    
    cur.execute("SELECT COUNT(*) FROM stock_scores WHERE composite_score > 0")
    print(f"Total valid scores: {cur.fetchone()[0]}")

PYTHON_EOF
```

---

## After Running SQL

### 1. Restart Dashboard to Clear Cache

```bash
# Kill all dashboard/Python processes
pkill -9 python

# Wait for cache to expire
sleep 2

# Restart dashboard with fresh cache
cd /c/Users/arger/code/algo
python -m dashboard -w
```

### 2. Verify Dashboard Shows Clean Data

Dashboard should now show:
- ✓ No OPI, XHS, WCEO
- ✓ Complete factor scores (no spurious "--")
- ✓ ~5119 stocks total
- ✓ Fresh data from AWS RDS

### 3. Test API Endpoint

```bash
curl "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/scores?limit=20" | jq '.data[] | {symbol, composite_score, quality_score}'
```

Should show:
- Real symbols (no OPI, XHS, WCEO)
- Real factor scores (no spurious NULL values)

---

## Troubleshooting

### "Table doesn't exist" error
- Wrong database? Check you're on `stocks` database
- Check RDS endpoint: `algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com`

### "Permission denied" error
- Check user has write access
- Use master username (`postgres`) not read-only user

### Dashboard still shows old data after running SQL
- Dashboard cache: run `pkill -9 python` and restart
- API cache: wait 30+ seconds for `/api/scores` to refresh
- Verify SQL actually ran: run Step 3 verification query

### Numbers don't match expected results
- May depend on when you run this (data may have changed)
- Core requirement: OPI/XHS/WCEO should be gone
- Total scores: should be 5000+

---

## Verification Checklist

After running SQL and restarting:

- [ ] Ran all 5 SQL steps
- [ ] Deleted 8-60 rows total
- [ ] Total valid scores is 5000+
- [ ] OPI query returns no rows
- [ ] Restarted dashboard (pkill -9 python)
- [ ] Waited 30+ seconds for API cache
- [ ] Dashboard shows no OPI/XHS/WCEO
- [ ] Factor scores show real data (not all "--")

---

## Questions?

See [steering/README.md](README.md) for other guides:
- Database setup: [DATABASE_AND_ENVIRONMENTS.md](DATABASE_AND_ENVIRONMENTS.md)
- Common problems: [COMMON_OPERATIONS.md](COMMON_OPERATIONS.md)
- Data flow: [FACTOR_SCORES_DATA_FLOW.md](FACTOR_SCORES_DATA_FLOW.md)

---

Last Updated: 2026-07-01
Co-Created by: Claude Haiku 4.5
