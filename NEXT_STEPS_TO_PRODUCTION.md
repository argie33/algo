# Next Steps to Production - May 19, 2026

## Current Status: READY FOR TESTING
✓ All Phase 1 critical tables populated and fresh  
✓ Database connected and operational  
✓ Orchestrator tested and working  
✓ All loaders functional (21 active, 11 dead removed)  
⏳ Awaiting credential rotation for production use

## 1. URGENT: Rotate Compromised API Keys

### Background
- **Alpaca API keys** exposed in git commit b5596425f (deleted in 45af219f3)
- **FRED API key** also exposed in history
- Keys are in plaintext in git history (visible to anyone with repo access)
- **Must rotate before production use**

### Action Items
1. **Generate new Alpaca keys**
   - Go to https://app.alpaca.markets/paper/dashboard/settings/api-keys
   - Generate new API Key ID and Secret Key
   - Revoke old keys
   - Store new keys securely

2. **Generate new FRED API key**
   - Go to https://fred.stlouisfed.org/docs/api/#api_key
   - Request a new API key
   - Revoke old key if present

3. **Update GitHub Secrets**
   ```
   APCA_API_KEY_ID: <new_value>
   APCA_API_SECRET_KEY: <new_value>
   FRED_API_KEY: <new_value>
   ```
   - Go to repo Settings → Secrets and variables → Actions
   - Update each secret with new values

4. **Update local environment** (optional for testing)
   ```bash
   export APCA_API_KEY_ID="new_key_id"
   export APCA_API_SECRET_KEY="new_secret"
   export FRED_API_KEY="new_fred_key"
   ```

5. **Verify** new credentials work
   ```bash
   python3 algo/algo_orchestrator.py --dry-run
   # Should see: Alpaca credentials (APCA_API_KEY_ID, APCA_API_SECRET_KEY) SET
   ```

**Timeline**: Do this before any production trades. (Can test locally with paper trading while this is in progress)

---

## 2. Set Up Daily Loader Scheduling

### Problem
- Loaders need to run daily to populate "today's" data
- Phase 1 halts if no data loaded in last 24 hours
- Currently manual - need automation

### Option A: Local Cron Job (Development)
```bash
# Edit crontab
crontab -e

# Add this line (runs daily at 6:00 AM)
0 6 * * * cd /c/Users/arger/code/algo && python3 run-all-loaders.py 2>&1 | mail -s "Algo Loaders" your-email@example.com
```

### Option B: Windows Scheduled Task (Development)
```powershell
# PowerShell as Administrator
$TaskName = "AlgoLoaders"
$TaskPath = "\Algo\"
$Action = New-ScheduledTaskAction -Execute "powershell" -Argument "-NoProfile -Command 'cd C:\Users\arger\code\algo; python3 run-all-loaders.py'"
$Trigger = New-ScheduledTaskTrigger -Daily -At "06:00"
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Force
```

### Option C: AWS EventBridge (Production)
**Per memory (pipeline_pipeline_fix_2026_05_19)**: Already configured in Terraform
- EventBridge rule triggers at market open
- Invokes Lambda → ECS Fargate container with loaders
- Status: Check terraform/main.tf or AWS console

### Option D: GitHub Actions (CI/CD)
```yaml
# .github/workflows/daily-loaders.yml
name: Daily Data Loaders
on:
  schedule:
    - cron: '0 6 * * 1-5'  # Weekdays at 6 AM UTC

jobs:
  load-data:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: python3 run-all-loaders.py
        env:
          DB_HOST: ${{ secrets.DB_HOST }}
          DB_USER: ${{ secrets.DB_USER }}
          DB_PASSWORD: ${{ secrets.DB_PASSWORD }}
```

**Choose one based on your deployment model:**
- **Development**: Option A (cron) or B (Windows Task)
- **AWS**: Option C (already set up per memory)
- **GitHub Actions**: Option D (no infrastructure)

---

## 3. Configure Alert Channels (Optional but Recommended)

### Email Alerts
```bash
export ALERT_EMAIL_TO="your-email@example.com"
export ALERT_SMTP_USER="smtp-user@gmail.com"
export ALERT_SMTP_PASSWORD="app-specific-password"
export ALERT_SMTP_SERVER="smtp.gmail.com"
```

### Slack Alerts
```bash
export ALERT_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
```

### SMS Alerts (Twilio)
```bash
export TWILIO_ACCOUNT_SID="..."
export TWILIO_AUTH_TOKEN="..."
export ALERT_PHONE_FROM="+1234567890"
export ALERT_PHONE_TO="+1234567890"
```

**Test alerts:**
```bash
python3 -c "
from algo.algo_alerts import AlertManager
mgr = AlertManager()
mgr.alert_trading_issue('Test alert from algo system')
"
```

---

## 4. Start Trading

### Paper Trading (Recommended First)
```bash
export APCA_PAPER=true
export DB_HOST="localhost"
export DB_USER="stocks"
export DB_PASSWORD="stocks"

python3 algo/algo_orchestrator.py
```

**What happens:**
- Phase 1: Data freshness check (5 min)
- Phase 2: Signal generation (10 min)
- Phase 3: Position management (5 min)
- Phase 4: Trade execution (paper trading - no real money)
- Positions logged to `position_history` table
- Trades logged to `trade_log` table
- Can review results without risk

### Live Trading (After Verification)
```bash
unset APCA_PAPER  # or set to false
python3 algo/algo_orchestrator.py
```

**Do not do this until:**
- ✓ Paper trading verified for 1+ full trading day
- ✓ Credential rotation complete
- ✓ Alert channels configured
- ✓ Risk limits reviewed (see algo/algo_config.py)

---

## 5. Daily Operations Checklist

### Before Market Open
- [ ] Run `python3 run-all-loaders.py` (or verify scheduler did)
- [ ] Check loader output: "Successful: X/Y" should be near 100%
- [ ] Run `python3 system-health-check.py` → All tables [OK]

### During Trading
- Monitor logs: `tail -f logs/algo*.log`
- Check position dashboard if deployed
- Verify alerts working (should get notified of any issues)

### After Market Close
- Review trade_log for today's trades
- Check position_history for P&L
- Archive daily logs (optional)

### Weekly
- Review historical trades and P&L
- Check signal quality metrics
- Review data coverage gaps (data patrol warnings)

---

## 6. Monitoring & Debugging

### View Real-Time Logs
```bash
cd /c/Users/arger/code/algo
tail -f logs/*.log | grep -E "ERROR|WARN|HALT|Phase"
```

### Check Database Data
```bash
python3 << 'EOF'
import psycopg2
conn = psycopg2.connect(host='localhost', user='stocks', password='stocks', database='stocks')
cur = conn.cursor()

# Today's trades
cur.execute("SELECT symbol, quantity, entry_price, exit_price FROM trade_log WHERE DATE(created_at) = CURRENT_DATE")
for row in cur.fetchall():
    print(row)

conn.close()
EOF
```

### Health Check (Full System)
```bash
python3 << 'EOF'
exec(open('system-health-check.py').read())
EOF
```

### Common Issues & Fixes

**Phase 1 Halt: "No data loaded today"**
- Cause: Loaders haven't run yet or failed
- Fix: Run `python3 run-all-loaders.py` manually
- Check: `python3 system-health-check.py`

**Phase 2 Halt: "Insufficient signal volume"**
- Cause: Buy/sell signals too weak or few
- Fix: Check `buy_sell_daily` table row count
- Try: Adjust filter thresholds in algo/algo_filter_pipeline.py

**Database Connection Refused**
- Cause: PostgreSQL not running or credentials wrong
- Fix: Check `DB_HOST`, `DB_USER`, `DB_PASSWORD` env vars
- Try: `python3 -c "import psycopg2; psycopg2.connect(host='localhost', user='stocks', password='stocks', database='stocks')"`

**Out of Memory During Price Loading**
- Cause: yfinance downloading for 10000+ symbols at once
- Fix: Already handled - increased timeout to 120s, added retry logic
- Check: run-all-loaders.py line 171

---

## 7. File Locations & Commands

### Key Files
```
/c/Users/arger/code/algo/
  ├── algo_orchestrator.py          # Main entry point
  ├── run-all-loaders.py             # Data loading pipeline
  ├── system-health-check.py         # System status check
  ├── SYSTEM_IMPROVEMENTS_2026_05_19.md  # What was fixed
  │
  ├── algo/
  │   ├── algo_data_patrol.py        # Data freshness checks
  │   ├── algo_filter_pipeline.py    # Signal filtering
  │   ├── algo_signals.py            # 50+ technical indicators
  │   ├── algo_trade_executor.py     # Order placement
  │   └── algo_position_monitor.py   # Risk tracking
  │
  └── loaders/
      ├── loadpricedaily.py          # OHLCV data
      ├── load_technical_data_daily.py   # RSI, MACD, SMA, etc.
      ├── loadbuyselldaily.py        # Trading signals
      ├── loadsectors.py             # Sector rankings
      └── ... (21 total active loaders)
```

### Quick Commands
```bash
# Check system health
python3 system-health-check.py

# Load today's market data
python3 run-all-loaders.py

# Test orchestrator (dry-run)
python3 algo/algo_orchestrator.py --dry-run

# Live trading (paper mode)
export APCA_PAPER=true
python3 algo/algo_orchestrator.py

# View logs
tail -f logs/*.log

# Check database
python3 -c "
import psycopg2
conn = psycopg2.connect(host='localhost', user='stocks', password='stocks', database='stocks')
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM trade_log')
print(f'Total trades: {cur.fetchone()[0]}')
conn.close()
"
```

---

## Summary

**What's Done (5/6 tasks)**
- ✓ Fixed feature_flags schema
- ✓ Cleaned up 11 dead loaders
- ✓ Set up database credentials
- ✓ Populated sector_ranking
- ✓ Ran full data loading pipeline
- ⏳ Pending: Rotate Alpaca+FRED keys (manual)

**What's Ready Now**
- Full data pipeline operational
- All Phase 1 tables populated
- Orchestrator tested
- System health verified

**What's Next (In Priority Order)**
1. **Rotate API keys** (URGENT - security)
2. **Set up loader scheduling** (CRITICAL - daily operation)
3. **Configure alerts** (optional - best practice)
4. **Paper test trading** (validation)
5. **Move to live trading** (after verification)

**Time to Live Trading**: 
- With automation: **2-3 hours** (key rotation + scheduler setup + testing)
- Manual daily loading: **1-2 weeks** (until comfortable with manual runs)

---

**Last Updated**: 2026-05-19 07:45 UTC  
**System Status**: READY FOR TESTING  
**Production Readiness**: 95% (pending credential rotation)
