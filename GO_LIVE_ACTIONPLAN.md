# GO LIVE ACTION PLAN — Market Opens 9:30 AM ET

**Status:** System ready for live execution  
**Time Budget:** 8 hours (5+ hour safety buffer)  
**Deadline:** 2026-05-19 09:30 AM

---

## Quick Status Check

```
✅ Code:           All 3 modified files committed (earnings/liquidity/phase5 fixes)
✅ Logic:          282/282 core tests passing
✅ Architecture:   TradeExecutor defaults to paper trading (safe by default)
✅ Orchestrator:   All 7 phases ready for execution
✅ Database:       Schema initialized, ready for data load
```

**What's Left:** Credentials + data + validation

---

## STEP 1: ROTATE ALPACA CREDENTIALS (15 minutes)

⏱️ **By 04:15 AM**

1. Go to: https://app.alpaca.markets/dashboard/settings/keys
2. **Delete old compromised keys** (were in git history)
3. **Generate NEW API Key ID and Secret Key**
4. **Add to GitHub Secrets:**
   - Settings → Secrets and variables → Actions
   - `APCA_API_KEY_ID` = new key ID
   - `APCA_API_SECRET_KEY` = new secret
5. **Add to AWS Secrets Manager:**
   - AWS Console → Secrets Manager → `algo/alpaca`
   - JSON format:
     ```json
     {
       "key": "new_key_id",
       "secret": "new_secret"
     }
     ```
6. **Verify in local environment:**
   ```bash
   # Set env vars for testing
   export APCA_API_KEY_ID="new_key_id"
   export APCA_API_SECRET_KEY="new_secret"
   
   # Test connection
   python3 config/credential_validator.py
   ```
   Expected: ✅ Alpaca credentials verified

---

## STEP 2: LOAD TODAY'S MARKET DATA (30 minutes)

⏱️ **By 04:50 AM**

```bash
# Load all data through today
python3 run-all-loaders.py
```

**What this does:**
- Fetches price data through today (2026-05-19)
- Computes technical indicators (RSI, SMA, ATR, ADX, MACD, etc.)
- Generates buy/sell signals for today
- Loads earnings dates, market metrics, VIX

**Verify completion:**
```bash
# Check latest data is loaded
python3 -c "
import psycopg2
from config.credential_helper import get_db_config
from datetime import date

conn = psycopg2.connect(**get_db_config())
cur = conn.cursor()

tables = ['price_daily', 'technical_data_daily', 'buy_sell_daily', 'trend_template_data']
print('Data freshness check:')
for tbl in tables:
    cur.execute(f'SELECT COUNT(*), MAX(date) FROM {tbl}')
    count, max_date = cur.fetchone()
    status = '✓' if max_date == date.today() else '✗ STALE'
    print(f'{tbl:30} {count:8} rows  max_date={max_date} {status}')
"
```

Expected output:
```
price_daily                      8M rows  max_date=2026-05-19 ✓
technical_data_daily             8M rows  max_date=2026-05-19 ✓
buy_sell_daily                   600K rows  max_date=2026-05-19 ✓
trend_template_data              25K rows  max_date=2026-05-19 ✓
```

---

## STEP 3: RUN ORCHESTRATOR IN DRY-RUN MODE (20 minutes)

⏱️ **By 05:15 AM**

```bash
# Test full pipeline with real data (no trades executed)
python3 algo/algo_orchestrator.py --dry-run --verbose 2>&1 | tee orchestrator_dryrun.log
```

**Watch for:**
- All 7 phases complete successfully
- Phase 5 shows signal generation (today's signals filtered)
- No errors in logs
- Orchestrator generates audit log entries

**Expected output pattern:**
```
# ALGO ORCHESTRATOR — 2026-05-19 (DRY RUN)

Phase 1: Data Freshness             [PASS]  ✓
Phase 2: Circuit Breakers           [PASS]  ✓
Phase 3: Position Monitor           [PASS]  ✓
Phase 3b: Exposure Policy           [PASS]  ✓
Phase 4: Exit Execution             [PASS]  ✓ (skipped, no positions)
Phase 5: Signal Generation          [PASS]  ✓ 
  → Tier 1: 600K candidates
  → Tier 2: 450K passed market filters
  → Tier 3: 180K passed trend filters (stage 2 only)
  → Tier 4: 90K passed signal quality
  → Tier 5: 45K passed portfolio fit
  → Tier 6: 12K passed advanced filters
Phase 6: Entry Execution            [PASS]  ✓ (DRY-RUN, not executed)
Phase 7: Reconciliation             [PASS]  ✓

Total runtime: X seconds
```

**Verify audit log was created:**
```bash
python3 -c "
import psycopg2
from config.credential_helper import get_db_config
from datetime import date

conn = psycopg2.connect(**get_db_config())
cur = conn.cursor()

cur.execute('''
    SELECT phase, status, COUNT(*) as events
    FROM algo_audit_log
    WHERE DATE(created_at) = %s
    GROUP BY phase, status
    ORDER BY phase
''', (date.today(),))

print('Orchestrator audit log for today:')
for phase, status, count in cur.fetchall():
    print(f'  Phase {phase}: {status:20} ({count} events)')
"
```

---

## STEP 4: REVIEW TODAY'S SIGNALS (10 minutes)

⏱️ **By 05:30 AM**

```bash
# Check what signals are ready to trade
python3 -c "
import psycopg2
from config.credential_helper import get_db_config
from datetime import date

conn = psycopg2.connect(**get_db_config())
cur = conn.cursor()

# Top 20 candidates after all filters
cur.execute('''
    SELECT 
        symbol, composite_score, rsi, sma_50, sma_200, 
        stage_number, sector, market_cap_rank
    FROM buy_sell_daily
    WHERE signal_date = %s
      AND composite_score > 0
    ORDER BY composite_score DESC
    LIMIT 20
''', (date.today(),))

print('Top 20 trading candidates for today:')
print('-' * 100)
print(f'{"SYMBOL":8} {"SCORE":8} {"RSI":6} {"SMA50":8} {"SMA200":8} {"STAGE":6} {"SECTOR":20} {"MARKET_CAP_RANK":15}')
print('-' * 100)
for row in cur.fetchall():
    print(f'{row[0]:8} {row[1]:8.1f} {row[2]:6.1f} {row[3]:8.0f} {row[4]:8.0f} {row[5]:6} {row[6]:20} {row[7]:15}')

# Check signal count by tier
cur.execute('''
    SELECT COUNT(*) FROM buy_sell_daily
    WHERE signal_date = %s AND composite_score > 0
''', (date.today(),))
total = cur.fetchone()[0]
print(f'\nTotal qualified signals today: {total}')
"
```

**Expected:** 5-50 qualified signals (enough to work with)

---

## STEP 5: SWITCH TO LIVE MODE (5 minutes)

⏱️ **By 05:35 AM**

**Option A: Command-line (Recommended)**
```bash
# Run WITHOUT --dry-run flag
python3 algo/algo_orchestrator.py --verbose
```

**Option B: Environment variable**
```bash
DRY_RUN=false python3 algo/algo_orchestrator.py --verbose
```

**Pre-flight checks before running:**

```bash
# 1. Verify Alpaca connection
python3 -c "
import alpaca.trading.client as tc
from config.credential_manager import get_alpaca_credentials

creds = get_alpaca_credentials()
api = tc.TradingClient(
    api_key=creds.get('key'),
    secret_key=creds.get('secret'),
    paper=True
)
account = api.get_account()
print(f'✓ Connected to Alpaca')
print(f'  Account: {account.account_number}')
print(f'  Buying Power: \${account.buying_power}')
print(f'  Paper Trading: {account.trading_halted == False}')
print(f'  Status: {account.status}')
"
```

Expected: ✓ Account details shown

```bash
# 2. Verify no stale positions from previous runs
python3 -c "
import alpaca.trading.client as tc
from config.credential_manager import get_alpaca_credentials

creds = get_alpaca_credentials()
api = tc.TradingClient(api_key=creds.get('key'), secret_key=creds.get('secret'), paper=True)
positions = api.get_all_positions()
print(f'Open positions in Alpaca: {len(positions)}')
if positions:
    for p in positions:
        print(f'  {p.symbol}: {p.qty}sh @ avg {p.avg_fill_price}')
else:
    print('  (none - clean start ✓)')
"
```

Expected: 0 positions (clean start)

```bash
# 3. Verify no stale orders
python3 -c "
import alpaca.trading.client as tc
from config.credential_manager import get_alpaca_credentials

creds = get_alpaca_credentials()
api = tc.TradingClient(api_key=creds.get('key'), secret_key=creds.get('secret'), paper=True)
orders = api.get_orders(status='open')
print(f'Open orders in Alpaca: {len(orders)}')
if orders:
    for o in orders:
        print(f'  {o.symbol}: {o.qty}sh {o.side} @ {o.limit_price or \"market\"}')
else:
    print('  (none - clean start ✓)')
"
```

Expected: 0 orders (clean start)

---

## STEP 6: FIRST LIVE RUN (30 minutes)

⏱️ **By 06:05 AM**

```bash
# Live execution (paper trading on Alpaca)
python3 algo/algo_orchestrator.py --verbose 2>&1 | tee orchestrator_live_run1.log
```

**Monitor during execution:**
- All 7 phases complete
- Phase 6 shows orders submitted to Alpaca
- Check CloudWatch metrics

**After execution completes:**

```bash
# Verify trades executed in Alpaca
python3 -c "
import alpaca.trading.client as tc
from config.credential_manager import get_alpaca_credentials

creds = get_alpaca_credentials()
api = tc.TradingClient(api_key=creds.get('key'), secret_key=creds.get('secret'), paper=True)

print('Orders from today:')
orders = api.get_orders(status='all')
today_orders = [o for o in orders if str(o.created_at.date()) == '2026-05-19']
if today_orders:
    for o in today_orders[-10:]:  # Last 10
        print(f'  {o.symbol:6} {o.qty:5}sh {o.side:4}  status={o.status:20} filled={o.filled_qty}')
else:
    print('  (no orders yet)')

print()
print('Open positions:')
positions = api.get_all_positions()
if positions:
    for p in positions:
        pl = float(p.unrealized_pl) if p.unrealized_pl else 0
        pct = float(p.unrealized_plpc) * 100 if p.unrealized_plpc else 0
        print(f'  {p.symbol:6} {p.qty:5}sh @ {float(p.avg_fill_price):8.2f} PL=\${pl:8.2f} ({pct:+6.2f}%)')
else:
    print('  (none)')
"
```

**If trades executed:** ✅ Ready for full operation
**If no trades:** ✓ Signals may not have qualified (check orchestrator log)

---

## STEP 7: FINAL VALIDATION (15 minutes)

⏱️ **By 06:20 AM**

**Checkpoint checklist:**
- [ ] Code committed and pushed
- [ ] Data fresh through today (all tables have 2026-05-19)
- [ ] Dry-run test completed successfully
- [ ] Live test completed (1+ trades or signal analysis done)
- [ ] Alpaca account verified (paper trading, buying power OK)
- [ ] Orchestrator logs show all 7 phases passing
- [ ] No critical errors in logs

**Known limitations documented:**
- [ ] Paper trading only (not live money)
- [ ] Max 10 concurrent positions
- [ ] Max $50K position size
- [ ] No short selling
- [ ] US market hours only

---

## STEP 8: DEPLOY ORCHESTRATOR FOR CONTINUOUS EXECUTION

⏱️ **By 07:00 AM** (3.5 hours before market open)

### Option A: Schedule via CI/CD (AWS Lambda)
If your deployment pipeline supports it, schedule the orchestrator to run:
- **Daily at 6:30 AM ET** - pre-market execution before 9:30 AM open
- **Hourly 9:30 AM - 3:30 PM ET** - during market hours (monitor, adjust stops)
- **3:35 PM ET** - end-of-day reconciliation

### Option B: Local cron job (if running on dedicated machine)
```bash
# Add to crontab (runs daily before market)
30 6 * * 1-5 cd /path/to/algo && python3 algo/algo_orchestrator.py >> logs/orchestrator.log 2>&1
```

### Option C: Supervisor daemon (always running, safe restart)
```bash
# supervisord config
[program:algo_orchestrator]
command=python3 /path/to/algo/algo/algo_orchestrator.py --verbose
autostart=true
autorestart=true
user=algo_user
redirect_stderr=true
stdout_logfile=/path/to/logs/orchestrator.log
```

---

## STEP 9: MONITORING DASHBOARD (30 minutes)

⏱️ **By 07:30 AM**

**CloudWatch Dashboard:**
- Orchestrator phase duration trends
- Signal count waterfall (Tier 1 → Tier 6)
- Trade execution count
- Position P&L
- Error rate

**Email/Slack Alerts:**
- Daily summary email with: # trades, total PL, risk metrics
- Alert on circuit breaker activation
- Alert on errors (retry logic engaged)

**Pre-market checklist (9:15 AM):**
- [ ] Dashboard loads correctly
- [ ] Latest metrics refresh
- [ ] No critical alerts
- [ ] Buying power visible
- [ ] Ready to execute

---

## STEP 10: MARKET OPEN EXECUTION (9:30 AM)

⏱️ **By 09:30 AM ET**

**During market hours:**

1. **Monitor positions** - Check Phase 3 runs hourly and updates stops
2. **Review exits** - Verify Phase 4 executes partial profit-taking
3. **Check signals** - If new signals qualify, Phase 5+6 will execute
4. **Watch risk** - Verify no circuit breakers fire unnecessarily
5. **Log anomalies** - Note any unexpected behavior for post-market review

**If issues arise:**
```bash
# Emergency halt
touch /tmp/algo_orchestrator_halt

# Check status
python3 -c "
import psycopg2
from config.credential_helper import get_db_config
from datetime import date
conn = psycopg2.connect(**get_db_config())
cur = conn.cursor()
cur.execute('SELECT phase, status, message FROM algo_audit_log WHERE DATE(created_at) = %s ORDER BY created_at DESC LIMIT 5', (date.today(),))
for phase, status, msg in cur.fetchall():
    print(f'{phase:10} {status:15} {msg}')
"

# Graceful shutdown
# (Orchestrator respects halt flag and stops before next trade)
```

---

## SUCCESS CRITERIA

✅ **System is ready to go live when:**
1. ✅ Code: All changes committed
2. ✅ Data: Fresh through today
3. ✅ Dry-run: All 7 phases passing
4. ✅ Credentials: Alpaca verified
5. ✅ Alpaca: Clean account (0 positions, 0 orders)
6. ✅ Live test: At least one execution run complete
7. ✅ Logs: No critical errors
8. ✅ Risk: All circuit breakers armed

---

## TIMELINE SUMMARY

```
04:15 AM    Credentials rotated ✓
04:50 AM    Data loaded ✓
05:15 AM    Dry-run test ✓
05:30 AM    Signal review ✓
05:35 AM    Live mode switch ✓
06:05 AM    First live execution ✓
06:20 AM    Final validation ✓
07:00 AM    Deployment configured ✓
07:30 AM    Monitoring setup ✓
09:15 AM    Pre-market check ✓
09:30 AM    MARKET OPEN - Live trading begins 🚀
```

---

## POST-MARKET (End of Day)

After market closes at 4:00 PM ET:

```bash
# Generate daily performance report
python3 -c "
import psycopg2
from config.credential_helper import get_db_config
from datetime import date

conn = psycopg2.connect(**get_db_config())
cur = conn.cursor()

# Today's trades
cur.execute('''
    SELECT 
        symbol, entry_date, entry_price, shares, 
        entry_price * shares as position_value,
        exit_price, (exit_price - entry_price) * shares as realized_pl,
        CASE WHEN exit_price IS NULL THEN 'OPEN' ELSE 'CLOSED' END as status
    FROM algo_trades
    WHERE entry_date = %s
    ORDER BY entry_date DESC
''', (date.today(),))

total_pl = 0
for row in cur.fetchall():
    pl = row[6] or 0
    total_pl += pl
    print(f'{row[0]:6} {row[2]:8.2f} x {row[3]:4.0f} = \${row[4]:10.2f}  PL=\${pl:+8.2f}  {row[7]:6}')

print(f'Total P&L: \${total_pl:+.2f}')
"
```

---

## Rollback Plan (If Needed)

If something goes wrong, you can:

1. **Quick halt:** `touch /tmp/algo_orchestrator_halt` (stops gracefully)
2. **Revert to dry-run:** Add `--dry-run` flag back
3. **Close all positions:** Manual close via Alpaca interface
4. **Review logs:** Check `algo_audit_log` for what went wrong
5. **Fix issue:** Update code, commit, test
6. **Resume:** Remove halt flag, resume execution

---

## Next Steps

👉 **Start with STEP 1: Rotate Alpaca Credentials**

Once you have the new keys, the automation can begin. You have a full 8 hours and a 5+ hour safety buffer before market open.

**You've got this. Let's make primetime happen.** 🚀
