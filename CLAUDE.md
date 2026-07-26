# Project Quick Reference

**Status:** ✅ System fully operational — production-ready. All 9 orchestrator phases verified. See `steering/` docs for architecture, runbooks, and troubleshooting.

## Start Here

1. **Dashboard issues or "data not available"?** → `steering/COMMON_OPERATIONS.md`
2. **Local dev setup?** → `QUICKSTART_LOCAL.md`
3. **Architecture & rules?** → `steering/GOVERNANCE.md`
4. **AWS/deployment?** → `steering/OPERATIONS.md`
5. **Data loading system?** → `steering/DATA_LOADERS.md`
6. **Data stale or broken?** → `python scripts/monitor_data_staleness.py` + `steering/LOADER_RECOVERY_GUIDE.md`

## Quick Setup - AWS or LOCAL

### Local Development Mode (RECOMMENDED - Use This!)

**THIS IS THE ONLY CORRECT WAY TO RUN LOCAL DEVELOPMENT**

```bash
# Run this ONE command - handles everything automatically:
python start_dashboard_dev.py

# Optional: auto-refresh dashboard every 30 seconds
python start_dashboard_dev.py -w 30
```

**What it does:**
1. Fetches prices, technicals, market status
2. Refreshes scores if needed
3. Regenerates buy/sell signals (critical: always runs to avoid stale signals)
4. Starts dev_server on localhost:3001
5. Starts dashboard, cleans up on exit

**First run:** 20-30 minutes (includes metrics pipeline for 5000+ stocks)  
**Subsequent runs:** 5-10 minutes (skips metrics if fundamentals already fresh)

This approach ensures buy/sell signals regenerate with fresh prices every time (prior bug: signals frozen after metrics run).

### AWS Mode (Production/Cloud)

```bash
# Auto-detects AWS credentials and uses Lambda API
python dashboard.py
python dashboard.py -w 30    # Auto-refresh every 30s
```

AWS mode auto-fetches from Secrets Manager:
- `DASHBOARD_API_URL` - Lambda API Gateway endpoint
- `COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID`, `COGNITO_USERNAME`, `COGNITO_PASSWORD`

### Manual Setup (NOT RECOMMENDED - Only if start_dashboard_dev.py fails)

If `start_dashboard_dev.py` doesn't work, you can manually orchestrate, but this is error-prone:

```bash
# Terminal 1: Run backend API
python lambda/api/dev_server.py
# Wait for: [INFO] Starting API dev server on http://localhost:3001

# Terminal 2: Fetch fresh data (MUST run before dashboard)
python scripts/local_loader_scheduler.py --now morning
python scripts/local_loader_scheduler.py --now signals

# Terminal 3: Run dashboard
python dashboard.py --local       # Forces localhost:3001
python dashboard.py -w 30         # With auto-refresh
```

⚠️ **Risk:** If signals pipeline doesn't run, dashboard shows stale buy/sell signals.

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
3. Refresh data: `python3 scripts/local_loader_scheduler.py --now morning` (NOT
   `run_local_orchestrator.py` - that's the trading orchestrator, it reads existing DB
   data and does not fetch fresh prices/technicals/fundamentals; confirmed 2026-07-20)
4. Restart dashboard

## System Status

- **Database:** PostgreSQL, 8.6M+ prices
- **Dashboard:** ✅ Operational (AWS + local dev)
- **Dev Server:** ✅ Validation included
- **Orchestrator:** ✅ All 9 phases operational

## Running Orchestrator

**CRITICAL CONCEPTS:**
- **Data loaders** → Fetch prices/technicals/metrics from external sources (2 AM morning, 3:30 PM metrics, 4:05 PM signals ET)
- **Orchestrator** → Executes trades USING already-loaded data (9:30 AM, 1 PM, 3 PM ET)
- **Both must be fresh:** Orchestrator won't trade on stale prices (Phase 1 guard). Metrics must run BEFORE signals (3:30 PM < 4:05 PM) so stock_scores has fresh fundamentals.

**FOR LOCAL DEVELOPMENT:**
The unified launcher `start_dashboard_dev.py` runs everything in the right order:
1. Load fresh data (morning + signals pipelines)
2. Start API server
3. Start dashboard
4. Dashboard shows fresh signals

If you want to manually test orchestrator AFTER `start_dashboard_dev.py` has loaded fresh data:
```bash
python scripts/run_local_orchestrator.py              # morning run
python scripts/run_local_orchestrator.py --afternoon  # afternoon run
python scripts/run_local_orchestrator.py --evening    # evening run
```

**FOR PRODUCTION (AWS):**
Automatic schedules via Terraform EventBridge:
- **9:30 AM ET** → Morning execution at market open
- **1:00 PM ET** → Afternoon rebalance
- **3:00 PM ET** → Pre-close execution

All protected by Phase 8 market-hours guard (9:30 AM - 4:00 PM ET only).

**Check orchestrator status:**
```sql
SELECT overall_status, COUNT(*) as count, MAX(started_at) as latest
FROM algo_orchestrator_runs
WHERE started_at > NOW() - INTERVAL '24 hours'
GROUP BY overall_status
ORDER BY latest DESC;
```

## Common Fixes

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| **Dashboard: "Data not available" on all panels** | Manual setup with incomplete loader pipeline | Use: `python start_dashboard_dev.py` (unified launcher runs ALL pipelines) |
| **Buy/sell signals frozen/stale** | Only morning pipeline ran, signals pipeline skipped (pre-2026-07-21 bug) | Use: `python start_dashboard_dev.py` (guarantees signals pipeline always runs) |
| **Prices loaded but technicals missing** | Ran `load_prices.py` separately without running technicals loader | Use: `python start_dashboard_dev.py` (handles entire morning pipeline) |
| **"Data not available" after running manual loaders** | dev_server not running when dashboard started | Always start `start_dashboard_dev.py` (includes dev_server auto-startup) |
| **AWS Mode: Lambda 503 "Service Unavailable"** | VPC cold-start (15-40s) exceeds API Gateway 29s timeout | Enable provisioned concurrency (5 units) via Terraform |
| **PostgreSQL "connection refused"** | Database not running or wrong credentials | Verify: `psql -d stocks -c "SELECT 1"` |
| **Orchestrator halted with "data_incomplete"** | Not all stock prices/technicals loaded for the day | Run: `python start_dashboard_dev.py` to load complete dataset |
| **Code fails pre-commit hooks** | Type errors or formatting issues | Run: `make format && make type-check` |
| **Only VIX price in database** | Loader crashed/hung mid-execution | Restart: `python start_dashboard_dev.py` (retry with fresh process) |

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

**DATA LOADER schedules** (fetch external data):
- Morning: MON-FRI 2:00 AM ET (pre-market prices + technical indicators) - prepares data for 9:30 AM execution
- Metrics: MON-FRI 3:30 PM ET (slow SEC/EDGAR fundamentals: financial statements, 13F, insider, positioning, quality/growth/value) - runs BEFORE signals
- Signals/EOD: MON-FRI 4:05 PM ET (closing prices/technicals + stock scores/buy_sell_daily trading signals) - uses fresh fundamentals from metrics
- Weekends/holidays: No loaders run (expected behavior)
- Local dev: `scripts/local_loader_scheduler.py` mirrors this 3-pipeline split (`morning`/`metrics`/`signals`)

**ORCHESTRATOR (TRADING) schedules** (execute trades during market hours only):
- 9:30 AM ET: Morning execution at market open (PRIMARY)
- 1:00 PM ET: Afternoon rebalance (mid-day)
- 3:00 PM ET: Pre-close execution (before 4 PM close)
- All protected by Phase 8 market-hours guard (9:30 AM - 4:00 PM ET)
- Local dev: `scripts/run_local_orchestrator.py` - only Phase 8 executes if within market hours

**If data is stale during trading hours:**
1. Run: `python scripts/monitor_data_staleness.py` (diagnose)
2. Check: `python scripts/verify_eventbridge_scheduler.py` (verify schedules enabled)
3. Fix: `python scripts/local_loader_scheduler.py --now morning` (manual refresh - see note above, `run_local_orchestrator.py` does not fetch data)
4. See: `steering/LOADER_RECOVERY_GUIDE.md` (detailed recovery steps)


## Non-Negotiable Rules

- **Type safety:** `mypy strict` enforced (pre-commit blocks all type errors)
- **Code cleanliness:** No `.env`, `pdb`, or `print()` in library code
- **Data integrity:** Explicit `data_unavailable` flags (no silent fallbacks)
- **Safety:** Circuit breakers enforce risk limits
- **Loader dependencies:** Always use `start_dashboard_dev.py` - never run pipelines separately in local dev

See steering docs for architecture, policy details, and deployment procedures.
