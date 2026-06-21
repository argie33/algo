# Fallback Anti-Pattern Fixes - Task Breakdown

## Phase 1: CRITICAL Safety Gates (Block all other work)

### Task 1.1: Market Circuit Breaker Must Fail Fast
- **File:** `algo/infrastructure/market_events.py`
- **Lines:** 340-342 (handle_market_circuit_breaker)
- **Change:** Replace `return {"action": "ERROR", ...}` with `raise RuntimeError(...)`
- **Reason:** Circuit breakers are safety gates. Error dicts look like valid responses.
- **Acceptance:** Orchestrator receives exception, logs it, and halts trading
- [ ] TODO

### Task 1.2: Stock Halt Handler Must Fail Fast
- **File:** `algo/infrastructure/market_events.py`
- **Lines:** 289-291 (handle_single_stock_halt)
- **Change:** Replace error dict return with `raise`
- **Acceptance:** Callers receive exception, not error dict
- [ ] TODO

### Task 1.3: Exit Execution Audit Must Not Proceed if Log Fails
- **File:** `algo/infrastructure/audit_logger.py`
- **Lines:** 253-254 (log_exit_execution)
- **Change:** Replace `logger.warning()` with `raise RuntimeError(...)`
- **Reason:** If we can't audit exits, we shouldn't execute them
- **Acceptance:** Exit executor receives exception, transaction rolls back
- [ ] TODO

---

## Phase 2: Data Integrity (Compliance/State Correctness)

### Task 2.1: Position Sizing Audit Must Not Proceed if Log Fails
- **File:** `algo/infrastructure/audit_logger.py`
- **Lines:** 121-122 (log_position_sizing_audit)
- **Change:** Replace `logger.warning()` with `raise`
- [ ] TODO

### Task 2.2: Stop Loss Audit Must Not Proceed if Log Fails
- **File:** `algo/infrastructure/audit_logger.py`
- **Lines:** 192-193 (log_stop_loss_calculation)
- **Change:** Replace `logger.warning()` with `raise`
- [ ] TODO

### Task 2.3: Portfolio Snapshot Audit Must Not Proceed if Log Fails
- **File:** `algo/infrastructure/audit_logger.py`
- **Lines:** 353-354 (log_portfolio_snapshot_audit)
- **Change:** Replace `logger.warning()` with `raise`
- [ ] TODO

### Task 2.4: Reconciliation Audit Must Not Proceed if Log Fails
- **File:** `algo/infrastructure/audit_logger.py`
- **Lines:** 387-388 (log_position_reconciliation_audit)
- **Change:** Replace `logger.warning()` with `raise`
- [ ] TODO

### Task 2.5: Position Sizing Summary Must Raise, Not Return Error Dict
- **File:** `algo/infrastructure/audit_logger.py`
- **Lines:** 284-286 (get_position_sizing_summary)
- **Change:** Replace `logger.warning()` + `return {"error": ...}` with `raise`
- **Reason:** Callers get type-confused by error dict (expect dict, get error state)
- [ ] TODO

### Task 2.6: Reconciliation Main Function Must Raise, Not Return Error Dict
- **File:** `algo/infrastructure/reconciliation.py`
- **Lines:** 524-526 (run_reconciliation)
- **Change:** Replace `return {"success": False, ...}` with `raise`
- **Reason:** Forces callers to handle exception rather than ignore `success` flag
- [ ] TODO

### Task 2.7: Exit Fill Reconciliation Must Raise, Not Return Error Dict
- **File:** `algo/infrastructure/reconciliation.py`
- **Lines:** 695-697 (reconcile_exit_fills)
- **Change:** Replace `return {"updated": 0, "message": "Error: ..."}` with `raise`
- **Reason:** Disambiguates "0 fills reconciled" from "query failed"
- [ ] TODO

### Task 2.8: Partial Fill Check Must Raise, Not Return Error Dict
- **File:** `algo/infrastructure/reconciliation.py`
- **Lines:** 1034-1036 (check_partial_fills)
- **Change:** Replace error dict return with `raise`
- [ ] TODO

### Task 2.9: Pending Reconciliation Check Must Raise, Not Return Error Dict
- **File:** `algo/infrastructure/reconciliation.py`
- **Lines:** 1107-1109 (check_pending_reconciliations)
- **Change:** Replace error dict return with `raise`
- [ ] TODO

---

## Phase 3: Observability & Error Responses (API Consistency)

### Task 3.1: Market Breadth Handler Must Return 503 on Error
- **File:** `lambda/api/routes/market.py`
- **Lines:** 130-151 (_handle_breadth)
- **Change:** Remove `freshness = {}` fallback. Let exception propagate to API framework.
- **Reason:** Clients get 503 (server error) not 200 with empty data
- [ ] TODO

### Task 3.2: Market Technicals Handler Must Return 504 on Timeout
- **File:** `lambda/api/routes/market.py`
- **Lines:** 235-257 (_handle_technicals)
- **Change:** Remove `breadth = {}` fallback
- **Reason:** Clients know query timed out, not that breadth is zero
- [ ] TODO

### Task 3.3: McClellan Handler Must Return 503 on Error
- **File:** `lambda/api/routes/market.py`
- **Lines:** 277-288 (_handle_mcclellan)
- **Change:** Remove oscillator fallback
- [ ] TODO

---

## Phase 4: Monitoring & Health (Observability)

### Task 4.1: Data Patrol Configuration Logging Must Not Fail Silently
- **File:** `algo/monitoring/data_patrol/logger.py`
- **Lines:** 40-41 (log_configuration)
- **Change:** Replace `logger.error()` with `raise`
- [ ] TODO

### Task 4.2: Data Patrol Results Logging Must Not Fail Silently
- **File:** `algo/monitoring/data_patrol/logger.py`
- **Lines:** 65-66 (log_results)
- **Change:** Replace `logger.error()` with `raise`
- [ ] TODO

### Task 4.3: Optimal Loader Metrics Must Not Fail Silently
- **File:** `utils/optimal_loader.py`
- **Lines:** 1197-1198 (metrics publishing)
- **Change:** Replace `logger.debug()` with `raise`
- **Reason:** Loader failures should be visible to orchestrator health checks
- [ ] TODO

---

## Testing Strategy

For each task:

1. **Unit test:** Mock the failure path, verify exception is raised
2. **Integration test:** Verify exception propagates through orchestrator/API framework
3. **Manual test:** Trigger the error condition, verify proper error response
4. **Regression test:** Ensure happy path still works

---

## Rollout Plan

1. **Week 1:** Phase 1 (2 PRs, critical path)
2. **Week 2:** Phase 2 (2 PRs, data integrity)
3. **Week 3:** Phase 3 (1 PR, API consistency)
4. **Week 4:** Phase 4 (1 PR, observability)

Each PR should:
- Fix only one module/file
- Include unit + integration tests
- Update error response docs
- Document exception types raised
