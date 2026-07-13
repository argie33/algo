# Local Development Setup - Algo Dashboard

**Problem**: Dashboard shows "data not available" in all panels  
**Root Cause**: Dev server not running when dashboard starts  
**Solution**: Use unified startup script (handles both automatically)

## Quick Start (RECOMMENDED)

**Option 1: Simple startup (no auto-refresh)**
```bash
python start_dashboard_dev.py
```

**Option 2: With auto-refresh every 30 seconds**
```bash
python start_dashboard_dev.py -w 30
```

This single command will:
1. ✓ Check if dev server is running on localhost:3001
2. ✓ Start dev server automatically if not running
3. ✓ Wait for dev server to be ready (max 30s)
4. ✓ Start dashboard pointing to localhost:3001
5. ✓ Clean up dev server when dashboard exits (Ctrl+C)

## System Health Check

Before starting dashboard, verify all systems are healthy:

```bash
python check_system_health.py
```

This checks:
- ✓ Database connectivity and data freshness
- ✓ Dev server availability
- ✓ Orchestrator execution status
- ✓ Dashboard module imports

Example output:
```
[✓] Database
    ✓ price_daily: 8,601,859 rows, latest: 0.0h ago
    ✓ stock_scores: 4,711 rows, latest: 0.1h ago
    ✓ algo_orchestrator_runs: 259 rows, latest: 0.2h ago
    ✓ market_exposure_daily: 63 rows, latest: 0.0h ago
    ✓ technical_data_daily: 10 rows, latest: 72.0h ago (weekend)

[✓] Orchestrator Status
    ✓ Latest run: 15 minutes ago
    Runs in last 24h: 11

[✓] Dev Server (localhost:3001)
    Dev server is running and responding
    Health check: OK

[✓] Dashboard Module
    Dashboard module imports successfully

✓ ALL SYSTEMS OPERATIONAL
```

## Manual Setup (If Needed)

**Terminal 1: Start Dev Server**
```bash
python3 api-pkg/dev_server.py
```

Wait for:
```
[INFO] Starting API dev server on http://localhost:3001
[INFO] Press Ctrl+C to stop
```

**Terminal 2: Start Dashboard**
```bash
# Without auto-refresh
python3 -m dashboard

# Or with auto-refresh every 30s
python3 -m dashboard -w 30
```

## Troubleshooting

### "Data not available" in all dashboard panels

**Check 1: Is dev server running?**
```bash
curl http://localhost:3001/api/health
# Should return 200 OK
```

**Check 2: Run health check**
```bash
python check_system_health.py
```

**Check 3: Check database freshness**
```bash
python3 scripts/diagnose_dashboard.py
```

### Dev server starts but dashboard still shows "data not available"

This usually means:
1. Dashboard hasn't re-fetched data yet (wait 3-5 seconds)
2. API endpoints aren't responding properly
3. Database doesn't have required data

**Fix**: Refresh data manually:
```bash
# In a separate terminal while dashboard is running:
python3 scripts/run_local_orchestrator.py --morning
```

Then refresh dashboard (if using watch mode, it auto-refreshes; otherwise close and restart).

### "Connection refused" on localhost:3001

Dev server didn't start or crashed. Check:

```bash
# Check if port 3001 is in use
# Windows:
netstat -ano | find "3001"

# Mac/Linux:
lsof -i :3001
```

If something is using port 3001, either:
1. Kill it: `kill -9 <PID>` (Mac/Linux)
2. Use a different port:
   ```bash
   API_PORT=3002 python3 api-pkg/dev_server.py
   # Then start dashboard with:
   DASHBOARD_API_URL=http://localhost:3002 python3 -m dashboard
   ```

### PostgreSQL "connection refused"

Database is not running or wrong credentials. Check:

```bash
# Test connection
python3 -c "import psycopg2; psycopg2.connect('dbname=stocks user=stocks host=localhost')"

# If fails, ensure:
# - PostgreSQL is running on localhost:5432
# - Database name is 'stocks'
# - User 'stocks' exists with correct password
```

## Data Freshness

Dashboard reads data from database via API. For fresh data:

1. **Orchestrator runs** (scheduled):
   - Runs at 2:15 AM and 4:00 PM ET via EventBridge Scheduler (production)
   - Runs on-demand: `python3 scripts/run_local_orchestrator.py`

2. **Data loaders** (triggered by orchestrator):
   - load_prices.py: Fetches latest OHLCV data
   - load_technical_indicators.py: Computes technical signals
   - load_stock_scores.py: Ranks stocks by quality/growth/value/momentum
   - load_market_health_daily.py: Tracks market conditions

3. **Dashboard fetch cycle**:
   - Default: Fetches once on startup
   - With `-w 30`: Re-fetches every 30 seconds automatically

## Dashboard Panels Explained

| Panel | Data Source | Refresh Frequency | Notes |
|-------|-------------|-------------------|-------|
| Health | `circuit_breaker_status` | On startup | Shows market conditions + algo circuit breaker state |
| Signals | `algo_signals` | On startup | Shows active buy/sell signals |
| Portfolio | `positions`, `trades` | On startup | Paper trading positions + recent trades |
| Performance | `portfolio_performance` | On startup | P&L, returns, Sharpe ratio |
| Market | `market_exposure_daily` | On startup | Sector exposure, SPY levels |
| Scores | `stock_scores` | On startup | Top ranked stocks by composite score |

## Architecture

```
┌─────────────┐
│  Dashboard  │
│   (UI)      │
└──────┬──────┘
       │ HTTP
       ↓
┌──────────────────────┐
│ Dev Server           │ ← localhost:3001
│ (routes requests)    │
└──────┬───────────────┘
       │ Lambda handler
       ↓
┌──────────────────────┐
│ Lambda Function      │
│ (business logic)     │
└──────┬───────────────┘
       │ SQL
       ↓
┌──────────────────────┐
│ PostgreSQL Database  │
│ (data storage)       │
└──────────────────────┘
```

- **Dashboard**: Rich TUI, renders fetched data
- **Dev Server**: HTTP server that routes to Lambda handler
- **Lambda Function**: Implements /api/* endpoints
- **Database**: PostgreSQL with 5K+ stocks, real-time pricing, signals

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `LOCAL_MODE` | (auto) | Use localhost API instead of AWS |
| `DASHBOARD_API_URL` | (auto-detect) | API endpoint for dashboard |
| `API_PORT` | 3001 | Dev server port |
| `DB_HOST` | localhost | Database host |
| `DB_USER` | stocks | Database user |
| `DB_PASSWORD` | stocks | Database password |
| `DB_NAME` | stocks | Database name |

Example override:
```bash
API_PORT=3002 DB_HOST=prod-rds.aws.amazon.com python3 api-pkg/dev_server.py
```

## Next Steps

1. ✓ Start dashboard: `python start_dashboard_dev.py`
2. ✓ Verify data loads (should see portfolio/signals/health within 3-5s)
3. ✓ Test trading: Execute trades via dashboard
4. ✓ Monitor logs: Check CloudWatch for any errors

## Getting Help

```bash
# Comprehensive diagnostics
python check_system_health.py
python3 scripts/diagnose_dashboard.py
python3 scripts/diagnose_system.py

# View logs
tail -f /tmp/dev_server.log

# Check database state
python3 scripts/debug_db.py
```
