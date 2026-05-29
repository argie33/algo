# Critical Data Display Issues - Priority Fix List
**Generated:** 2026-05-28  
**Total Issues Found:** 68  
**Critical Issues (Today):** 5 loaders  
**Estimated Fix Time:** 2 hours

---

## PRIORITY 1: BROKEN LOADERS (Fix immediately - these insert 0 rows)

### P1.1 load_signal_themes.py - Column name errors
**File:** `loaders/load_signal_themes.py`  
**Status:** BROKEN (0 rows inserted)  
**Impact:** signal_themes table is EMPTY  
**Time to Fix:** 5 minutes

**Problem:**
```python
Line 44: sqs.signal_score > 50  # ❌ Column doesn't exist
Line 53: WHERE sqs.signal_date = %s  # ❌ Column doesn't exist
```

**Signal_Quality_Scores Schema (actual columns):**
- `date` (NOT `signal_date`)
- `composite_sqs` (NOT `signal_score`)

**Fix - Two line changes:**
```python
# Line 44 - in the WHERE clause inside the INSERT SELECT:
- AND sqs.signal_score > 50
+ AND sqs.composite_sqs > 50

# Line 53 - in the WHERE clause:
- WHERE sqs.signal_date = %s
+ WHERE sqs.date = %s
```

**After fix, verify:**
```bash
# Manually run loader
python loaders/load_signal_themes.py
# Check result:
# SELECT COUNT(*) FROM signal_themes;  -- Should have rows now
```

---

### P1.2 load_sector_rotation_signals.py - Wrong column names + missing date
**File:** `loaders/load_sector_rotation_signals.py`  
**Status:** BROKEN (0 rows inserted)  
**Impact:** sector_rotation_signal table is EMPTY  
**Time to Fix:** 10 minutes

**Problem:**
```python
INSERT INTO sector_rotation_signal (sector_name, direction, strength, created_at, updated_at)
# But table expects: (date, sector, signal, strength, rank, details, created_at, updated_at)
```

**Table Schema vs Loader Insert:**
| Expected Column | Loader Provides | Match |
|---|---|---|
| date | ❌ Missing | ❌ NO |
| sector | sector_name | ❌ NO |
| signal | direction | ❌ NO |
| strength | strength | ✓ YES |
| rank | ❌ Missing | ❌ NO |
| details | ❌ Missing | ❌ NO |

**Fix - Rewrite INSERT section (lines 35-56):**
```python
cur.execute("""
    INSERT INTO sector_rotation_signal (date, sector, signal, strength, created_at, updated_at)
    SELECT
        %s::date,                                    -- Add date
        sr.sector_name,                             -- Correct column name
        CASE
            WHEN sr.momentum_score > 0.1 THEN 'up'
            WHEN sr.momentum_score < -0.1 THEN 'down'
            ELSE 'neutral'
        END AS signal,                              -- Use 'signal' not 'direction'
        ABS(sr.momentum_score)::numeric,
        NOW(),
        NOW()
    FROM (
        SELECT DISTINCT sector_name, momentum_score
        FROM sector_ranking
        WHERE date_recorded = %s
    ) sr
    ON CONFLICT (sector, date) DO UPDATE SET        -- Change conflict detection
        signal = EXCLUDED.signal,
        strength = EXCLUDED.strength,
        updated_at = NOW()
""", (latest_date, latest_date))
```

**After fix, verify:**
```sql
SELECT COUNT(*) FROM sector_rotation_signal;  -- Should have rows
```

---

### P1.3 load_signal_trade_performance.py - Date column error
**File:** `loaders/load_signal_trade_performance.py`  
**Status:** PARTIALLY BROKEN (3 stale rows only)  
**Impact:** signal_trade_performance has minimal data  
**Time to Fix:** 5 minutes

**Problem:**
```python
Line 60-64: Uses non-existent column 'signal_date'
WHERE sqs.signal_date >= NOW() - INTERVAL '180 days'  # ❌ Doesn't exist
# Should be:
WHERE sqs.date >= NOW() - INTERVAL '180 days'  # ✓
```

**Fix - One line change:**
```python
# Line 64 in the WHERE clause:
- WHERE sqs.signal_date >= NOW() - INTERVAL '180 days'
+ WHERE sqs.date >= NOW() - INTERVAL '180 days'
```

**After fix, verify:**
```sql
SELECT COUNT(*) FROM signal_trade_performance;
-- Should have > 3 rows after loader runs
```

---

### P1.4 load_sentiment.py - Table schema completely wrong!
**File:** `loaders/load_sentiment.py`  
**Status:** COMPLETELY BROKEN (wrong table)  
**Impact:** sentiment table is EMPTY + cannot insert sentiment data  
**Time to Fix:** 20 minutes (choose approach)

**Problem:**
The `sentiment` table has **PRICE DATA columns**, not sentiment columns!

**Current sentiment table schema:**
```sql
sentiment (id, symbol, date, open, high, low, close, volume, created_at, updated_at)
           -- These are PRICE columns, not sentiment!
```

**Loader tries to insert:**
```python
INSERT INTO sentiment (symbol, sentiment_score, sentiment_label, created_at, updated_at)
-- But sentiment_score and sentiment_label columns DON'T EXIST!
```

**Fix Options:**

**Option A: Use different table (RECOMMENDED - 5 min)**
Use `market_sentiment` instead of `sentiment`:
```python
# Line 20: Change table name
- INSERT INTO sentiment (symbol, sentiment_score, sentiment_label, created_at, updated_at)
+ INSERT INTO market_sentiment (date, sentiment_score, sentiment_label, created_at, updated_at)

# Line 28 - Add date to SELECT:
SELECT
    CURRENT_DATE::date,  # Add this
    COALESCE(symbol, 'MARKET') AS symbol,
    ... rest stays same
```

**Option B: Fix sentiment table schema (15 min)**
Drop and recreate sentiment table:
```sql
-- First, rename old broken table
ALTER TABLE sentiment RENAME TO sentiment_broken_old;

-- Create new sentiment table with correct schema
CREATE TABLE sentiment (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR NOT NULL,
    date DATE,
    sentiment_score NUMERIC,
    sentiment_label VARCHAR,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(symbol)
);
```

**RECOMMENDATION: Use Option A** - market_sentiment already exists, just redirect loader there.

**After fix, verify:**
```sql
SELECT COUNT(*) FROM market_sentiment WHERE sentiment_label IS NOT NULL;
-- Should have rows with sentiment data
```

---

### P1.5 load_sentiment_social.py - Placeholder data only
**File:** `loaders/load_sentiment_social.py`  
**Status:** Works but inserts FAKE data (0.5 sentiment, hardcoded counts)  
**Impact:** sentiment_social table is EMPTY or has dummy data  
**Time to Fix:** 10 minutes (decision only)

**Problem:**
```python
Lines 48-57: All hardcoded placeholder values
0.5::numeric AS twitter_sentiment_score,
100::integer AS twitter_mention_count,  # Hardcoded!
50::integer AS reddit_mention_count,    # Hardcoded!
```

**Decision needed:**
1. **Option A:** Remove from frontend/API (this feature not ready)
2. **Option B:** Comment out loader from schedule (don't run)
3. **Option C:** Integrate real Twitter/Reddit/StockTwits API
4. **Option D:** Keep placeholder as-is (acceptable for demo)

**Action:** Check with product - should social sentiment be a feature?

---

## PRIORITY 2: EMPTY LOADER EXECUTION TRACKING (Fix today afternoon)

### P2.1 loader_execution_history - No execution logs!
**Table:** `loader_execution_history`  
**Status:** EMPTY (0 rows)  
**Impact:** Cannot diagnose loader failures  
**Time to Fix:** 1-2 hours (add logging to all loaders)

**Requirement:**
All loaders should log execution to this table:
```sql
INSERT INTO loader_execution_history (
    loader_name, execution_start, execution_end, status, 
    rows_processed, error_message, created_at, updated_at
) VALUES (...)
```

**Fix Steps:**
1. Create helper function in `utils/db_connection.py`:
```python
def log_loader_execution(loader_name, start_time, end_time, status, rows, error=None):
    """Log loader execution to tracking table"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO loader_execution_history 
        (loader_name, execution_start, execution_end, status, rows_processed, error_message, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, NOW())
    """, (loader_name, start_time, end_time, status, rows, error))
    conn.commit()
    cur.close()
    conn.close()
```

2. Update each loader to call this function

**After fix, verify:**
```sql
SELECT COUNT(*) FROM loader_execution_history;  -- Should have rows
SELECT DISTINCT loader_name FROM loader_execution_history;  -- Should list all loaders
```

---

### P2.2 loader_sla_status - No health tracking!
**Table:** `loader_sla_status`  
**Status:** EMPTY (0 rows)  
**Impact:** Cannot track data freshness SLAs  
**Time to Fix:** 1 hour (create monitoring job)

**Requirement:**
Periodically check loader health:
```sql
INSERT INTO loader_sla_status (
    loader_name, table_name, latest_data_date, row_count_today, status, last_check_at
) VALUES (...)
```

**Create monitoring function:**
```python
def update_loader_sla_status():
    """Check all loaders and update SLA status"""
    loaders = [
        ('stock_prices', 'price_daily', 1),
        ('signals', 'buy_sell_daily', 1),
        ('sentiment', 'aaii_sentiment', 6),
        # ... etc for all loaders
    ]
    
    for loader_name, table_name, max_age_hours in loaders:
        # Check latest data date
        # Check row count
        # Set status (healthy/warning/failed)
        # Insert/update SLA status
```

**After fix, verify:**
```sql
SELECT * FROM loader_sla_status;  -- Should have entries for all loaders
```

---

## PRIORITY 3: STALE DATA - Verify Loaders Are Running (Check today)

### P3.1 Verify EventBridge schedule
**File:** `terraform/modules/loaders/main.tf`  
**Check:**
- Are loader schedules set for trading days (Mon-Fri)?
- Are times in UTC correct?
- Are rules ENABLED?

**Example cron format:**
```hcl
schedule_expression = "cron(0 9 ? * MON-FRI *)"  # 4:00 AM ET (9:00 AM UTC)
```

### P3.2 Manually trigger stale loaders
```bash
# Manually run via AWS CLI (or GitHub Actions workflow)
aws lambda invoke \
  --function-name algo-trigger-loaders-dev \
  /tmp/response.json
```

**Loaders to re-run immediately:**
- stock_prices_daily (price_daily is fresh, OK)
- technical_data_daily (stale - 6d old)
- signals (buy_sell_daily is stale - 10d old)
- aaii_sentiment (stale - 6d old)
- key_metrics (stale - 7d old)

---

## PRIORITY 4: VERIFY FIXES WORK (End of day)

After applying all fixes above, run verification:

```bash
# 1. Check all loaders run without error
python loaders/load_signal_themes.py
python loaders/load_sector_rotation_signals.py
python loaders/load_signal_trade_performance.py
python loaders/load_sentiment.py
python loaders/load_sentiment_social.py

# 2. Check data is inserted
psql -c "SELECT COUNT(*) FROM signal_themes;"
psql -c "SELECT COUNT(*) FROM sector_rotation_signal;"
psql -c "SELECT COUNT(*) FROM signal_trade_performance;"
psql -c "SELECT COUNT(*) FROM sentiment WHERE sentiment_label IS NOT NULL;"

# 3. Check API endpoints return data
curl http://localhost:3000/api/signals/themes
curl http://localhost:3000/api/sectors
curl http://localhost:3000/api/sentiment/summary

# 4. Check frontend shows data (not blank)
# Open browser, navigate to each page, verify charts/lists populated
```

---

## SUMMARY

| Priority | Fix | Time | Impact |
|----------|-----|------|--------|
| P1.1 | load_signal_themes.py | 5 min | Empty signal themes |
| P1.2 | load_sector_rotation_signals.py | 10 min | Empty sector rotation |
| P1.3 | load_signal_trade_performance.py | 5 min | Stale performance data |
| P1.4 | load_sentiment.py | 20 min | Empty sentiment |
| P1.5 | load_sentiment_social.py | 10 min | Placeholder social data |
| P2.1 | loader_execution_history tracking | 1-2 hr | No execution logs |
| P2.2 | loader_sla_status tracking | 1 hr | No health monitoring |
| P3 | Verify loaders scheduled/running | 30 min | Stale data |
| P4 | Test all fixes | 30 min | Verify working |

**Total Time:** ~4-5 hours  
**Expected Outcome:** All critical data display issues resolved, frontend shows fresh data

---

**Next Steps:**
1. Start with P1 issues (15-30 minutes to fix)
2. Run loaders manually to verify
3. Update P2 for monitoring
4. Verify everything in P4
5. Monitor data freshness over next few days
