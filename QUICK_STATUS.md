# Quick Status - What's Broken vs What Still Needs Fixing
**Date:** 2026-05-07

---

## CURRENT BROKEN STATE

```
Database Check Results:
  ✗ Same-day trades:        39 out of 39 closed trades (0 days held)
  ✗ Zero P&L:              39 out of 39 trades at 0.00%
  ✗ NULL entry prices:     239 out of 425,400 signals
  ✗ Out of range entries:  24,309 out of 425,161 signals (5.72%)
  ✓ Open positions:        10 filled + 1 open (monitoring)
```

---

## WHO'S DOING WHAT

### Someone Else (Entry Price Issue)
- **Issue:** 24,309 signals (5.7%) have entry_price outside daily [low, high] range
- **Status:** IN PROGRESS
- **Action needed from you:** When they're done, run `python3 loadbuyselldaily.py` to verify

### YOU NEED TO DO (Right Now)

#### TASK #1: FIX SAME-DAY EXITS (5 minutes)
**File:** `algo_exit_engine.py`, line 113  
**What:** Add 1-day minimum hold check  
**Why:** All 39 trades enter and exit same day → 0% P&L  

```python
days_held = (current_date - trade_date).days

# ADD THESE 3 LINES:
if days_held < 1:
    print(f"  {symbol}: need 1d hold")
    continue

exit_signal = self._evaluate_position(...)
```

**Then test:**
```bash
python3 << 'EOF'
import psycopg2
conn = psycopg2.connect(...)  # uses .env.local
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM algo_trades WHERE status='closed' AND trade_date=exit_date")
print(f"Same-day trades: {cur.fetchone()[0]} -- should be 0 after fix")
EOF
```

---

#### TASK #2: FIX NULL ENTRY PRICES (15 minutes)
**File:** `loadbuyselldaily.py`, method `_generate_signal_row()`  
**What:** Validate entry_price before returning signal  
**Why:** 239 signals can't be traded without entry price  

```python
# After calculating entry_price, ADD THIS:
if entry_price is None or entry_price <= 0:
    return None  # Skip this signal

# ... then later in return dict:
"entry_price": entry_price,  # Now guaranteed non-NULL
```

**Then test:**
```bash
# 1. Clean existing NULL entries
python3 << 'EOF'
import psycopg2
conn = psycopg2.connect(...)
cur = conn.cursor()
cur.execute("DELETE FROM buy_sell_daily WHERE signal='BUY' AND entry_price IS NULL")
conn.commit()
print(f"Deleted {cur.rowcount} NULL signals")
EOF

# 2. Re-run loader
python3 loadbuyselldaily.py --parallelism 8

# 3. Verify
python3 << 'EOF'
import psycopg2
conn = psycopg2.connect(...)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM buy_sell_daily WHERE signal='BUY' AND entry_price IS NULL")
print(f"NULL entries: {cur.fetchone()[0]} -- should be 0")
EOF
```

---

#### TASK #3: ADD DATABASE CONSTRAINTS (10 minutes)
**Type:** Infrastructure safety  
**Why:** Prevent impossible states at database level  

```sql
-- Run these in psql or DB client:
ALTER TABLE algo_trades
ADD CONSTRAINT min_hold_one_day 
  CHECK (status != 'closed' OR (exit_date - trade_date) >= 1);

ALTER TABLE buy_sell_daily
ADD CONSTRAINT entry_price_in_range
  CHECK (signal != 'BUY' OR (entry_price >= low AND entry_price <= high));

ALTER TABLE buy_sell_daily
ADD CONSTRAINT entry_price_required
  CHECK (signal != 'BUY' OR entry_price IS NOT NULL);

ALTER TABLE algo_trades
ADD CONSTRAINT exit_after_entry
  CHECK (status != 'closed' OR exit_date > trade_date);
```

**Then verify:**
```sql
SELECT constraint_name FROM information_schema.table_constraints
WHERE table_name IN ('algo_trades', 'buy_sell_daily') AND constraint_type='CHECK';
-- Should show: 4 new constraints
```

---

## PRIORITY & TIME

| Task | Time | Priority | Blocks |
|------|------|----------|--------|
| Fix same-day exits | 5 min | CRITICAL | All trading |
| Fix NULL entry prices | 15 min | MAJOR | New signals |
| Add DB constraints | 10 min | MEDIUM | Data safety |
| Wait for entry price fix | ? | CRITICAL | Loader quality |

**Total time if you do all 3:** ~30 minutes

---

## HOW TO PROCEED

1. **Right now:** Do Task #1 (5 min) - stops more 0% trades
2. **Next 10 min:** Do Task #2 (15 min) - prevents bad signals  
3. **Later today:** Do Task #3 (10 min) - permanent safety
4. **When someone finishes:** They'll notify you to re-run loader
5. **Then verify:** All issues resolved with final database check

---

## WHAT TO DO AFTER FIXES

After all fixes are complete:

```bash
# 1. Commit your changes
git add algo_exit_engine.py loadbuyselldaily.py
git commit -m "Fix: same-day exits and NULL entry prices"

# 2. Final verification
python3 << 'EOF'
import psycopg2
conn = psycopg2.connect(...)
cur = conn.cursor()

print("FINAL VERIFICATION:")
cur.execute("SELECT COUNT(*) FROM algo_trades WHERE status='closed' AND trade_date=exit_date")
print(f"  Same-day trades: {cur.fetchone()[0]} (should be 0)")

cur.execute("SELECT COUNT(*) FROM buy_sell_daily WHERE signal='BUY' AND entry_price IS NULL")
print(f"  NULL entry prices: {cur.fetchone()[0]} (should be 0)")

cur.execute("""
  SELECT COUNT(*) FROM algo_trades 
  WHERE status='closed' AND (profit_loss_pct = 0 OR profit_loss_pct IS NULL)
""")
print(f"  Zero P&L trades: {cur.fetchone()[0]} (should be much less than 39)")

cur.close()
EOF

# 3. Resume trading
# The system is now ready!
```

---

## REFERENCE

For detailed steps and explanation, see:
- `REMAINING_ISSUES_ACTION_PLAN.md` - Complete implementation guide
- `SAME_DAY_EXIT_FIX.md` - Deep dive into same-day exit issue
- `DATA_QUALITY_CHECKLIST.md` - All validation checks needed
- `AUDIT_SUMMARY.md` - Executive summary of all issues

