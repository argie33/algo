# CRITICAL FINDINGS - Orchestrator Bypass Patterns & Data Issues

**Date:** 2026-07-19  
**Status:** ❌ ACTIVE - Multiple violations of GOVERNANCE.md "Fail-fast on missing data" principle

---

## 🚨 CRITICAL BUG #1: Weekend Trading Execution

**Severity:** CRITICAL - Violates market trading hours

**Evidence:**
- 79 orchestrator runs on Sunday 2026-07-19 (non-trading day)
- 195 runs on Saturday 2026-07-18 (non-trading day) 
- 3 live trades executed on Sunday with status "open":
  - CTRE: 95 shares @ $42.88
  - EPRT: 120 shares @ $33.33
  - KRC: 86 shares @ $40.25

**Root Cause:** No market calendar enforcement at orchestrator entry point. LOCAL runs execute regardless of trading day status.

**Impact:** Orders sent to Alpaca on weekends, likely buffered for Monday open. Creates confusion about when trading actually occurred.

**Fix Required:** Add is_trading_day() check at orchestrator start; prevent non-trading-day execution.

---

## 🚨 CRITICAL BUG #2: Data Staleness During Trading

**Severity:** CRITICAL - Violates "do not accept stale data" principle

**Evidence:**
- `price_daily`: 2.0 days old (DEAD) - latest data from 2026-07-17
- `technical_data_daily`: 2.0 days old (DEAD)
- `growth_metrics`: 10.1 hours old (CRITICAL) - beyond acceptable SLA
- `quality_metrics`: 10.1 hours old (CRITICAL)
- `value_metrics`: 10.1 hours old (CRITICAL)
- `market_exposure_daily`: 1.0 day old (DEAD)

**Context:** Today is Sunday 2026-07-19 (non-trading day). Expected behavior: use last trading day data (Friday 2026-07-17). But metrics are 10+ hours stale from yesterday, suggesting loaders didn't run at scheduled time.

**Root Cause:** EventBridge Scheduler or manual triggers not executing on schedule. Loaders last ran 2026-07-18 22:29 UTC (yesterday evening).

**Impact:** Orchestrator running with stale market data. Phase 7 signals generated using day-old metrics.

**Fix Required:** Verify EventBridge Scheduler is enabled and running. Check CloudWatch logs for loader failures.

---

## 🚨 CRITICAL BUG #3: Phase 1 Metric Staleness Handling - Confusing Logic

**Severity:** HIGH - Governance violation risk

**File:** `algo/orchestrator/phase1_data_freshness.py:834-868`

**Issue:**
```python
# Line 834: "Instead of HALT on stale metrics, allow DEGRADED mode"
# This COMMENT violates GOVERNANCE.md

# Line 854: Checks if trading day
if MarketCalendar.is_trading_day(run_date_obj):
    # Set degraded_reason → HALT below
    degraded_reason = "Stale metric data - trading halted..."
else:
    # On weekends/holidays: DON'T set degraded_reason → PROCEED
    # This allows trading with stale metrics on weekends
```

**The Problem:**
- Comment says "allow DEGRADED mode" (wrong)
- Code attempts to HALT but logic is unclear
- Weekend exception allows proceeding with stale metrics
- Previous commit e499d1372 INTRODUCED "degraded mode fallback" which violates GOVERNANCE

**Evidence from DB:**
- 17 recent halts with reason: "Stale metric data (older than 1 day) - using available data"
- These show status="halted" (correct) but message implies proceeding (wrong)
- 7 orchestrator runs show overall_status="degraded" (should be zero)

**Impact:** Misleading halt messages. Potential for edge cases where degraded data gets used.

**Fix Required:** 
1. Remove comment about "allowing degraded mode"
2. Clarify when metrics are considered stale
3. Eliminate all "degraded" status - replace with "halted"
4. Add integration tests for stale metric scenarios

---

## 🚨 CRITICAL BUG #4: Empty Phase Result Summaries

**Severity:** HIGH - Prevents error visibility

**Evidence:**
- Phase 1 halts with status="halted" but summary=""
- Makes debugging impossible - don't know WHY phase halted
- Orchestrator tries to use summary for halt_reason, gets empty string

**Root Cause:** phase1_data_freshness returns PhaseResult with error="" instead of actual error message

**Example:**
```
Run: LOCAL-MORNING-20260718-232910-258620
  Phase 1: halted - summary="" ❌ EMPTY!
  Overall halt_reason: "Stale metric data..." (correctly halted but no debug info)
```

**Impact:** Cannot trace failures. Operators can't see root cause.

**Fix Required:** Ensure all phase halts include non-empty summary with specific reason.

---

## 🚨 CRITICAL BUG #5: Metrics Monitoring Still Incomplete (Session 285 Fix Not Applied)

**Severity:** HIGH - Monitoring gap persists

**Previous Claim:** Session 285 fixed "monitoring gap - 86/94 tables never monitored"

**Current Reality:**
- data_loader_status shows:
  - ✅ 8 tables with correct row_count/age_days
  - ❌ 86 tables with NULL values (same as before "fix")

**Tables Affected (Sample):**
- algo_positions, algo_trades, algo_signals (critical algo tables)
- market_exposure_daily (critical market data)
- All growth_metrics, quality_metrics, value_metrics (critical scoring)
- 80+ more unmonitored

**Root Cause:** Session 280 only added dashboard workaround (querying tables directly when NULL). Session 285 claimed fix but it either:
1. Was not properly applied
2. Was reverted
3. Is incomplete

**Impact:** Dashboard showing stale status, no real-time visibility into table freshness.

**Fix Required:** 
1. Audit monitoring implementation in PipelineHealth
2. Verify all 94 tables are queried for row_count and age_days
3. Make data_loader_status the source of truth (not workaround)

---

## 📊 ORCHESTRATOR STATUS SUMMARY

**Last 7 Days (565 runs):**
- success: 539 runs (95%)
- halted: 170 runs (intentional)
- error: 100 runs (18%)
- **degraded: 7 runs (should be 0!)**

**Halt Reasons (Top):**
- 574 runs with NULL halt reason (incomplete logging)
- 23 runs: Phase 7 halted due to stale buy_sell_daily data
- 20 runs: Stock scores only 26.1% complete
- 17 runs: Stale metric data (older than 1 day)
- 15 runs: AWS DynamoDB credential errors
- 12 runs: Alpaca credentials not available

---

## ✅ WHAT WAS SUPPOSEDLY FIXED (Session 285)

Per session_285_comprehensive_findings.md:

✅ Exception-swallowing in phases 2/4/9 (12 issues) - FIXED per 49983dfb6  
✅ Monitoring gap - 86/94 tables (1 issue) - FIXED per db612f036  
✅ buy_sell_daily universe filter bypass (1 issue) - FIXED per 4b8f3372e  
✅ Phase 9 fallback patterns (1 issue) - FIXED per b1cb7cb86

**BUT:** Current data shows some of these issues may NOT be fully fixed or have regressed.

---

## FIXES APPLIED (This Session)

✅ **Market Day Enforcement (Commit 082277485)**
- Added is_trading_day() check in orchestrator preflight checks
- Prevents orchestrator execution on weekends/holidays
- Prevents future weekend trades

## ACTION ITEMS (Priority Order)

### IMMEDIATE (Today)
- [x] Stop weekend orchestrator runs - add market day check at entry point ✅ FIXED
- [ ] Verify EventBridge Scheduler is running morning/EOD pipelines
- [ ] Check CloudWatch logs for loader failures since 2026-07-17
- [ ] Fix AWS credentials for local orchestrator runs (DynamoDB lock access)
- [ ] Refresh stale data manually: `python scripts/run_local_orchestrator.py --morning`

### SHORT-TERM (This Week)
- [ ] Audit phase1_data_freshness.py:834-868 for degraded mode logic
- [ ] Ensure all phase halts include non-empty summary messages
- [ ] Verify data_loader_status monitoring for all 94 tables
- [ ] Remove "allow degraded mode" comment and clarify staleness thresholds
- [ ] Add integration tests for weekend/stale data scenarios

### FOLLOW-UP
- [ ] Review all 7 "degraded" runs - why status is degraded instead of halted
- [ ] Fix NULL halt_reason logs (574 runs) - add explicit error messages
- [ ] Verify Session 285 fixes were actually applied to production
- [ ] Add operational runbook for weekend trading incident response

---

## GOVERNANCE VIOLATIONS CONFIRMED

From GOVERNANCE.md:
> "Fail-fast on missing data. No silent fallbacks."  
> "Finance applications cannot silently fall back to secondary data sources"

**Violations Found:**
1. ✅ Degraded mode allows proceeding with stale metrics (should be fixed but logic unclear)
2. ✅ Weekend trading executes with day-old data (NO MARKET CALENDAR CHECK)
3. ✅ Empty phase summaries hide error details (silent failure symptom)
4. ✅ Monitoring incomplete - 86 tables have no visibility (Session 285 fix not verified)

---

## NEXT STEPS

1. **Immediate:** Run health check and fix stale data
2. **Urgent:** Add market day enforcement to prevent weekend trading
3. **This week:** Clear up Phase 1 metric staleness logic and verify Session 285 fixes

See CLAUDE.md for health check and troubleshooting commands.
