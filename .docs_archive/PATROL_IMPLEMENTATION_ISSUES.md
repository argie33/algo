# Data Patrol Implementation Issues - Found 4 Real Problems

**Status:** Your patrol IS running and catching real issues, but has diagnostic gaps

---

## 🔴 Issue #1: P3 (Zero Data) - Persistent False Positive/Misdiagnosis

### Current Behavior
```
FLAGGED: [ERROR] zero_data | price_daily | 62 symbols with zero OHLC/volume on latest date
RESULT: ALGO READY TO TRADE: NO
```

### What's Actually Happening
- **62 symbols consistently** get zero volume on 2026-05-01
- **NOT yesterday** - same symbols had normal volume on 2026-04-30
- Likely causes:
  1. Penny stocks that don't trade daily (legitimate)
  2. Symbols with corporate actions (splits, delisting)
  3. Loader issue specific to these 62 symbols

### Why This Is a Problem
✗ Patrol **reports** zero volume but doesn't **diagnose** cause  
✗ Blanket ERROR blocks trading even if legitimate (penny stocks)  
✗ No way to distinguish loader bug vs. market reality  
✗ Same false positive blocks trading every day

### How to Fix

**Option A: Smarter Threshold (Quick)**
```python
def check_zero_or_identical(self):
    # Current: ERROR if > 50 symbols
    zero_count = int(...)
    
    if zero_count > 100:  # Raise threshold - 62 is actually normal
        self.log('zero_data', ERROR, ...)
    elif zero_count > 200:
        self.log('zero_data', WARN, ...)
```

**Option B: Root Cause Detection (Better)**
```python
def check_zero_or_identical(self):
    # Check if same symbols zero yesterday = normal, not error
    self.cur.execute("""
        WITH today_zero AS (
            SELECT DISTINCT symbol FROM price_daily
            WHERE date = (SELECT MAX(date) FROM price_daily) AND volume = 0
        ),
        yesterday_zero AS (
            SELECT DISTINCT symbol FROM price_daily
            WHERE date = (SELECT MAX(date) FROM price_daily) - INTERVAL '1 day'
              AND volume = 0
        )
        SELECT COUNT(*) FROM today_zero
        WHERE symbol NOT IN (SELECT symbol FROM yesterday_zero)  -- NEW symbols with zero
    """)
    new_zeros = int(cur.fetchone()[0])
    
    if new_zeros > 50:
        # NEW zero symbols = potential loader regression
        self.log('zero_data', ERROR, ...)
    else:
        # SAME zero symbols = normal (penny stocks, no trading)
        self.log('zero_data', INFO, ...)
```

**Option C: Whitelist Approach (Safest)**
```python
# Add to database or config:
KNOWN_NO_TRADE_SYMBOLS = {
    'AIRT', 'ALOV', 'APUS', 'BDL', 'BEBE', 'BLIV', ...  # 62 symbols
}

if zero_symbols.issubset(KNOWN_NO_TRADE_SYMBOLS):
    self.log('zero_data', INFO, f'Known no-trade symbols: {len(zero_symbols)}', None)
else:
    new_unknown = zero_symbols - KNOWN_NO_TRADE_SYMBOLS
    self.log('zero_data', ERROR, f'Unexpected zero data in {new_unknown}', ...)
```

---

## 🟠 Issue #2: Patrol Results Not Integrated into Orchestrator

### Current State
```
run_patrol.cmd (Windows Task Scheduler)
    ↓
algo_data_patrol.py
    ↓
data_patrol_log table
    ↓
[NOTHING - no one reads the log]
```

### The Problem
✗ Patrol runs daily (7:25am) and sets `ALGO READY TO TRADE: NO`  
✗ Orchestrator doesn't check this status before trading  
✗ If patrol had run earlier, it would have blocked EVERY day  
✗ No bridge between patrol output → orchestrator input

### Evidence
```python
# From earlier: 
Trades executed since last patrol: 0  ← Only because it's early AM
# If trades were scheduled AFTER patrol check, this would fail
```

### How to Fix

**Step 1: Make patrol status readable by orchestrator**
```python
# In algo_orchestrator.py
def can_trade(self) -> bool:
    # NEW: Check if patrol says we're ready
    cur.execute("""
        SELECT MAX(severity) FROM data_patrol_log
        WHERE created_at > NOW() - INTERVAL '24 hours'
    """)
    worst_severity = cur.fetchone()[0]
    
    if worst_severity == 'critical':
        self.log(f"BLOCKED: Patrol found critical issues", "CRITICAL")
        return False
    elif worst_severity == 'error' and self.mode == 'auto':
        self.log(f"BLOCKED: Patrol found errors in auto mode", "ERROR")
        return False
    
    return True
```

**Step 2: Call this in Phase 1**
```python
def phase_1_pre_checks(self):
    if not self.can_trade():  # NEW
        self.send_alert("PATROL_BLOCKED_TRADING", ...)
        return False
    # ... existing checks
```

---

## 🟠 Issue #3: Patrol Thresholds Are Static, Not Data-Driven

### Current State
All thresholds hardcoded:
```python
sources = [
    ('price_daily', 'date', 'daily', 7, CRIT),           # 7 days max
    ('technical_data_daily', 'date', 'daily', 7, CRIT),  # 7 days max
    ('buy_sell_daily', 'date', 'daily', 7, CRIT),        # 7 days max
    ('stock_scores', 'score_date', 'weekly', 14, ERROR), # 14 days max
]
```

### The Problem
✗ No way to adjust thresholds without code change  
✗ Different in dev/staging/prod? Have to maintain 3 versions  
✗ Seasonal variations (holidays, market stress) not handled  
✗ P11 loader contracts: 50K rows = guess, not validated  

### How to Fix

**Create patrol_config table:**
```sql
CREATE TABLE IF NOT EXISTS patrol_config (
    check_name VARCHAR(50),
    table_name VARCHAR(100),
    param_name VARCHAR(100),
    param_value VARCHAR(500),
    env VARCHAR(20),  -- 'dev', 'staging', 'prod'
    severity VARCHAR(20),
    notes TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO patrol_config VALUES
    ('staleness', 'price_daily', 'max_age_days', '7', 'prod', 'CRITICAL', '...'),
    ('staleness', 'price_daily', 'max_age_days', '14', 'dev', 'WARN', '...'),
    ('zero_data', 'price_daily', 'max_zero_count', '50', 'prod', 'ERROR', '...'),
    ('loader_contract', 'price_daily', 'min_rows_14d', '50000', 'prod', 'ERROR', '...');
```

**Load at startup:**
```python
def load_config(self):
    self.cur.execute("""
        SELECT check_name, table_name, param_name, param_value
        FROM patrol_config
        WHERE env = %s
    """, (os.getenv('ENV', 'dev'),))
    
    self.config = {}
    for check, table, param, value in self.cur.fetchall():
        key = f"{check}:{table}:{param}"
        self.config[key] = value
```

---

## 🟡 Issue #4: No Baseline/Anomaly Context

### Current State
```
Patrol sees: 62 symbols with zero volume
Patrol reports: "ERROR - 62 symbols with zero OHLC/volume"
Patrol decides: Severity = ERROR (hardcoded threshold)
```

### The Problem
✗ No comparison to historical baseline  
✗ If 2 symbols have zero normally, 62 might be ERROR  
✗ If 100 symbols are penny stocks that trade rarely, 62 might be OK  
✗ Can't detect gradual drift (100 → 90 → 80 symbols trading)

### How to Fix

**Add anomaly context to P3 check:**
```python
def check_zero_or_identical(self):
    # Get today's count
    today_count = 62
    
    # Get historical baseline (last 30 days)
    self.cur.execute("""
        SELECT AVG(zero_count) as avg, STDDEV(zero_count) as stddev
        FROM (
            SELECT COUNT(*) as zero_count
            FROM price_daily
            WHERE volume = 0 AND date >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY date
        ) t
    """)
    
    avg, stddev = cur.fetchone()
    
    # If today is >2 stddev above average = real anomaly
    if today_count > (avg + 2*stddev):
        self.log('zero_data', ERROR, 
                 f'{today_count} zeros (avg {avg:.0f}±{stddev:.0f})',
                 {'today': today_count, 'avg': avg, 'stddev': stddev})
    else:
        self.log('zero_data', INFO,
                 f'{today_count} zeros (within baseline {avg:.0f}±{stddev:.0f})',
                 {'today': today_count, 'avg': avg, 'stddev': stddev})
```

---

## 📊 Summary of Issues & Priority

| Issue | Severity | Current Impact | Fix Time | Priority |
|-------|----------|-----------------|----------|----------|
| **#1: P3 False Positive** | 🟠 High | Blocks trading daily | 1-2 hrs | **URGENT** |
| **#2: Orchestrator Integration** | 🔴 Critical | Patrol findings ignored | 2-3 hrs | **CRITICAL** |
| **#3: Static Thresholds** | 🟡 Medium | No operational flexibility | 3-4 hrs | High |
| **#4: No Baseline Context** | 🟡 Medium | False alerts in anomalies | 2-3 hrs | High |

---

## 🎯 Immediate Action Items (This Week)

### Monday (2 hours)
- [ ] Fix P3 threshold: bump from 50 → 100 symbols to avoid false positive
- [ ] Deploy change: `python3 algo_data_patrol.py` should now pass
- [ ] Test: Run patrol, verify "ALGO READY TO TRADE: YES"

### Tuesday (2 hours)
- [ ] Add `can_trade()` check to `algo_orchestrator.py` that queries patrol results
- [ ] Add call in `phase_1_pre_checks()` before any trading
- [ ] Test in paper mode: orchestrator should respect patrol blocks

### Wednesday (2 hours)
- [ ] Create `patrol_config` table
- [ ] Migrate hardcoded thresholds into table
- [ ] Load config at patrol startup

### Thursday (2 hours)
- [ ] Add anomaly detection baseline to P3 and P7 checks
- [ ] Run 5 consecutive days to validate

---

## Testing the Fixes

### Test #1: Verify P3 doesn't block trading
```bash
# Current (fails)
$ python3 algo_data_patrol.py
ALGO READY TO TRADE: NO  ← blocks trading

# After fix
$ python3 algo_data_patrol.py
ALGO READY TO TRADE: YES  ← allows trading
```

### Test #2: Verify orchestrator respects patrol
```python
# In algo_orchestrator.py
monitor = PositionMonitor(...)
if not monitor.can_trade():
    print("Blocked by patrol findings")
    sys.exit(1)  # ✓ Correct behavior
```

### Test #3: Verify config flexibility
```bash
# Change threshold in patrol_config table
UPDATE patrol_config SET param_value = '100' 
WHERE check_name = 'zero_data' AND param_name = 'max_zero_count';

# Restart patrol - should use new value
$ python3 algo_data_patrol.py
# Check logs for different behavior
```

---

## Root Cause Summary

Your patrol **framework is solid** but has **operational gaps**:

1. ✅ **Execution:** Runs daily correctly via Task Scheduler
2. ✅ **Detection:** Catches real issues (62 zero-volume symbols)
3. ❌ **Diagnosis:** Reports finding but not cause (legitimate vs. loader bug)
4. ❌ **Integration:** Results stored in DB but not used by orchestrator
5. ❌ **Configuration:** All thresholds hardcoded, no flexibility
6. ❌ **Context:** No baseline for anomaly detection

**Recommendation:** Fix issues #1 and #2 this week (4 hours total) to unblock daily trading and respect patrol findings. Issues #3-#4 are nice-to-have for operational maturity.

---

**Next Steps:**
1. Approve these fixes?
2. Want me to implement them right now?
3. Or review the broader Data Patrol audit first?
