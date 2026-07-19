# Dashboard Troubleshooting Guide

Last updated: 2026-07-17 (Session 203)

Quick reference for diagnosing dashboard issues. Always run `python check_system_health.py` first.

---

## "Data Not Available" on All Panels

**Symptom:** Dashboard shows "Data not available" for Portfolio, Performance, Market, Circuit Breakers, etc.

### Step 1: Check System Health
```bash
python check_system_health.py
```

This checks:
- Database connectivity
- Dev server (localhost:3001)
- Orchestrator status
- Module imports

---

## AWS Mode Issues

**Dashboard tries to connect to AWS Lambda but data fails to load:**

### Step 1: Verify AWS Credentials
```bash
# Check if credentials are cached
python -c "from dashboard.credentials_provider import CredentialsProvider; cp = CredentialsProvider(); print(cp.get_credentials())"
```

If this fails or hangs, credentials are not available in Secrets Manager.

### Step 2: Verify Lambda Endpoint
```bash
# Check if API Gateway endpoint is reachable
curl -I https://<your-api-gateway-url>/api/health
# Should return HTTP 200
```

If HTTP 503 (Service Unavailable), see `steering/AWS_LAMBDA_503_FIX.md`.

### Step 3: Check Lambda CloudWatch Logs
```bash
aws logs tail /aws/lambda/algo-api-dev --follow
# Watch for errors as you refresh dashboard
```

---

## Local Dev Mode Issues

### Dev Server Not Running
**Symptom:** "Connection refused on localhost:3001"

```bash
# Terminal 1: Start dev server
python lambda/api/dev_server.py

# Wait for:
# [INFO] Starting API dev server on http://localhost:3001

# Terminal 2: Run dashboard
python dashboard.py
# Or with auto-refresh:
python dashboard.py -w 30
```

**Alternative: Use unified startup script**
```bash
python start_dashboard_dev.py
# This auto-detects and starts everything
```

### Dev Server Starts But Dashboard Still Shows "Data Not Available"

**Step 1:** Verify dev_server is actually running
```bash
curl http://localhost:3001/api/health
# Should return: {"status": "ok"}
```

**Step 2:** Check if dashboard is connecting to dev_server
```bash
# Run dashboard with verbose logging
python dashboard.py --local 2>&1 | grep -i "connect\|localhost\|3001"
```

**Step 3:** Refresh data locally
```bash
python3 scripts/run_local_orchestrator.py --morning
# Wait for orchestrator to complete
# Then refresh dashboard (Ctrl+R or F5)
```

**Step 4:** Check database connectivity
```bash
python -c "import psycopg2; c = psycopg2.connect('dbname=stocks user=stocks host=localhost'); print('✓ DB connected')"
```

If this fails, PostgreSQL is not running or credentials are wrong.

---

## Stale Data Issues

**Symptom:** Dashboard shows data older than expected (prices, portfolio values old).

### Root Causes by Age

**Different tables have different freshness thresholds.** See `utils/validation/freshness_config.py` for exact values.

| Data Type | Acceptable Age | Risk Level | Fix |
|-----------|---|---|---|
| **Prices** (price_daily) | < 1d (24h) | CRITICAL if > 1d | Run: `python scripts/run_local_orchestrator.py --morning` |
| **Portfolio snapshots** (algo_portfolio_snapshots) | < 1d (24h) | CRITICAL if > 1d | Run Phase 9: `python3 -c "from algo.orchestrator import phase9_reconciliation; phase9_reconciliation.run(...)"` |
| **Performance metrics** (algo_performance_daily) | < 1d (24h) | CRITICAL if > 1d | Rerun orchestrator morning pipeline |
| **Risk metrics** (algo_risk_daily) | < 1d (24h) | CRITICAL if > 1d | Rerun orchestrator morning pipeline |
| **Weekly prices** (price_weekly) | < 7d | HIGH if > 7d | Rerun with weekly aggregation |
| **Monthly prices** (price_monthly) | < 30d | MEDIUM if > 30d | Rerun with monthly aggregation |

**Quick check:** `python scripts/monitor_data_staleness.py` shows actual age of each table.

### Quick Data Refresh (Local)
```bash
# Run all three pipeline phases locally
python3 scripts/run_local_orchestrator.py --run-all

# Then refresh dashboard
# Wait 30-60s for data to process
```

### Check Data Freshness Status
```sql
-- Portfolio age
SELECT EXTRACT(EPOCH FROM (NOW() - MAX(created_at)))/3600 as hours_old
FROM algo_portfolio_snapshots;

-- Price data age
SELECT EXTRACT(EPOCH FROM (NOW() - MAX(date)))/3600 as hours_old
FROM stock_prices_daily;

-- Technical indicators age
SELECT EXTRACT(EPOCH FROM (NOW() - MAX(date)))/3600 as hours_old
FROM technical_data_daily;
```

---

## Circuit Breaker Not Showing (HTTP 500 Error)

**Symptom:** Circuit breaker panel shows error, `/api/algo/circuit-breakers` returns 500.

### Step 1: Check Lambda VPC Configuration
```bash
# Verify Lambda has VPC access to database
bash scripts/fix-lambda-vpc.sh
```

This ensures Lambda can reach RDS. See `steering/AWS_LAMBDA_503_FIX.md` for manual fix.

### Step 2: Check Database Connectivity
```bash
# Verify RDS is reachable
aws rds describe-db-instances --db-instance-identifier algo-db --region us-east-1
```

### Step 3: Verify Circuit Breaker Table Data
```sql
SELECT * FROM algo_circuit_breaker_status LIMIT 1;
-- Should have recent timestamp
```

---

## Portfolio Data Missing (No Positions Showing)

**Symptom:** "Portfolio value: N/A", no positions listed.

### Root Cause: Phase 9 Not Running

Portfolio data lives in `algo_portfolio_snapshots`, created by Phase 9 (Daily Reconciliation) of the orchestrator.

### Quick Fix (AWS)
1. AWS Lambda Console → `algo-orchestrator` function
2. Click **Test** tab → Create test event → **Test**
3. Wait 60-120 seconds
4. ✅ Status should show "success"
5. Refresh dashboard (5-30s refresh delay)

### Quick Fix (Local)
```bash
python3 scripts/run_local_orchestrator.py --morning
# Or use unified script
python start_dashboard_dev.py
```

### Check Latest Snapshot Age
```sql
SELECT 
  EXTRACT(EPOCH FROM (NOW() - MAX(created_at)))/60 as minutes_old,
  COUNT(*) as snapshot_count
FROM algo_portfolio_snapshots;
```

If minutes_old > 360 (6 hours), portfolio is stale.

---

## Performance Metrics Missing

**Symptom:** Performance panel shows "Data not available", no PnL history.

### Root Cause: Orchestrator Phase 9 or Trade Recording

Phase 9 creates `algo_portfolio_snapshots` which feeds performance metrics. If Phase 9 doesn't run, no snapshots = no performance data.

### Check Trade History
```sql
SELECT COUNT(*) as total_trades, MAX(entry_date) as latest_trade
FROM algo_trades;
```

If this returns 0 trades, no performance history can be shown (expected on first run).

---

## Market Regime Not Showing

**Symptom:** "Market: Data not available"

### Root Cause: Market Exposure Table Stale

`market_exposure_daily` is computed during EOD loader pipeline (4:05 PM ET).

### Verify Market Data Exists
```sql
SELECT * FROM market_exposure_daily ORDER BY date DESC LIMIT 1;
-- Should have recent date (within 24h)
```

### Force Refresh (Local)
```bash
python3 scripts/run_local_orchestrator.py --afternoon
```

---

## Earnings Blackout Not Respected

**Symptom:** Dashboard shows earnings blackout active, but trades still executed.

### Check Earnings Calendar
```sql
SELECT 
  symbol,
  DATE(earnings_date) as earnings_date,
  EXTRACT(DAY FROM (earnings_date - NOW())) as days_until_earnings
FROM earnings_calendar
WHERE symbol IN (SELECT symbol FROM algo_trades WHERE status = 'open')
ORDER BY earnings_date;
```

### Verify Configuration
```sql
SELECT * FROM algo_config WHERE key = 'enable_earnings_blackout';
-- Should show value = 'true'
```

### Manual Fix: Adjust Blackout Window
```sql
UPDATE algo_config 
SET value = '10' 
WHERE key = 'earnings_blackout_days_before';
-- Increases blackout from 7→10 days
```

---

## VIX Level Missing or Stale

**Symptom:** "VIX: Data not available"

### Root Cause: Market Health Loader Not Run

VIX comes from market health loader, part of EOD pipeline.

### Verify VIX Data
```sql
SELECT vix_level, EXTRACT(EPOCH FROM (NOW() - MAX(date)))/3600 as hours_old
FROM market_health_daily
ORDER BY date DESC LIMIT 1;
```

### Force Refresh
```bash
python3 scripts/run_local_orchestrator.py --afternoon
```

---

## System Health Check Failures

**Symptom:** `python check_system_health.py` shows ✗ failures.

See the output carefully — it lists:
- Database connectivity (PostgreSQL, credentials)
- Dev server availability (if using local mode)
- Orchestrator execution status (last run timestamp)
- Module import errors (missing dependencies, syntax)

### Common Fixes

| Error | Fix |
|-------|-----|
| `psycopg2: Connection refused` | Start PostgreSQL; verify credentials in .env or env vars |
| `Module import error: dashboard` | Run `pip install -e .` to reinstall package |
| `Dev server not responding` | Start `python lambda/api/dev_server.py` in Terminal 1 |
| `Orchestrator never run` | Run `python3 scripts/run_local_orchestrator.py --morning` |

---

## Performance Issues (Slow Load)

**Symptom:** Dashboard takes >10 seconds to load data.

### Step 1: Check Database Load
```sql
SELECT 
  pid, 
  query, 
  EXTRACT(EPOCH FROM (NOW() - query_start)) as runtime_sec
FROM pg_stat_activity
WHERE state = 'active'
ORDER BY query_start;
```

If any query > 60s, it's likely a slow data fetch.

### Step 2: Check Network Latency
```bash
# If AWS mode
time curl -s https://<api-gateway-url>/api/health | wc

# If local mode
time curl -s http://localhost:3001/api/health | wc
```

### Step 3: Reduce Dashboard Refresh Interval
```bash
# Instead of
python dashboard.py -w 10   # 10s refresh

# Try
python dashboard.py         # Manual refresh only (Ctrl+R)
```

---

## Dashboard Crashes or Shows Errors

**Symptom:** Dashboard process exits or shows unhandled exception.

### Check Logs
```bash
# If using unified startup script
python start_dashboard_dev.py 2>&1 | tail -100

# If using direct dashboard
python dashboard.py 2>&1 | tail -100
```

### Common Errors

**Error:** `ImportError: cannot import name 'X' from dashboard`
→ Module structure broken. Run `pip install -e .` to reinstall.

**Error:** `ConnectionRefusedError: localhost:3001`
→ Dev server not running. Start it in Terminal 1.

**Error:** `psycopg2.OperationalError: connection failed`
→ Database not accessible. Verify PostgreSQL running + credentials.

**Error:** `UnicodeEncodeError` (Windows only)
→ Fixed in Session 203. Upgrade to latest code: `git pull origin main`

---

## Still Stuck?

1. Run: `python check_system_health.py` (captures full system state)
2. Review output for ✗ failures
3. Check relevant section above for that failure type
4. If still stuck, check:
   - `steering/COMMON_OPERATIONS.md` — broader troubleshooting
   - `steering/LOADER_RECOVERY_GUIDE.md` — data pipeline issues
   - `steering/AWS_LAMBDA_503_FIX.md` — AWS-specific issues
5. Check git log for recent changes: `git log --oneline -20`
