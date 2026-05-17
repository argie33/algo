# Comprehensive Production Hardening Plan

**Date:** 2026-05-17  
**Status:** IN PROGRESS  
**Total Issues Found:** 42 (5 CRITICAL, 14 HIGH, 20 MEDIUM, 3 LOW)  
**Estimated Total Effort:** 120-140 hours over 3-4 weeks

---

## Executive Summary

The stock analytics trading system is **85-90% production-ready** with solid architectural foundations. However, a comprehensive audit identified 42 remaining issues across 10 categories that must be addressed before live money trading:

- **5 CRITICAL BLOCKERS** — Would cause production failures
- **14 HIGH IMPACT** — Should fix before staging
- **20 MEDIUM** — Important improvements for reliability
- **3 LOW** — Nice-to-have polish items

This plan prioritizes work by impact and dependencies, enabling parallel work streams.

---

## CRITICAL BLOCKERS (Must Fix Before Live Trading)

### CRITICAL #1: Exception Handler Coverage (150+ instances)
**Files:** lambda/api/lambda_function.py (59), algo/* (40+), loaders/* (20+)  
**Problem:** Bare `except Exception as e:` masks failures in trading, data loading, API handling  
**Impact:** Silent failures → corrupted positions, wrong signals, system crashes  
**Fix:** Replace with specific exceptions (psycopg2.*, requests.*, ValueError, etc.)  
**Effort:** 8-10 hours  
**Status:** NOT STARTED  
**Task:** #8

### CRITICAL #2: Input Validation Schema  
**Files:** lambda/api/lambda_function.py, all loaders, all API endpoints  
**Problem:** No validation — bad data silently propagates through system  
**Impact:** Invalid symbols, out-of-range prices → corrupted trades, signals  
**Fix:** Pydantic validation schema (validation_schema.py created), apply to all endpoints  
**Effort:** 5-6 hours  
**Status:** SCHEMA CREATED, INTEGRATION PENDING  
**Task:** #9

### CRITICAL #3: SQL Injection Risks
**Files:** algo/algo_data_patrol.py, loaders/, algo/algo_pipeline_health.py  
**Problem:** f-string SQL with table/column names — data breach vectors  
**Impact:** Arbitrary query execution, data theft, DoS  
**Fix:** Parameterize all dynamic table/column names with allowlist  
**Effort:** 4-5 hours  
**Status:** NOT STARTED  
**Task:** #10

### CRITICAL #4: Core Business Logic Untested
**Files:** algo_orchestrator.py (2046 LOC), algo_filter_pipeline.py (1461 LOC), 6 other modules  
**Problem:** Zero unit tests for position sizing, signal generation, exit logic  
**Impact:** Calculation bugs in production → wrong position sizes, bad exits  
**Fix:** Add 100+ unit tests covering phases, tiers, orders, reconciliation  
**Effort:** 20-25 hours  
**Status:** NOT STARTED  
**Task:** #11

### CRITICAL #5: Data Validation in Loaders
**Files:** All 41 loaders  
**Problem:** No validation of OHLCV data before insert (high >= low, volume >= 0, etc.)  
**Impact:** Corrupt data enters database → bad signals, bad calculations  
**Fix:** Add pre-insert validators to all loaders  
**Effort:** 5-6 hours  
**Status:** NOT STARTED  
**Task:** #20

---

## HIGH IMPACT ITEMS (Weeks 1-2)

### HIGH #1: Database Performance
- **Task #12:** Add missing composite indexes (3-4h) — 10-50x query speedup
- **Task #13:** Fix N+1 query patterns (3-4h) — reduce 5000 queries → 5

### HIGH #2: API Rate Limiting
- **Task #15:** Per-endpoint rate limiting (2-3h) — prevent DoS on expensive endpoints

### HIGH #3: Code Quality
- **Task #16:** Add type hints to core modules (4-5h) — IDE support, mypy checks
- **Task #14:** Remove print() statements (1-2h) — proper logging in production

---

## MEDIUM ITEMS (Weeks 2-3)

### MEDIUM #1: Frontend Reliability
- **Task #17:** Error boundaries + error handling (6-8h) — graceful API failures

### MEDIUM #2: Configuration Management
- **Task #18:** Config validation at startup (3-4h) — catch config errors early

### MEDIUM #3: API Standardization
- **Task #19:** Standardize response format (4-5h) — consistent client parsing

---

## RECOMMENDED EXECUTION ORDER

### Week 1 (40-45 hours) — Foundation & Critical Fixes
**Day 1-2: Exception Handlers (8-10h)**
- Audit all exception handlers
- Create mapping of specific exception types
- Replace in critical paths first (API, orchestrator, trade executor)
- Add context logging

**Day 2-3: Input Validation (5-6h)**
- Apply validation_schema.py to lambda_function.py endpoints
- Add validation to all 41 loaders
- Test with invalid data

**Day 3-4: SQL Injection (4-5h)**
- Create safe_query() helper with allowlist
- Audit and replace all f-string SQL
- Add tests for injection prevention

**Day 4-5: Unit Tests for Core Logic (20-25h)**
- Create test files for 8 untested modules
- Implement 100+ unit tests
- Achieve 80%+ coverage on critical modules

### Week 2 (35-40 hours) — Performance & Quality
**Day 6-7: Database Optimization (6-8h)**
- Add missing indexes
- Fix N+1 queries
- Verify 10-50x speedup on slow queries

**Day 8-9: Code Quality (7-10h)**
- Add type hints to 6 large modules
- Remove 244 print() statements → logger calls
- Run mypy checks

**Day 10: API Hardening (2-3h)**
- Add per-endpoint rate limiting

### Week 3 (25-30 hours) — Frontend & Integration
**Day 11-12: Frontend Reliability (6-8h)**
- Add error boundaries
- Add loading states
- Test API failure scenarios

**Day 13: Configuration (3-4h)**
- Add config validation at startup
- Create separate config files (.env.prod, .env.test)

**Day 14: API Standardization (4-5h)**
- Create response wrapper functions
- Update all 34 endpoints
- Update frontend parsing

### Week 4 (20-25 hours) — Testing & Validation
**Day 15-17: Full System Testing (15-20h)**
- End-to-end orchestrator test
- Load testing (5000+ symbols)
- Chaos engineering (market disruptions)
- Shadow trading (paper mode, real signals)

**Day 18: Deploy & Monitor (5h)**
- Deploy to staging
- Monitor first 24 hours
- Verify no silent failures

---

## PARALLEL WORK STREAMS

These can be done simultaneously:

**Stream A (Backend):**
- Exception handlers → Input validation → SQL injection fixes
- Database optimization (indexes, N+1 queries)
- Core business logic unit tests

**Stream B (Frontend):**
- Error boundaries → Loading states → API standardization
- Type hints for frontend code

**Stream C (Testing):**
- Unit tests (backend)
- Integration tests (end-to-end)
- Load tests

**Stream D (Operations):**
- Configuration validation
- Monitoring/alerting setup

---

## RISK MITIGATION

### What Breaks Without These Fixes?
1. **Silent failures** — position tracking wrong, trades execute incorrectly
2. **Data corruption** — bad OHLCV enters system, spreads through signals
3. **Security breach** — SQL injection, DoS attacks
4. **Undetectable bugs** — untested code paths fail in production

### Testing Strategy
1. **Unit tests** — verify calculation accuracy (position sizing, P&L, exits)
2. **Integration tests** — end-to-end pipeline (load → signal → trade)
3. **Load tests** — behavior at 5000+ symbols
4. **Chaos tests** — missing data, API failures, market disruptions
5. **Shadow trading** — paper mode with real signals, no real money risk

### Rollback Plan
- Keep Git history clean with atomic commits
- Tag stable points: `v1.0-staging-ready`, `v1.0-live-ready`
- Maintain previous version branch for quick rollback
- Database migrations are reversible

---

## TRACKING PROGRESS

### Completed (Session 76)
- ✅ Security fix: Removed plaintext password from STATUS.md
- ✅ Data accuracy: Fixed McClellan oscillator A/D line
- ✅ Verified all 6 hardening phases complete
- ✅ Created validation_schema.py

### In Progress
- 🔄 Task #9: Input validation schema integration

### Blocked By
- Exception handler audit (Task #8) — needed before full validation
- Unit test framework — need testing infrastructure setup

### Ready to Start
- Task #10: SQL injection audit (low dependency)
- Task #12: Database indexes (low dependency)
- Task #15: Rate limiting (low dependency)

---

## SUCCESS CRITERIA

**Before Staging Deployment:**
- ✅ All 5 CRITICAL blockers fixed
- ✅ 14 HIGH items addressed
- ✅ 50+ unit tests passing
- ✅ Load test passes (5000+ symbols)
- ✅ No SQL injection vectors
- ✅ All API inputs validated

**Before Live Money:**
- ✅ All MEDIUM items completed
- ✅ 100+ unit tests passing
- ✅ 1 week of shadow trading clean
- ✅ Chaos testing passed (market disruptions)
- ✅ 24-hour dry-run orchestrator test clean
- ✅ All team members trained on production runbooks

---

## Resources Needed

- 1 Senior Developer (Primary implementation)
- 1 QA/Tester (Testing framework, test design)
- Database with 5000+ symbols for load testing
- Staging environment (separate from production)
- Monitoring/alerting setup (CloudWatch, Datadog)

---

## Estimated Timeline

| Phase | Duration | Start | End | Status |
|-------|----------|-------|-----|--------|
| Week 1: Critical Fixes | 5 days | Day 1 | Day 5 | PENDING |
| Week 2: Performance | 5 days | Day 6 | Day 10 | PENDING |
| Week 3: Frontend | 5 days | Day 11 | Day 15 | PENDING |
| Week 4: Testing | 5 days | Day 16 | Day 20 | PENDING |
| **TOTAL** | **4 weeks** | Today | +28 days | ON TRACK |

---

## Dependencies & Blockers

### Must Do First:
1. Exception handlers (unblocks reliable code)
2. Input validation (unblocks safe data)
3. SQL injection fixes (unblocks security)

### Can Do in Parallel:
- Database indexes (performance improvement)
- Type hints (code quality)
- Config validation (operational)
- Frontend error handling

### Dependent on Above:
- Unit tests (need stable code first)
- Integration tests (need all pieces working)
- Load tests (need optimized queries)

---

## Quick Wins (Can Do First)

**Easy to Complete, High Impact:**
1. Remove print() statements → proper logging (1-2h)
2. Add type hints to largest files (2-3h)
3. Database indexes (3-4h, big impact)
4. Config validation (2-3h, catches errors early)

---

## Next Steps

1. **Assign Tasks:** Pick developer(s) for each stream
2. **Setup:** Create test environment, prepare fixtures
3. **Week 1:** Focus on 5 critical blockers
4. **Daily:** 15-min standup, blockers/progress tracking
5. **Weekly:** Review completed tasks, plan next week

---

**Owner:** Claude (AI Developer)  
**Last Updated:** 2026-05-17  
**Next Review:** Daily
