# Jun 6 Critical System Verification Procedures

**Date:** June 6, 2026  
**Goal:** Verify system stability before operational launch  
**Critical Deadline:** 4:05 PM ET (data freshness check)  
**Duration:** 3:30 AM ET → 6:00 PM ET

---

## Timeline

| Time | Action | Success Criteria |
|------|--------|------------------|
| 3:30 AM | Morning prep pipeline startup | ECS task RUNNING within 60s |
| 8:00 AM | Morning prep completion | price_daily, technical_data, buy_sell_daily loaded |
| 10:00 AM | Dev server chart rendering | Zero console warnings, all charts render |
| 4:05 PM | **CRITICAL** Data freshness check | All staleness columns non-NULL, max age ≤ 0 days |
| 4:30 PM | EOD pipeline verification | 9 core loaders running |
| 5:00 PM | Signal quality baseline | 2-5 qualified signals, no age rejections |
| 5:30 PM | Intraday orchestrator | Phase 7 complete, no data halts |
| 6:00 PM | Final verification summary | All checkpoints passed |

---

## Critical Checkpoint: 4:05 PM Data Freshness Check

**Execute:**
```powershell
./scripts/check-data-freshness.ps1
```

**Expected:**
- Total rows: 9000+ (90%+ coverage)
- buy_sell_daily_age_days: ALL non-NULL, max = 0
- technical_data_age_days: ALL non-NULL, max = 0
- trend_template_age_days: ALL non-NULL, max = 0

**If FAILS:** Immediately check `/ecs/algo-loader` logs for EOD pipeline errors. May need manual data patrol trigger.

---

## Debugging Commands

**Monitor Pipelines:**
```bash
# Morning prep
aws logs tail /ecs/algo-loader --follow --since 2h

# Orchestrator
aws logs tail /lambda/algo-algo-dev --follow --since 1h

# API
aws logs tail /lambda/algo-api-dev --follow --since 30m
```

**System Health:**
```bash
# RDS connections
aws cloudwatch get-metric-statistics --namespace AWS/RDS --metric-name DatabaseConnections \
  --start-time 2026-06-06T03:30:00Z --end-time 2026-06-06T18:00:00Z --period 300 --statistics Maximum

# RDS Proxy status
aws rds describe-db-proxies --query 'DBProxies[?DBProxyName==`algo-rds-proxy-dev`]'
```

---

## Escalation Criteria

- ❌ Morning prep not RUNNING by 4:00 AM → Check ECS cluster
- ❌ Morning prep not COMPLETED by 8:30 AM → Check yfinance/RDS
- ❌ Data freshness check returns NULL → CRITICAL: EOD pipeline failed
- ❌ Charts show errors at 10 AM → Check API NULL fields
- ❌ Phase 1 never starts at 9:30 AM → Check Lambda

---

## Pre-Launch Verification

✅ API NULL safety (COALESCE in scores.py, stocks.py, signals.py, algo.py)  
✅ Frontend null checks (MarketIndicators.jsx, DeepValueStocks.jsx)  
✅ RDS Proxy active (terraform/modules/database/main.tf)  
✅ yfinance resilience (token bucket, exponential backoff, circuit breaker)  
✅ Signal data age filtering (Phase 5, parameterized threshold)  
✅ Phase 1 grace period (configurable via algo_config)  
✅ Data patrol thresholds (parameterized via algo_config)  
✅ Test suite (test_phase1_failsafe_logic.py: 9/9 passing)  

**System ready for verification.**
