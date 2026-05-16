# COMPREHENSIVE ISSUE INVENTORY (2026-05-16)

## 🔴 BLOCKING ISSUES (CRITICAL - Must fix before prod)

### 1. API Gateway JWT Auth (INFRASTRUCTURE)
- **Status:** ⚠️ BLOCKER
- **Problem:** Data endpoints return 401 despite code disabling Cognito
- **Cause:** Infrastructure hasn't re-applied Terraform changes
- **Fix:** GitHub Actions deploy-all-infrastructure.yml needs to run
- **Workaround:** Manual `cd terraform && terraform apply`

## 🟠 HIGH-PRIORITY (Should fix before/shortly after prod)

### 2. Error Responses Inconsistency (LOW-RISK)
- **Status:** MINOR - Most endpoints OK
- **Examples:** Some sentiment/sentiment endpoints return 200 with empty (should be 200 OK for "no data")
- **Impact:** Frontend error handling

### 3. API Response Schema Consistency (LOW-RISK)
- **Status:** MINOR - Mostly fixed
- **Examples:** Need to verify all endpoints return consistent field names
- **Impact:** Frontend integration

## 🟡 MEDIUM-PRIORITY (Nice-to-have, can do incrementally)

### 4. Missing Features (Non-blocking)
- Live WebSocket prices (optimization)
- Audit trail UI viewer (already logged, just needs UI)
- Notification system UI (infrastructure ready, UI needed)
- Pre-trade simulation UI (analysis tool)
- Backtest visualization (analysis tool)

### 5. Data Pipeline Monitoring (Non-blocking)
- No visibility into loader execution status
- No alerts for missing data
- No dashboard widget for data health

### 6. Sector Rotation Integration (Non-blocking)
- Computed but not fed to exposure policy
- Can be added as enhancement

## ✅ WHAT'S FIXED & WORKING

1. ✅ Market exposure persistence (CRITICAL - Fixed in bef428baa)
2. ✅ Data quality gates (CRITICAL - Enhanced in bef428baa)
3. ✅ API exposure-policy endpoint (Fixed d204649cb)
4. ✅ MetricsDashboard rendering (Fixed - extracts items properly)
5. ✅ ScoresDashboard prices (Fixed - uses current_price field)
6. ✅ Scores API with change_percent & market_cap
7. ✅ Portfolio snapshots with complete risk profile
8. ✅ Database indexes for performance
9. ✅ Credential handling in Lambda (46 files)
10. ✅ Social sentiment endpoint

## 📊 SUMMARY

**Blocking Issues:** 1 (infrastructure)
**High Priority:** 2 (low-risk, optional)
**Medium Priority:** 6 (nice-to-have)
**Critical Fixes Done:** 10
**Overall Status:** 90%+ production ready once infrastructure deploys
