# GET SYSTEM LIVE IN 5 MINUTES

**This guide gets your trading system executing real trades TODAY.**

---

## Step 1: Get Your Alpaca API Keys (2 minutes)

### If you DON'T have an Alpaca account yet:
1. Go to https://app.alpaca.markets/
2. Click "Sign Up"
3. Complete registration (free, no deposit required for paper trading)
4. After login, click your name → "Account" → "API Keys"
5. Copy these two values:
   - **API Key ID** (format: `PK_PAPER_xxxxxxxxxxxxx`)
   - **Secret Key** (long random string)

### If you ALREADY have an account:
1. Log in to https://app.alpaca.markets/
2. Click your name → "Account" → "API Keys"
3. Copy the same two values above

---

## Step 2: Add to GitHub Secrets (2 minutes)

1. Open: https://github.com/argie33/algo/settings/secrets/actions
2. Click "New repository secret"
3. Enter:
   - **Name:** `ALPACA_API_KEY_ID`
   - **Value:** [Paste your PK_PAPER_xxxxx key]
   - Click "Add secret"
4. Repeat for second secret:
   - **Name:** `APCA_API_SECRET_KEY`
   - **Value:** [Paste your secret key]
   - Click "Add secret"

✅ Both secrets are now in GitHub.

---

## Step 3: Deploy (1 minute)

Choose one option:

### Option A: Auto-deploy (Recommended)
```bash
git push
# GitHub Actions automatically runs CI → deploys to AWS
# Watch: https://github.com/argie33/algo/actions
```

### Option B: Manual trigger
1. Go to: https://github.com/argie33/algo/actions/workflows/deploy-all-infrastructure.yml
2. Click "Run workflow"
3. Select branch: `main`
4. Click green "Run workflow" button
5. Wait 5-10 minutes for deployment

---

## Step 4: Verify It Works (1 minute)

Once deployment completes, verify the system is trading:

```bash
# Check if orchestrator can access credentials
python scripts/test_full_trading_pipeline.py
# Should see: [SUCCESS] Full trading pipeline is operational

# Or run the local orchestrator
python scripts/run_local_orchestrator.py --morning
# Look for: [PHASE 8] Alpaca credentials loaded successfully
#          [PHASE 8] Entered X positions
```

---

## Step 5: Watch It Trade Automatically

The system now trades automatically on this schedule:

### Morning (2:00 AM ET)
- Loads prices & technical data
- Generates trading signals (9-12 qualified trades)
- **Executes buy orders** ← YOUR TRADES ENTER HERE
- Positions appear in your Alpaca account

### End of Day (4:05 PM ET)
- Calculates quality/growth/value metrics
- Updates stock scores
- Queues exit signals

### During Market Hours
- Phase 3 monitors open positions
- Phase 6 executes exits at profit targets
- Dashboard tracks P&L in real-time

---

## Verification Checklist

After setup, verify each component works:

### 1. Check Credentials Are Set
```bash
# Credentials should load without errors
python -c "from config.credential_manager import get_credential_manager; print('OK')"
```

### 2. Check Phase 1 Data Validation
```bash
# Should pass all freshness checks
python scripts/check_system_health.py
```

### 3. Check Signals Generate
```bash
# Should show "X qualified signals generated"
python scripts/run_local_orchestrator.py --morning 2>&1 | grep "Phase 7"
```

### 4. Check Phase 8 Executes
```bash
# Should show "Entered X positions"
python scripts/run_local_orchestrator.py --morning 2>&1 | grep "PHASE 8"
```

### 5. Check Dashboard
```bash
python start_dashboard_dev.py
# Visit http://localhost:3001
# Should see: Open positions, P&L, trading signals
```

---

## What Happens After Setup

### Positions Appear in Alpaca
- Log into https://app.alpaca.markets/
- Go to "Account" → "Positions"
- You'll see your open positions from the algo system

### Dashboard Shows Everything
- http://localhost:3001 shows:
  - Open positions (qty, entry price, current P&L)
  - Generated signals (today's buy signals)
  - Portfolio metrics (total P&L, allocations)
  - Sector breakdown
  - Risk metrics

### Automatic Trading Starts
- 2:00 AM ET each trading day: Positions enter
- During day: Positions monitored, exits triggered
- 4:05 PM ET: Metrics updated for next day
- No manual intervention needed

---

## Troubleshooting

### "Credentials not found" error
**Solution:** Verify secrets added correctly
```bash
# GitHub won't show secret values, but you can verify they exist
# Go to: https://github.com/argie33/algo/settings/secrets/actions
# Both ALPACA_API_KEY_ID and APCA_API_SECRET_KEY should be listed
```

### "No positions entering" 
**Possible causes:**
1. Deployment not complete (check GitHub Actions)
2. No qualified signals (check Phase 7 output)
3. Market hours check (algo only trades during 9:30 AM - 4:00 PM ET)

**Verify:**
```bash
# Check latest logs
python scripts/run_local_orchestrator.py --morning 2>&1 | tail -50
# Look for: [PHASE 8] Alpaca credentials loaded successfully
```

### "Orchestrator not running on schedule"
**Solution:** Verify EventBridge Scheduler is configured
```bash
python scripts/verify_eventbridge_scheduler.py
# Should show: Morning schedule: ENABLED, EOD schedule: ENABLED
```

---

## What You Just Enabled

✅ **Automated Trading System**
- Generates 9-12 qualified trading signals daily
- Enters positions automatically
- Monitors with live P&L
- Exits at profit targets & stops
- Calculates returns
- Runs 24/7 without intervention

✅ **Risk Management**
- Circuit breakers (halt on market extremes)
- Position limits (20% max per stock)
- Stop losses (ATR-based)
- Liquidity filters (avoids illiquid stocks)

✅ **Monitoring & Alerts**
- Real-time dashboard
- P&L tracking
- Signal quality metrics
- Trade audit log

✅ **Production Infrastructure**
- AWS cloud deployment
- Event-driven scheduling
- Database persistence
- Credential security (AWS Secrets Manager)

---

## Next Steps (Optional)

### Monitor Actively
```bash
# Watch data freshness
python scripts/monitor_data_staleness.py --watch 60
# Checks every 60 seconds, exits if data stale
```

### Adjust Settings
Edit `algo_config` table to customize:
- `max_positions` (default: 5)
- `max_risk_pct` (default: 2%)
- `initial_capital_paper_trading` (default: $100k)

### View Trade History
```bash
# Check all executed trades
python -c "
import psycopg2
conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
cur = conn.cursor()
cur.execute('SELECT symbol, qty, entry_price, entry_date FROM algo_trades ORDER BY entry_date DESC LIMIT 10')
for row in cur:
    print(row)
"
```

---

## CRITICAL: You're Now Live

Once you complete these 5 steps:
- **Real money is NOT at risk** (paper trading)
- **But real trades ARE executing** to your account
- **Monitor the first few days** to ensure signals look reasonable
- **Pause trading** if anything looks wrong (set `max_positions=0` in config)

---

## Questions?

See these docs:
- **Architecture:** `steering/GOVERNANCE.md`
- **Data Loading:** `steering/DATA_LOADERS.md`
- **Troubleshooting:** `steering/COMMON_OPERATIONS.md`
- **Dashboard:** `DASHBOARD_TROUBLESHOOTING.md`

---

## Summary

**You have everything needed.** This guide gets you from "system ready" to "system trading" in 5 minutes flat.

1. Get API keys (2 min)
2. Add to GitHub Secrets (2 min)
3. Deploy (1 min)
4. Verify (1 min)
5. **System trades automatically**

🚀 **Your automated trading system is ready to launch.**

The only thing between you and live trading is running these 4 steps.
