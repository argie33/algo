# Run Algo Dashboard Locally - Complete Guide

## ONE-TIME SETUP (Done Once)

All infrastructure is already set up. Database has data. Just verify:

```bash
# Check everything is working
python check_system_health.py

# Expected output: ALL SYSTEMS OPERATIONAL
```

## DAILY STARTUP (3 Terminal Windows)

### TERMINAL 1: Start Backend API (keep running)
```bash
python lambda/api/dev_server.py
```
**Wait for output:**
```
[INFO] Starting API dev server on http://localhost:3001
[INFO] Uvicorn running on http://0.0.0.0:3001
```

### TERMINAL 2: Run Daily Orchestrator (wait 10 seconds after Terminal 1)
```bash
# Option A: Full refresh (prices, technicals, signals, portfolio reconciliation)
python scripts/run_local_orchestrator.py --run-all

# Option B: Morning pipeline only (if running early in day)
python scripts/run_local_orchestrator.py --morning
```

**Expected output (at end):**
```
FINAL REPORT - LOCAL-*
  [OK]  Phase 1: all_tables_fresh       
  [OK]  Phase 2: circuit_breakers       
  [OK]  Phase 3: position_monitor       
  [OK]  Phase 4: reconciliation         
  [OK]  Phase 5: exposure_policy        
  [OK]  Phase 6: exit_execution         
  [OK]  Phase 7: signal_generation      <-- SIGNALS GENERATED HERE
  [?]   Phase 8: entry_execution        <-- Expected to halt (no Alpaca)
  [OK]  Phase 9: reconciliation         

Status: OK - COMPLETED
```

### TERMINAL 3: Start Dashboard (after Terminal 2 completes)
```bash
# With auto-refresh every 30 seconds
python start_dashboard_dev.py -w 30

# Or standard start:
python dashboard.py --local
```

**Expected output:**
```
[INFO] Mode: local (localhost:3001)
[INFO] Dashboard ready at http://localhost:8080
[INFO] Refreshing data every 30s
```

Then open browser to **http://localhost:8080** or **http://127.0.0.1:8080**

## WHAT YOU'LL SEE ON DASHBOARD

### Dashboard Sections (All Working)
1. **Portfolio** - Total value, P&L, daily return
2. **Positions** - Open positions with entry price, current price, P&L
3. **Market Regime** - Current market exposure, regime (uptrend/caution/etc)
4. **Circuit Breakers** - All risk checks (should show green/clear)
5. **Phase 7 Signals** - Qualified BUY signals from today's run
6. **Portfolio Metrics** - Risk, Beta, concentration, VaR

All data is **FRESH** from the orchestrator run you just completed.

## MONITORING COMMAND (Optional, Terminal 4)

Watch data freshness in real-time:
```bash
# One-time check
python scripts/monitor_data_staleness.py

# Continuous monitoring (updates every 60s)
python scripts/monitor_data_staleness.py --watch 60
```

## COMMON SCENARIOS

### "I want to test Phase 7 signal generation"
1. Modify Phase 7 code (algo/orchestrator/phase7_signal_generation.py)
2. Run: `python scripts/run_local_orchestrator.py --run-all`
3. Check: Dashboard shows new signals (or orchestrator logs for Phase 7 output)
4. Iterate

### "Data looks stale"
```bash
# Run full refresh
python scripts/run_local_orchestrator.py --run-all

# Or refresh specific loader:
python scripts/run_loader.py prices --force-refresh
python scripts/run_loader.py technical --force-refresh
python scripts/run_loader.py scores --force-refresh
```

### "Dev server crashed"
1. Kill it (Ctrl+C or kill process)
2. Restart: `python lambda/api/dev_server.py`
3. Wait for "running on http://localhost:3001"
4. Reload browser (F5)

### "Dashboard shows old data"
1. Make sure Terminal 2 orchestrator completed
2. Reload browser (F5)
3. Or restart dashboard (Ctrl+C, then rerun)

### "I want to test without orchestrator overhead"
```bash
# Load a single phase directly
python -c "
from algo.orchestrator.phase7_signal_generation import run as run_phase7
result = run_phase7(
    run_date=today,
    dry_run=False,
    verbose=True,
    log_phase_result_fn=lambda *args, **kwargs: None,
    config={},
)
print(result)
"
```

## EXPECTED BEHAVIOR

### Success Indicators
- ✓ Orchestrator shows "Status: OK - COMPLETED"
- ✓ Phase 7 shows "X signals qualified from Y candidates"
- ✓ Dashboard loads without errors
- ✓ Portfolio value displays (e.g., $101,089)
- ✓ Market regime shows current state (e.g., confirmed_uptrend 78%)

### Expected Limitations (Normal)
- Phase 8 halts (no Alpaca creds) - this is OK, Phase 9 still runs
- Some symbols missing growth metrics (17 out of 10K) - acceptable
- No automatic 4:05 PM ET scheduler - run manually or cron
- Dashboard auth still checks (but works through dev_server)

### Things That Should NOT Happen
- ✗ Orchestrator status "HALTED" (indicates data problem)
- ✗ Phase 7 showing "no signals" (indicates data quality issue)
- ✗ Dashboard showing "Data not available" (dev_server not running)
- ✗ Database connection errors (PostgreSQL down)
- ✗ Prices older than 1 day (yfinance fetch failed)

## TROUBLESHOOTING QUICK REFERENCE

| Symptom | Check | Fix |
|---------|-------|-----|
| "Phase 7 no signals" | BUY signals table stale? | `python scripts/run_loader.py prices --force-refresh` |
| Orchestrator halts | Check latest run status | `python check_system_health.py` |
| Dashboard won't load | Is dev_server running? | Terminal 1 output or `curl http://localhost:3001/api/health` |
| Connection refused | PostgreSQL down? | `psql -d stocks -U stocks -h localhost` |
| Dev server port busy | Port 3001 taken? | `lsof -i :3001` then `kill -9 <PID>` |
| Data is 2+ days old | Loaders haven't run | `python scripts/run_local_orchestrator.py --run-all` |

## DEPLOYMENT READINESS

Once you're comfortable with local development:
1. Same codebase works in AWS with:
   - `ENVIRONMENT=production` (uses Lambda functions)
   - AWS credentials configured
   - DynamoDB locks instead of file locks
   - EventBridge Scheduler triggers orchestrator

2. No code changes needed - environment config handles the rest.

---

**You're all set. Happy testing!**
