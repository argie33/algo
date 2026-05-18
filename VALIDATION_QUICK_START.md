# Pipeline Validation Quick Start Guide
**Time Estimate:** 2-4 weeks of continuous operation  
**Effort:** 15 min setup, then automated daily runs  
**Goal:** Prove entire system works before live trading

---

## Step 1: Local Environment Setup (15 minutes)

### 1.1 Start PostgreSQL

**macOS:**
```bash
brew services start postgresql
```

**Windows (with PostgreSQL installer):**
- Open Services (services.msc)
- Find "PostgreSQL" service
- Right-click → Start

**Windows (with WSL):**
```bash
wsl
sudo systemctl start postgresql
```

**Linux:**
```bash
sudo systemctl start postgresql
```

### 1.2 Set Environment Variables

**Create `.env.local` in project root:**
```bash
cat > .env.local << 'EOF'
# Database
DB_HOST=localhost
DB_PORT=5432
DB_USER=stocks
DB_NAME=stocks
DB_PASSWORD=your_postgres_password

# Alpaca (get from https://app.alpaca.markets)
APCA_API_KEY_ID=your_alpaca_api_key
APCA_API_SECRET_KEY=your_alpaca_secret_key
APCA_API_BASE_URL=https://paper-api.alpaca.markets

# Development
DEV_MODE=true
LOG_LEVEL=INFO

# Alerts (optional)
ALERT_EMAIL=your-email@gmail.com
EOF
```

### 1.3 Load Environment Variables

```bash
# Bash/Zsh
export $(cat .env.local | grep -v '^#' | xargs)

# OR manually
export DB_PASSWORD=your_postgres_password
export APCA_API_KEY_ID=your_alpaca_key
export APCA_API_SECRET_KEY=your_alpaca_secret
export APCA_API_BASE_URL=https://paper-api.alpaca.markets
```

### 1.4 Verify Setup

```bash
# Test database
python3 -c "from utils.db_connection import get_db_connection; c = get_db_connection(); print('✓ Database OK')" 2>&1 | grep -i "ok\|error"

# Test orchestrator imports
python3 -c "from algo.algo_orchestrator import Orchestrator; print('✓ Orchestrator imports OK')" 2>&1 | grep -i "ok\|error"
```

---

## Step 2: Initial Data Load (30-60 minutes, one-time)

```bash
# Initialize database schema
python3 init_database.py

# Load all market data (this is the long one)
python3 run-all-loaders.py

# Monitor the output - you should see:
# - Tier 0: Stock symbols [✓ 1/1]
# - Tier 1: Price data [✓ 2/2]
# - ... (all tiers)
# - SUMMARY: Successful: 33/33

# NOTE: This takes 30-60 minutes. Be patient. Grab coffee.
```

---

## Step 3: Run Validation Phases (Day 1)

### Phase 1: Database Check
```bash
python3 << 'PYTHON'
from utils.db_connection import get_db_connection

conn = get_db_connection()
cur = conn.cursor()

checks = [
    ('stock_symbols', 'SELECT COUNT(*) FROM stock_symbols'),
    ('price_daily', 'SELECT COUNT(*) FROM price_daily'),
    ('buy_sell_daily', 'SELECT COUNT(*) FROM buy_sell_daily'),
    ('algo_trades', 'SELECT COUNT(*) FROM algo_trades'),
]

print("\nDATABASE VERIFICATION:")
for name, query in checks:
    cur.execute(query)
    count = cur.fetchone()[0]
    if count > 0 or name == 'algo_trades':
        print(f"  ✓ {name:25s}: {count:,d} records")
    else:
        print(f"  ✗ {name:25s}: {count:,d} records (expected > 0)")

cur.close()
conn.close()
PYTHON
```

### Phase 2: Orchestrator Dry-Run
```bash
python3 algo/algo_orchestrator.py --date $(date +%Y-%m-%d) --dry-run

# EXPECT: All 7 phases complete, 0 errors
# ACTUAL TRADE COUNT: 0 (because --dry-run)
```

### Phase 3: Signal Check
```bash
python3 << 'PYTHON'
from utils.db_connection import get_db_connection
from datetime import date

conn = get_db_connection()
cur = conn.cursor()

cur.execute("""
    SELECT signal_type, COUNT(*), AVG(signal_quality_score)
    FROM signal_quality_scores
    WHERE signal_date >= DATE_TRUNC('day', NOW()) - INTERVAL '3 days'
    GROUP BY signal_type
""")

print("\nSIGNAL GENERATION:")
for sig_type, count, avg_score in cur.fetchall():
    print(f"  {sig_type}: {count:4d} signals (avg quality: {avg_score:.0f}/100)")

cur.close()
conn.close()
PYTHON
```

---

## Step 4: Paper Trading Phase (Days 2-14, Automated Daily)

### Setup Daily Scheduler

**macOS/Linux (Cron):**
```bash
# Edit crontab
crontab -e

# Add this line (runs at 9:30 AM ET daily, Mon-Fri):
30 09 * * 1-5 cd /path/to/algo && python3 algo/algo_orchestrator.py >> logs/daily.log 2>&1
```

**Windows (Task Scheduler):**
1. Open Task Scheduler
2. Create Basic Task
3. Name: "Algo Orchestrator Daily"
4. Trigger: Daily @ 9:30 AM
5. Action: Run program `python3`
6. Arguments: `algo/algo_orchestrator.py`
7. Start in: `/path/to/algo`

### Daily Manual Check (if you want to run manually)

```bash
# Each morning, run:
python3 algo/algo_orchestrator.py

# Then check results:
python3 << 'PYTHON'
from utils.db_connection import get_db_connection
from datetime import date

conn = get_db_connection()
cur = conn.cursor()
today = date.today()

# Check phases completed
cur.execute("""
    SELECT phase, status FROM algo_audit_log
    WHERE DATE(created_at) = %s
    ORDER BY created_at
""", (today,))

print(f"\nORCHESTRATOR RUN ({today}):")
for phase, status in cur.fetchall():
    symbol = "✓" if status == "success" else "✗"
    print(f"  {symbol} {phase:20s}: {status}")

# Check trades
cur.execute("""
    SELECT COUNT(*) FROM algo_trades WHERE entry_date = %s
""", (today,))

trade_count = cur.fetchone()[0]
print(f"\nTrades placed: {trade_count}")

cur.close()
conn.close()
PYTHON
```

### Weekly Review (End of Each Week)

```bash
python3 << 'PYTHON'
from utils.db_connection import get_db_connection
from datetime import date, timedelta

conn = get_db_connection()
cur = conn.cursor()

week_start = date.today() - timedelta(days=7)
week_end = date.today()

# Get weekly stats
cur.execute("""
    SELECT 
        COUNT(*) as trades,
        SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
        AVG(pnl_pct) as avg_return,
        MAX(MAX_DRAWDOWN) as max_dd
    FROM algo_trades
    WHERE entry_date BETWEEN %s AND %s
""", (week_start, week_end))

trades, wins, avg_ret, max_dd = cur.fetchone()
win_rate = (wins / trades * 100) if trades > 0 else 0

print(f"\nWEEKLY SUMMARY ({week_start} to {week_end}):")
print(f"  Trades: {trades}")
print(f"  Winners: {wins} ({win_rate:.0f}%)")
print(f"  Avg Return: {avg_ret:+.2f}%")
print(f"  Max Drawdown: {max_dd:.2f}%")

# Validation checks
print(f"\nVALIDATION:")
if trades >= 3:
    print(f"  ✓ Minimum trades placed")
else:
    print(f"  ! Low trade count - check circuit breakers")

if 30 <= win_rate <= 50:
    print(f"  ✓ Win rate in expected range")
else:
    print(f"  ! Win rate out of range - investigate")

cur.close()
conn.close()
PYTHON
```

---

## Step 5: Final Validation (Days 15-21)

After 2+ weeks of paper trading, run the final validation:

```bash
python3 << 'PYTHON'
from utils.db_connection import get_db_connection
from datetime import date, timedelta
import json

conn = get_db_connection()
cur = conn.cursor()

start = date.today() - timedelta(days=21)
end = date.today()

# Get paper trading results
cur.execute("""
    SELECT 
        COUNT(*) as total_trades,
        SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
        AVG(pnl_pct) as avg_return
    FROM algo_trades
    WHERE entry_date BETWEEN %s AND %s AND status = 'closed'
""", (start, end))

total, wins, avg_ret = cur.fetchone()
paper_win_rate = (wins / total * 100) if total > 0 else 0

# Load backtest metrics
backtest = json.loads(open('tests/backtest/reference_metrics.json').read())
backtest_win_rate = backtest['metrics']['win_rate_pct']

print("\n" + "="*70)
print("21-DAY VALIDATION RESULTS")
print("="*70)

print(f"\nPaper Trading Results:")
print(f"  Total trades: {total}")
print(f"  Win rate: {paper_win_rate:.1f}%")
print(f"  Avg return: {avg_ret:+.2f}%")

print(f"\nComparison to Backtest:")
print(f"  Backtest win rate: {backtest_win_rate:.1f}%")
print(f"  Variance: {paper_win_rate - backtest_win_rate:+.1f}%")

print(f"\nValidation Gates:")
if abs(paper_win_rate - backtest_win_rate) <= 10:
    print(f"  ✓ Gate 1: Win rate within ±10%")
else:
    print(f"  ✗ Gate 1: Win rate variance exceeds tolerance")

if total >= 30:
    print(f"  ✓ Gate 2: Sufficient trades for validation (30+)")
else:
    print(f"  ✗ Gate 2: Insufficient trades ({total})")

# Check for errors
cur.execute("""
    SELECT COUNT(*) FROM algo_audit_log
    WHERE details LIKE '%exception%' AND DATE(created_at) BETWEEN %s AND %s
""", (start, end))

if cur.fetchone()[0] == 0:
    print(f"  ✓ Gate 3: No unhandled exceptions")
else:
    print(f"  ✗ Gate 3: Exceptions found - investigate")

print(f"\n{'='*70}")
if abs(paper_win_rate - backtest_win_rate) <= 10 and total >= 30:
    print("VERDICT: ✅ READY FOR LIVE TRADING")
else:
    print("VERDICT: ⚠️  MORE VALIDATION NEEDED")
print(f"{'='*70}\n")

cur.close()
conn.close()
PYTHON
```

---

## Troubleshooting

### "No trades placed"
```bash
# Check circuit breakers
python3 << 'PYTHON'
from utils.db_connection import get_db_connection

conn = get_db_connection()
cur = conn.cursor()

cur.execute("""
    SELECT details FROM algo_audit_log
    WHERE details LIKE '%circuit%' OR details LIKE '%HALT%'
    ORDER BY created_at DESC LIMIT 5
""")

for (detail,) in cur.fetchall():
    print(f"  {detail}")

cur.close()
conn.close()
PYTHON

# Check signal generation
python3 << 'PYTHON'
from utils.db_connection import get_db_connection
from datetime import date

conn = get_db_connection()
cur = conn.cursor()

cur.execute("""
    SELECT COUNT(*) FROM signal_quality_scores
    WHERE signal_date = %s AND signal_quality_score > 60
""", (date.today(),))

count = cur.fetchone()[0]
print(f"Signals with quality > 60: {count}")

cur.close()
conn.close()
PYTHON
```

### "Database connection failed"
```bash
# Verify PostgreSQL is running
pg_isready -h localhost -p 5432

# Verify credentials
export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=stocks
export DB_NAME=stocks
export DB_PASSWORD=your_password
psql -h localhost -p 5432 -U stocks -d stocks -c "SELECT 1"
```

### "Loaders taking too long"
- This is normal. First run takes 30-60 min
- Subsequent runs are 5-15 min
- Can run loaders in background with `nohup`

---

## Success Timeline

| Week | Activity | Duration | Expected Outcome |
|------|----------|----------|------------------|
| Week 0 | Setup + Initial data load | 1-2 hours | Database populated |
| Week 1 | Paper trading (5 trading days) | Automated | 5+ trades placed |
| Week 2 | Paper trading (5 trading days) | Automated | 10+ total trades, stable |
| Week 3 | Final validation | 15 min | Performance validated |
| Week 3+ | **READY FOR LIVE TRADING** | - | Begin ramp |

---

## Final Checklist Before Live Trading

Once you've completed all steps above, verify:

- [ ] 21+ days of paper trading complete
- [ ] 30+ trades placed in paper mode
- [ ] Win rate within ±10% of backtest (40-45%)
- [ ] No unhandled exceptions in audit log
- [ ] Circuit breakers firing appropriately
- [ ] Exits executing correctly
- [ ] Monitoring/alerts working
- [ ] Runbook prepared for manual halt

**Once all boxes checked: Launch with confidence!** 🚀

---

## Notes

- **All timestamps are automatic** - system uses market dates
- **Paper trading uses real Alpaca prices** - perfect fidelity
- **No money at risk** - paper mode is simulation only
- **Fully automated after setup** - minimal daily effort
- **All results logged** - can review anytime

Good luck! Let me know if you hit any issues during validation. 📊
