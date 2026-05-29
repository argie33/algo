# Quick Fix Checklist - Data Display Issues
**Target:** Fix broken loaders today  
**Time Budget:** 2 hours  
**Success Criteria:** All 5 broken loaders fixed and tested

---

## FIXES TO APPLY (Copy-paste ready)

### Fix 1: loaders/load_signal_themes.py
```python
# Line 44 - Change this:
sqs.signal_score > 50
# To:
sqs.composite_sqs > 50

# Line 53 - Change this:
WHERE sqs.signal_date = %s
# To:
WHERE sqs.date = %s
```
**Test:** `python loaders/load_signal_themes.py` then check `SELECT COUNT(*) FROM signal_themes;`

---

### Fix 2: loaders/load_sector_rotation_signals.py
**Complete rewrite of INSERT section (lines 35-56):**

```python
cur.execute("""
    INSERT INTO sector_rotation_signal (date, sector, signal, strength, created_at, updated_at)
    SELECT
        %s::date,
        sr.sector_name,
        CASE
            WHEN sr.momentum_score > 0.1 THEN 'up'
            WHEN sr.momentum_score < -0.1 THEN 'down'
            ELSE 'neutral'
        END AS signal,
        ABS(sr.momentum_score)::numeric AS strength,
        NOW(),
        NOW()
    FROM (
        SELECT DISTINCT sector_name, momentum_score
        FROM sector_ranking
        WHERE date_recorded = %s
    ) sr
    ON CONFLICT (sector, date) DO UPDATE SET
        signal = EXCLUDED.signal,
        strength = EXCLUDED.strength,
        updated_at = NOW()
""", (latest_date, latest_date))
```
**Test:** `python loaders/load_sector_rotation_signals.py` then check `SELECT COUNT(*) FROM sector_rotation_signal;`

---

### Fix 3: loaders/load_signal_trade_performance.py
```python
# Line 64 - Change this:
WHERE sqs.signal_date >= NOW() - INTERVAL '180 days'
# To:
WHERE sqs.date >= NOW() - INTERVAL '180 days'
```
**Test:** `python loaders/load_signal_trade_performance.py` then check `SELECT COUNT(*) FROM signal_trade_performance;`

---

### Fix 4: loaders/load_sentiment.py
**Option A (RECOMMENDED - Use different table):**

Change line 20-23 from:
```python
cur.execute("""
    INSERT INTO sentiment (symbol, sentiment_score, sentiment_label, created_at, updated_at)
    SELECT
```

To:
```python
cur.execute("""
    INSERT INTO market_sentiment (date, sentiment_score, sentiment_label, created_at, updated_at)
    SELECT
        CURRENT_DATE::date,
```

Also update the SELECT to include date:
```python
# Original line 28-32
SELECT
    COALESCE(symbol, 'MARKET') AS symbol,

# Change to:
SELECT
    CURRENT_DATE::date,
    COALESCE(symbol, 'MARKET') AS symbol,
```

And update CONFLICT clause (line 43):
```python
# Original:
ON CONFLICT (symbol) DO UPDATE SET

# Change to:
ON CONFLICT (symbol, date) DO UPDATE SET
```

**Test:** `python loaders/load_sentiment.py` then check `SELECT COUNT(*) FROM market_sentiment WHERE sentiment_score IS NOT NULL;`

---

### Fix 5: loaders/load_sentiment_social.py
**Decision Required:**
- Is this feature needed? 
- If YES → Keep as-is (placeholder OK for now)
- If NO → Comment out from loader schedule

**Action:** For now, keep as-is but add to monitoring.

---

## VERIFICATION CHECKLIST

After applying fixes, run these in sequence:

- [ ] Fix 1: `python loaders/load_signal_themes.py`
- [ ] Check: `SELECT COUNT(*) FROM signal_themes;` > 0
- [ ] Fix 2: `python loaders/load_sector_rotation_signals.py`
- [ ] Check: `SELECT COUNT(*) FROM sector_rotation_signal;` > 0
- [ ] Fix 3: `python loaders/load_signal_trade_performance.py`
- [ ] Check: `SELECT COUNT(*) FROM signal_trade_performance;` > 500
- [ ] Fix 4: `python loaders/load_sentiment.py`
- [ ] Check: `SELECT COUNT(*) FROM market_sentiment WHERE sentiment_score IS NOT NULL;` > 0
- [ ] Fix 5: Review `load_sentiment_social.py` (keep or remove?)
- [ ] Test API: `curl http://localhost:3000/api/signals`
- [ ] Test API: `curl http://localhost:3000/api/sectors`
- [ ] Test API: `curl http://localhost:3000/api/sentiment/summary`
- [ ] Manual UI test: Check for blank data/charts
- [ ] Check git status: All changes staged
- [ ] Commit: `git add loaders/*.py && git commit -m "fix: Correct loader query syntax and schema mismatches"`
- [ ] Push: `git push origin main`

---

## MONITORING TASKS (Not urgent but important)

- [ ] Add logging to `loader_execution_history` table (next day)
- [ ] Set up `loader_sla_status` tracking (next day)
- [ ] Verify EventBridge schedules in Terraform (verify existing)
- [ ] Set up alerts for stale data (next week)

---

## DONE!
Once all checks pass, you can mark this audit complete. The 5 critical loaders will be fixed and data should display properly in the frontend.
