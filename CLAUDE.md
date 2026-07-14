# Project Quick Reference

**Status:** ✅ Production Ready (Session 110 - Added data staleness monitoring & loader recovery guide. EventBridge scheduler properly configured (MON-FRI 2AM/4:05PM ET). System operational.)

## Start Here

1. **Dashboard "data not available"?** → `DASHBOARD_TROUBLESHOOTING.md` (Auto-detect works - no flag needed)
2. **Local dev setup?** → `QUICKSTART_LOCAL.md`
3. **Architecture & rules?** → `steering/GOVERNANCE.md`
4. **AWS/deployment?** → `steering/OPERATIONS.md`
5. **Data loading system?** → `steering/DATA_LOADERS.md`
6. **Data is stale (prices old)?** → `steering/LOADER_RECOVERY_GUIDE.md` + `python scripts/monitor_data_staleness.py`
7. **Lambda 503 errors?** → `steering/AWS_LAMBDA_503_FIX.md`
8. **AWS credentials rotation & cleanup?** → `IaC_CLEANUP_STATUS.md` (Automated via GitHub Actions + Terraform)
9. **AWS billing emails & cost controls?** → `BILLING_QUICK_REFERENCE.md` (or `steering/AWS_BILLING_AND_COST_CONTROLS.md`)
10. **Troubleshooting?** → `steering/COMMON_OPERATIONS.md`

## Quick Setup - AWS or LOCAL

### AWS Mode (Production/Cloud)

```bash
# Simplest: Just run it (AWS by default if credentials set; auto-fetches
# Cognito/API creds from Secrets Manager via dashboard/credentials_provider.py)
python dashboard.py
python dashboard.py -w 30    # Auto-refresh every 30s
```

AWS mode requires these credentials (auto-fetched from Secrets Manager):
- `DASHBOARD_API_URL` - Lambda API Gateway endpoint
- `COGNITO_USER_POOL_ID` - Cognito pool ID
- `COGNITO_CLIENT_ID` - Cognito app client ID
- `COGNITO_USERNAME` - User email
- `COGNITO_PASSWORD` - User password (from AWS Secrets Manager)

### Local Development Mode

**NEW: Unified startup script (auto-starts both dev_server and dashboard)**

```bash
# Recommended: Start with this ONE command
python start_dashboard_dev.py

# Or with auto-refresh every 30s
python start_dashboard_dev.py -w 30
```

This handles everything automatically:
- ✅ Detects if dev_server is running (localhost:3001)
- ✅ Starts dev_server if needed
- ✅ Waits for dev_server to be ready
- ✅ Starts dashboard
- ✅ Cleans up when you exit (Ctrl+C)

**Manual Setup (if preferred)**

```bash
# Terminal 1: Run backend API
python lambda/api/dev_server.py
# Wait for: [INFO] Starting API dev server on http://localhost:3001

# Terminal 2: Run dashboard (auto-detects localhost)
python dashboard.py              # Auto-connects to localhost
python dashboard.py -w 30        # Auto-refresh every 30s

# Or force local mode explicitly:
python dashboard.py --local      # Forces localhost:3001 (ignores AWS config)
```

## System Health Check

Before starting dashboard, verify everything is working:

```bash
python check_system_health.py
```

This checks:
- Database connectivity and data freshness
- Dev server availability
- Orchestrator execution status
- Dashboard module imports

**If you see "Data not available" on all panels:**
1. Run: `python check_system_health.py` (diagnose issues)
2. Verify dev_server is running: `curl http://localhost:3001/api/health`
3. Refresh data: `python3 scripts/run_local_orchestrator.py --morning`
4. Restart dashboard

## System Status

- **Database:** PostgreSQL, 8.6M+ prices, fresh data
- **Dashboard (AWS):** ✅ Fully operational with Cognito authentication, credentials auto-loaded from Secrets Manager
- **Dashboard (Local Dev):** ✅ All 26 fetchers working when using `--local` flag or detected localhost + dev_server running
- **Dashboard Startup:** ✅ Defaults to AWS (if configured), respects `--local` flag, auto-detects localhost
- **Circuit Breaker:** ✅ All 9 circuit breaker metrics available, auto-reset on dashboard startup
- **Dev Server:** ✅ Startup validation included - fails fast with clear instructions
- **Production Orchestrator:** ✅ Step Functions runs 2x daily (2:15 AM ET + 4:00 PM ET)

## Running Orchestrator

**Local/dev (NEW - Session 106):** Use the local runner for development (no AWS Lambda/EventBridge needed)
```bash
python3 scripts/run_local_orchestrator.py              # morning run (default)
python3 scripts/run_local_orchestrator.py --afternoon  # afternoon run
python3 scripts/run_local_orchestrator.py --evening    # evening run
python3 scripts/run_local_orchestrator.py --run-all    # all three runs
```

**Local/test (Legacy):** Via AWS Lambda (requires AWS credentials)
```bash
python3 scripts/trigger_orchestrator.py --run morning --mode paper
```

**Production:** Configured in `terraform/modules/services/2x-daily-orchestrator.tf`, runs via EventBridge Scheduler (4x daily: 9:30 AM, 1 PM, 3 PM, 5:30 PM ET).

**Check status:**
```sql
SELECT COUNT(*) as runs_last_hour, MAX(started_at) as latest
FROM algo_orchestrator_runs
WHERE started_at > NOW() - INTERVAL '1 hour';
```

## Common Fixes

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| **Dashboard: "Data not available" on all panels** | Dashboard running WITHOUT `--local` flag, trying AWS Lambda | Use: `python3 -m dashboard --local` (requires Terminal 1: dev_server running) |
| **Dashboard: "Data not available" on all panels (v2)** | dev_server not running when dashboard starts | Start Terminal 1: `python3 lambda/api/dev_server.py` FIRST, wait for "running on http://localhost:3001", THEN start Terminal 2: dashboard |
| **AWS Mode: Lambda 503 "Service Unavailable"** | VPC cold-start (15-40s) exceeds API Gateway 29s timeout | See `steering/AWS_LAMBDA_503_FIX.md` - enable provisioned concurrency (5 units) to keep Lambda warm |
| **Dev server "Connection refused"** | dev_server not listening on localhost:3001 | Check Terminal 1 is running: `python3 lambda/api/dev_server.py` and wait for startup message |
| **PostgreSQL "connection refused"** | Database not running or wrong credentials | Verify: `python3 -c "import psycopg2; psycopg2.connect('dbname=stocks user=stocks host=localhost')"` |
| **Code fails pre-commit hooks** | Type errors or formatting issues | Run: `make format && make type-check` |
| **Orchestrator not executing** | Step Functions not triggered or EventBridge broken | Check: `aws stepfunctions describe-execution` + EventBridge Scheduler logs |
| **Data older than 4 hours** | Loaders not running per schedule | Check EventBridge Scheduler + CloudWatch logs for loader tasks |

## Data Monitoring (Session 110+)

**Check data staleness:**
```bash
python scripts/monitor_data_staleness.py              # One-time check (exit code = # of stale tables)
python scripts/monitor_data_staleness.py --watch 60   # Poll every 60 seconds (Ctrl+C to exit)
```

**Verify EventBridge Scheduler is running:**
```bash
python scripts/verify_eventbridge_scheduler.py        # Check morning/EOD pipeline schedules
python scripts/verify_eventbridge_scheduler.py --fix  # Auto-enable if disabled
```

**Loader schedules:**
- Morning: MON-FRI 2:00 AM ET (prices + technical indicators)
- EOD: MON-FRI 4:05 PM ET (quality/growth/value metrics)
- Weekends/holidays: No loaders run (expected behavior)

**If data is stale during trading hours:**
1. Run: `python scripts/monitor_data_staleness.py` (diagnose)
2. Check: `python scripts/verify_eventbridge_scheduler.py` (verify schedules enabled)
3. Fix: `python scripts/run_local_orchestrator.py --morning` (manual refresh)
4. See: `steering/LOADER_RECOVERY_GUIDE.md` (detailed recovery steps)

## Non-Negotiable Rules

- **Type safety:** `mypy strict` enforced (pre-commit blocks all type errors)
- **Code cleanliness:** No `.env`, `pdb`, or `print()` in library code
- **Data integrity:** Explicit `data_unavailable` flags (no silent fallbacks)
- **Safety:** Circuit breakers enforce risk limits

See steering docs for architecture, policy details, and deployment procedures.
