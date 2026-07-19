# Dev Server Startup Guide

## Current Status
- ✅ Log file is configured correctly: `C:\Users\arger\.algo\logs\dashboard-local.log`
- ❌ Dev server is NOT running on localhost:3001
- ❌ Positions data is empty (cannot fetch from API)
- ❌ Sector aggregation fails (requires positions data)

## Quick Fix - Start Everything Together

**Option 1: RECOMMENDED - Unified startup (handles everything)**
```bash
python start_dashboard_dev.py
```
This will:
1. Run morning pipeline (5-10 min) - loads prices + technicals
2. Run metrics pipeline if needed (5-10 min) - loads financial scores
3. Start dev_server on localhost:3001
4. Start dashboard pointing to dev_server
5. Auto-refresh every 30s

First run takes ~20 min (metrics refresh), subsequent runs ~2 min.

**Option 2: Manual - If you prefer 3 terminal windows**

Terminal 1: Start dev_server (API backend)
```bash
python lambda/api/dev_server.py
# Wait for: "Starting API dev server on http://localhost:3001"
```

Terminal 2: Start dashboard (in another terminal, after dev_server is ready)
```bash
python dashboard.py
```

Terminal 3 (Optional): Run loaders to refresh data
```bash
python scripts/run_local_orchestrator.py --morning
```

## Verify Everything is Working

```bash
# Check dev server is responding
curl http://localhost:3001/api/health

# Check dashboard logs
Get-Content $env:USERPROFILE/.algo/logs/dashboard-local.log -Tail 20

# Check database data freshness
python scripts/monitor_data_staleness.py
```

## What Each Component Does

| Component | Port | Purpose | Logs |
|-----------|------|---------|------|
| dev_server | 3001 | API backend | `lambda/api/dev_server.log` |
| dashboard | (web) | Web UI | `~/.algo/logs/dashboard-local.log` |
| loaders | (async) | Data pipeline | Orchestrator logs in DB |

## Common Issues

### Dev server won't start on port 3001
```bash
# Kill any orphaned dev_server processes (Windows)
wmic process where "CommandLine like '%dev_server%'" delete

# Then try again
python lambda/api/dev_server.py
```

### Dashboard still shows "data not available"
1. Make sure dev_server is running first
2. Check: `curl http://localhost:3001/api/health`
3. Check dashboard logs: `Get-Content ~/.algo/logs/dashboard-local.log -Tail 50`
4. Restart dashboard: `python dashboard.py`

### Positions data is still empty
1. Verify dev_server is running on localhost:3001
2. Run morning pipeline: `python scripts/run_local_orchestrator.py --morning`
3. Wait 5-10 minutes for loader to complete
4. Restart dashboard
