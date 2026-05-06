# Complete System Deployment Checklist

Your data patrol + monitoring system is **fully built** and ready to deploy. This checklist covers configuration, testing, and production launch.

---

## 🎯 What You Have

### 4 Tiers of Monitoring

| Tier | Scope | Checks | Frequency | Alert On |
|------|-------|--------|-----------|----------|
| **Tier 1** | Critical blocking | 4 checks | Daily | CRITICAL or ERROR >2 |
| **Tier 2** | Data quality | 10 checks | Daily | Missing/corrupt data |
| **Tier 3** | Trends & perf | Config + trends + concentration + speed | Weekly | Degradation, slow checks |
| **Tier 4** | Advanced | Market calendar + continuous + metrics | Continuous (15min) | Real-time issue detection |

### 20 Total Checks

**Data Quality (P1-P17):**
- P1: Staleness | P2: NULL anomalies | P3: Zero/identical OHLC | P3b: Corporate actions
- P4: Price sanity | P5: Volume sanity | P5b: OHLC relationships
- P6: Cross-source validation (Alpaca/Yahoo) | P6b: Signal-data alignment
- P7: Universe coverage | P8: Sequence continuity | P9: DB constraints
- P10: Score freshness | P11: Loader contracts | P12: Earnings data
- P13: ETF data | P14: Cross-alignment | P15: Fundamentals | P16: Trade-price alignment
- P17: Derived metrics (RSI bounds, etc.)

**Position & Account:**
- Stale order detection (>1 hour)
- Sector concentration check (>3 same sector)
- Position-Alpaca reconciliation
- Stop price validation

**Observability:**
- Configuration audit (thresholds logged)
- Quality trends (7/30/90 day windows)
- Patrol performance tracking
- Market calendar (holidays, early closes)
- Continuous critical monitoring (15min intervals)

### 3 Alert Channels

- ✅ **Email** (Gmail SMTP)
- ✅ **SMS** (Twilio)
- ✅ **Slack** (webhooks)

---

## 📋 Pre-Deployment Checklist

### Phase 1: Environment Setup (15 minutes)

- [ ] **Gmail app password**
  - Go to https://myaccount.google.com/apppasswords
  - Select Mail + your device type
  - Copy 16-character password

- [ ] **Twilio account** (optional but recommended)
  - Sign up at https://www.twilio.com/console (free: 1000 SMS/month)
  - Create trial number (e.g., +1-414-XXX-XXXX)
  - Copy Account SID, Auth Token, Twilio number

- [ ] **Slack webhook** (optional)
  - Go to Slack workspace → Manage apps → Create New App
  - Name: "Algo Alerts"
  - Enable Incoming Webhooks
  - Create webhook to #trading-alerts channel
  - Copy webhook URL

### Phase 2: Configure .env.local (5 minutes)

Create/update `.env.local` in project root:

```bash
# Gmail (required)
ALERT_EMAIL_FROM=edgebrookecapital@gmail.com
ALERT_EMAIL_TO=argeropolos@gmail.com
ALERT_SMTP_HOST=smtp.gmail.com
ALERT_SMTP_PORT=587
ALERT_SMTP_USER=edgebrookecapital@gmail.com
ALERT_SMTP_PASSWORD=<your_16_char_app_password_no_spaces>

# Twilio (optional but recommended for SMS)
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_PHONE_NUMBER=+1-414-XXX-XXXX
ALERT_PHONE_NUMBERS=+1-312-307-8620

# Slack (optional)
ALERT_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# Database (should already be set)
DB_HOST=localhost
DB_PORT=5432
DB_USER=stocks
DB_PASSWORD=your_password
DB_NAME=stocks

# Alpaca (should already be set for reconciliation)
APCA_API_KEY_ID=your_key
APCA_API_SECRET_KEY=your_secret
APCA_API_BASE_URL=https://paper-api.alpaca.markets
```

**Important:** `.env.local` is in `.gitignore` — never commit it

### Phase 3: Install Dependencies (2 minutes)

```bash
pip install -r requirements.txt
# or just the new one
pip install twilio
```

### Phase 4: Test Everything (15 minutes)

```bash
# Test 1: Market calendar
python3 algo_market_calendar.py

# Test 2: All components
python3 test_patrol_system.py

# Test 3: Send actual alert
python3 test_patrol_system.py --send-test-alert
# Check: email arrives in argeropolos@gmail.com
# Check: SMS arrives on +1-312-307-8620
# Check: Slack message in #trading-alerts (if configured)

# Test 4: Quality trends
python3 algo_quality_trends.py --days 7

# Test 5: Continuous monitor (runs once)
python3 algo_continuous_monitor.py --once
```

**All tests should show ✓ or [OK]**

### Phase 5: Dry-Run Orchestrator (5 minutes)

```bash
# Run in paper mode, skip actual trades
python3 algo_orchestrator.py --dry-run --skip-entries

# Watch output:
#   - Patrol runs (16 checks)
#   - Reconciliation runs
#   - Positions reviewed
#   - Alerts send if issues found
```

Check logs:
```bash
psql stocks -c "SELECT * FROM data_patrol_log ORDER BY created_at DESC LIMIT 20"
psql stocks -c "SELECT * FROM algo_audit_log ORDER BY created_at DESC LIMIT 10"
```

### Phase 6: Verify Database (2 minutes)

```bash
# Check patrol logging works
psql stocks -c "SELECT COUNT(*) FROM data_patrol_log"

# Should show recent entries (within last 24 hours)
psql stocks -c "
  SELECT created_at, severity, check_name, message
  FROM data_patrol_log
  ORDER BY created_at DESC LIMIT 5"
```

---

## 🚀 Production Deployment

### Option A: Full Automation (Recommended)

**Daily orchestrator run:**
```bash
# Add to crontab (runs at 8:00 AM before market open)
0 8 * * 1-5 cd /path/to/algo && python3 algo_orchestrator.py >> /var/log/algo_orchestrator.log 2>&1
```

**Continuous monitoring (15 min intervals during market hours):**
```bash
# Add to crontab (runs every 15 min, 9:30 AM - 4:00 PM ET, Mon-Fri)
*/15 9-16 * * 1-5 cd /path/to/algo && python3 algo_continuous_monitor.py --once >> /var/log/algo_monitor.log 2>&1
```

**Weekly trend analysis (Friday 5 PM):**
```bash
0 17 * * 5 cd /path/to/algo && python3 algo_quality_trends.py --days 7 >> /var/log/algo_trends.log 2>&1
```

### Option B: Manual Runs

**Morning (before market open):**
```bash
python3 algo_orchestrator.py
```

**During market (optional, for real-time monitoring):**
```bash
python3 algo_continuous_monitor.py
```

**Weekly review:**
```bash
python3 algo_quality_trends.py --days 7
```

### Option C: Docker / Systemd

If using containers or systemd services, create wrapper scripts that:
1. Load .env.local
2. Run orchestrator/continuous monitor
3. Log to syslog
4. Email logs on failure

---

## 📊 Daily Operations

### Before Market Open (8:00 AM)

```bash
# Run full orchestrator
python3 algo_orchestrator.py

# Expected output:
#   - Data Patrol: 16 checks
#   - Phase 1-7 results
#   - Final audit log entry
```

**If CRITICAL alert received:**
1. Check email/SMS immediately
2. Run: `python3 algo_data_patrol.py --json | jq '.all_results[] | select(.severity=="critical")'`
3. Fix the underlying issue (see MONITORING_SYSTEM.md)
4. Run patrol again: `python3 algo_data_patrol.py --quick`
5. Continue once clear

**If ERROR alert received:**
1. Investigate the 2+ error findings
2. Decide: can we trade with this issue? If unsure, pause until fixed
3. Fix and re-run patrol

**If WARN only:**
1. Note the finding
2. Continue running
3. Monitor for patterns

### During Market Hours

**Optional: Continuous monitoring**
```bash
python3 algo_continuous_monitor.py
```
- Runs every 15 minutes (P1/P3/P7/P9 only)
- Alerts immediately if critical checks fail
- Auto-stops at market close

### Weekly Review (Friday 5 PM)

```bash
python3 algo_quality_trends.py --days 7
```

Shows:
- Finding trends (better/worse/stable)
- Recurring issues (same check failing repeatedly)
- Quality degradation alerts

**If quality degrading:**
1. Identify the check with most failures
2. Review recent changes to that loader/computation
3. Fix or escalate to engineering

---

## 🔧 Troubleshooting

### Alerts Not Arriving

```bash
# Check email config
python3 -c "
from algo_alerts import AlertManager
a = AlertManager()
print(f'From: {a.email_from}')
print(f'To: {a.email_to}')
print(f'SMTP: {a.smtp_host}:{a.smtp_port}')
print(f'User: {a.smtp_user}')
print('Password: ' + ('SET' if a.smtp_password else 'NOT SET'))
"

# Test send
python3 algo_alerts.py
```

**If still failing:**
- Check .env.local is readable: `cat .env.local | grep ALERT`
- Check Gmail app password is correct (no spaces)
- Check Gmail "Less secure apps" is enabled
- Try: `echo "test" | swaks --tls --host smtp.gmail.com --port 587 --auth LOGIN --auth-user EMAIL --auth-password PASS --to argeropolos@gmail.com`

### Patrol Slow (>2 minutes)

```bash
# Identify slow check
python3 algo_data_patrol.py 2>&1 | grep -i "slow\|seconds"

# Profile individual checks
time python3 -c "from algo_data_patrol import DataPatrol; p = DataPatrol(); p.connect(); p.check_loader_contracts(); p.disconnect()"
```

**Common causes:**
- Large DB table without indexes → add indexes
- SQL query scans full table → add WHERE clause
- Network latency → check DB connectivity

**Fix:**
```sql
-- Add indexes if missing
CREATE INDEX IF NOT EXISTS idx_price_daily_date ON price_daily(date);
CREATE INDEX IF NOT EXISTS idx_price_daily_symbol ON price_daily(symbol);
CREATE INDEX IF NOT EXISTS idx_technical_data_daily_date ON technical_data_daily(date);
```

### Reconciliation Shows Divergence

```bash
# Check what Alpaca actually has
python3 -c "
from alpaca.trading.client import TradingClient
tc = TradingClient(api_key='...', secret_key='...')
for pos in tc.get_all_positions():
    print(f'{pos.symbol}: {pos.qty} @ {pos.current_price}')"

# Check DB
psql stocks -c "
SELECT symbol, quantity, status
FROM algo_positions
WHERE status='open' AND quantity > 0
ORDER BY symbol"

# Sync (manual if needed)
UPDATE algo_positions SET status='closed' WHERE symbol='ABC' AND status='open'
```

### Market Calendar Wrong

```bash
# Check holidays
python3 -c "
from algo_market_calendar import MarketCalendar, US_HOLIDAYS
from datetime import date
today = date.today()
for hol, name in sorted(US_HOLIDAYS.items()):
    if hol.year == today.year:
        print(f'{hol}: {name}')"

# Update holidays in algo_market_calendar.py if needed
```

---

## 📈 Monitoring Dashboard

**Create a simple bash script to check health:**

```bash
#!/bin/bash
# health_check.sh
echo "=== ALGO HEALTH CHECK ==="
echo
echo "Latest patrol run:"
psql stocks -c "
  SELECT created_at, severity, COUNT(*) as count
  FROM data_patrol_log
  WHERE created_at > NOW() - INTERVAL '24 hours'
  GROUP BY created_at, severity
  ORDER BY created_at DESC LIMIT 5"
echo
echo "Recent alerts:"
psql stocks -c "
  SELECT created_at, status
  FROM algo_audit_log
  WHERE created_at > NOW() - INTERVAL '24 hours'
  ORDER BY created_at DESC LIMIT 5"
echo
echo "Open positions:"
psql stocks -c "
  SELECT symbol, quantity, current_price, unrealized_pnl_pct
  FROM algo_positions
  WHERE status='open' ORDER BY symbol"
```

Run daily:
```bash
bash health_check.sh
```

---

## ✅ Deployment Sign-Off

Before going live, verify:

- [ ] All tests pass (`test_patrol_system.py`)
- [ ] Alert arrives via email + SMS (test alert)
- [ ] Dry-run orchestrator completes without errors
- [ ] DB has patrol logs from last 24 hours
- [ ] No CRITICAL findings in patrol results
- [ ] Market calendar shows correct holidays
- [ ] .env.local configured (not in git)
- [ ] Cron/scheduler configured (if automated)
- [ ] Logs configured (stdout or files)
- [ ] On-call process documented

**You're ready to launch!**

---

## 📞 Support

**For issues:**
1. Check MONITORING_SYSTEM.md (16-page reference)
2. Check troubleshooting section above
3. Check patrol logs: `SELECT * FROM data_patrol_log WHERE severity IN ('error', 'critical')`
4. Check audit logs: `SELECT * FROM algo_audit_log ORDER BY created_at DESC`

**For questions:**
- Market calendar: `python3 algo_market_calendar.py`
- Patrol results: `python3 algo_data_patrol.py --json`
- Reconciliation: `python3 algo_reconciliation.py`
- Trends: `python3 algo_quality_trends.py --days 7`

**Live monitoring:**
```bash
# Watch patrol as it runs
watch -n 5 "psql stocks -c 'SELECT created_at, severity, check_name FROM data_patrol_log ORDER BY created_at DESC LIMIT 10'"

# Watch for alerts
watch -n 5 "psql stocks -c 'SELECT created_at, status FROM algo_audit_log ORDER BY created_at DESC LIMIT 5'"
```

---

## 🎉 Summary

You now have a **production-grade data patrol system** that:
- ✅ Validates 17 aspects of data quality daily
- ✅ Reviews positions and stops continuously
- ✅ Reconciles account state nightly
- ✅ Alerts you via email + SMS + Slack
- ✅ Tracks quality trends over time
- ✅ Fails closed on critical issues
- ✅ Provides full audit trail

**Deploy with confidence!**
