# Dev Server Troubleshooting Guide

## Quick Fixes

### Dev server won't start or keeps crashing

**1. Kill orphaned processes:**
```powershell
# Windows - Kill any stuck process on port 3001
$proc = Get-NetTCPConnection -LocalPort 3001 -ErrorAction SilentlyContinue | Select -First 1
if ($proc) { Stop-Process -Id $proc.OwningProcess -Force }

# OR use the built-in health check:
python scripts/dev_server_health_check.py --kill-orphaned
```

**2. Check dev server health:**
```bash
python scripts/dev_server_health_check.py --diagnose
```

**3. Start fresh:**
```bash
# This automatically kills orphaned processes and starts clean
python start_dashboard_dev.py
```

---

## Infrastructure Fixes Applied

### ✅ Fix 1: Thread-safe Connection Pool
**Location:** `utils/db/connection.py` line 104
**Issue:** `SimpleConnectionPool` is not thread-safe. With `ThreadingHTTPServer` serving concurrent requests, this causes socket deadlocks when 2+ threads try to use the same connection.
**Fix:** Using `ThreadedConnectionPool` with proper locking.
**Verified:** Line 104 shows `psycopg2.pool.ThreadedConnectionPool`

### ✅ Fix 2: IPv6 Localhost Stall
**Location:** Dashboard API client code
**Issue:** Windows resolves `localhost` to IPv6 (::1) first, which stalls 2+ seconds per request on IPv4-only servers.
**Fix:** Using `127.0.0.1` explicitly in all API calls.
**Verified:** All dashboard client code uses `http://127.0.0.1:3001` not `http://localhost:3001`

### ✅ Fix 3: Orphaned Port 3001 Cleanup
**Location:** `start_dashboard_dev.py` lines 77-121
**Issue:** When launcher is killed (Ctrl+C), the dev_server subprocess keeps running, causing "Port 3001 already in use" on next startup.
**Fix:** `cleanup_orphaned_dev_servers()` kills any existing process on port 3001 before starting.
**Verified:** Called automatically in `start_dev_server()` line 403

---

## Logging & Diagnostics

Dev server logs are saved to: `~/.algo/logs/dev_server.log`

When dev_server fails to start:
1. Logs are printed to console showing last 20 lines
2. Full logs available at `~/.algo/logs/dev_server.log`
3. Each startup appends with timestamp separator

---

## Common Issues & Solutions

### "Port 3001 already in use"
```bash
# Kill the orphaned process
python scripts/dev_server_health_check.py --kill-orphaned

# Then start fresh
python start_dashboard_dev.py
```

### "Connection refused" or "Port not responding"
```bash
# Check what's actually listening
Get-NetTCPConnection -LocalPort 3001

# Full diagnostics
python scripts/dev_server_health_check.py --diagnose
```

### Dashboard loads slowly (each request takes 2-3s)
- This was the IPv6 stall issue - already fixed
- Check that code uses `127.0.0.1` not `localhost`
- If issue persists, run: `python scripts/dev_server_health_check.py --diagnose`

### Database connection timeouts
- Check that ThreadedConnectionPool is being used
- Verify `utils/db/connection.py` line 104 has `ThreadedConnectionPool`
- Check `.env.local` has correct `DB_*` variables

---

## Manual dev_server startup (if needed)

```bash
# Set these environment variables
set LOCAL_MODE=true
set ENVIRONMENT=development
set ALPACA_PAPER_TRADING=true

# Then start the server
python lambda/api/dev_server.py

# Server should listen on http://127.0.0.1:3001
```

---

## For Developers: Adding New Endpoints

When adding new endpoints to dev_server.py:
1. Use `127.0.0.1:3001` in all client code, never `localhost`
2. The ThreadedConnectionPool handles concurrent requests automatically
3. No special concurrency handling needed - pool handles locking
4. Test with concurrent requests: `python -c "import concurrent.futures, requests; list(concurrent.futures.ThreadPoolExecutor(max_workers=11).map(lambda _: requests.get('http://127.0.0.1:3001/api/algo/health'), range(11)))"`
