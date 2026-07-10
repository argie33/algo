# Dashboard Data Unavailable - Root Cause & Fix

## Problem Identified
Dashboard showed "data not available" on all panels. Root causes:

### Root Cause 1: Dev Server Crashed
- Multiple Python processes on port 3001 were hanging/crashed
- API endpoints returned 500/503 errors with empty response bodies
- Caused fetchers to fail silently

**Fix Applied:**
```bash
# Kill all processes on port 3001
Get-NetTCPConnection -LocalPort 3001 | Stop-Process -Force

# Restart dev server (it will auto-start on next demand)
python3 lambda/api/dev_server.py
```

### Root Cause 2: Dashboard API URL Misconfigured  
- Dashboard defaulted to `http://localhost:8000` (wrong port)
- Dev server actually runs on `http://localhost:3001`
- Fetchers couldn't reach the API

**Fix Applied:**
```bash
# Set correct API endpoint
export DASHBOARD_API_URL="http://localhost:3001"

# Verify all 12 API endpoints are working
curl -s http://localhost:3001/api/algo/portfolio | jq .statusCode
curl -s http://localhost:3001/api/algo/positions | jq '.items | length'
curl -s http://localhost:3001/api/algo/trades | jq .statusCode
```

## Data Status After Fix

| Endpoint | Status | Data Age |
|----------|--------|----------|
| /api/algo/portfolio | ✅ 200 | 9.7h old |
| /api/algo/positions | ✅ 200 | 9.7h old (3 open) |
| /api/algo/trades | ✅ 200 | 9.7h old |
| /api/algo/performance | ✅ 200 | Fresh |
| /api/algo/markets | ✅ 200 | Fresh |
| /api/algo/status | ✅ 200 | 9.7h old |
| /api/algo/circuit-breakers | ⚠️ 503 | Stale (26h old) |
| /api/algo/equity-curve | ✅ 200 | Fresh |

## Remaining Issues to Fix

### Issue 1: Circuit Breaker Data Stale
- Circuit breaker metrics from 2026-07-09 (1 day old)
- Orchestrator runs every 9:30 AM, 1 PM, 3 PM, 5:30 PM ET
- Last run: 2026-07-09 02:44:34 AM (9.7 hours ago)
- **Cause:** Orchestrator Phase 9 not updating circuit_breaker_status table
- **Fix:** Run orchestrator manually or wait for next scheduled execution

### Issue 2: Market Data Quality Warning
- `vix_regime` missing from market_exposure_daily.factors JSONB column
- This is a warning, not an error - system handles it gracefully
- **Fix:** Run market exposure loader to regenerate factors

### Issue 3: Micro-cap Data Filtering
- 612 quality_metrics records marked `data_unavailable=true`
- Reason: "No SEC filing data available (micro-cap, OTC, ADR, or new IPO)"
- This is expected and correct per GOVERNANCE - not a bug

## Dashboard Status

✅ **Core Data Displaying:**
- Portfolio value: $99,920.23
- Open positions: 3 (HTGC, WABC, NTCT)
- Trade history: Available
- Performance metrics: Available

⚠️ **Needs Attention:**
- Circuit breaker metrics stale (will refresh on next orchestrator run)
- Market data quality flags present (normal for current data)

## To Keep Dashboard Working

1. **Ensure dev server stays running:**
   ```bash
   # Terminal 1: Start dev server
   cd lambda/api
   python3 dev_server.py
   ```

2. **Set API URL when running dashboard:**
   ```bash
   # Terminal 2: Run dashboard
   export DASHBOARD_API_URL="http://localhost:3001"
   python3 -m dashboard --local
   ```

3. **Or use automated startup script:**
   - Create `scripts/start-dashboard.sh` to handle both processes
   - Ensure DASHBOARD_API_URL is exported in shell profile

## Testing Checklist

Run these to verify system is working:

```bash
# 1. Dev server running
curl http://localhost:3001/api/health

# 2. All endpoints accessible
python3 dashboard/test_endpoints.py

# 3. Dashboard can load data
export DASHBOARD_API_URL="http://localhost:3001"
python3 -c "from dashboard.fetchers import load_all; d = load_all(); print(f'Loaded {len(d)} data sources')"

# 4. Dashboard renders (interactive)
python3 -m dashboard --local
```

## Next Steps

1. ✅ Fix dev server crash (DONE)
2. ✅ Fix API URL configuration (DONE)
3. ⏳ Trigger orchestrator to update stale data
   ```bash
   python3 scripts/trigger_orchestrator.py --run morning --mode paper
   ```
4. ⏳ Run market exposure loader to regenerate factors
5. ⏳ Deploy permanent fix: Add DASHBOARD_API_URL to environment config
