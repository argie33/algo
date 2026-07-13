# Project Quick Reference

**Status:** ✅ Production Ready (Session 107 - Fixed orchestrator Phase 9 AlgoConfig type mismatch + Windows Unicode issue. Dashboard auto-detects localhost. System fully operational.)

## Start Here

1. **Dashboard "data not available"?** → `DASHBOARD_TROUBLESHOOTING.md` (Auto-detect works - no flag needed)
2. **Local dev setup?** → `QUICKSTART_LOCAL.md`
3. **Architecture & rules?** → `steering/GOVERNANCE.md`
4. **AWS/deployment?** → `steering/OPERATIONS.md`
5. **Data loading system?** → `steering/DATA_LOADERS.md`
6. **Lambda 503 errors?** → `steering/AWS_LAMBDA_503_FIX.md`
7. **AWS billing emails & cost controls?** → `BILLING_QUICK_REFERENCE.md` (or `steering/AWS_BILLING_AND_COST_CONTROLS.md`)
8. **Troubleshooting?** → `steering/COMMON_OPERATIONS.md`

## Quick Setup (LOCAL DEVELOPMENT)

**CRITICAL: Follow these steps EXACTLY to avoid "data not available" errors**

**Step 1: Open TERMINAL 1** - Run the backend API (localhost:3001)
```bash
python3 api-pkg/dev_server.py
```
Wait for this exact output:
```
[INFO] Starting API dev server on http://localhost:3001
[INFO] Press Ctrl+C to stop
```
**Keep this terminal open and running.**

**Step 2: Open TERMINAL 2** - Run the dashboard (ONLY after Terminal 1 shows "running")
```bash
python3 -m dashboard
```
Or with watch mode for auto-refresh every 30 seconds:
```bash
python3 -m dashboard -w 30
```

**KEY REQUIREMENTS:**
- ✅ **ALWAYS start Terminal 1 first** - Dashboard needs dev_server to fetch data
- ✅ **Keep both terminals running** - If either crashes, restart it independently
- ✅ **Dashboard takes 3-5 seconds to load** - Fetches data from all 26 sources, shows "Fetching..." spinner initially
- ✅ **AUTO-DETECT**: Dashboard automatically detects localhost:3001 and uses it (no --local flag needed)

**If you see "Data not available" on all panels:**
- ❌ Is dev_server still running in Terminal 1? (check the window, it must stay open)
- ❌ Is stock_scores data stale? (circuit breaker blocks trading if data >24h old)
  - FIX: `python3 scripts/run_local_orchestrator.py --morning` to refresh data
- ❌ Did you restart dashboard before dev_server was ready? (restart dashboard after dev_server prints "running")

**Diagnostic commands:**
```bash
# Comprehensive dashboard setup check (recommended if data not loading)
python3 scripts/diagnose_dashboard.py

# System-wide diagnostic
python3 scripts/diagnose_system.py
```

**Expected output from diagnose_dashboard.py:**
```
[OK] Dev Server: Dev server is running on localhost:3001
[OK] Database: Database connected (8,600,000+ price records)
[OK] API Endpoints: API responding with data (200 OK)
[OK] Dashboard Module: Dashboard module can be imported
[!] LOCAL_MODE env var: (OK if you're using --local flag)
```

## System Status

- **Database:** PostgreSQL, 8.6M+ prices, fresh data
- **Dashboard (Local):** ✅ All 26 fetchers working when using `--local` flag + dev_server running
- **Dashboard (AWS Lambda):** ⚠️ May timeout with 503 errors - VPC cold-start exceeds 29s API Gateway timeout (see fix below)
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
| **Dashboard: "Data not available" on all panels (v2)** | dev_server not running when dashboard starts | Start Terminal 1: `python3 api-pkg/dev_server.py` FIRST, wait for "running on http://localhost:3001", THEN start Terminal 2: dashboard |
| **AWS Mode: Lambda 503 "Service Unavailable"** | VPC cold-start (15-40s) exceeds API Gateway 29s timeout | See `steering/AWS_LAMBDA_503_FIX.md` - enable provisioned concurrency (5 units) to keep Lambda warm |
| **Dev server "Connection refused"** | dev_server not listening on localhost:3001 | Check Terminal 1 is running: `python3 api-pkg/dev_server.py` and wait for startup message |
| **PostgreSQL "connection refused"** | Database not running or wrong credentials | Verify: `python3 -c "import psycopg2; psycopg2.connect('dbname=stocks user=stocks host=localhost')"` |
| **Code fails pre-commit hooks** | Type errors or formatting issues | Run: `make format && make type-check` |
| **Orchestrator not executing** | Step Functions not triggered or EventBridge broken | Check: `aws stepfunctions describe-execution` + EventBridge Scheduler logs |
| **Data older than 4 hours** | Loaders not running per schedule | Check EventBridge Scheduler + CloudWatch logs for loader tasks |

## Non-Negotiable Rules

- **Type safety:** `mypy strict` enforced (pre-commit blocks all type errors)
- **Code cleanliness:** No `.env`, `pdb`, or `print()` in library code
- **Data integrity:** Explicit `data_unavailable` flags (no silent fallbacks)
- **Safety:** Circuit breakers enforce risk limits

See steering docs for architecture, policy details, and deployment procedures.
