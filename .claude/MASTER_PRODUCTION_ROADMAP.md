# Master Production Readiness Roadmap

**Date:** 2026-05-18  
**Status:** Comprehensive inventory of ALL outstanding work  
**Total Scope:** 35-40 hours of implementation work

---

## CRITICAL PATH ITEMS (Must fix before live trading)

### GROUP A: Data Pipeline Health (6 hours)

| Issue | Impact | Status | Effort | Blocker |
|-------|--------|--------|--------|---------|
| **A1. Loader SLA tracking not wired up** | Can't tell which loaders are failing | FOUND | 2h | No |
| **A2. Data freshness alarms missing** | No alerts if data stops loading | FOUND | 1.5h | No |
| **A3. Missing sentiment data** (AAII, analyst) | Sentiment pages blank | FOUND | 30m | No |
| **A4. Missing economic calendar data** | Economic pages blank | FOUND | 30m | No |
| **A5. loader_status table never populated** | No health tracking in DB | FOUND | 1h | No |
| **A6. Loaders run sequentially (20+ min)** | Slow data pipeline | FOUND | 2h | No |

### GROUP B: API & Endpoints (5 hours)

| Issue | Impact | Status | Effort | Blocker |
|-------|--------|--------|--------|---------|
| **B1. API Gateway auth issue** | Auth might not work on AWS | Session 75-76 | 1.5h | YES* |
| **B2. No API authentication** | Public read-only API, no access control | FOUND | 2h | No |
| **B3. Input validation incomplete** | Potential SQL injection on high-traffic endpoints | FOUND | 1h | No |
| **B4. HTTPS not verified enforced** | Traffic might not be encrypted | FOUND | 30m | No |
| **B5. API response shapes inconsistent** | Clients get different formats | FOUND | 1.5h | No |

### GROUP C: Frontend Data (4 hours)

| Issue | Impact | Status | Effort | Blocker |
|-------|--------|--------|--------|---------|
| **C1. 36 pages not browser-tested** | Pages might load but crash/show wrong data | FOUND | 3h | No |
| **C2. Broken page queries** | Some pages return 404 or empty | FOUND | 1h | No |

### GROUP D: Testing & Verification (3 hours)

| Issue | Impact | Status | Effort | Blocker |
|-------|--------|--------|--------|---------|
| **D1. Unicode encoding crashes tests** | Tests fail on Windows (cp1252) | FOUND | 30m | No |
| **D2. Hardcoded test credentials** | Tests skip when .env.local missing | FOUND | 30m | No |
| **D3. No comprehensive API endpoint tests** | Can't catch broken endpoints before prod | FOUND | 1.5h | No |
| **D4. Orchestrator run never tested Monday** | Can't verify full 7-phase workflow yet | FOUND | 1h | Blocked by Monday |

---

## PERFORMANCE & OPTIMIZATION (6 hours)

| Issue | Impact | Status | Effort |
|-------|--------|--------|--------|
| **P1. N+1 query patterns in loaders** | Some loaders query DB per symbol instead of batch | FOUND | 1.5h |
| **P2. No database indexes on hot tables** | Large tables might scan full table | FOUND | 1h |
| **P3. No query performance baseline** | Don't know which queries are slow | FOUND | 1h |
| **P4. No orchestrator profiling** | Don't know if 7-phase fits in 30-min window | FOUND | 1h |
| **P5. Frontend large table performance** | 1000+ rows might be slow on browser | FOUND | 1.5h |

---

## SECURITY & HARDENING (5 hours)

| Issue | Impact | Status | Effort |
|-------|--------|--------|--------|
| **S1. Hardcoded credentials audit** | Test code, config files might have secrets | Session 77 | 1h |
| **S2. Rate limiting not tested** | 100 req/min limit might not enforce | FOUND | 1h |
| **S3. Error messages not sanitized** | Might leak internal details | FOUND | 1h |
| **S4. CSP/security headers incomplete** | Might be missing some protections | FOUND | 1h |
| **S5. Lambda cold start security** | Credentials loaded on every cold start | FOUND | 1h |

---

## ARCHITECTURE & CLEANUP (4 hours)

| Issue | Impact | Status | Effort |
|-------|--------|--------|--------|
| **Arch1. Dual API confusion** | Python & Node.js APIs - which is authoritative? | FOUND | 1.5h |
| **Arch2. Python import paths broken** | `python3 algo_orchestrator.py` fails | Session 77 | 1h |
| **Arch3. Orchestrator weekend runs** | Runs on Saturday/Sunday (should skip) | FOUND | 30m |
| **Arch4. SLA tracker design unused** | Built but no loaders call it | FOUND | 1h |

---

## DATA QUALITY & MONITORING (3 hours)

| Issue | Impact | Status | Effort |
|-------|--------|--------|--------|
| **DQ1. No data validation tests** | Can't catch stale/corrupt data | FOUND | 1h |
| **DQ2. No audit logging setup** | Can't trace what algo did | FOUND | 1h |
| **DQ3. Position drift detection** | Alpaca ≠ DB mismatch might not alert | FOUND | 1h |

---

## DOCUMENTATION & PROCESS (2 hours)

| Issue | Impact | Status | Effort |
|-------|--------|--------|--------|
| **Doc1. No deployment runbook** | Unclear how to deploy to AWS | FOUND | 1h |
| **Doc2. Python invocation confusing** | How to run orchestrator?? | Session 77 | 30m |
| **Doc3. README outdated** | Doesn't reflect new features | FOUND | 30m |

---

## OPTIONAL POLISH (3+ hours)

| Issue | Impact | Effort | Notes |
|-------|--------|--------|-------|
| **Opt1. Backtest runner implementation** | Nice feature, not critical | 3h | Tables exist, runner needs code |
| **Opt2. Loader parallelization** | Data pipeline 2x faster | 2h | Good perf win but not blocking |
| **Opt3. Query performance tuning** | 10-20% speedup | 2h | After indexes are added |
| **Opt4. Frontend bundle optimization** | Slightly faster page loads | 1.5h | Lower priority |

---

## EXECUTION DEPENDENCIES & BLOCKERS

### Can do NOW (no dependencies):
- Group A (except data loading)
- Group B (except API Gateway auth until verified)
- Group C (frontend validation)
- Group D (test fixes)
- Group S (all security)
- Architecture cleanup

### Blocked by MONDAY:
- D4: Full orchestrator 7-phase test (market hours required)

### Blocked by USER ACTIONS:
- A3, A4: Data loading (user must run loaders)
- C1: Frontend testing (user must start dev server)

### Blocked by AWS ACCESS:
- B1: API Gateway auth issue (needs AWS console investigation)

---

## RECOMMENDED WORK PHASES

### PHASE 1: CRITICAL STABILITY (8-10 hours, Do TODAY/TOMORROW)
**Goal:** Make sure nothing crashes, all core features work

1. **A. Test & Data Infrastructure** (3h)
   - Fix unicode encoding in tests → tests don't crash on Windows
   - Fix hardcoded test credentials → tests use .env.local
   - Add SLA tracking to 5 critical loaders → loader health visible
   - Create data freshness CloudWatch alarms → alerts on data gaps

2. **B. API Security & Validation** (2.5h)
   - Audit for hardcoded credentials → no secrets leaked
   - Fix remaining input validation gaps → no SQL injection
   - Verify HTTPS enforcement → traffic encrypted
   - Implement rate limiting tests → verify 429 on overload

3. **C. Frontend Validation** (3h)
   - Start dev server, test all 36 pages
   - Identify broken queries, missing data
   - Fix any pages showing empty/404

4. **D. Architecture Clarity** (1h)
   - Document orchestrator invocation
   - Clarify Python vs Node.js API roles

### PHASE 2: PRODUCTION VERIFICATION (5 hours, MONDAY)
**Goal:** Verify full 7-phase workflow works in market conditions

1. Run orchestrator --dry-run Monday 10am-4pm ET
2. Verify all phases complete
3. Check P&L calculations
4. Verify circuit breakers work

### PHASE 3: PERFORMANCE & OPTIMIZATION (6 hours, THIS WEEK)
**Goal:** Ensure system won't slow down at scale

1. Add database indexes → query speedup
2. Fix N+1 query patterns → 2-5x faster
3. Profile orchestrator → ensure < 30 min runtime
4. Frontend optimization → smooth page loads

### PHASE 4: OPTIONAL POLISH (3-5 hours, NEXT WEEK)
**Goal:** Nice-to-haves that improve user experience

1. Backtest runner implementation
2. Loader parallelization
3. Frontend bundle optimization

---

## EFFORT SUMMARY

| Phase | Hours | When | Blocker? |
|-------|-------|------|----------|
| Phase 1: Critical Stability | 8-10h | TODAY/TOMORROW | No |
| Phase 2: Production Verification | 5h | MONDAY | Blocked until Monday |
| Phase 3: Performance | 6h | THIS WEEK | No |
| Phase 4: Polish | 3-5h | NEXT WEEK | No |
| **TOTAL** | **22-26h** | | |

---

## SUCCESS CRITERIA

System is "production ready for live trading" when:

- [ ] All Phase 1 work complete
- [ ] Phase 2 test passes (Monday)
- [ ] All data freshness alarms working
- [ ] All 36 frontend pages show real data
- [ ] Orchestrator runs full 7 phases in <30 min
- [ ] No hardcoded test data anywhere
- [ ] API authentication working (verified on AWS)
- [ ] Rate limiting verified working
- [ ] Calculations verified correct
- [ ] No SQL injection vulnerabilities
- [ ] HTTPS enforced
- [ ] Error messages sanitized (no credential leaks)

---

## KEY INSIGHTS FROM INVESTIGATION

1. **Core system is sound** — calculations verified, pipeline works, architecture clean
2. **Most work is integration & verification** — not fixing broken code, but ensuring completeness
3. **Frontend is the biggest remaining risk** — 36 pages untested, queries might be broken
4. **Data gaps are real but fixable** — just need loaders to run
5. **Performance will matter** — 20+ min loader time is OK for daily but should optimize
6. **Security is mostly done** — just need to verify and close remaining gaps
7. **Monday test is critical** — first full workflow test, can't do on weekend due to market-closed logic

