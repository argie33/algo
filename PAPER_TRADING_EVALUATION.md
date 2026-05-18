# Paper Trading Evaluation Framework
**Purpose:** Prove the algo is ready for live trading through controlled paper trading validation  
**Duration:** 1-2 weeks minimum  
**Success Criteria:** All validation gates pass

---

## Setup: Pre-Paper Trading (30 minutes)

### Step 1: Set Up Database & Market Data

```bash
# 1a. Ensure PostgreSQL is running
# Mac: brew services start postgresql
# Windows: Services > PostgreSQL > Start
# Linux: sudo systemctl start postgresql

# 1b. Set environment variables
export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=stocks
export DB_NAME=stocks
export DB_PASSWORD=your_postgres_password

# 1c. Initialize database schema
python3 init_database.py

# 1d. Load all market data (this takes 30-60 min)
python3 run-all-loaders.py
# Monitor output - should see:
#   - Tier 0: Stock symbols (1 loader)
#   - Tier 1: Price data (2 loaders)
#   - Tier 1b: Price aggregates
#   - Tier 2: Fundamentals and sentiment
#   - Tier 2c: TTM aggregates
#   - Tier 2b: Computed metrics
#   - Tier 2d: Stock scores
#   - Tier 3: Trading signals
#   - Tier 3b: Signal aggregates
# Expect: All loaders successful, minimal failures
```

### Step 2: Set Up Alpaca Paper Trading Credentials

```bash
# Get credentials from: https://app.alpaca.markets
# Account > Settings > API Keys

export ALPACA_API_KEY_ID=your_key_id
export ALPACA_API_SECRET_KEY=your_secret_key
export APCA_API_BASE_URL=https://paper-api.alpaca.markets

# Optional: For alerts
export ALERT_EMAIL=your-email@gmail.com
export ALERT_PHONE=+1234567890
```

### Step 3: Verify Setup

```bash
# Test database connection
python3 -c "from utils.db_connection import get_db_connection; get_db_connection(); print('DB OK')"

# Test orchestrator startup (dry-run)
python3 algo/algo_orchestrator.py --dry-run
# Should output: 7 phases checked, no errors, dry-run = no trades placed
```

---

## Phase 1: Initial Validation (Day 1)

### Test 1a: Dry-Run Orchestrator

```bash
# Run in dry-run mode (no trades placed)
python3 algo/algo_orchestrator.py --date 2026-05-18 --dry-run

# Expected output:
# [PASS] Phase 1: Data Freshness Check — all tables recent
# [PASS] Phase 2: Circuit Breakers — all clear
# [PASS] Phase 3: Position Monitor — 0 open positions
# [PASS] Phase 4: Exit Execution — no exits needed
# [PASS] Phase 5: Signal Generation — N candidate signals
# [PASS] Phase 6: Entry Execution — 0 trades placed (dry-run)
# [PASS] Phase 7: Reconciliation — portfolio synced

# Verify: No errors, all phases green
```

**Validation Gate 1:** ✅ Orchestrator runs without errors in dry-run mode

### Test 1b: Check Signal Generation

```bash
# Query generated signals for today
python3 << 'PYTHON'
from utils.db_connection import get_db_connection
from datetime import date

conn = get_db_connection()
cur = conn.cursor()

# Check today's buy signals
cur.execute("""
    SELECT COUNT(*), AVG(signal_quality_score) 
    FROM signal_quality_scores
    WHERE signal_date = %s AND signal_type = 'BUY'
""", (date.today(),))

count, avg_score = cur.fetchone()
print(f"Buy signals today: {count} (avg quality: {avg_score:.1f}/100)")

# Check signal distribution by score
cur.execute("""
    SELECT 
        CASE WHEN signal_quality_score >= 80 THEN 'Excellent'
             WHEN signal_quality_score >= 60 THEN 'Good'
             WHEN signal_quality_score >= 40 THEN 'Fair'
             ELSE 'Poor' END as quality,
        COUNT(*) as count
    FROM signal_quality_scores
    WHERE signal_date = %s AND signal_type = 'BUY'
    GROUP BY quality
    ORDER BY quality DESC
""", (date.today(),))

for quality, count in cur.fetchall():
    print(f"  {quality}: {count} signals")

cur.close()
conn.close()
PYTHON

# Expected: 50-200 BUY signals, average quality 60-75
```

**Validation Gate 2:** ✅ Signal generation produces reasonable quantity and quality

### Test 1c: Verify Data Freshness

```bash
# Check that all critical tables have recent data
python3 << 'PYTHON'
from utils.db_connection import get_db_connection
from datetime import date, timedelta

conn = get_db_connection()
cur = conn.cursor()

critical_tables = [
    ('price_daily', 'price_date'),
    ('buy_sell_daily', 'signal_date'),
    ('technical_data_daily', 'data_date'),
    ('market_health_daily', 'market_date'),
]

today = date.today()
threshold = today - timedelta(days=7)

for table, date_col in critical_tables:
    cur.execute(f"SELECT MAX({date_col}) FROM {table}")
    max_date = cur.fetchone()[0]
    if max_date >= threshold:
        print(f"✓ {table:30s}: {max_date} (recent)")
    else:
        print(f"✗ {table:30s}: {max_date} (STALE)")

cur.close()
conn.close()
PYTHON

# Expected: All tables have data from within 7 days
```

**Validation Gate 3:** ✅ All critical data is fresh (within 7 days)

---

## Phase 2: Paper Trading Week 1 (Days 2-8)

### Setup: Live Paper Trading Mode

```bash
# Run orchestrator every trading day at market open (9:30 AM ET)
# Use a scheduler or cron job:

# MacOS/Linux: Add to crontab
# 30 09 * * 1-5 cd /path/to/algo && python3 algo/algo_orchestrator.py

# Windows: Use Task Scheduler
# Action: run python3 algo/algo_orchestrator.py --mode paper
# Trigger: Daily at 09:30
```

### Daily Monitoring Checklist

Each trading day, check:

```bash
# 1. Check if orchestrator ran successfully
python3 << 'PYTHON'
from utils.db_connection import get_db_connection
from datetime import date

conn = get_db_connection()
cur = conn.cursor()

today = date.today()

# Get today's orchestrator run
cur.execute("""
    SELECT run_id, phase, status, details
    FROM algo_audit_log
    WHERE DATE(created_at) = %s
    ORDER BY created_at DESC
    LIMIT 20
""", (today,))

print("Latest orchestrator run:")
for run_id, phase, status, details in cur.fetchall():
    print(f"  {phase:20s} {status:10s} {details[:60]}")

cur.close()
conn.close()
PYTHON

# 2. Check data patrol for any issues
python3 << 'PYTHON'
from utils.db_connection import get_db_connection
from datetime import date

conn = get_db_connection()
cur = conn.cursor()

today = date.today()

# Check patrol results
cur.execute("""
    SELECT check_name, severity, COUNT(*) as findings
    FROM data_patrol_log
    WHERE DATE(created_at) = %s
    GROUP BY check_name, severity
    ORDER BY severity DESC, check_name
""", (today,))

print("\nData patrol results:")
for check, severity, count in cur.fetchall():
    if severity == 'critical':
        print(f"  [CRITICAL] {check}: {count} findings - NEEDS INVESTIGATION")
    elif severity == 'error':
        print(f"  [ERROR] {check}: {count} findings")
    else:
        print(f"  {severity.upper():10s} {check}: {count}")

cur.close()
conn.close()
PYTHON

# 3. Check any trades placed
python3 << 'PYTHON'
from utils.db_connection import get_db_connection
from datetime import date

conn = get_db_connection()
cur = conn.cursor()

today = date.today()

# Check trades
cur.execute("""
    SELECT symbol, entry_price, entry_date, status
    FROM algo_trades
    WHERE entry_date = %s
    ORDER BY entry_date DESC
""", (today,))

trades = cur.fetchall()
print(f"\nTrades placed: {len(trades)}")
for symbol, entry_price, entry_date, status in trades:
    print(f"  {symbol:10s} @ {entry_price:.2f} ({status})")

if len(trades) == 0:
    print("  (None - may be due to circuit breakers or market conditions)")

cur.close()
conn.close()
PYTHON

# 4. Check portfolio health
python3 << 'PYTHON'
from utils.db_connection import get_db_connection
from datetime import date

conn = get_db_connection()
cur = conn.cursor()

today = date.today()

# Get latest portfolio snapshot
cur.execute("""
    SELECT portfolio_value, cash, open_positions, total_pnl_pct
    FROM algo_portfolio_snapshots
    WHERE snapshot_date = %s
    ORDER BY created_at DESC
    LIMIT 1
""", (today,))

result = cur.fetchone()
if result:
    portfolio_val, cash, positions, pnl_pct = result
    print(f"\nPortfolio snapshot ({today}):")
    print(f"  Value:           ${portfolio_val:,.2f}")
    print(f"  Cash:            ${cash:,.2f}")
    print(f"  Open positions:  {positions}")
    print(f"  Total P&L:       {pnl_pct:+.2f}%")
else:
    print("\nNo portfolio snapshot available yet")

cur.close()
conn.close()
PYTHON
```

### Weekly Review (End of Day 5)

```bash
# Get trading statistics for the week
python3 << 'PYTHON'
from utils.db_connection import get_db_connection
from datetime import date, timedelta

conn = get_db_connection()
cur = conn.cursor()

start_date = date.today() - timedelta(days=5)
end_date = date.today()

# Trades placed
cur.execute("""
    SELECT COUNT(*), AVG(entry_price), SUM(CASE WHEN exit_price > entry_price THEN 1 ELSE 0 END)
    FROM algo_trades
    WHERE entry_date BETWEEN %s AND %s
""", (start_date, end_date))

total_trades, avg_entry, winning_trades = cur.fetchone()
win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

# Portfolio performance
cur.execute("""
    SELECT 
        MAX(portfolio_value) as max_value,
        MIN(portfolio_value) as min_value,
        (SELECT portfolio_value FROM algo_portfolio_snapshots WHERE snapshot_date = %s LIMIT 1) as final_value
    FROM algo_portfolio_snapshots
    WHERE snapshot_date BETWEEN %s AND %s
""", (end_date, start_date, end_date))

max_val, min_val, final_val = cur.fetchone()

print(f"\nWeek 1 Summary ({start_date} to {end_date}):")
print(f"  Trades placed:     {total_trades}")
print(f"  Winning trades:    {winning_trades} ({win_rate:.1f}%)")
print(f"  Avg entry price:   ${avg_entry:.2f}")
print(f"  Portfolio max:     ${max_val:,.2f}")
print(f"  Portfolio min:     ${min_val:,.2f}")
print(f"  Final portfolio:   ${final_val:,.2f}")

# Check against expectations
print(f"\nValidation:")
if total_trades >= 3:
    print(f"  ✓ Minimum trades placed (expected 3+, got {total_trades})")
else:
    print(f"  ! Low trade count - check circuit breakers or market conditions")

if 30 <= win_rate <= 50:
    print(f"  ✓ Win rate reasonable (expected 30-50%, got {win_rate:.1f}%)")
elif win_rate < 30:
    print(f"  ! Win rate below expectations - may need signal review")

# Check for circuit breaker trips
cur.execute("""
    SELECT details, COUNT(*) as count
    FROM algo_audit_log
    WHERE details LIKE '%circuit%' OR details LIKE '%HALT%'
    AND created_at >= %s
    GROUP BY details
""", (start_date,))

breaker_trips = cur.fetchall()
if breaker_trips:
    print(f"\n  Circuit breaker trips:")
    for details, count in breaker_trips:
        print(f"    - {details} ({count} times)")

cur.close()
conn.close()
PYTHON
```

**Validation Gate 4:** ✅ Trades are being placed, win rate is reasonable (30-50%)

---

## Phase 3: Extended Validation (Days 9-14)

### Performance Comparison to Backtest

```bash
python3 << 'PYTHON'
from utils.db_connection import get_db_connection
from datetime import date, timedelta
import json

conn = get_db_connection()
cur = conn.cursor()

# Get paper trading results
start_date = date.today() - timedelta(days=14)
end_date = date.today()

cur.execute("""
    SELECT 
        COUNT(*) as total_trades,
        SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
        AVG(pnl_pct) as avg_return,
        SUM(pnl) as total_pnl
    FROM algo_trades
    WHERE entry_date BETWEEN %s AND %s AND status = 'closed'
""", (start_date, end_date))

total, wins, avg_ret, total_pnl = cur.fetchone()
win_rate = (wins / total * 100) if total and total > 0 else 0

print(f"\nPaper Trading Results (14 days):")
print(f"  Total trades:      {total}")
print(f"  Winning trades:    {wins} ({win_rate:.1f}%)")
print(f"  Avg return:        {avg_ret:.2f}%")
print(f"  Total P&L:         ${total_pnl:.2f}")

# Load backtest expectations
backtest_metrics = json.loads(open('tests/backtest/reference_metrics.json').read())
expected_win_rate = backtest_metrics['metrics']['win_rate_pct']
expected_sharpe = backtest_metrics['metrics']['sharpe_ratio']

print(f"\nComparison to Backtest:")
print(f"  Expected win rate: {expected_win_rate:.1f}%")
print(f"  Actual win rate:   {win_rate:.1f}%")
print(f"  Difference:        {win_rate - expected_win_rate:+.1f}%")

if abs(win_rate - expected_win_rate) <= 10:
    print(f"  ✓ Within acceptable variance")
else:
    print(f"  ! Variance exceeds expected range - investigate")

cur.close()
conn.close()
PYTHON
```

**Validation Gate 5:** ✅ Paper trading performance matches backtest expectations (±10%)

---

## Success Criteria: Final Validation

All of the following must be TRUE to declare ready for live trading:

```python
VALIDATION_GATES = {
    "Gate 1": {
        "criterion": "Orchestrator runs without errors",
        "validation": "0 exceptions in dry-run mode",
        "status": "PENDING"
    },
    "Gate 2": {
        "criterion": "Signal generation works",
        "validation": "50-200 signals per day, quality 60+",
        "status": "PENDING"
    },
    "Gate 3": {
        "criterion": "Data is fresh",
        "validation": "All critical tables updated within 7 days",
        "status": "PENDING"
    },
    "Gate 4": {
        "criterion": "Trades execute in paper mode",
        "validation": "3+ trades per week, win rate 30-50%",
        "status": "PENDING"
    },
    "Gate 5": {
        "criterion": "Performance matches backtest",
        "validation": "Within ±10% of backtest win rate",
        "status": "PENDING"
    },
    "Gate 6": {
        "criterion": "Risk controls work",
        "validation": "Circuit breakers fire appropriately",
        "status": "PENDING"
    },
    "Gate 7": {
        "criterion": "No unhandled errors",
        "validation": "Audit log clean, no exceptions",
        "status": "PENDING"
    },
    "Gate 8": {
        "criterion": "Position monitoring works",
        "validation": "Exits trigger correctly, trailing stops adjust",
        "status": "PENDING"
    }
}
```

## Checklist: Declare Ready

Before moving to live trading, verify:

- [ ] **Gate 1 PASS:** Orchestrator runs in dry-run without errors
- [ ] **Gate 2 PASS:** Signal generation producing 50+ signals/day
- [ ] **Gate 3 PASS:** All data tables updated within 7 days
- [ ] **Gate 4 PASS:** 3+ trades placed per week in paper mode
- [ ] **Gate 5 PASS:** Win rate within 40-45% (±5% of backtest)
- [ ] **Gate 6 PASS:** No unhandled exceptions in audit log
- [ ] **Gate 7 PASS:** Circuit breakers logged when triggered
- [ ] **Gate 8 PASS:** Exit engine correctly managing open positions
- [ ] **Monitoring:** Email/SMS alerts working
- [ ] **Runbook:** Manual halt procedure documented and tested
- [ ] **Review:** All trades reviewed, no unexpected behavior

---

## Troubleshooting Paper Trading Issues

### Problem: "No trades placed"
**Possible causes:**
1. Circuit breaker active (check `algo_audit_log`)
2. No signals passing 5-tier filter (check signal_quality_scores)
3. Data stale (check patrol log)
4. Market closed (check market calendar)

**Solution:**
```bash
# Check circuit breaker status
grep -i "circuit" /path/to/logs

# Check signal quality
SELECT COUNT(*) FROM signal_quality_scores 
WHERE signal_date = TODAY() AND signal_quality_score > 60

# Check data freshness
SELECT MAX(price_date) FROM price_daily
```

### Problem: "Win rate much lower than expected"
**Possible causes:**
1. Real slippage (paper vs backtest)
2. Market regime different
3. Signal filter too loose

**Solution:**
1. Review actual trade entries vs signals
2. Compare market conditions to backtest period
3. Check advanced filter rejections

### Problem: "Too many trades placed"
**Possible causes:**
1. Position limit not enforced
2. Risk sizing too large
3. Filter too loose

**Solution:**
1. Verify `max_positions` in config
2. Check position sizing calculation
3. Review advanced filter scores

---

## Sign-Off: Ready for Live Trading

```
Date: [TODAY]

Paper Trading Evaluation: ✓ APPROVED

All validation gates passed:
  ✓ Orchestrator operational
  ✓ Signals generating correctly
  ✓ Data fresh and reliable
  ✓ Trades executing in paper mode
  ✓ Performance matches backtest
  ✓ Risk controls active
  ✓ No unhandled errors
  ✓ Position management working

Recommendation: READY FOR LIVE TRADING

Next steps:
  1. Start with 10% of planned capital
  2. Monitor first 20 trades closely
  3. Ramp to 100% over 2-4 weeks
  4. Continue daily monitoring
```

---

## Daily Operations (Once Live)

```bash
# Daily checks (run each morning after market open)
python3 algo/algo_orchestrator.py --date $(date +%Y-%m-%d)

# Weekly review (end of week)
python3 << 'PYTHON'
# Review audit log
# Check portfolio P&L
# Validate exits are working
# Monitor for any issues
PYTHON

# Monthly optimization (quarterly)
python3 algo/algo_backtest.py --walk-forward-test \
  --start 2024-01-01 --end 2026-05-18 \
  --window 252  # 1 year rolling window
```

---

## Final Checklist

Before considering the algorithm ready:

- [ ] Paper trading evaluation complete (2+ weeks)
- [ ] All 8 validation gates PASS
- [ ] No unexpected behavior
- [ ] Monitoring infrastructure verified
- [ ] Runbook prepared
- [ ] Team briefed on daily procedures
- [ ] Emergency shutdown plan ready

**Once all items checked: APPROVED FOR LIVE TRADING** ✅
