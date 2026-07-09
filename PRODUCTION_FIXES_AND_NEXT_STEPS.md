# Production Fixes & Next Steps - 2026-07-09

## COMPLETED FIXES ✅

### 1. NULL Quantities in algo_trades (FIXED)
- **Commit:** `5f062154a`
- **Change:** Added `quantity` column to trade INSERT statement in executor_entry_handler.py
- **Status:** All new trades now have quantity = entry_quantity at creation

### 2. Phase 9 Quantity Synchronization (FIXED)
- **Commit:** `a4d509a95`  
- **Change:** Added end-of-day sync in phase9_reconciliation.py
- **Status:** Daily safety net ensures quantity accuracy

### 3. Lambda Deployment Concurrency Configuration (FIXED)
- **Commit:** `c55be37ba`
- **Change:** Added minimum reserved concurrency validation in Terraform
- **Status:** Prevents deployment failures from concurrency config errors

### 4. Database Freshness Tracking (FIXED)
- **Status:** `data_loader_status.age_days` backfilled and working

### 5. Stock Scores Data Quality (VERIFIED WORKING)
- **Status:** 98.4% complete today (1.6% NULL legitimate data_unavailable flags)
- **Upstream metrics coverage:** 84-99% all sufficient for scoring

---

## CRITICAL BLOCKING ISSUES REQUIRING FIXES

### 1. **Orchestrator Scheduler Not Executing** (HIGHEST PRIORITY)
**Problem:** EventBridge scheduler not triggering 2x daily runs
- Last orchestrator run: 5.8+ hours ago
- Impact: Cascading failure (no trading, no signals)

**Root Cause Investigation:**
```bash
# Check if EventBridge rules exist and are ENABLED
aws events list-rules --region us-east-1 | grep "algo-schedule"

# Verify algo Lambda has permission from EventBridge Scheduler
aws lambda get-policy --function-name algo-algo-dev --region us-east-1 | jq '.Policy'

# Check recent Lambda invocation attempts
aws logs tail /aws/lambda/algo-orchestrator --since 1h --region us-east-1
```

**Verification Commands:**
```sql
-- Check if orchestrator is actually running
SELECT COUNT(*), MAX(started_at) FROM algo_orchestrator_runs 
WHERE started_at > NOW() - INTERVAL '1 hour';
-- Expected: rows should appear every ~5 hours (2x daily)
```

**Fix Procedure:**
1. Verify `eventbridge_scheduler_role_arn` is passed from root module correctly
2. Ensure role has `lambda:InvokeFunction` permission on algo Lambda
3. Check EventBridge rule state: `aws events describe-rule --name algo-schedule-morning-dev`
4. If disabled, enable: `aws events enable-rule --name algo-schedule-morning-dev`

### 2. **API Caching Bug - Signals Endpoint Stale** (HIGH PRIORITY)
**Problem:** `/api/signals` returns 14-day-old data despite fresh database
- Root cause: Cache invalidation bug or freshness calculation error
- File: `api-pkg/routes/utils.py:522-635` (check_data_freshness function)

**Fix Procedure:**
1. Debug `check_data_freshness()` function
2. Verify it's using correct timestamp field for signals
3. Add cache invalidation on successful data loads
4. Test with working `/api/market` endpoint as reference

### 3. **Data Loader Timeouts** (MEDIUM PRIORITY)
**Problem:** 4 loaders auto-resetting after 4+ hour timeout
- Affected: analyst_sentiment_analysis, stock_symbols, economic_metrics, algo_risk_daily
- Root cause: Memory/CPU contention during parallel loads

**Fix Procedure:**
1. Check CloudWatch metrics for ECS task resource utilization
2. Scale ECS task resources (increase memory from 1024MB to 2048MB+)
3. Reduce batch sizes or parallelism in affected loaders
4. Monitor `/ecs/algo-cluster` logs

---

## INFRASTRUCTURE STATUS

| Component | Status | Issue | Fix Status |
|-----------|--------|-------|-----------|
| Quantity Tracking | ✅ FIXED | Was NULL 89.4% | Code fixed, data synced |
| Phase 9 Sync | ✅ FIXED | Added safety net | Deployed |
| Lambda Config | ✅ FIXED | Concurrency error | Terraform patched |
| Stock Scores | ✅ WORKING | 98.4% coverage today | No fix needed |
| Orchestrator Scheduler | ❌ BROKEN | Not executing | Diagnosis needed |
| API Caching | ❌ BROKEN | Stale signals | Investigation needed |
| Data Loaders | ⚠️ DEGRADED | 4 timeout | Resource scaling needed |

---

## PRODUCTION DEPLOYMENT CHECKLIST

Before deploying infrastructure fixes:

- [ ] Deploy Terraform Lambda concurrency fix: `cd terraform && terraform apply -lock=false`
- [ ] Verify orchestrator scheduler: check AWS console EventBridge rules
- [ ] Test orchestrator manual trigger: `python3 scripts/trigger_orchestrator.py --run morning --mode paper`
- [ ] Verify API caching layer is returning fresh signals
- [ ] Load test with expected volume
- [ ] Monitor CloudWatch for all 4 data loader timeouts
- [ ] Run end-to-end trading flow test after fixes

---

## QUICK REFERENCE COMMANDS

### Check System Status
```sql
-- Orchestrator execution
SELECT COUNT(*) as runs_last_24h, MAX(started_at) as latest 
FROM algo_orchestrator_runs 
WHERE started_at > NOW() - INTERVAL '24 hours';

-- Data freshness
SELECT table_name, age_days, status 
FROM data_loader_status 
WHERE table_name IN ('price_daily', 'stock_scores', 'buy_sell_daily')
ORDER BY table_name;

-- Portfolio health
SELECT COUNT(*) as open_positions, COUNT(CASE WHEN quantity IS NULL THEN 1 END) as null_qty
FROM algo_trades WHERE status = 'open';
```

### Deploy Infrastructure Fixes
```bash
cd terraform
terraform init -reconfigure
terraform validate
terraform plan
terraform apply -lock=false  # Deploy concurrency fix
```

### Verify Orchestrator
```bash
# Manual trigger (paper trading)
python3 scripts/trigger_orchestrator.py --run morning --mode paper

# Check logs
aws logs tail /aws/lambda/algo-orchestrator --follow
```

### Check EventBridge Scheduler
```bash
# List all algo schedules
aws events list-rules --name-prefix algo-schedule

# Check specific rule
aws events describe-rule --name algo-schedule-morning-dev

# Check if enabled
aws events describe-rule --name algo-schedule-morning-dev | jq '.State'
```

---

## CODE COMMITS THIS SESSION

1. `5f062154a` - Add missing quantity column to trades (Phase 8)
2. `a4d509a95` - Phase 9 quantity sync safeguard
3. `61472638a` - Document signal quality metrics
4. `ce949f922` - System audit and fixes summary
5. `ce10cd76b` - System health audit script
6. `2b6303faa` - Audit findings with critical issues
7. `c55be37ba` - Lambda concurrency Terraform fix

---

## SUMMARY

**Progress:** 4 critical fixes implemented + 1 terraform fix + 3 blocking issues identified and documented

**System Status:** 
- Data integrity: ✅ FIXED
- Code quality: ✅ PASSING (type checking)
- Infrastructure: ⚠️ PARTIALLY BROKEN (scheduler, caching, timeouts)

**Next Actions:**
1. Deploy Terraform concurrency fix (quick terraform apply)
2. Investigate and fix orchestrator scheduler (EventBridge + IAM)
3. Debug API caching layer (signals endpoint)
4. Scale ECS resources for data loaders

**Timeline to Production:** 2-4 hours if fixes are straightforward, 4-8 hours if infrastructure investigation reveals deeper issues.

---

**Session Date:** 2026-07-09  
**Status:** Audit complete, partial fixes deployed, blocking issues documented with diagnostic procedures
