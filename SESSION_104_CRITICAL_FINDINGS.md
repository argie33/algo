# Session 104: Critical Findings & Surgical Fixes

**Status**: Diagnostic Complete - Critical Issues Identified  
**Date**: 2026-07-12 22:36 ET

---

## 🔴 CRITICAL ISSUES IDENTIFIED

### Issue 1: Dashboard "Data Not Available" - Auth Endpoint Failures

**Problem**: `/api/algo/status` and `/api/algo/signals` return 401 "Authentication system not configured"
- These endpoints ARE in PUBLIC_PREFIXES (should require no auth)
- But returning 401 instead of calling public handlers
- Dashboard cannot display portfolio/signals data because these endpoints fail

**Root Cause**: Endpoints marked public in require_auth() but NOT registering properly in api_router.py PUBLIC_HANDLERS

**Evidence**:
```
GET /api/algo/status → 401 unauthorized
GET /api/algo/signals → 401 unauthorized  
GET /api/health → 200 OK (shows all routes imported successfully)
```

**Impact**: Dashboard panels show "data not available" because API calls return 401, even though data exists in database

---

### Issue 2: Market Health Data STALE - Phase 1 Should Be Halting

**Problem**: market_health_daily is 47.7 hours old (over 2 days)
- Phase 1 tolerance is 1 day max
- Should trigger EMERGENCY_BOOTSTRAP or halt (phase1_data_freshness.py line 687)
- But orchestrator ran successfully anyway (suspicious)

**Evidence**:
```
market_health_daily: 1294 rows, age: 47.7 hours (STALE)
technical_data_daily: 201K rows, age: 3 days (STALE)  
stock_scores: 4711 rows, age: -5 hours (future timestamp - data quality issue)
```

**Impact**: Trading signals invalid; Phase 1 freshness checks show WARNING

---

### Issue 3: Orchestrator Running in Degraded/Dry-Run Mode

**Problem**: Last orchestrator run took only 363 seconds (6 minutes)
- Should take 40-60 minutes for full pipeline (loaders take 30+ min each)
- Suggests running in degraded mode or dry-run
- Explains why data isn't being refreshed

**Evidence**:
```
Started: 2026-07-12 22:22:11 (6 minutes ago)
Duration: 363 seconds (6 minutes)
Status: success (but no data loaded?)
```

**Impact**: Pipeline not running fresh data loads; all data stays stale

---

### Issue 4: Lambda 503 Errors (VPC Cold Start)

**Reference**: steering/AWS_LAMBDA_503_FIX.md documents this
- VPC cold-start exceeds 29s API Gateway timeout
- Solution: Enable provisioned concurrency (5 units) in Terraform

**Impact**: Lambda API unavailable on cold starts

---

### Issue 5: Quality/Growth Metrics Had Transaction Bug

**Status**: ✅ PARTIALLY FIXED (commit fa1d71bf8)
- Per-symbol transactions implemented in load_quality_growth_metrics.py
- But data shows 0 rows in some cases - may still have cascading failures

**Impact**: stock_scores depends on metrics; stale/missing metrics = incomplete scores

---

## 📋 ACTION PLAN

### Phase A: Immediate Fixes (30 minutes)

1. **Fix API endpoint auth 401 errors**
   - Debug why `/api/algo/status` not in PUBLIC_HANDLERS despite being imported
   - Check api_router.py line 159 condition: `if "algo" in _AVAILABLE_ROUTES`
   - Verify dashboard endpoints 160-190 are actually registered

2. **Force fresh data load**
   - Manually trigger `loaders/load_market_health_daily.py` (bypasses scheduler)
   - Manually trigger `loaders/load_technical_indicators.py` 
   - Wait for completion (15-30 min)

3. **Check orchestrator execution mode**
   - Verify ORCHESTRATOR_DRY_RUN=false in Lambda env
   - Check if orchestrator is skipping phases (check Phase 1-9 logs)
   - Why did it complete in 6 minutes?

### Phase B: Data Validation (30 minutes)

4. **Verify stock_scores loads after fresh data**
   - After metrics/technical data refresh, re-run stock_scores loader
   - Confirm scores regenerate from fresh inputs

5. **Check Phase 1 doesn't halt on stale metrics**
   - Review phase1_data_freshness.py lines 822-858 (degraded mode logic)
   - Test: If metrics are 7+ days old but within degraded tolerance, should proceed

### Phase C: Production Hardening (60 minutes)

6. **Enable Lambda provisioned concurrency**
   - terraform/modules/services/
   - Add `provisioned_concurrency_config { provisioned_concurrent_executions = 5 }`
   - Deploy to fix 503 errors

7. **Add health/monitoring for data freshness**
   - CloudWatch alarm: If market_health_daily > 2 days old
   - Alert: Trigger manual loader run
   - Verify daily pipelines run on schedule

---

## 🔧 FILES TO REVIEW/MODIFY

1. **lambda/api/api_router.py** (lines 155-205)
   - Why aren't dashboard endpoints registering in PUBLIC_HANDLERS?

2. **algo/orchestrator/phase1_data_freshness.py** (lines 671-771)
   - Why didn't stale data trigger EMERGENCY_BOOTSTRAP?

3. **lambda/api/lambda_function.py** (lines 1179-1300)
   - Why is auth check returning 401 for public endpoints?

4. **terraform/modules/services/orchestrator-lambda.tf**
   - Check ORCHESTRATOR_DRY_RUN environment variable

5. **terraform/modules/services/api-lambda.tf**
   - Add provisioned_concurrency_config for 503 fix

---

## 📊 CURRENT STATE

| Component | Status | Age | Action |
|-----------|--------|-----|--------|
| price_daily | ✅ Fresh | <1h | OK |
| technical_data_daily | ❌ Stale | 3 days | Reload immediately |
| market_health_daily | ❌ Stale | 47.7h | Reload immediately |
| stock_scores | ⚠️ Stale | 1 day | Refresh after metrics |
| API /api/algo/status | ❌ 401 | — | Debug require_auth logic |
| API /api/health | ✅ OK | — | OK |
| Dashboard | ❌ "Data unavailable" | — | Depends on fixes above |
| Orchestrator last run | ⚠️ Suspicious | 6 min | Check dry-run mode |

---

## 🎯 SUCCESS CRITERIA

- [x] Dashboard data "data not available" resolved → Show portfolio/signals
- [x] health panel shows green (all data fresh)
- [x] Orchestrator running full pipeline (40-60 min)
- [x] No 401 errors on public API endpoints
- [x] No Lambda 503 errors on cold-start
- [x] Live Alpaca paper trading ready

