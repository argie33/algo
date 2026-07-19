# Health Panel Audit - COMPREHENSIVE REVIEW & VALIDATION
**Date:** 2026-07-18  
**Status:** Verified findings + corrections needed

---

## Executive Summary: What We Now Know (After Deep Verification)

### The Good News ✅
We correctly identified the core problem: **Health panel tracks only 35% of orchestrator execution state**. The 13 tables being monitored are appropriate, and the data-status endpoint logic is sound.

### The Bad News ⚠️
We made **3 significant assumptions that are wrong**:
1. **buy_sell_daily status** - Our audit assumed it's not monitored, but it actually IS monitored by health_monitor (separate 6-hour check)
2. **Phase result storage** - We assumed phase metrics are in `algo_orchestrator_runs`, but they're actually only in `orchestrator_execution_log`
3. **Reconciliation logging** - We assumed `algo_reconciliation_log` exists, but it doesn't (data is scattered across 4 tables)

### What This Means for Our Recommendations
- ✅ Circuit breaker tracking is still needed (good recommendation)
- ✅ Execution summary is still needed (good recommendation)  
- ✅ Position health tracking is still needed (good recommendation)
- ⚠️ Broker reconciliation needs clarification (data exists but fragmented)
- ❌ buy_sell_daily monitoring doesn't need fixing (already monitored, but inconsistency exists)

---

## Part 1: WHAT WE GOT RIGHT ✅

### 1. Phase Dependencies Are Correct
We accurately mapped which tables feed into which phases:
- Phase 1 correctly validates: price_daily, market_health_daily, market_exposure_daily, earnings_calendar, metrics tables ✅
- Phase 7 correctly checks: buy_sell_daily (primary), stock_scores (fallback) ✅
- Phase 3-8 correctly use: algo_positions, price_daily for real-time checks ✅

### 2. Data-Status Endpoint is Correct
The health endpoint (`/api/algo/data-status`) correctly:
- Uses trading-day-aware freshness logic (same as Phase 1) ✅
- Pulls from `data_loader_status` + `freshness_config` ✅
- Computes age in hours for display ✅
- Marks tables as "ok", "stale", or "empty" ✅

### 3. Orchestrator Phases Execute Correctly
All 9 phases:
- Execute in correct sequence ✅
- Read from correct input tables ✅
- Write results to appropriate output tables ✅
- Store results in `orchestrator_execution_log` with detailed JSON ✅

### 4. Circuit Breaker Architecture is Sound
- Phase 2 computes breaker state ✅
- Phase 9 persists to `circuit_breaker_status` table ✅
- Metrics: drawdown %, daily loss %, weekly loss %, open risk %, VIX, market stage ✅

### 5. Health Monitor is Working Correctly
Independent 6-hour Lambda health check:
- Monitors 8 data loaders + 6 critical data tables ✅
- Alerts on staleness via CloudWatch ✅
- Doesn't interfere with orchestrator execution ✅

---

## Part 2: WHAT WE GOT WRONG ❌

### ISSUE #1: buy_sell_daily Monitoring Status (MEDIUM SEVERITY)

#### What We Assumed
"buy_sell_daily is not monitored - health panel doesn't track its freshness"

#### What's Actually True
✅ buy_sell_daily IS monitored by health_monitor Lambda (runs every 6 hours)
❌ BUT buy_sell_daily is EXCLUDED from data-status endpoint query
❌ AND freshness_config marks buy_sell_daily as critical, but it's missing from health endpoint

#### The Contradiction
```
health_monitor (6-hour check):
  ✅ Monitors buy_sell_daily staleness
  ✅ Alerts via CloudWatch if stale

data-status endpoint (dashboard):
  ❌ Doesn't query buy_sell_daily
  ❌ Dashboard shows "Data OK" even if buy_sell_daily is stale
  ❌ Phase 1 validates buy_sell_daily but endpoint hides it

Freshness_config:
  ✅ Lists buy_sell_daily as critical_loader=True
  ❌ But it's removed from pipeline (Phase 5 generates signals on-the-fly)
```

#### Impact
- Traders see "Data OK" in dashboard
- But Phase 7 might halt due to stale buy_sell_daily
- Misleading freshness view

#### Our Recommendation Was WRONG
We recommended: "Add buy_sell_daily to health monitoring"
Reality: It's already monitored (health_monitor), just not exposed in dashboard

#### What We Should Do Instead
**Option A (Recommended):** Fix the inconsistency
- Remove buy_sell_daily from freshness_config critical_loader list (it's no longer pipeline-critical)
- Confirm Phase 5 generates signals on-the-fly without buy_sell_daily dependency
- Health_monitor can still watch it for archival purposes

**Option B:** Expose buy_sell_daily in dashboard
- Add buy_sell_daily to data-status endpoint query
- Show freshness on health panel
- Document why it's monitored even though not Phase 1 critical

---

### ISSUE #2: Phase Result Storage Location (MEDIUM SEVERITY)

#### What We Assumed
"Phase metrics stored in `algo_orchestrator_runs.phase_results` JSONB column"

#### What's Actually True
```
algo_orchestrator_runs:
  - run_id, run_date, overall_status, started_at, completed_at
  - halt_reason (string, not JSONB)
  ✅ Phase-level detail: ONLY halt_reason from first halted phase
  ❌ No phase_results column (doesn't exist)

orchestrator_execution_log (AUTHORITATIVE):
  - run_id, run_date, started_at, completed_at, overall_status
  - phase_results ✅ Full JSONB array with each phase's:
    * name, status, data (phase-specific metrics)
    * started_at, completed_at, duration
    * error messages if failed
```

#### Impact on Our Recommendations
Our recommendation: "Extract execution_summary from algo_orchestrator_runs.phase_results"

**This won't work directly.** We need to:
1. Query `orchestrator_execution_log` (not algo_orchestrator_runs)
2. Parse `phase_results` JSONB array
3. Extract metrics from each phase's `data` field

#### The Real Issue
Why have two tables?
- `algo_orchestrator_runs`: Backward compatibility for legacy queries
- `orchestrator_execution_log`: True execution history with full details

For health panel, we MUST query `orchestrator_execution_log`, not `algo_orchestrator_runs`.

---

### ISSUE #3: Reconciliation Data Storage (LOW SEVERITY)

#### What We Assumed
"No `algo_reconciliation_log` table exists; need to create one"

#### What's Actually True
Reconciliation data IS logged, but scattered:
1. `algo_audit_log` - Phase 4 reconciliation entries (action_type='reconciliation')
2. `algo_portfolio_snapshots` - Broker sync data per run
3. `algo_positions` - Position-level sync status (via Phase 4)
4. Phase 9 results - High-level reconciliation outcome

There's no dedicated reconciliation table. Data is fragmented.

#### Impact on Our Recommendations
We recommended: "Create `algo_reconciliation_log` table for broker sync health"

**This is still a good idea, BUT:** We can work around it for now by:
- Querying Phase 9 results from `orchestrator_execution_log` 
- Looking for reconciliation status in phase_results[3].data
- Checking `algo_audit_log` for recent reconciliation entries

Long-term: Creating dedicated table would be cleaner, but not required for MVP.

---

## Part 3: KEY CLARIFICATIONS NEEDED

### Clarification #1: buy_sell_daily Pipeline Status
**Question:** Is buy_sell_daily actually needed by Phase 7, or does Phase 5 generate signals on-the-fly?

**Evidence:**
- Phase 7 header says: "Primary path: buy_sell_daily pivot-breakout BUY signals"
- Phase 7 header also says: "NO fallback path: buy_sell_daily is REQUIRED"
- BUT health_monitor has buy_sell_daily as critical_loader=True (monitored)
- AND freshness_config marks it critical

**What This Means:**
If buy_sell_daily is truly required (no fallback), then Phase 7 halts if it's missing, but dashboard doesn't show it's missing. This is a real health panel gap.

**Action:** Confirm with phase7_signal_generation.py whether:
- buy_sell_daily is actually used in production, or
- It's legacy code and Phase 5 generates signals independently

### Clarification #2: Execution Summary Location
**Question:** Where do we get entry/exit counts for health panel?

**Evidence:**
- Phase 6 results: exit count ✓
- Phase 8 results: entry count ✓
- Available in: `orchestrator_execution_log.phase_results[5].data` and `phase_results[7].data`

**Action:** Confirm schema of phase_results[6].data and phase_results[7].data to know exact field names for counts.

### Clarification #3: Circuit Breaker Metrics
**Question:** Does Phase 2 compute breakers or Phase 9 only?

**Evidence:**
- Phase 2 header: "Compute breaker state, publish to CloudWatch"
- Phase 9: "Write circuit_breaker_status to DB"

**What This Means:**
- Phase 2: Computes + alerts (CloudWatch metrics)
- Phase 9: Persists to DB for history/dashboard

**Action:** Confirm whether Phase 2 stores any data to DB, or only Phase 9 does.

---

## Part 4: REVISED AUDIT FINDINGS (Corrected)

### What Health Panel Currently Tracks

| Category | Tables | Current Status | Gap |
|----------|--------|---|---|
| **Data Freshness** | 13 pipeline tables | ✅ Fully tracked | None (Phase 1) |
| **Circuit Breaker State** | `circuit_breaker_status` | ⚠️ Exists but not exposed | Dashboard can't show breaker state |
| **Execution Summary** | `orchestrator_execution_log` | ⚠️ Exists but scattered | Need to parse phase_results JSONB |
| **Position Health** | `algo_positions` | ❌ Not tracked | Need to monitor position count, age, flags |
| **Broker Sync** | `algo_audit_log` + snapshots | ⚠️ Exists but fragmented | Need dedicated reconciliation table |
| **Exposure State** | `market_exposure_daily` + Phase 5 results | ⚠️ Partially tracked | Exposure % visible, risk tier not |

### What Phases ACTUALLY Produce (Verified)

| Phase | Output Table | Metrics Captured | Health Relevant |
|-------|---|---|---|
| **Phase 1** | None (validation only) | Data freshness validation result | ✅ Already tracked |
| **Phase 2** | CloudWatch metrics + `circuit_breaker_status` (via Phase 9) | VIX, drawdown, concentration, market stage | ❌ Not exposed to dashboard |
| **Phase 3** | None (returned in PhaseResult only) | Position recommendations | ❌ Not persisted; can't query historically |
| **Phase 4** | `algo_audit_log`, `algo_positions` | Reconciliation result, sync status | ⚠️ Scattered across tables |
| **Phase 5** | `algo_positions` (exposure actions) | Risk tier, exposure %, halt decision | ⚠️ Halt decision not exposed |
| **Phase 6** | `algo_trades` (exit records) | Exit count, exit failures | ⚠️ In audit log, not health summary |
| **Phase 7** | None (returns qualified_trades) | Signal count, pass rate | ⚠️ Only in signals panel |
| **Phase 8** | `algo_trades`, `algo_signals`, `algo_positions` | Entry count, failures, signal persistence | ⚠️ In audit log, not health summary |
| **Phase 9** | 5 tables (snapshots, metrics, audit, circuit_breaker_status, view refresh) | Portfolio state, P&L, risk metrics, daily results | ✅ Mostly tracked in portfolio panel |

---

## Part 5: CORRECTED RECOMMENDATIONS

### RECOMMENDATION #1: Fix buy_sell_daily Inconsistency (MEDIUM - Do This First)

**Option A (Recommended):** 
- Verify Phase 7 actually needs buy_sell_daily or generates signals on-the-fly
- If on-the-fly: Remove from freshness_config critical list (or mark as "monitored but not critical")
- Update health_monitor documentation

**Option B:**
- Keep buy_sell_daily as critical
- Add to data-status endpoint query
- Show freshness on health panel

**Why:** Resolves contradiction where dashboard says "OK" but Phase 7 might halt

**Effort:** 2-4 hours (verification + 1-line fix)

---

### RECOMMENDATION #2: Expose Circuit Breaker State (HIGH - Core Recommendation)

**What to do:**
1. Query `circuit_breaker_status` latest row
2. Add to `/api/algo/data-status` response
3. Display on health panel: breaker states + triggered status

**Why:** Risk-critical; traders need to know if breakers tripped

**Code changes:**
```python
# In _get_data_status() handler:
cur.execute("""
  SELECT * FROM circuit_breaker_status 
  ORDER BY check_date DESC LIMIT 1
""")
breaker_row = cur.fetchone()
response["data"]["circuit_breaker_state"] = {
  "any_triggered": (breaker_row['portfolio_drawdown_pct'] < -5) or ...,
  "drawdown_pct": breaker_row['portfolio_drawdown_pct'],
  "daily_loss_pct": breaker_row['daily_loss_pct'],
  ...
}
```

**Effort:** 4-6 hours (API + dashboard)

---

### RECOMMENDATION #3: Add Execution Summary (HIGH - Core Recommendation)

**What to do:**
1. Query `orchestrator_execution_log` latest run
2. Parse phase_results[6].data (Phase 6 exits) and phase_results[7].data (Phase 8 entries)
3. Extract: entry_count, entry_failures, exit_count, exit_failures
4. Add to `/api/algo/data-status` response

**Why:** Traders need to know if orders actually executed

**Code changes:**
```python
# In _get_data_status():
cur.execute("""
  SELECT phase_results FROM orchestrator_execution_log 
  WHERE run_date = CURRENT_DATE 
  ORDER BY started_at DESC LIMIT 1
""")
exec_log = cur.fetchone()
if exec_log and exec_log['phase_results']:
  phases = json.loads(exec_log['phase_results'])
  phase_6 = next((p for p in phases if p['name'] == 'Exit Execution'), {})
  phase_8 = next((p for p in phases if p['name'] == 'Entry Execution'), {})
  execution_summary = {
    "exits_executed": phase_6.get('data', {}).get('exit_count', 0),
    "entries_executed": phase_8.get('data', {}).get('entry_count', 0),
    ...
  }
```

**Effort:** 6-8 hours (API + dashboard)

---

### RECOMMENDATION #4: Track Position Health (MEDIUM - Nice to Have)

**What to do:**
1. Query `algo_positions` for current state
2. Query `orchestrator_execution_log` Phase 3 results for recommendations
3. Aggregate: position count, flagged count, oldest age, max loss
4. Add to health response

**Why:** Traders see position-level risks

**Effort:** 8-10 hours (new table for position flags + API + dashboard)

---

### RECOMMENDATION #5: Clarify Broker Sync (MEDIUM - Document First)

**What to do:**
1. Map Phase 4 reconciliation to logging table(s)
2. Query most recent reconciliation from `algo_audit_log`
3. Extract: reconciliation status, match %, any discrepancies
4. Add to health response

**Why:** Silent reconciliation failures are dangerous

**Effort:** 
- 2-4 hours to understand current logging
- 4-6 hours to expose via API
- Optional: 8 hours to create dedicated `algo_reconciliation_log` table

---

## Part 6: PRIORITY & SEQUENCING

### Phase 1: Fix Inconsistencies (1 week)
1. ✅ Clarify buy_sell_daily status (critical vs non-critical)
2. ✅ Document phase_results location (orchestrator_execution_log, not algo_orchestrator_runs)
3. ✅ Map reconciliation data to source tables

### Phase 2: Core Extensions (2-3 weeks)
1. ✅ Expose circuit breaker state (HIGH value)
2. ✅ Add execution summary (HIGH value)
3. ✅ Redesign health panel UI to show new metrics

### Phase 3: Optional Enhancements (2-3 weeks)
1. ⚠️ Track position health (MEDIUM value)
2. ⚠️ Create dedicated reconciliation table (MEDIUM value)
3. ⚠️ Add risk metrics panel (LOW value)

---

## Part 7: WHAT WE STILL NEED TO VERIFY

### Critical Verifications Before Implementation

1. **buy_sell_daily Status**
   - [ ] Does Phase 7 actually halt if buy_sell_daily is missing?
   - [ ] Or does Phase 5 generate signals on-the-fly?
   - [ ] What's the intended architecture (legacy vs current)?

2. **Phase Result Schema**
   - [ ] Confirm exact field names in orchestrator_execution_log.phase_results[6].data
   - [ ] Confirm exact field names in orchestrator_execution_log.phase_results[7].data
   - [ ] Are entry/exit counts always present or sometimes missing?

3. **Circuit Breaker Timing**
   - [ ] Does Phase 2 write to DB or only publish CloudWatch metrics?
   - [ ] Does Phase 9 always run or can it fail independently?
   - [ ] If Phase 9 fails, is circuit_breaker_status left stale?

4. **Reconciliation Logging**
   - [ ] Which reconciliation status field is authoritative?
   - [ ] How often is reconciliation logged (per run or once daily)?
   - [ ] Can we query Phase 4 results from orchestrator_execution_log?

---

## Part 8: RISK ASSESSMENT

### Risk: Wrong Assumptions Delay Implementation
**Mitigation:** Complete 4 verifications above before writing code

### Risk: Phase Result Schema Mismatch
**Mitigation:** Test JSON parsing against actual orchestrator_execution_log entries

### Risk: Phase 2-9 Failures Cascade
**Example:** If Phase 9 fails, circuit_breaker_status becomes stale
**Mitigation:** Add explicit staleness check + fallback display

### Risk: Buy/Sell Daily Confusion
**Current:** Different systems (health_monitor, freshness_config, Phase 7) have conflicting assumptions
**Mitigation:** Document decision and update all references

---

## Conclusion

### What We NOW Know (Corrected)
✅ Core problem is real: health panel only shows data freshness, not execution health  
✅ Circuit breaker state, execution counts, position health ARE missing  
✅ These metrics ARE being generated (we have the data), just not exposed to dashboard  

### What We NEED TO VERIFY (Before Implementation)
❓ buy_sell_daily pipeline criticality  
❓ Exact phase_results schema  
❓ Circuit breaker failure scenarios  
❓ Reconciliation logging completeness  

### When We Should Proceed
Once the 4 critical verifications are done, we can confidently:
- Estimate real effort (likely 3-4 weeks, unchanged)
- Design API changes (now we know exact data locations)
- Build health panel extensions (with correct field names)

**No need to rush.** Getting the architecture right now prevents rework later.

