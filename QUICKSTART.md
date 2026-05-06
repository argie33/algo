# Quick Start — 15 Minutes to Live Trading Surveillance

Complete data patrol + monitoring system. Ready to deploy.

---

## 🚀 Fastest Path: Automated Setup (Recommended)

```bash
# Run interactive setup (will prompt for credentials)
python3 setup.py

# Test alerts
python3 test_patrol_system.py --send-test-alert

# Deploy
bash deploy_cron.sh
```

**That's it. You're live.**

---

## 📋 Manual Setup (Alternative)

### ✅ Step 1: Get Credentials (5 minutes)

**Gmail app password:**
1. Go to https://myaccount.google.com/apppasswords
2. Select **Mail** + **Your Device** (e.g., "Windows Computer")
3. Google generates 16-character password
4. Copy it (no spaces)

**Optional: Twilio SMS**
1. Go to https://www.twilio.com/console
2. Create free account
3. Get trial phone number (+1-XXX-XXX-XXXX)
4. Copy Account SID + Auth Token

### ✅ Step 2: Configure Environment (5 minutes)

```bash
# Copy template to .env.local
cp .env.template .env.local

# Edit and fill in credentials
nano .env.local
# or
vim .env.local
# or your editor

# Paste:
# - Gmail app password → ALERT_SMTP_PASSWORD
# - Twilio SID → TWILIO_ACCOUNT_SID
# - Twilio Token → TWILIO_AUTH_TOKEN
# - Twilio Phone → TWILIO_PHONE_NUMBER
# - (keep ALERT_PHONE_NUMBERS as is)
```

### ✅ Step 3: Test Configuration (3 minutes)

```bash
# Test alert system (sends real email + SMS)
python3 test_patrol_system.py --send-test-alert

# Wait for:
# - Email in inbox ✓
# - SMS on phone ✓
# - Slack message (if configured) ✓
```

### ✅ Step 4: Deploy (2 minutes)

**Option A: Automatic (Recommended)**
```bash
# Set up daily automated runs
bash deploy_cron.sh
# Follow prompts, confirm cron job installation
```

**Option B: Manual Runs**
```bash
# Run once per day (8 AM)
python3 algo_orchestrator.py

# Save output
python3 algo_orchestrator.py | tee -a orchestrator.log
```

---

## 🚀 What Happens Now

### Daily (8:00 AM)
```
Runs: python3 algo_orchestrator.py
  ✓ Data patrol (17 checks)
  ✓ Position monitoring
  ✓ Alpaca reconciliation
  ✓ Alerts sent (email + SMS + Slack)
  ✓ Results logged to DB
```

### Every 15 Minutes (9:30 AM - 4:00 PM, during market)
```
Runs: python3 algo_continuous_monitor.py --once
  ✓ 4 critical checks
  ✓ Immediate alerts if issues found
  ✓ Auto-stops at 4 PM
```

### Weekly (Friday 5 PM)
```
Runs: python3 algo_quality_trends.py --days 7
  ✓ Analyzes error trends
  ✓ Detects quality degradation
  ✓ Recommends actions
```

---

## 📊 What Gets Monitored

| What | How Often | Alerts |
|------|-----------|--------|
| Data staleness, prices, volumes, signals | Daily | CRITICAL/ERROR |
| Position health, stops, concentration | Daily | ERROR/WARN |
| DB-Alpaca account sync | Daily | CRITICAL |
| Quality trends, error rates | Weekly | WARN |
| Critical data issues | Every 15 min | CRITICAL (real-time) |

---

## 🎯 Alert Response

**CRITICAL (Stop Everything)**
- Email + SMS + Slack
- Example: Data >7 days old, OHLC broken, coverage <90%
- Action: Stop trading immediately, investigate, fix, resume

**ERROR (Investigate)**
- Email + Slack
- Example: Stale orders, loader contract failed
- Action: Check what failed, fix if possible, continue

**WARN (Note)**
- Slack only
- Example: Unusual volume patterns
- Action: Just monitor, continue running

---

## 📝 Logs & Monitoring

**View real-time logs:**
```bash
# Daily orchestrator
tail -f /var/log/algo/orchestrator.log

# Continuous monitoring
tail -f /var/log/algo/monitor.log

# Weekly trends
cat /var/log/algo/trends.log
```

**Check database:**
```bash
# Latest patrol findings
psql stocks -c "
  SELECT created_at, severity, check_name, message
  FROM data_patrol_log
  ORDER BY created_at DESC LIMIT 10"

# Recent alerts
psql stocks -c "
  SELECT created_at, status, action_type
  FROM algo_audit_log
  ORDER BY created_at DESC LIMIT 10"

# Open positions
psql stocks -c "
  SELECT symbol, quantity, current_price, unrealized_pnl_pct
  FROM algo_positions
  WHERE status='open'
  ORDER BY symbol"
```

---

## 🛠️ Troubleshooting

### Test Alert Not Arriving

```bash
# Check config
python3 -c "
from algo_alerts import AlertManager
a = AlertManager()
print(f'Email to: {a.email_to}')
print(f'Password set: {bool(a.smtp_password)}')"

# Check credentials in .env.local
cat .env.local | grep ALERT
```

### Patrol Slow (>120 seconds)

```bash
# Add database indexes
psql stocks -c "
CREATE INDEX IF NOT EXISTS idx_price_daily_date ON price_daily(date);
CREATE INDEX IF NOT EXISTS idx_price_daily_symbol ON price_daily(symbol);
"
```

### Schema Mismatch Errors

These are normal. System gracefully skips checks for missing columns.
Check your actual table schema if you want to fix them:
```bash
psql stocks -c "\d table_name"
```

---

## 📚 Full Documentation

- `README_PRODUCTION.md` — Complete deployment guide
- `MONITORING_SYSTEM.md` — 16-page reference (what/when/why/how)
- `ALERT_SETUP.md` — Detailed alert setup
- `DEPLOYMENT_CHECKLIST.md` — Pre-flight checklist

---

## ✅ Success Criteria

When ready to trade:

- [ ] `.env.local` configured with credentials
- [ ] Test alert received (email + SMS)
- [ ] `python3 test_patrol_system.py` passes
- [ ] Cron jobs installed (or manual schedule set)
- [ ] No CRITICAL findings in patrol results
- [ ] Open a position and verify monitoring works

---

## 🎬 Deploy Now

```bash
# 1. Configure
cp .env.template .env.local
# Edit .env.local with your credentials

# 2. Test
python3 test_patrol_system.py --send-test-alert
# Check email + SMS arrived

# 3. Deploy
bash deploy_cron.sh
# Or run manually: python3 algo_orchestrator.py

# 4. Monitor
tail -f /var/log/algo/orchestrator.log
```

**That's it. You're live.**

---

Questions? See `README_PRODUCTION.md` (quick ref) or `MONITORING_SYSTEM.md` (complete).
