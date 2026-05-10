# Loader Monitoring & Failure Detection

## Problem Solved

Before: Silent data failures — loaders could fail overnight with no alert, algo would run on stale/missing data

After: Comprehensive monitoring detects failures immediately, algo fails-closed before trading

## Components

### 1. `algo_loader_monitor.py` 
**Core monitoring engine** — checks data freshness state

```bash
# Check default critical symbols (AAPL, MSFT, NVDA, TSLA)
python3 algo_loader_monitor.py --check-freshness

# Check specific symbols
python3 algo_loader_monitor.py --check-symbols BRK.B,LEN.B,WSO.B

# JSON output for parsing
python3 algo_loader_monitor.py --check-freshness --json
```

**Checks performed:**
- **Per-symbol freshness** — alerts if AAPL, MSFT, NVDA, TSLA, SPY have no data
- **Daily load volume** — fails if < 4000 symbols loaded today (currently 0)
- **Universe coverage %** — warns if < 95% of symbols updated (98.6% now)
- **Stale symbols** — lists symbols with data > 5 days old (COEP, FOLD, etc)

### 2. `algo_loader_health_check.py`
**Standalone health monitor** — runs hourly via cron/EventBridge

```bash
# Local test
python3 algo_loader_health_check.py

# Returns exit code 0 (healthy) or 1 (issues)
# Sends email alerts if critical issues detected
```

**Use case:** Schedule to run 1 hour before algo execution to catch failures early

### 3. `algo_alerts.py` — New method: `send_loader_alert()`
**Alert handler** — sends email/webhook when loaders fail

Triggered by:
- `algo_loader_health_check.py` (hourly proactive check)
- `algo_orchestrator.py` Phase 1 (before each algo run)

**Email includes:**
- Severity (CRITICAL / ERROR / WARN)
- Findings (missing symbols, low volume, stale data)
- Action steps (check status, trigger loaders, review logs)

### 4. `algo_orchestrator.py` — Phase 1 Integration
**Fail-closed logic** in data freshness check:

1. Runs `LoaderMonitor.audit_all()` with critical symbols
2. **FAILS if:**
   - 0 symbols loaded today (no data ingestion)
   - Critical symbols missing (AAPL, MSFT, etc)
3. **WARNS if:** Other load volume issues (< 4000 when typically 5000+)
4. **Sends alert** before halting

Current behavior with stale data:
```
❌ Phase 1 fails → Algo halts → Alert sent
✓ No trades execute on stale/missing data
```

## Current System State (2026-05-09)

```
Loader Status:      FAILED ❌
  - Daily volume:   0 symbols (expected: 4000+)
  - Universe coverage: 98.6% (OK)
  - Critical symbols missing: QQQ, IWM
  - Stale symbols: COEP(15d), FOLD(12d), HVT.A(12d), SEMR(12d), EM(10d)

Algo Status:        HALTED ✓
  - Will not trade until data loads
  - Email alerts configured for failures
```

## Testing

```bash
# Verify orchestrator fails-closed on missing data
python3 -c "
from algo_orchestrator import Orchestrator
orch = Orchestrator(dry_run=True, verbose=False)
result = orch.phase_1_data_freshness()
assert result == False, 'Should have failed on zero data loaded'
print('✓ Orchestrator correctly halts on missing data')
"

# Verify monitor detects the issue
python3 algo_loader_monitor.py --check-freshness
# Output shows: 1 CRITICAL, 1 ERROR, 1 WARN
```

## Configuration

Alert settings in `.env.local`:
```bash
ALERT_EMAIL_FROM=noreply@algo.local
ALERT_EMAIL_TO=argeropolos@gmail.com
ALERT_SMTP_HOST=smtp.gmail.com
ALERT_SMTP_PORT=587
ALERT_SMTP_USER=your-gmail@gmail.com
ALERT_SMTP_PASSWORD=your-app-password
ALERT_WEBHOOK_URL=https://hooks.slack.com/services/...  # Optional
```

## Deployment

Lambda deployment:
```bash
# Files are copied to lambda-deploy/ for packaging
ls lambda-deploy/algo_loader_*

# Lambda orchestrator includes Phase 1 check automatically
# No additional Lambda function needed
```

CloudWatch/EventBridge setup (to run health check hourly):
```bash
# Schedule health check 1 hour before algo runs (e.g., 4:30pm ET for 5:30pm algo)
aws scheduler create-schedule \
  --name loader-health-check \
  --schedule-expression 'cron(0 20 ? * MON-FRI *)' \
  --target-role-arn arn:aws:iam::ACCOUNT:role/service-role/EventBridgeRole \
  --flexible-time-window '{"Mode":"OFF"}' \
  --target '{"Arn":"arn:aws:lambda:us-east-1:ACCOUNT:function:algo-loader-health-check"}'
```

## Recovery Steps

If loaders are failing:

1. **Check status immediately**
   ```bash
   python3 algo_loader_monitor.py --check-freshness
   ```

2. **Trigger loaders manually** (local)
   ```bash
   python3 loadpricedaily.py
   python3 loadbuysell_etf_daily.py
   # etc for each loader
   ```

3. **Check ECS task logs** (cloud)
   ```bash
   aws ecs describe-tasks --cluster stocks-data-cluster --tasks <task-arn> --region us-east-1
   aws logs tail /aws/ecs/stocks-loaders --follow
   ```

4. **Verify data loaded**
   ```bash
   python3 -c "
   import psycopg2, os
   from dotenv import load_dotenv
   from pathlib import Path
   from datetime import date
   
   load_dotenv(Path('.env.local'))
   conn = psycopg2.connect(host=os.getenv('DB_HOST'), user=os.getenv('DB_USER'), 
                           password=os.getenv('DB_PASSWORD'), database=os.getenv('DB_NAME'))
   cur = conn.cursor()
   cur.execute('SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = CURRENT_DATE')
   count = cur.fetchone()[0]
   print(f'Symbols with today\'s data: {count}')
   conn.close()
   "
   ```

5. **Once data loads, algo auto-resumes** (no manual restart needed)

## Future Enhancements

- [ ] SMS alerts via Twilio (on CRITICAL)
- [ ] Slack app integration (rich formatting)
- [ ] Per-symbol reload retry logic
- [ ] Orphaned loader task cleanup
- [ ] Data freshness dashboard (Grafana)
