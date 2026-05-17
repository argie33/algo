# Master Issues List — Complete System Audit

**Generated:** 2026-05-17  
**Status:** Comprehensive inventory of ALL known issues  
**Scope:** Everything blocking production readiness

---

## PART 1: SCHEMA/CODE CLEANUP (15 min)

### Issue 1.1: Orphaned Table Definitions in lambda/db-init/schema.sql
**Status:** NOT FIXED  
**Severity:** LOW (tables dropped from DB, but schema file has stale defs)  
**What:** These files still define tables we deleted from the database:
- `mean_reversion_signals_daily`
- `mean_reversion_signals_daily_etf`
- `range_signals_daily_etf`
- `range_signals_daily`

**Why It Matters:** On fresh DB init (AWS deployment), these orphaned tables would be recreated

**Fix Needed:** Delete these table definitions from schema files  
**Effort:** 15 min

---

### Issue 1.2: Orphaned Table Definitions in terraform/modules/database/init.sql
**Status:** NOT FIXED  
**Severity:** LOW (same as 1.1)  
**What:** Terraform IaC file has same orphaned table defs  
**Why It Matters:** Terraform would try to create these on AWS deployment  
**Fix Needed:** Delete same 4 CREATE TABLE blocks from Terraform  
**Effort:** 10 min

---

## PART 2: DATA HEALTH & OBSERVABILITY (2-3 hours)

### Issue 2.1: No Data Loader Health Tracking
**Status:** NOT FIXED  
**Severity:** MEDIUM (can't see which loaders are stale/failing)  
**What:** `data_loader_status` table exists but is EMPTY (populated 0 rows)

**Why It Matters:**
- Can't tell if a loader is broken or just hasn't run
- No alerts when data goes stale (>7 days old)
- Had to manually inspect database to find issues

**Fix Needed:** Create loader_health_tracker.py that records after each loader run  
**Effort:** 1-1.5 hours

---

### Issue 2.2: No CloudWatch Alarms for Data Freshness
**Status:** NOT FIXED  
**Severity:** MEDIUM (no monitoring in production)  
**What:** CloudWatch alarms not configured for data gaps

**Why It Matters:**
- Production has no alerting if data stops loading
- Oncall won't know algo is running on stale data
- Critical for SLA monitoring

**Alarms Needed:**
- Critical: Any table has 0 rows (data loading failed)
- Critical: Table older than 3 days (needs investigation)
- Warning: 3+ loaders failed in last 24 hours

**Effort:** 1-1.5 hours

---

### Issue 2.3: No Comprehensive Data Validation Tests
**Status:** NOT FIXED  
**Severity:** LOW-MEDIUM (can't catch issues until production)  
**What:** No automated test to verify all critical tables have data

**Fix Needed:** Create tests/test_data_integrity.py with:
- test_critical_tables_not_empty()
- test_data_freshness()

**Effort:** 30 min

---

## PART 3: SECURITY & API HARDENING (3-4 hours)

### Issue 3.1: No API Authentication
**Status:** NOT FIXED  
**Severity:** MEDIUM (public read-only API)  
**What:** Any client with API URL can read all stock data (no auth required)

**Why It Matters:**
- Violates data access policy
- No way to track who accessed what
- No protection against automated scraping

**Fix Needed:** Add API key authentication  
**Effort:** 2-3 hours

---

### Issue 3.2: Input Validation Not Systematically Checked
**Status:** NOT FIXED  
**Severity:** LOW-MEDIUM (SQL injection risk if not sanitized)  
**What:** Spot-check needed on high-traffic endpoints

**Fix Needed:**
1. Audit top 5 endpoints for SQL injection (verify parameterized queries)
2. Add test: try SQL injection in symbol field
3. Document validated vs not validated params

**Effort:** 1 hour

---

### Issue 3.3: HTTPS Not Enforced
**Status:** UNKNOWN  
**Severity:** LOW (API Gateway should enforce, but verify)  
**What:** API might accept HTTP (insecure) in addition to HTTPS

**Fix Needed:**
1. Verify API Gateway has HTTPS-only setting
2. Add redirect rule: HTTP → HTTPS
3. Add HSTS header

**Effort:** 30 min

---

## PART 4: PERFORMANCE OPTIMIZATION (2-3 hours)

### Issue 4.1: Orchestrator Runtime Not Profiled
**Status:** NOT FIXED  
**Severity:** MEDIUM (might exceed trading window)  
**What:** Don't know which phase is slowest, risk missing market opportunities

**Current State:**
- Orchestrator runs in ~5 min locally (unknown if acceptable)
- EventBridge scheduled for 5:30pm ET
- If runs too long, positions won't execute in time

**Fix Needed:**
1. Add timing to each phase
2. Log duration of each phase
3. Identify and optimize bottleneck (likely Phase 3-5)

**Effort:** 1 hour

---

### Issue 4.2: No Database Indexes on Frequently-Queried Columns
**Status:** NOT FIXED  
**Severity:** LOW-MEDIUM (queries might be slow on large tables)  
**What:** Tables with 1M+ rows might scan full table instead of using indexes

**High-Volume Tables:**
- `price_daily`: 1.5M rows
- `algo_trades`: likely to grow
- `buy_sell_signals`: 385K rows

**Fix Needed:** Add indexes and verify with EXPLAIN ANALYZE  
**Effort:** 1 hour

---

### Issue 4.3: Loaders Run Sequentially (40+ loaders take ~20 min)
**Status:** NOT FIXED  
**Severity:** LOW (not blocking, but could be faster)  
**What:** Currently serial, could parallelize independent loaders

**Fix Needed:**
1. Identify independent loaders
2. Group into parallel batches
3. Use asyncio/concurrent.futures
4. Reduces time from 20 min to ~10 min

**Effort:** 1.5 hours

---

## PART 5: TESTING & VERIFICATION (1.5 hours)

### Issue 5.1: APIs Not End-to-End Tested
**Status:** NOT FIXED  
**Severity:** MEDIUM (might have broken endpoints we don't know about)  
**What:** 19/22 APIs reported working, but not systematically tested

**Test Needed:**
1. Create test script that calls all 19 API endpoints
2. For each: GET, verify status 200, verify response shape
3. Test critical endpoints

**Effort:** 1 hour

---

### Issue 5.2: Frontend Pages Not Browser-Tested
**Status:** NOT FIXED  
**Severity:** MEDIUM (pages might load but crash or show empty data)  
**What:** 22 pages verified to exist, but haven't tested in browser

**Test Needed:**
1. Start `npm run dev`
2. Open each page in browser
3. Verify: page loads, data displays, no 404s
4. Test on previously broken pages (Sentiment, TradingSignals)

**Effort:** 30 min

---

## PART 6: DEPLOYMENT BLOCKER (AWS-ONLY)

### Issue 6.1: GitHub Actions OIDC Role Misconfiguration
**Status:** NOT FIXED (requires AWS access)  
**Severity:** CRITICAL (prevents AWS deployment)  
**What:** GitHub Actions can't assume IAM role

**Error:**
```
Could not assume role with OIDC: Request ARN is invalid
```

**Why It Matters:**
- `git push main` won't trigger deployment
- CI/CD pipeline broken
- Can't deploy to AWS until fixed

**Fix Needed:** (Requires AWS console access)
1. Verify IAM role exists
2. Check OIDC trust relationship
3. Verify GitHub OIDC provider is configured

**Effort:** 30 min (AWS console work)

---

## EXECUTION PRIORITY

| Phase | Issues | Time | Must Do? |
|-------|--------|------|----------|
| **1. Cleanup** | 1.1, 1.2 | 25 min | YES |
| **2. Verification** | 5.1, 5.2 | 1.5 hrs | YES |
| **3. Observability** | 2.1, 2.2 | 3 hrs | BEFORE PROD |
| **4. Security** | 3.1, 3.2 | 3.5 hrs | BEFORE PROD |
| **5. Performance** | 4.1, 4.2, 4.3 | 3.5 hrs | NICE-TO-HAVE |
| **6. Tests** | 2.3, 3.3 | 1 hr | FINAL POLISH |

**Critical Path:** Phases 1-2 (2 hours)  
**Before Production:** Phases 1-4 (9 hours)  
**Full System:** All phases (16 hours)

---

## NEXT: Systematic Execution Plan

We will:
1. Execute Phase 1 (cleanup) — 25 min
2. Execute Phase 2 (verification) — 1.5 hrs  
3. Execute Phase 3-4 (observability + security) — 6.5 hrs
4. Execute Phase 5-6 (performance + polish) — 4.5 hrs

**Ready to start with Phase 1?**
