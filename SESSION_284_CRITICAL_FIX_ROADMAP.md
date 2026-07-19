# Session 284 Extended: Complete Critical Fix Roadmap

**Date:** 2026-07-19  
**Status:** 3 P0 fixes committed + tested (676 tests passing)  
**Remaining:** 68 critical issues across 6 categories

## Executive Summary

Comprehensive audit by 6 agents identified **71 real vulnerabilities**. Session 284 fixed 3 critical race conditions. Remaining 68 issues organized by severity and category below.

---

## P0 (PRODUCTION-BREAKING) - 8 ISSUES

### ✅ Fixed (3)
1. [x] Halt flag auto-clear race condition → Atomic DynamoDB ConditionExpression
2. [x] Halt count non-atomic increment → DynamoDB UpdateExpression with ADD
3. [x] Portfolio value stale fallback → Prioritize DB snapshot > API > config

### 🔧 Remaining (5)

**P0 #4: Alpaca Credential Failures Cascade**
- **File:** phase8_entry_execution.py:724-758
- **Issue:** Partial credentials (missing key OR secret) not explicitly detected
- **Impact:** Operator sees generic error, real field is unclear
- **Fix:** Explicitly validate both key AND secret, fail with specific missing field name
- **Effort:** 30 min
- **Test:** Verify error message includes which field missing

**P0 #5: Transaction Retry Logic Missing**
- **File:** phase8_entry_execution.py (order execution ~line 1001+)
- **Issue:** Failed orders not idempotent, duplicates possible on retry
- **Impact:** Double orders, duplicate positions
- **Fix:** Check broker if trade_id missing, use Alpaca order ID for idempotency
- **Effort:** 1.5 hours
- **Test:** Simulate order rejection, verify no duplicate on next run

**P0 #6: Empty stock_symbols Table Not Pre-Validated**
- **File:** phase1_data_freshness.py (Phase 1 startup)
- **Issue:** If symbols loader fails, downstream phases attempt execution
- **Impact:** Cascading failures across all phases
- **Fix:** Add pre-flight check: require stock_symbols.count() > 0
- **Effort:** 30 min

**P0 #7: Partial Fill Reconciliation API Error Not Exception**
- **File:** phase4_reconciliation.py:55-66
- **Issue:** check_partial_fills() returns error status instead of raising
- **Impact:** Proceeds with undefined behavior
- **Fix:** Validate API status is OK before accessing 'mismatches' field
- **Effort:** 45 min

**P0 #8: Data Staleness Cascades Without Halt Check**
- **File:** Multiple phases (5-8)
- **Issue:** Phase 1 detects stale data but Phase 5 already generated signals
- **Impact:** Trades on outdated technicals
- **Fix:** Phase 5 re-checks halt flag before signal generation
- **Effort:** 1 hour

**Total P0 Effort:** 4 hours

---

## P1 (HIGH - DATA INTEGRITY) - 12 ISSUES

**P1 #1: Phase Executor Dependency Staleness Not Validated**
- Issue: Phase 5 constraints could be >1h old, still passes validation
- Fix: Add timestamp validation to phase_result contract
- Effort: 1 hour

**P1 #2: Database Connection Pool Not Monitored**
- Issue: Hung connection blocks orchestrator indefinitely
- Fix: Add context timeout, explicit release in exception paths
- Effort: 1.5 hours

**P1 #3-5: Phase Halt Conditions Skip Validation**
- Issues: Phase 1 degraded_mode desync, Phase 4 broker auth continues, Phase 9 P&L unknown
- Fix: Each phase validates halt flag independently before proceeding
- Effort: 2 hours total

**P1 #6-8: Silent Fallbacks in Phases 4, 8, 9**
- Issues: Broker unavailable, portfolio value fallback, P&L unknown continue
- Fix: Convert WARN to HALT for critical data unavailability
- Effort: 1.5 hours total

**P1 #9-12: Loader Health Check Issues**
- Issues: Late-in-preflight errors proceed, lock cleanup races, startup timing
- Fix: Move health checks to startup, add atomic cleanup
- Effort: 2 hours total

**Total P1 Effort:** 8 hours

---

## P2 (MEDIUM - DASHBOARD/CONFIG) - 35 ISSUES

### Dashboard Validation Issues (21)
1. data_unavailable flag type validation → Validate boolean explicitly
2. Portfolio allocation division by zero → Return error marker, not empty array
3. Negative/zero prices accepted → Add min price validation
4. Ladder calculation falsy zero handling → Use explicit None checks
5-21. Additional validation issues (see CURRENT_CRITICAL_FINDINGS.md)

**Effort:** 4 hours

### Configuration Issues (14)
1. int() type conversion without try/catch → Add try/except with clear error
2. Boolean coercion inconsistencies → Standardize on explicit 'true'/'false' parsing
3. Env var typo fallbacks → Document expected var names in startup
4-14. Additional config issues

**Effort:** 2 hours

**Total P2 Effort:** 6 hours

---

## P3 (CONCURRENCY SAFETY) - 5 ISSUES

**P3 #1: DynamoDB Lock Duration Expires Mid-Orchestrator**
- Issue: Lock held for 600s but Phase 1-9 execution takes 10+ min
- Fix: Extend lock TTL to 15 minutes
- Effort: 30 min

**P3 #2: Halt Count Increment Race** ✅ FIXED (see P0 #2)

**P3 #3: Circuit Breaker Failure Counter Race**
- Issue: Read-modify-write on _circuit_breaker_failures counter
- Fix: Use atomic counter with lock
- Effort: 1 hour

**P3 #4: Halt Flag Set-Check Window**
- Issue: 50-100ms race between halt write and halt check
- Fix: Single atomic operation or eliminate window
- Effort: 1 hour

**P3 #5: Loader Health Check Timing**
- Issue: Between kill and health check, stale status
- Fix: Poll health immediately after kill, validate recovery
- Effort: 1 hour

**Total P3 Effort:** 4 hours

---

## P4 (NUMERIC SAFETY) - 8 ISSUES

**Critical Numeric Divisions:**
1. SPY variance = 0 → Check before dividing in beta_exposure
2. Entry price = stop loss price → Validate price_diff > 0
3. Portfolio return all zeros → Skip VaR, return None with marker
4-8. Extreme values, precision loss, edge cases

**Effort:** 2 hours

---

## Total Remediation Effort

| Priority | Category | Issues | Effort |
|----------|----------|--------|--------|
| P0 | Race Conditions | 8 | 4 hours |
| P1 | Data Integrity | 12 | 8 hours |
| P2 | Dashboard/Config | 35 | 6 hours |
| P3 | Concurrency | 5 | 4 hours |
| P4 | Numeric Safety | 8 | 2 hours |
| **TOTAL** | | **71** | **24 hours** |

---

## Recommended Fix Sequence

**Session 284 (Current) - 8 hours:**
1. P0 #4-8 (5 critical issues) - 4 hours
2. P1 #1-3 (highest impact) - 2 hours  
3. P3 #1 (extend lock TTL) - 0.5 hour
4. Testing & verification - 1.5 hours

**Session 285 - 8 hours:**
1. P1 #4-12 (data integrity) - 4 hours
2. P2 #1-5 (critical dashboard) - 3 hours
3. Testing - 1 hour

**Session 286 - 8 hours:**
1. P2 #6-14 (config issues) - 2 hours
2. P3 #3-5 (concurrency) - 3 hours
3. P4 (numeric safety) - 2 hours
4. Integration testing - 1 hour

---

## Testing Strategy

After each commit:
```bash
# Run full test suite
python -m pytest tests/ -q

# Run critical-path tests
python -m pytest tests/integration/ -q

# Run regression suite
python -m pytest tests/test_session_284_*.py -v
```

**Current Status:** 676/677 tests passing (99.9%)

---

## Success Criteria

- [ ] All 71 issues documented and prioritized
- [ ] All P0 race conditions fixed and verified atomic
- [ ] All P1 data integrity gaps closed
- [ ] 100% of failing scenarios return explicit error markers (no silent fallbacks)
- [ ] Test suite 100% passing
- [ ] No new race conditions introduced
- [ ] Production ready for deployment

---

## Related Sessions

- [[session_284_audit_summary]] - Initial audit findings
- [[session_283_loader_governance_compliance]] - Loader bulletproofing
- [[session_282_comprehensive_audit]] - Orchestrator audit
