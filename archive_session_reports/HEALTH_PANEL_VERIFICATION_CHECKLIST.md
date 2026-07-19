# Health Panel Audit - Verification Checklist
**Purpose:** Systematically validate key assumptions before implementation  
**Status:** To Be Completed

---

## VERIFICATION #1: buy_sell_daily Pipeline Criticality

### Question
Is `buy_sell_daily` actually required by Phase 7, or does Phase 5 generate signals on-the-fly?

### Why This Matters
- **If CRITICAL:** Phase 7 halts without it → health panel should monitor it
- **If LEGACY:** Phase 5 generates signals independently → can deprecate monitoring
- **Current Contradiction:** Marked critical in freshness_config but excluded from health endpoint

### Investigation Steps

#### Step 1a: Check Phase 7 Implementation
```bash
# Look at phase7_signal_generation.py
# Find: Does it query buy_sell_daily? 
# Look for: cur.execute(...buy_sell_daily...)
# Check: Is there a fallback if buy_sell_daily is empty?
```

**What to look for:**
- Line where buy_sell_daily is queried (if at all)
- Error message if buy_sell_daily is empty
- Whether Phase 5 output is used as alternative

**File:** `algo/orchestrator/phase7_signal_generation.py`

**Your findings:**
- [ ] buy_sell_daily IS queried (line: ___)
- [ ] buy_sell_daily is NOT queried at all
- [ ] Fallback exists (Phase 5 on-the-fly generation)
- [ ] No fallback (halts if buy_sell_daily missing)

---

#### Step 1b: Check Phase 5 Implementation
```bash
# Look at phase5_exposure_policy.py
# Find: What does it output?
# Check: Are signals generated here or just filtering applied?
```

**What to look for:**
- Whether Phase 5 generates/computes signals
- Or whether it just validates Phase 7 signals
- Return structure (what does it pass to Phase 6/7)

**File:** `algo/orchestrator/phase5_exposure_policy.py`

**Your findings:**
- [ ] Phase 5 generates signals independently
- [ ] Phase 5 only filters/ranks existing signals
- [ ] Phase 5 output goes to Phase 6, not Phase 7

---

#### Step 1c: Check Freshness Config Definition
```bash
# Look for FRESHNESS_RULES or freshness_config
# Find: buy_sell_daily entry
# Check: What are the settings?
```

**What to look for:**
- critical_loader: true/false
- max_age_days: value
- is it used by Phase 1 or just monitoring?

**File:** Likely in `utils/validation.py` or similar

**Your findings:**
- [ ] buy_sell_daily marked critical_loader=True
- [ ] buy_sell_daily marked critical_loader=False
- [ ] max_age_days value: ___

---

#### Step 1d: Check Health Monitor Config
```bash
# Look for health monitoring configuration
# Find: Which loaders are monitored?
# Check: buy_sell_daily in list?
```

**File:** Likely in `loaders/health_monitor.py`

**Your findings:**
- [ ] buy_sell_daily in critical_loaders list
- [ ] buy_sell_daily in non_critical_loaders list
- [ ] buy_sell_daily not in any monitoring list

---

### DECISION POINT: buy_sell_daily Status
Based on above findings, buy_sell_daily is:

- [ ] **CRITICAL:** Phase 7 queries it, no fallback, halts if missing
  - *Action:* Add to data-status endpoint
  
- [ ] **LEGACY:** Phase 5 generates signals on-the-fly, buy_sell_daily unused
  - *Action:* Remove from freshness_config, keep health_monitor for archival
  
- [ ] **OPTIONAL:** Phase 7 prefers it but has fallback to Phase 5
  - *Action:* Monitor but don't halt, show in health panel as "stale but non-critical"

---

## VERIFICATION #2: Phase Result Schema

### Question
What are the exact field names in orchestrator_execution_log.phase_results[6].data and phase_results[7].data?

### Why This Matters
Our code to extract execution counts depends on knowing exact field names. Wrong names = silent failures.

### Investigation Steps

#### Step 2a: Find Recent Orchestrator Run
```bash
# In database, find latest run
SELECT run_id, run_date, started_at, phase_results 
FROM orchestrator_execution_log 
WHERE run_date = CURRENT_DATE 
ORDER BY started_at DESC LIMIT 1;

# Copy the phase_results JSON value
```

**Your findings:**
- [ ] Found recent run (run_id: _________________)
- [ ] No recent runs found

---

#### Step 2b: Extract Phase 6 (Exit Execution) Fields
Copy the phase_results array and find index 5 (Phase 6):

```json
// phase_results[5] should look like:
{
  "name": "Exit Execution",
  "phase": 6,
  "status": "success",
  "started_at": "...",
  "completed_at": "...",
  "data": {
    // ← What fields are here?
  }
}
```

**What to look for:**
- [ ] exits_executed: number
- [ ] exits_failed: number
- [ ] exits_skipped: number
- [ ] Other fields: _____________________

**Your findings (Phase 6 data fields):**
```
{
  // Paste actual fields from database
}
```

---

#### Step 2c: Extract Phase 8 (Entry Execution) Fields
Find index 7 (Phase 8):

```json
// phase_results[7] should look like:
{
  "name": "Entry Execution",
  "phase": 8,
  "status": "success",
  "data": {
    // ← What fields are here?
  }
}
```

**What to look for:**
- [ ] entries_executed: number
- [ ] entries_failed: number
- [ ] entries_skipped: number
- [ ] Other fields: _____________________

**Your findings (Phase 8 data fields):**
```
{
  // Paste actual fields from database
}
```

---

#### Step 2d: Check for Consistency Across Runs
```bash
# Query 3 recent runs to see if schema is consistent
SELECT 
  run_id,
  phase_results -> 5 ->> 'data' as phase6_data,
  phase_results -> 7 ->> 'data' as phase8_data
FROM orchestrator_execution_log 
WHERE run_date >= CURRENT_DATE - INTERVAL '7 days'
ORDER BY started_at DESC LIMIT 5;
```

**Your findings:**
- [ ] Schema is consistent across all runs
- [ ] Schema varies (note variations):

---

### DECISION POINT: Phase Result Fields
Based on above findings:

- [ ] Fields are consistent ✅
  - *Action:* Use exact field names in API query
  
- [ ] Schema varies ⚠️
  - *Action:* Add defensive null checks in API code

- [ ] Phase 6 or Phase 8 data is missing in some runs
  - *Action:* Handle gracefully (return null, not error)

---

## VERIFICATION #3: Circuit Breaker Timing & Persistence

### Question
Does Phase 2 write to DB, or only Phase 9? What if Phase 9 fails?

### Why This Matters
If only Phase 9 writes circuit_breaker_status, and Phase 9 fails, we're left with stale breaker data. Health panel needs to detect this.

### Investigation Steps

#### Step 3a: Check Phase 2 Code
```bash
# Look at phase2_circuit_breakers.py
# Find: Does it call cur.execute() with INSERT/UPDATE?
# Search for: circuit_breaker_status table writes
```

**File:** `algo/orchestrator/phase2_circuit_breakers.py`

**Your findings:**
- [ ] Phase 2 writes to circuit_breaker_status table
- [ ] Phase 2 only publishes CloudWatch metrics (no DB write)
- [ ] Phase 2 returns data in PhaseResult only

---

#### Step 3b: Check Phase 9 Code
```bash
# Look at phase9_reconciliation.py
# Find: circuit_breaker_status write
# Check: When is this write attempted?
```

**File:** `algo/orchestrator/phase9_reconciliation.py`

**Your findings:**
- [ ] Phase 9 writes circuit_breaker_status unconditionally
- [ ] Phase 9 only writes if earlier phases succeeded
- [ ] Phase 9 has error handling for this write

---

#### Step 3c: Query circuit_breaker_status Staleness
```bash
# Check: How fresh is circuit_breaker_status?
SELECT 
  check_date,
  CURRENT_TIMESTAMP - check_date::timestamp as age,
  *
FROM circuit_breaker_status 
ORDER BY check_date DESC LIMIT 1;

# Also check: Is there a row per day or per run?
SELECT COUNT(*), check_date 
FROM circuit_breaker_status 
WHERE check_date >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY check_date
ORDER BY check_date DESC;
```

**Your findings:**
- [ ] One row per day (check_date = date)
- [ ] One row per orchestrator run
- [ ] Stale data detected (last update: ___ days ago)

---

#### Step 3d: Check Error Handling
```bash
# Look at Phase 9 code
# Find: What happens if circuit_breaker_status write fails?
# Check: Does it halt the run or log+continue?
```

**Your findings:**
- [ ] Failure halts entire Phase 9
- [ ] Failure is logged but Phase 9 continues
- [ ] No explicit error handling (implicit fail)

---

### DECISION POINT: Circuit Breaker Persistence
Based on above findings:

- [ ] **Phase 9 Only:** Only Phase 9 writes to DB
  - *Action:* Add staleness check in health panel
  - *Action:* If circuit_breaker_status is > 24h old, flag as "data stale"

- [ ] **Phase 2 + Phase 9:** Both write to DB
  - *Action:* Use Phase 2 write as primary, Phase 9 as backup

- [ ] **CloudWatch Only:** No DB write at all
  - *Action:* Query CloudWatch metrics directly for health panel

---

## VERIFICATION #4: Reconciliation Logging Completeness

### Question
Where is reconciliation data actually logged? Can we reconstruct reconciliation status from available tables?

### Why This Matters
We recommended creating `algo_reconciliation_log`, but data may already exist. Don't create new table if we can query existing ones.

### Investigation Steps

#### Step 4a: Check Phase 4 Implementation
```bash
# Look at phase4_reconciliation.py
# Find: What does Phase 4 log/return?
# Search for: algo_audit_log writes or reconciliation data
```

**File:** `algo/orchestrator/phase4_reconciliation.py`

**Your findings:**
- [ ] Phase 4 writes to algo_audit_log (action_type = 'reconciliation')
- [ ] Phase 4 returns reconciliation result in PhaseResult only
- [ ] Phase 4 updates algo_positions with sync status

---

#### Step 4b: Check Phase 9 Logging
```bash
# Look at phase9_reconciliation.py
# Find: What reconciliation data does Phase 9 log?
# Search for: circuit_breaker_status, algo_audit_log writes
```

**File:** `algo/orchestrator/phase9_reconciliation.py`

**Your findings:**
- [ ] Phase 9 logs reconciliation summary to algo_audit_log
- [ ] Phase 9 writes reconciliation_status to separate table
- [ ] Phase 9 only writes portfolio snapshot (no reconciliation details)

---

#### Step 4c: Query Existing Reconciliation Data
```bash
# Check algo_audit_log for reconciliation entries
SELECT * FROM algo_audit_log 
WHERE action_type = 'reconciliation' 
ORDER BY created_at DESC LIMIT 5;

# Check: Do these have reconciliation details?
# Look for: match_percentage, sync_status, discrepancies, etc.
```

**Your findings:**
- [ ] Reconciliation data is detailed in algo_audit_log
- [ ] algo_audit_log only has action_type, status (no details)
- [ ] No reconciliation entries found

---

#### Step 4d: Check orchestrator_execution_log Phase 4 Results
```bash
# Query phase_results[3] (Phase 4)
SELECT 
  run_id,
  run_date,
  phase_results -> 3 ->> 'data' as phase4_reconciliation_data
FROM orchestrator_execution_log 
WHERE run_date >= CURRENT_DATE - INTERVAL '7 days'
ORDER BY started_at DESC LIMIT 5;
```

**Your findings:**
- [ ] Phase 4 data includes detailed reconciliation metrics
- [ ] Phase 4 data includes only status (ok/failed)
- [ ] Phase 4 data is empty or not present

---

#### Step 4e: Understand What Reconciliation Means
```bash
# Based on Phase 4 code, what is being reconciled?
# Check: algo_positions vs Broker API
# Check: algo_portfolio_snapshots vs broker account value
```

**Your findings:**
- Reconciliation validates: ___________________
- Reconciliation compares: ___________ vs ___________
- Reconciliation result fields: ___________________

---

### DECISION POINT: Reconciliation Data Availability
Based on above findings:

- [ ] **Data is Complete:** Full reconciliation details available
  - *Action:* Query from orchestrator_execution_log or algo_audit_log
  - *Action:* No new table needed

- [ ] **Data is Partial:** Some fields available, need consolidation
  - *Action:* Either create consolidated table OR leave as-is
  - *Effort:* ~4 hours to create table, ~2 hours to query existing

- [ ] **Data is Missing:** No reconciliation data logged anywhere
  - *Action:* Add Phase 4 logging to algo_audit_log
  - *Effort:* ~6 hours to implement + test

---

## VERIFICATION #5: Exposure State Tracking

### Question
Where is exposure state (risk tier, entry slots available) logged?

### Why This Matters
For health panel to show "Risk Tier 2, Slots 1/3 available", we need to know where this state comes from.

### Investigation Steps

#### Step 5a: Check Phase 5 Output
```bash
# Look at phase5_exposure_policy.py
# Find: What does it return?
# Search for: exposure constraints, risk tier, slots available
```

**File:** `algo/orchestrator/phase5_exposure_policy.py`

**Your findings:**
- [ ] Phase 5 returns exposure constraints with tier + slots
- [ ] Phase 5 only returns halt_flag (tier/slots not in result)
- [ ] Unclear what Phase 5 returns

---

#### Step 5b: Check market_exposure_daily Table
```bash
# Query latest market_exposure_daily
SELECT * FROM market_exposure_daily 
ORDER BY date DESC LIMIT 1;

# What fields exist?
```

**Your findings:**
- Fields in market_exposure_daily: ________________
- Risk tier is stored here: [ ] yes [ ] no
- Entry slots available is stored here: [ ] yes [ ] no

---

#### Step 5c: Check orchestrator_execution_log Phase 5
```bash
# Query Phase 5 results
SELECT 
  run_id,
  phase_results -> 4 ->> 'data' as phase5_exposure_data
FROM orchestrator_execution_log 
WHERE run_date = CURRENT_DATE 
ORDER BY started_at DESC LIMIT 1;
```

**Your findings:**
- Phase 5 data fields: ___________________
- Risk tier field name: ___________________
- Entry slots field name: ___________________

---

### DECISION POINT: Exposure State Storage
Based on above findings:

- [ ] **Stored in DB:** market_exposure_daily or orchestrator_execution_log
  - *Action:* Query for health panel

- [ ] **Not Stored:** Only in memory during Phase 5
  - *Action:* Either persist to DB or leave out of health panel

---

## SUMMARY: Verification Status

### Before You Begin
- [ ] All 5 verifications completed
- [ ] All decision points resolved
- [ ] No conflicts or inconsistencies found

### Ready to Implement When
- ✅ buy_sell_daily status is clear (critical vs legacy)
- ✅ Phase result schema is documented (exact field names)
- ✅ Circuit breaker staleness handling is clear
- ✅ Reconciliation data location is mapped
- ✅ Exposure state persistence is confirmed

---

## Notes Section

Use this space to capture any additional findings or edge cases discovered during verification:

```
Findings & Notes:
- 
-
-
```

---

## Next Steps

Once verification is complete:
1. Update HEALTH_PANEL_AUDIT_REVIEW.md with findings
2. Create implementation design document with exact queries
3. Schedule implementation work
4. Create PR with code changes

**No rush.** Getting this right prevents rework later.

