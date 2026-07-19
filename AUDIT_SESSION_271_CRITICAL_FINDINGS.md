# SESSION 271: CRITICAL AUDIT - PHASE BYPASS & OUTPUT TABLE FAILURES

**Status:** 🔴 CRITICAL - System not working as advertised

**Date:** 2026-07-19
**Finding Time:** ~10:55 ET

## Executive Summary

The orchestrator reports "9/9 phases passing" but this is **FALSE**. The system has a systematic bypass:
- Phases 1-2 validate INPUT tables only (price_daily, market_exposure_daily, etc.)
- Phases 3-8 skip silently when dependencies fail
- Output tables (algo_trades, algo_positions, algo_reconciliation_log) remain **EMPTY**
- Dashboard and memory report "success" based on input table freshness, not actual output

**Impact:** Trading system is non-functional. No trades executed, no positions tracked, no reconciliation logged.

---

## Critical Issues

### Issue 1: Output Tables Are Empty (Phase Execution Bypass)

```
algo_trades:               EMPTY (0 rows)       - P8 produces nothing
algo_positions:            EMPTY (0 rows)       - P3/P4 produce nothing
algo_reconciliation_log:   EMPTY (0 rows)       - P4 produces nothing
algo_signals_evaluated:    46 DAYS OLD          - Last update 2026-06-03
```

**Root Cause:** Phases skip their work but don't fail. When P4 (reconciliation) fails or produces no data, downstream phases (P5, P7, P8) skip silently.

**Evidence:**
```python
# Phase executor: After phase fails/skips, it stores skip data:
result = PhaseResult(
    phase_num=phase_num,
    status="skipped",
    data=self._get_default_skip_data(phase_num),  # <-- Empty defaults!
    halted=True,
)
```

The "success" metrics in memory are based on Phase 1 checking input tables, not verifying phases actually produced output.

### Issue 2: Input Tables Are Stale (Phase 1 Validation Incomplete)

```
price_daily:               2 DAYS OLD   (last: 2026-07-17, today 2026-07-19 Sat)
technical_data_daily:      2 DAYS OLD   (last: 2026-07-17)
market_exposure_daily:     1 DAY OLD    (only 2 rows! - should have full exposure snapshot)
industry_ranking:          13 DAYS OLD  (last: 2026-07-06)
trend_template_data:       2 DAYS OLD   (last: 2026-07-17)
```

**Root Cause:** 
- Today is Saturday (non-trading day) - prices being 2 days old (Fri close) is expected
- But `market_exposure_daily` has only 2 rows total (corrupted or never properly loaded)
- Phase 1 doesn't validate row counts or that tables have sufficient data

### Issue 3: Abandoned/Stale Metrics Table

```
algo_signals_evaluated:    541 rows, last: 2026-06-03 (46 DAYS OLD)
```

**Root Cause:** This table was populated once in early June, then abandoned. Phase 7 (signal generation) doesn't update it.

---

## Missing Output Table Data

### Phase 4 (Reconciliation) → algo_reconciliation_log

Expected: Daily reconciliation record comparing broker positions vs database state
Actual: EMPTY (0 rows)

**Impact:** No audit trail of position synchronization. Can't verify broker-db sync worked.

### Phase 8 (Entry Execution) → algo_trades

Expected: New trade entries from Phase 8 execution
Actual: EMPTY (0 rows) - Only 67 rows in `algo_trades_archive` from 2026-07-09

**Impact:** 
- Dashboard can't show "entries executed" (returns None → shows as HALTED)
- No trade history for this week
- Entry execution is non-functional

### Phase 3 (Position Monitor) → algo_positions

Expected: Current open positions synced from Alpaca
Actual: EMPTY (0 rows)

**Impact:**
- No visibility into current holdings
- Phase 5 (exposure policy) can't enforce position limits
- Exit execution (Phase 6) has nothing to exit

---

## The Bypass Mechanism

```
PHASE EXECUTION FLOW (What's Actually Happening):

Phase 1: Data Freshness Check
  ✓ Checks price_daily (2d old) - PASSES because Saturday
  ✓ Checks market_exposure_daily exists - PASSES (1d old, 2 rows)
  → Returns "ok" status even though data quality is poor

Phase 2: Circuit Breakers
  ✓ Depends on Phase 1 → Runs because P1 "ok"
  → Returns circuit breaker status

Phase 3: Position Monitor
  ✓ Always runs (always_run=True)
  → Syncs Alpaca positions → EMPTY result (no query output stored)

Phase 4: Reconciliation
  ✓ Depends on Phase 3
  → Should log reconciliation but algo_reconciliation_log is EMPTY
  → Returns "ok" even though nothing was logged

Phase 5: Exposure Policy
  ✓ Depends on Phase 4 (which "ok"ed)
  → Tries to read market_exposure_daily (only 2 rows, stale)
  → Gets market regime but with corrupted/incomplete data
  → Returns "ok" with skip data

Phase 7: Signal Generation
  ✓ Depends on Phase 5
  → Tries to generate signals from exposure policy
  → Gets skip data because Phase 5 had no real constraints
  → Returns "ok" with no signals (0 signals per dashboard)

Phase 8: Entry Execution  
  ✓ Depends on Phase 7 & 5
  → Has no signals from Phase 7
  → Returns "ok" with 0 entries (algo_trades EMPTY)
  → Dashboard shows as "HALTED" because no data

Phase 9: Portfolio Snapshot
  ✓ Always runs (always_run=True)
  → Creates snapshot with empty portfolio (no positions)
```

**Result:** Orchestrator reports "9/9 phases success" but all phases 3-8 produced empty/skip data.

---

## Why Memory Said "All 9/9 Phases Passing"

Session 270 audit checked ONLY:
- ✅ Input tables exist and have data
- ✅ Phase execution completes
- ❌ Did NOT verify output tables were populated
- ❌ Did NOT validate phases actually produced real data
- ❌ Did NOT check for empty result tables

The audit was incomplete. It verified the framework works but not that the system produces output.

---

## Confirmed Non-Kosher Patterns Found

1. **Silent Phase Skipping:** Phases return "ok" status even when skipped due to bad dependency data
2. **Skip Data Masquerading as Real Data:** When phase.dependencies fail, executor returns `_get_default_skip_data()` which looks like real but is empty defaults
3. **Incomplete Output Validation:** Phase 1 doesn't verify downstream phases will have data to work with
4. **Abandoned Metrics:** `algo_signals_evaluated` populated once, never updated again
5. **Corrupted Table State:** `market_exposure_daily` has only 2 rows (should be ~500 exposure snapshots)
6. **Unmonitored Stale Tables:** Industry ranking (13d), trend_template_data (2d) not in freshness monitor
7. **Monitor Gap:** Only 5 tables monitored, 11+ critical tables have stale/empty data

---

## Impact Assessment

**Critical (System Non-Functional):**
- ❌ No trades executing (algo_trades empty)
- ❌ No positions tracked (algo_positions empty)
- ❌ No reconciliation logged (algo_reconciliation_log empty)
- ❌ Portfolio completely dark to system

**High (Data Integrity):**
- ❌ `algo_signals_evaluated` 46 days stale
- ❌ `market_exposure_daily` corrupted (only 2 rows)
- ❌ `industry_ranking` 13 days stale
- ⚠️  `price_daily` 2 days old (expected for weekend, but needs refresh Mon)

**Medium (Observability):**
- ❌ Dashboard shows P5, P8 as "HALTED" (because tables empty)
- ❌ No phase-level status stored in database
- ⚠️  Staleness monitor only checks 5/16 critical tables

---

## What Needs to Happen

### Immediate Fixes (Critical Path)

1. **Verify Phase 4 Output:** Why is `algo_reconciliation_log` empty?
   - Does Phase 4 even write to this table?
   - Is it using wrong table name?
   - Does it fail silently?

2. **Verify Phase 8 Output:** Why is `algo_trades` empty?
   - Phase 7 signals exist (99 rows in algo_signals)
   - Phase 8 should be executing these
   - Check if Phase 8 even writes to algo_trades or different table

3. **Fix market_exposure_daily:** Why only 2 rows?
   - Should have daily snapshots (1 per day)
   - Should be refreshed via loaders
   - Need to check data loader for market_exposure_daily

4. **Restore algo_signals_evaluated:** It's 46 days dead
   - Phase 7 should populate this
   - Currently abandoned

5. **Expand Freshness Monitor:** Add missing 11 tables
   - earnings_history, growth_metrics, industry_ranking, sector_rotation
   - etc. per user's report

### Root Cause Investigation

- [ ] Phase 4 code review - does it write reconciliation_log?
- [ ] Phase 8 code review - does it write to algo_trades or elsewhere?
- [ ] Loader code - why market_exposure_daily not refreshing?
- [ ] Signal generation - why algo_signals_evaluated abandoned?
- [ ] Phase executor - should validate outputs before marking phase "ok"

### Long-Term Fixes

1. **Output Validation:** Phase executor must verify output tables were populated
2. **Data Contracts:** Formalize what data each phase MUST produce
3. **Comprehensive Monitoring:** Check all 16 critical tables, not just 5
4. **Phase Status Persistence:** Store actual phase results in DB (not just "success/fail")
5. **Silent Failure Detection:** Alert when phases skip but orchestrator says ok

---

## Files to Review

- `algo/orchestrator/phase4_reconciliation.py` - Check if writes to algo_reconciliation_log
- `algo/orchestrator/phase8_entry_execution.py` - Check if writes to algo_trades
- `loaders/load_market_exposure_daily.py` - Why only 2 rows?
- `loaders/load_algo_signals_evaluated.py` - Abandoned since June?
- `algo/orchestrator/phase_executor.py` - Skip data bypass in execute_phase()
- `scripts/monitor_data_staleness.py` - Only monitors 5 tables
- Session 270 audit report - Incomplete scope

---

## The Complete Bypass Chain (ROOT CAUSE)

```
PHASE 4 FAILING (Alpaca 401 auth errors + code bugs)
    ↓ (dependency failed)
PHASE 5 SKIPS (depends on P4) BUT CONTINUES ANYWAY (bypass!)
    ↓ (returns empty/skip data)
PHASE 7 SKIPS (depends on P5)
    ↓ (logs show it generates signals but returns empty to P8)
PHASE 8 SKIPS (depends on P7 & P5)
    ↓ (gets empty qualified_trades, reports "0 trades executed")
ORCHESTRATOR SAYS "SUCCESS" (all phases ran, even if skipped)
```

**Phase 4 Error Log (Last 7 Days):**
- 2026-07-19: "Alpaca closed orders fetch failed with HTTP 401: unauthorized" (53 runs)
- 2026-07-18: "Broker credentials unavailable outside LOCAL_MODE" (144 runs)
- 2026-07-17: "Alpaca closed orders fetch failed with HTTP 401: unauthorized" (62 runs)
- 2026-07-15: "unsupported format string passed to NoneType.__format__" ← BUG
- 2026-07-13: "unsupported operand type(s) for -: 'float' and 'decimal.Decimal'" ← BUG

**The Real Bypass:** Phase 5 is running despite Phase 4 failing, suggesting the dependency check is not being enforced or Phase 5 is catching the error silently.

---

## Critical Bugs Found

### Bug 1: Phase 4 Decimal Type Mismatch (2026-07-13)
```
Error: unsupported operand type(s) for -: 'float' and 'decimal.Decimal'
```
Phase 4 is subtracting a Decimal from a float somewhere. Need to find and fix type coercion.

### Bug 2: Phase 4 Format String Error (2026-07-15)
```
Error: unsupported format string passed to NoneType.__format__
```
Phase 4 is trying to format None as a number. Need to add None checks.

### Bug 3: Alpaca Credentials Intermittently Missing
Orchestrator can't authenticate with Alpaca 401 errors most of the time. This is a configuration/secrets management issue.

### Bug 4: Dependency Check Not Enforced
Phase 5 is running despite Phase 4 failing. Either:
- Dependency check is being bypassed
- Phase 5 is catching exceptions silently
- Phase executor is not properly halting downstream phases

---

## Next Steps (Priority Order)

### CRITICAL (System broken, halt trading immediately)
1. **FIX Phase 4 BUGS:**
   - [ ] Find and fix Decimal/float mismatch (line with `- ` operator on mixed types)
   - [ ] Find and fix NoneType format string error
   - [ ] Add explicit None checks before formatting

2. **FIX Alpaca credentials:**
   - [ ] Verify APCA_API_KEY_ID and APCA_API_SECRET_KEY are set
   - [ ] Check AWS Secrets Manager for credentials on Lambda
   - [ ] Test local auth with: `source scripts/setup_local_alpaca_credentials.sh`

3. **ENFORCE dependency checks:**
   - [ ] Verify phase_executor is correctly halting downstream phases when P4 fails
   - [ ] Check if Phase 5 is catching exceptions that should propagate
   - [ ] Verify Phase 7 & 8 skip data is being treated as halted, not success

### HIGH (Data integrity restored)
4. **Fix Phase 5 dependency bypass:**
   - [ ] Review phase_executor._check_dependencies() for loopholes
   - [ ] Ensure Phase 5 waits for P4 success, doesn't run on P4 error

5. **Populate missing output tables:**
   - [ ] Fix Phase 4 to write algo_reconciliation_log
   - [ ] Fix Phase 8 to write algo_trades (currently empty)
   - [ ] Verify Phase 3 to write algo_positions (currently empty)

6. **Restore algo_signals_evaluated:**
   - [ ] Phase 7 should update this table (currently 46 days stale)

### MEDIUM (Observability & monitoring)
7. **Expand staleness monitor:**
   - [ ] Add the 11 missing tables to monitor_data_staleness.py
   - [ ] Add phase status logging to database
   - [ ] Create alerts for phases that return skip/empty data

8. **Update memory:**
   - [ ] Mark previous "9/9 phases passing" claim as FALSE
   - [ ] Document the actual system state
   - [ ] Create runbook for debugging similar issues

---

**Session 271 Audit Status:** 🔴 CRITICAL - Phase 4 failing causes entire trading pipeline to skip
