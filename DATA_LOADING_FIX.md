# Dashboard "Data Not Available" - Root Cause & Fix

## The Problem

Dashboard shows "data not available" on all panels when you run:
```bash
python3 -m dashboard --local
```

## Root Cause

**The dev_server is NOT running.** 

The dashboard needs to connect to `http://localhost:3001` to fetch data. If this port is not available, all 26 data fetchers fail, causing every panel to show "data not available".

## The Fix

### Option 1: Use the Startup Script (RECOMMENDED)

**Windows (PowerShell):**
```powershell
.\scripts\start_dev_environment.ps1
```

**Linux/macOS:**
```bash
bash scripts/start_dev_environment.sh
```

This script:
- ✓ Checks if dev_server is already running
- ✓ Starts dev_server on port 3001 if needed  
- ✓ Waits for it to be ready
- ✓ Launches dashboard automatically
- ✓ Cleans up on exit

### Option 2: Manual Two-Terminal Setup

**Terminal 1** - Start API dev server:
```bash
python3 api-pkg/dev_server.py
```

Wait for this output:
```
2026-07-12 ... - INFO - Starting API dev server on http://localhost:3001
```

**Terminal 2** - Start dashboard (MUST use --local flag):
```bash
python3 -m dashboard --local
```

Key points:
- ⚠️ MUST use `--local` flag (enables localhost connection)
- ⚠️ Start Terminal 1 (dev_server) BEFORE Terminal 2 (dashboard)
- ⚠️ Keep Terminal 1 running while using dashboard
- ⚠️ Press Ctrl+C to stop (stops dashboard first, then dev_server)

## Why This Happens

| Scenario | Result | Fix |
|----------|--------|-----|
| Dev_server NOT running | Dashboard shows "data not available" on ALL panels | Start dev_server first |
| Dev_server running, no `--local` flag | Dashboard tries AWS Lambda, needs Cognito auth | Add `--local` flag |
| Dev_server running, WITH `--local` flag | ✓ Dashboard loads all 26 fetchers successfully | Everything works! |

## Verification

Test that the system is working:

```bash
# Terminal 1: Make sure dev_server is running
curl -H "Authorization: Bearer dev-admin" http://localhost:3001/api/algo/portfolio

# Should return:
# {"statusCode": 200, "data": {...portfolio data...}}

# Terminal 2: Run dashboard
python3 -m dashboard --local

# Should show: Loading... then display all panels with data
```

##  Troubleshooting

### "Connection refused" when starting dashboard

**Cause:** Dev_server is not running or not listening on port 3001.

**Check:**
```bash
# Check if port 3001 is listening
netstat -an | grep 3001    # Linux/macOS
netstat -ano | grep 3001   # Windows

# Should show: 0.0.0.0:3001 ... LISTENING
```

**Fix:**
1. Kill any orphaned processes: `pkill -9 python`  or `Stop-Process -Name python3 -Force` (PowerShell)
2. Start fresh: `python3 api-pkg/dev_server.py`
3. Wait for "Starting API dev server on http://localhost:3001" message
4. In another terminal: `python3 -m dashboard --local`

### Dashboard shows blank panels or errors

**Step 1:** Verify dev_server is responding:
```bash
curl -H "Authorization: Bearer dev-admin" http://localhost:3001/api/sectors
```

Should return a JSON response with sector data.

**Step 2:** Check database is accessible:
```bash
psql -U stocks stocks -c "SELECT COUNT(*) FROM algo_price_daily;"
```

Should return a number > 0.

**Step 3:** Run system diagnostics:
```bash
python3 scripts/audit_system.py
```

Should show:
```
[OK] All systems operational
```

### "PostgreSQL connection refused"

**Cause:** Database isn't running.

**Fix:**
1. Check if PostgreSQL is running:
   - Linux: `sudo systemctl status postgresql`
   - macOS: `brew services list | grep postgresql`
   - Windows: Check Services or use TaskScheduler

2. Start PostgreSQL if stopped
3. Verify connection: `psql -U stocks stocks -c "SELECT 1"`
4. Restart dev_server and dashboard

## Performance Notes

- Initial dashboard load: 2-3 seconds (loads 26 data sources concurrently)
- Subsequent refreshes: <1 second (uses cache)
- Dashboard refresh interval: 30 seconds (watch mode) or manual

## Architecture Notes

The system has three layers:

```
┌─────────────────────────────────────┐
│   Dashboard (localhost:5173 UI)     │  [Terminal 2]
│   - Fetches data every 30 seconds   │
│   - Renders 26 panels               │
└──────────────┬──────────────────────┘
               │ HTTP calls
               ↓
┌─────────────────────────────────────┐
│  Dev Server (localhost:3001 API)    │  [Terminal 1]
│  - Routes to Lambda function        │
│  - Uses local PostgreSQL            │
│  - Returns JSON responses           │
└──────────────┬──────────────────────┘
               │ SQL queries
               ↓
┌─────────────────────────────────────┐
│   PostgreSQL (localhost:5432)       │
│   - Demo/development data           │
│   - 8.6M+ price records             │
│   - 230k+ trading signals           │
└─────────────────────────────────────┘
```

## Next Steps

1. **For development:** Use the startup script or two-terminal setup
2. **For AWS/production:** See `steering/OPERATIONS.md`
3. **For advanced debugging:** Check logs at `~/.local/logs/dev_server.log`

---

**Last Updated:** 2026-07-12  
**Tested With:** Python 3.9+, PostgreSQL 12+  
**Dashboard Status:** ✓ Production Ready (when dev_server is running)
