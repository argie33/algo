# Critical System Fixes - Complete Checklist

**Goal:** Get dashboard data displaying + full orchestration working + paper trading active

**Current Status:** ✅ Data exists, ✅ Orchestrator running, ❌ Dashboard not showing data

---

## ROOT CAUSE: dev_server Not Running

The React dashboard proxies `/api/*` calls to `localhost:3001`, but the Python dev_server isn't listening there.

**Result:** Dashboard shows "data not available" for all panels.

### Fix (Choose One)

#### Option 1: Start Services Manually (5 min)
```bash
# Terminal 1: Python API backend
cd api-pkg
python dev_server.py
# Expect: [DEV_SERVER] Ready on http://localhost:3001

# Terminal 2: React frontend
cd webapp/frontend
npm run dev
# Expect: Local: http://localhost:5173

# Open dashboard: http://localhost:5173
```

#### Option 2: Automated Startup (3 min)
```bash
bash scripts/start-all-dev-services.sh
```

#### Option 3: Diagnose Issues First
```bash
python3 scripts/diagnose-dashboard-issue.py
```

---

##  System Verification (All Should PASS)

```bash
# 1. Orchestrator status
python3 scripts/validate_orchestrator_readiness.py

# Expected: ✓ ORCHESTRATOR IS READY FOR EXECUTION

# 2. Database data exists
python3 -c "
from utils.db.context import DatabaseContext
with DatabaseContext('read') as cur:
    cur.execute('SELECT COUNT(*) FROM algo_signals WHERE signal_active = true')
    print(f'Active signals: {cur.fetchone()[0]}')
"

# Expected: Active signals: [positive number]

# 3. API endpoints respond
curl -H 'Authorization: Bearer dev-admin' http://localhost:3001/api/health

# Expected: HTTP 200 OK with health status
```

---

## AWS Production Status

✅ **Infrastructure Deployed:**
- Terraform: All resources created (RDS, Lambda, EventBridge)
- GitHub Actions: CI/CD workflows functional
- Lambda: Latest code deployed
- EventBridge: Schedules ENABLED and firing
  - Morning 2:00 AM ET: loads prices/technicals
  - Afternoon 12:50 PM ET: fresh scores
  - EOD 4:05 PM ET: post-market analysis

✅ **Data Pipeline Running:**
- Loaders execute on schedule via Step Functions
- Data populating RDS
- Orchestrator runs 2x daily (9:30 AM & 1 PM ET)
- 210+ orchestrator runs on record

❌ **Missing: Dashboard Access to AWS Lambda**
- React dashboard needs Cognito authentication for AWS endpoints
- Or use local dev_server (localhost:3001)
- Production setup requires AWS Cognito token configuration

---

## Paper Trading Verification

```bash
# Check portfolio status
python3 -c "
from utils.db.context import DatabaseContext
with DatabaseContext('read') as cur:
    cur.execute('SELECT SUM(position_value) FROM algo_positions WHERE status = \"open\"')
    print(f'Portfolio value: {cur.fetchone()[0]}')
    
    cur.execute('SELECT COUNT(*) FROM algo_positions WHERE status = \"open\"')
    print(f'Open positions: {cur.fetchone()[0]}')
"

# Expected: Portfolio value > 0, Open positions > 0
```

---

## Next Steps (In Priority Order)

### 1. **GET DASHBOARD WORKING IMMEDIATELY** (Do this first)
- [ ] Start dev_server: `cd api-pkg && python dev_server.py`
- [ ] Start React: `cd webapp/frontend && npm run dev`
- [ ] Open http://localhost:5173
- [ ] Verify all panels load with data

### 2. **Verify End-to-End Orchestration**
- [ ] Run validation: `python3 scripts/validate_orchestrator_readiness.py`
- [ ] Check database has data: verify queries above
- [ ] Confirm 3+ open positions exist
- [ ] Confirm recent orchestrator runs exist

### 3. **Test Paper Trading**
- [ ] Manually trigger orchestrator: `python3 scripts/trigger_orchestrator.py --run morning --mode paper`
- [ ] Check new signals generated
- [ ] Verify positions updated
- [ ] Monitor portfolio value changes

### 4. **AWS Production (If Needed)**
- [ ] Verify EventBridge schedules are ENABLED
- [ ] Check Lambda logs: `aws logs tail /aws/lambda/algo-api-dev --follow`
- [ ] Test Lambda endpoints: `curl https://[API_GATEWAY_URL]/api/health`
- [ ] Configure Cognito tokens for dashboard (production step)

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "data not available" in dashboard | dev_server not running | `cd api-pkg && python dev_server.py` |
| API returns 401 | Missing dev-admin token | Use `-H "Authorization: Bearer dev-admin"` |
| Dashboard can't reach API | Vite proxy misconfigured | Run `cd webapp/frontend && npm run setup-dev` |
| No data in database | Loaders not running | Check EventBridge schedules in AWS console, or run `python3 scripts/test_orchestrator_execution.py` |
| Lambda returns 503 | Cold start during off-hours | Normal - Lambda is graceful, returns "INITIALIZING" status |
| Positions panel empty | No open positions | Trigger orchestrator: `python3 scripts/trigger_orchestrator.py --run morning` |

---

## Cleanup Done This Session

✅ Removed 30+ leftover debug/test files from previous troubleshooting  
✅ Removed migration documentation clutter  
✅ Created diagnostic script: `scripts/diagnose-dashboard-issue.py`  
✅ Created startup script: `scripts/start-all-dev-services.sh`  
✅ Updated documentation: `QUICKSTART_DEV.md`  

---

## Key Files to Know

- **Development setup:** `QUICKSTART_DEV.md`
- **Architecture:** `steering/GOVERNANCE.md`
- **Operations:** `steering/OPERATIONS.md`
- **Data loading:** `steering/DATA_LOADERS.md`
- **Deployment:** `.github/workflows/deploy-all-infrastructure.yml`
- **IaC config:** `terraform/modules/`

---

## Success Criteria

✅ **Dashboard displays data**
- Portfolio value visible
- Positions show open trades
- Performance metrics display
- Market health panel loads

✅ **Orchestrator executes**
- Loaders run on schedule (or manually)
- Signals generated daily
- Positions updated automatically
- Portfolio reconciles

✅ **Paper trading active**
- New positions open/close
- Trades recorded in database
- Portfolio value changes reflect trades
- Circuit breakers active

---

**Next Action:** Run `bash scripts/start-all-dev-services.sh` and open http://localhost:5173
