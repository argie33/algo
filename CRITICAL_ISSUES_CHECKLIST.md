# Critical Issues Checklist & GO/NO-GO Decision

## Decision: ✅ GO — Proceed with E1 completion and deployment

**Rationale:** All blocking issues (E8, E9, E10, H1-H3) are already resolved. Only E1 (API migration) remains incomplete. Current uncommitted changes are safe and unrelated to critical path.

---

## Pre-Deployment Verification Checklist

### ✅ Critical Issues Already Fixed
- [x] **E8, E9** — Configuration externalized to `algo_config` table (commit b4b81133b)
- [x] **E10** — Win rate includes open P&L (commit b64f32f09)
- [x] **H1** — Frontend error display wired (commit 554693cdc)
- [x] **H2** — ErrorBoundary isolation per-route (commit 554693cdc)
- [x] **H3** — Data validation middleware (commit 554693cdc)
- [x] **E2, E3, E4, E5, E6, E7** — All prior tiers resolved (17 HIGH severity issues per commit d8014c3d1)

### ⏳ In Progress (Not Blocking)
- [ ] **E1** — API-only conversion (40% complete, 14+ functions remain)
  - Migration guide available in `API_MIGRATION_SCRIPT.py`
  - Data validation helpers ready
  - Estimated: 1-2 hours to complete + test

### ⚠️ Uncommitted Changes (Safe to Stage)
- [ ] `tools/dashboard/dashboard.py` — Partial E1 migration (imports in place, safe to extend)
- [ ] `algo/orchestrator/phase5_signal_generation.py` — Halt flag check (ISSUE #8, independent)
- [ ] `terraform/modules/pipeline/main.tf` — Timeout increase (independent, safe)

---

## Deployment Plan (7 Steps)

### 1. ✅ Verify Prerequisites (5 min)
- [x] api_data_layer.py exists
- [x] No git conflicts
- [x] E8, E9, E10, H1-H3 all resolved
- [x] Migration script available

**Status:** Ready to proceed

### 2. ⏳ Stage & Commit Current Changes (10 min)
- [ ] Stage: `git add tools/dashboard/dashboard.py algo/orchestrator/phase5_signal_generation.py terraform/modules/pipeline/main.tf`
- [ ] Commit: "WIP: Dashboard API migration partial E1 + phase5 halt flag + timeout increase"
- [ ] Verify: `git status` shows clean working tree

### 3. ⏳ Complete E1 API-Only Conversion (1-2 hours)
Priority functions (high-traffic fetch_* functions):
- [ ] `fetch_portfolio()` — Used in dashboard header
- [ ] `fetch_perf()` — Used in performance panel
- [ ] `fetch_recent_trades()` — Used in trade history
- [ ] `fetch_market()` — Market display
- [ ] `fetch_activity()` — Activity log
- [ ] `fetch_health()` — Data health status
- [ ] `fetch_algo_config()` — Configuration panel

For each:
1. Replace DB query with API call (see `API_MIGRATION_SCRIPT.py`)
2. Use safe_* conversion functions
3. Test: Verify no `_error` field in response

### 4. ⏳ Verify Data Quality (30 min)
- [ ] Run dashboard: `python tools/dashboard/dashboard.py`
- [ ] Check all panels display without `_error`
- [ ] Verify no null/undefined fields
- [ ] Check logs: `logger.error` or `logger.warning` messages

### 5. ⏳ Test End-to-End (30 min)
- [ ] Run dashboard in watch mode: `python tools/dashboard/dashboard.py -w 30`
- [ ] Verify auto-refresh every 30s
- [ ] Confirm no connection errors
- [ ] Check performance (should be faster than DB queries)

### 6. ⏳ Stage & Commit E1 Complete (5 min)
- [ ] `git add tools/dashboard/dashboard.py`
- [ ] Commit: "FIX: Complete E1 — convert all fetch_* functions to API-only data layer"
- [ ] Verify: All 20+ fetch_* functions now use API calls

### 7. ⏳ Push & Deploy (1 hour)
- [ ] `git push origin main`
- [ ] Wait for CI/CD pipeline
- [ ] Verify Lambda API endpoints responding
- [ ] Verify dashboard operational in AWS
- [ ] Monitor logs for errors

---

## Risk Assessment

| Issue | Risk | Mitigation |
|-------|------|-----------|
| Incomplete E1 at deploy | **Low** | Only 14 functions remain; API endpoints already exist |
| Data type mismatches | **Low** | safe_* conversion functions handle all edge cases |
| Missing `_error` handling | **Low** | Migration script includes error checks in all functions |
| Performance regression | **Low** | API calls are cached; faster than DB queries |

---

## Decision Summary

**GO/NO-GO:** ✅ **GO**

**Rationale:**
1. All critical blocking issues (E8, E9, E10, H1-H3) are already fixed
2. E1 migration is 40% complete with safe, reversible changes
3. Migration script provides exact patterns for remaining functions
4. No git conflicts; uncommitted changes are independent and safe
5. Data validation infrastructure ready (safe_* functions, error handling)
6. No external dependencies blocking deployment

**Next Action:** Proceed with step 2 (stage & commit) immediately. Complete E1 within this session.

**Estimated Total Time:** 3-4 hours (1-2 hours E1 + 30 min verify + 30 min test + 1 hour deploy + buffers)

