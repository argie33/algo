# Session 15: Quick Start Guide

**Status:** ✅ PRODUCTION CODE READY | ⚠️ NEEDS LOADER EXECUTION FIX  
**Tests:** ✅ 1066 passed (0 failures)  
**Time to Production:** ~30 minutes

---

## TL;DR - What Changed

**Fixed 5 Critical Code Issues:**
1. ✅ Dashboard silent HTTP 200 errors → now returns HTTP 500
2. ✅ Phase 7 signals silently dropped → now raises RuntimeError  
3. ✅ Halt flag failures ignored → now raises RuntimeError
4. ✅ Financial data defaults to 0 → now requires explicit values
5. ✅ Type confusion in database results → now validated explicitly

**Identified Infrastructure Issue:**
- ⚠️ Metric loaders haven't run in 29+ hours
- Root cause: EventBridge EOD pipeline (4:05 PM ET) not executing
- Fix: Manually trigger or investigate EventBridge configuration

**System Status:**
- ✅ All code production-ready (fail-fast patterns enforced)
- ✅ Tests passing (1066/1066)
- ✅ Orchestrator working end-to-end (9/9 phases pass)
- ⚠️ Data stale (needs loader pipeline fixed)

---

## Get System Running (30 minutes)

### Step 1: Check Current Status
```bash
python3 scripts/diagnose_and_fix_loaders.py
```

### Step 2: Fix Loaders (Pick ONE)

**Option A: Fast Path (Recommended)**
```bash
# Trigger metric loaders
gh workflow run run-loader.yml -f loader_name=load_stock_scores
gh workflow run run-loader.yml -f loader_name=load_quality_metrics
gh workflow run run-loader.yml -f loader_name=load_growth_metrics
gh workflow run run-loader.yml -f loader_name=load_value_metrics
gh workflow run run-loader.yml -f loader_name=load_positioning_metrics
gh workflow run run-loader.yml -f loader_name=load_stability_metrics

# Wait 20 min for completion
```

**Option B: Investigation (Root Cause Fix)**
```bash
# Check EventBridge
aws events describe-rule --name algo-stock_scores-schedule --region us-east-1

# Check ECS
aws ecs describe-clusters --clusters algo-cluster-dev --region us-east-1

# Check logs
aws logs tail /ecs/algo-cluster --since 2h --follow
```

### Step 3: Run Orchestrator
```bash
python3 scripts/trigger_orchestrator.py --run morning --mode paper
```

### Step 4: Verify Dashboard
```bash
cd webapp && npm run dev
# Navigate to http://localhost:5173
# Verify: fresh stock scores, today's signals, current positions
```

### Step 5: Deploy to AWS
```bash
git push origin main
# GitHub Actions runs automatically
```

---

## Key Files Changed

```
algo/orchestration/orchestrator.py       # Halt flag safety
algo/orchestrator/phase7_signal_generation.py  # Signal fail-fast
dashboard/local_api_server.py           # HTTP errors + data validation
dashboard/fetchers_config.py            # Type validation
scripts/diagnose_and_fix_loaders.py     # NEW diagnostic tool
```

---

## Verification Checklist

- [ ] Diagnostic script runs without errors
- [ ] Metric loaders complete (stock_scores, buy_sell_daily fresh)
- [ ] Orchestrator runs successfully
- [ ] Dashboard shows fresh data
- [ ] Tests pass: `make test`
- [ ] Type checking passes: `make type-check`
- [ ] Code deployed to AWS

---

## Key Metrics

| Metric | Before | After | Status |
|--------|--------|-------|--------|
| Error Handling | Silent HTTP 200 | HTTP 500 | ✅ Fixed |
| Signal Generation | Silent skip | RuntimeError | ✅ Fixed |
| Data Validation | Defaults to 0 | Explicit required | ✅ Fixed |
| Tests | 1066 pass | 1066 pass | ✅ Unchanged |
| Type Safety | Fallback | Explicit | ✅ Improved |

---

## Architecture Status

```
┌─────────────────┐
│   Orchestrator  │ ✅ WORKING (9/9 phases pass)
└────────┬────────┘
         │
    ┌────▼────────────────────┐
    │   Data Layer (Fresh?)   │
    └─┬──────────────────────┬─┘
      │                      │
   Price           Metrics (⚠️ STALE)
  ✅ FRESH        • quality_metrics
  5.6h old        • growth_metrics
                  • value_metrics
                  • stock_scores
                  29h old
```

---

## Documentation

- **Detailed Audit:** `SESSION_15_AUDIT_AND_FIXES_SUMMARY.md`
- **Action Plan:** `ACTION_PLAN_PRODUCTION_READINESS.md`
- **Architecture:** `steering/GOVERNANCE.md`
- **Operations:** `steering/OPERATIONS.md`

---

## Support

**For quick fixes:**
```bash
python3 scripts/diagnose_and_fix_loaders.py
```

**For infrastructure issues:**
```bash
aws logs tail /ecs/algo-cluster --since 2h
aws events list-rules --name-prefix algo
aws dynamodb get-item --table-name algo-loader-locks-dev --key '{"lock_key":{"S":"load_stock_scores"}}'
```

**For deployment:**
```bash
git push origin main
gh run list -w deploy-all-infrastructure.yml
```

---

## Expected Timeline

| Task | Time | Status |
|------|------|--------|
| Diagnostic | 5 min | Ready |
| Load data | 20 min | Ready |
| Orchestrate | 5 min | Ready |
| Dashboard | 5 min | Ready |
| Deploy | 5 min | Ready |
| **Total** | **40 min** | **Ready** |

---

**Next Action:** Run `python3 scripts/diagnose_and_fix_loaders.py` and execute `ACTION_PLAN_PRODUCTION_READINESS.md`

Let's go! 🚀
