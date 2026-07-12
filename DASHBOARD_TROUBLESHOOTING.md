# Dashboard Troubleshooting Guide

## "Data Not Available" Error - Most Common Issue

### ❌ Symptoms
- Dashboard shows "Data not available" on all panels
- All fetchers fail with similar errors
- System appears completely broken

### ✅ Root Cause
You are running the dashboard **WITHOUT the `--local` flag** when trying to connect to `localhost:3001`.

### 🔧 Solution

**For Local Development:**
```bash
# Terminal 1: Start the API dev server
python3 api-pkg/dev_server.py

# Terminal 2: Start dashboard with --local flag (MUST USE --local)
python3 -m dashboard --local
```

**Why?**
- `DASHBOARD_API_URL` environment variable defaults to AWS Lambda endpoint
- AWS Lambda requires Cognito authentication
- Local dev server has no Cognito tokens → returns 401 (Unauthorized)
- `--local` flag overrides API URL to `http://localhost:3001` and auto-injects `dev-admin` token

## Quick Reference

| Scenario | Command | Result |
|----------|---------|--------|
| **Local Dev (RECOMMENDED)** | `python -m dashboard --local` | ✅ Works perfectly |
| **AWS Mode** | `python -m dashboard` | ⚠️ Lambda timeout (VPC issue) |
| **Raw test** | `curl -H "Authorization: Bearer dev-admin" http://localhost:3001/api/algo/portfolio` | ✅ Works |

### Current Status (Session 85, 2026-07-12)
- **Dev Server:** ✅ Running and responding on localhost:3001
- **AWS Lambda:** ⚠️ Timing out (VPC cold-start issue, needs investigation)
- **Data:** ✅ Fresh (today is Saturday, price data current through Friday)

## Health Check

To verify system is operational:
```bash
python3 scripts/audit_system.py
```

Expected output:
```
[OK] All systems operational
   - Orchestrator Status: OK
   - Data Freshness: OK
   - API Endpoints: OK
   - Dashboard Fetchers: OK
```

## Common Scenarios

### Scenario 1: Dashboard loading hangs
**Cause:** dev_server not running  
**Fix:** Start dev_server first in Terminal 1: `python3 api-pkg/dev_server.py`

### Scenario 2: Positions show as empty
**Cause:** No live positions open  
**Expected:** Portfolio snapshot will show data, positions empty is correct

### Scenario 3: Signals show 0 count
**Cause:** Orchestrator hasn't run today  
**Expected:** On weekends, orchestrator doesn't run (scheduled MON-FRI)  
**Manual trigger:** `python3 scripts/trigger_orchestrator.py --run morning --mode paper`

### Scenario 4: Health panel shows errors
**Cause:** Usually a stale data warning  
**Fix:** Run manual orchestrator trigger to load fresh data

## System Status

### Current Deployment (Session 75)
- ✅ **Local dev mode:** Fully operational (all 26 dashboard fetchers working)
- ✅ **Database:** 230k+ signals, fresh this morning
- ✅ **Orchestrator:** Running on schedule (5.4h ago)
- ✅ **Data loaders:** All executing successfully
- ⚠️ **AWS mode:** Requires proper Cognito configuration

### Data Freshness (as of 2026-07-11)
| Table | Latest | Status |
|-------|--------|--------|
| price_daily | 2026-07-10 | ✅ Fresh |
| technical_data_daily | 2026-07-10 | ✅ Fresh |
| buy_sell_daily | 2026-07-11 08:06 | ✅ Very fresh |
| stock_scores | 26 hours ago | ⚠️ Due for refresh |

## Troubleshooting Flowchart

```
Dashboard showing "Data not available"?
  ├─ Run with --local flag?
  │  ├─ No → Add --local flag to command
  │  └─ Yes → Continue...
  │
  ├─ dev_server running?
  │  ├─ No → Start: python3 api-pkg/dev_server.py
  │  └─ Yes → Continue...
  │
  ├─ Health check passing?
  │  ├─ No → Run: python3 scripts/audit_system.py
  │  └─ Yes → System is working, issue is elsewhere
  │
  └─ Still broken?
     └─ Check: logs at `~/.local/logs/dev_server.log`
```

## Performance Notes

### Dashboard Refresh Time
- Initial load: 2-3 seconds (fetches all 26 data sources)
- Subsequent refresh: 1-2 seconds (cached API responses)
- Slow if: API timeout or database lock

### Data Update Frequency
- Prices: Real-time during market hours
- Signals: After daily orchestrator run (2:15 AM + 4:00 PM ET)
- Positions: Real-time from Alpaca
- Scores: Once per day after EOD loaders

## Advanced: AWS Mode Setup

If you need to use the AWS Lambda endpoints:

1. **Configure Cognito:**
   ```bash
   export COGNITO_USER_POOL_ID="your-pool-id"
   export COGNITO_CLIENT_ID="your-client-id"
   export DASHBOARD_API_URL="https://your-api-endpoint.us-east-1.amazonaws.com"
   ```

2. **Get JWT Token:**
   ```bash
   # AWS CLI
   aws cognito-idp admin-initiate-auth \
     --user-pool-id $COGNITO_USER_POOL_ID \
     --client-id $COGNITO_CLIENT_ID \
     --auth-flow ADMIN_NO_SRP_AUTH \
     --auth-parameters USERNAME=argeropolos@gmail.com,PASSWORD=yourpassword
   ```

3. **Run Dashboard:**
   ```bash
   python3 -m dashboard
   # Dashboard will prompt for token if not in environment
   ```

## Getting Help

**Check existing issues:**
```bash
# Review steering docs
cat steering/AWS_LAMBDA_503_FIX.md
cat steering/OPERATIONS.md
cat CLAUDE.md
```

**Run diagnostics:**
```bash
python3 scripts/audit_system.py
python3 scripts/diagnose_system.py
```

**Check logs:**
```bash
# Dev server log
tail -f ~/.local/logs/dev_server.log

# Recent commits
git log --oneline -20
```

## Summary

**TL;DR:** Run `python -m dashboard --local` and make sure dev_server is running in another terminal. The system is fully operational when used correctly.
