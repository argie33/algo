# Algo Trading System - Quick Start Guide

## 30-Second Setup (Local Development)

### Terminal 1: Start Backend API
```bash
python3 api-pkg/dev_server.py
```

**Wait for this output:**
```
[INFO] Starting API dev server on http://localhost:3001
[INFO] Press Ctrl+C to stop
```

### Terminal 2: Start Dashboard
```bash
python3 -m dashboard
```

Dashboard automatically detects the API on localhost:3001 (no `--local` flag needed).

**Expected:**
- Dashboard loads in ~3-5 seconds
- See "Fetching..." spinner briefly
- Panels display with data
- Green checkmarks (✓) = data available
- Em dashes (—) = optional data not available (normal)

---

## Common Issues & Fixes

### Issue: "Data not available" on all panels

**Cause:** Dev server not running

**Fix:**
1. Check Terminal 1 - is dev_server running?
2. If not, start it: `python3 api-pkg/dev_server.py`
3. Wait for: `[INFO] Starting API dev server on http://localhost:3001`
4. Restart dashboard in Terminal 2

### Issue: "This is optional data" (em dashes —) everywhere

**Cause:** Normal behavior on weekends/holidays when market is closed

**What's happening:**
- Market data is stale (expected 2-3 days old on weekends)
- Optional enrichment data not available
- **This is correct and expected behavior**

**What's NOT shown:**
- All critical data (prices, regime, positions, trades) still work
- System continues to function for Monday when market opens

### Issue: Dashboard slow to load (>10 seconds)

**Cause:** One or more fetchers timing out or API slow

**Fix:**
1. Check CPU/memory on dev_server (Terminal 1)
2. Try again - may be network latency
3. If persistent, check database: `psycopg2.connect('dbname=stocks user=stocks host=localhost')`

### Issue: "Cognito authentication" error (AWS mode)

**Cause:** Running in AWS mode without credentials

**Fix - Use Local Mode:**
```bash
python3 -m dashboard
# Dashboard auto-detects dev_server and uses it
```

**OR - Setup AWS Mode:**
Set environment variables:
```bash
export DASHBOARD_API_URL=https://your-api.example.com
export COGNITO_USER_POOL_ID=us-east-1_xxxxxxxxx
export COGNITO_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxxxx
export COGNITO_USERNAME=your_username
export COGNITO_PASSWORD=your_password  # From AWS Secrets Manager

python3 -m dashboard
```

---

## Manual Data Refresh (Optional)

If data is very stale and you want fresh data:

```bash
python3 scripts/run_local_orchestrator.py --morning
```

This runs the full data loading pipeline:
- Loads stock symbols
- Updates prices
- Calculates technical indicators
- Scores signals
- Updates market regime

---

## System Architecture

```
┌──────────────────┐
│  Your Terminal   │
│  (Dashboard)     │  ← python3 -m dashboard
└────────┬─────────┘
         │ HTTP requests
         ▼
┌──────────────────┐
│  Dev Server      │  ← python3 api-pkg/dev_server.py
│  (API Routes)    │    Runs on localhost:3001
└────────┬─────────┘
         │ SQL queries
         ▼
┌──────────────────┐
│  PostgreSQL      │
│  (Local DB)      │  ← 8.6M+ price records
└──────────────────┘
```

---

## What Each Terminal Does

| Terminal | Command | Purpose | Exit With |
|----------|---------|---------|-----------|
| 1 | `python3 api-pkg/dev_server.py` | API server | Ctrl+C |
| 2 | `python3 -m dashboard` | Dashboard UI | 'q' or Ctrl+C |

**Both terminals must stay running.**

If either crashes, restart independently:
- Terminal 1 dies → restart dev_server, keep dashboard running
- Terminal 2 dies → just restart dashboard

---

## Watch Mode (Auto-Refresh)

```bash
python3 -m dashboard -w 30
```

Auto-refreshes every 30 seconds. Useful for monitoring live trading:
- Shows latest positions
- Updates market data
- Displays circuit breaker status

Press 'q' to exit.

---

## Troubleshooting Checklist

- [ ] Terminal 1: `python3 api-pkg/dev_server.py` running?
- [ ] Terminal 1: Shows `[INFO] Starting API dev server on http://localhost:3001`?
- [ ] Terminal 1: No error messages?
- [ ] Terminal 2: `python3 -m dashboard` started?
- [ ] Database can connect: `psycopg2.connect('dbname=stocks user=stocks host=localhost')`?
- [ ] Port 3001 is not in use: `lsof -i :3001` (or Windows equivalent)

If all above pass and dashboard still shows "Data not available":

```bash
python3 scripts/diagnose_dashboard.py
```

This runs comprehensive checks and reports what's broken.

---

## Next Steps

1. **Verify system works locally** (this guide)
2. **Check CLAUDE.md** for full architecture & deployment
3. **Review steering/GOVERNANCE.md** for system policies
4. **Check steering/OPERATIONS.md** for AWS deployment
