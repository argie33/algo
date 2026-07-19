# Data Loading Flag System - Root Cause Analysis

## The Problem: "Flags In Loading Always Causing Troubles"

The data loading system has **5 independent, poorly-integrated flag systems** that create cascading failures and silent data issues:

### Flag System #1: `data_loader_status.status` (String Enum)
**Used by:** Orchestrator Phase 1 to determine if loaders are stale  
**Current issue:** Status values are INCONSISTENT across loaders

```python
# load_market_exposure_daily.py
UPDATE data_loader_status SET status = %s WHERE table_name = %s
# status values: "running" | "completed" | "failed"

# load_prices.py  
INSERT INTO data_loader_status (status) VALUES (...)
# status values: "running" | "complete" | "error" 

# load_quality_growth_metrics.py
UPDATE data_loader_status SET status = %s WHERE table_name = %s
# status values: unclear/inconsistent
```

**Root cause:** No centralized enum or validation for status values  
**Result:** Phase 1 and loader health check query this status column but can't reliably parse results

---

### Flag System #2: `data_loader_status.completion_pct` (Nullable Float)
**Used by:** Orchestrator to detect hung/incomplete loaders  
**Current issue:** Can be NULL when query fails, but code doesn't distinguish between:
- NULL = "database error, can't report progress"  
- NULL = "loader never ran"  
- NULL = "loader ran but crashed before reporting"

```python
# orchestrator.py line 658
if completion_pct is None:
    is_complete = False
    logger.error(f"[LOADER HEALTH] {table_name} completion_pct is NULL")
# Treats database errors same as "loader didn't complete"
```

**Root cause:** No explicit "loader started" vs "loader failed to initialize" distinction  
**Result:** Can't tell if loader is hung, never started, or encountered DB connectivity issues

---

### Flag System #3: `data_unavailable` Markers (Dict Field)
**Used by:** Individual loaders to signal "data is unavailable" (optional data case)  
**Current issue:** Not being set correctly in failure cases

```python
# utils/loaders/unavailable_markers.py has 3 marker types:
marker_loader_failed()        # "loader_failed:..." reason
marker_not_applicable()       # "not_applicable:..." reason  
marker_temporary_unavailable()  # "unavailable_temporary:..." reason
```

**Problem:** 
- Loaders often return `None` or `[]` instead of using markers
- Markers have 3 subtypes but orchestrator doesn't always respect them
- Session 193 showed ValueMetrics silently failing, never returning data_unavailable

**Root cause:** No required schema validation - loaders CAN return invalid responses  
**Result:** Dashboard can't distinguish between "loader failed" vs "data genuinely not available"

---

### Flag System #4: DynamoDB Halt Flag (`orchestrator_halt`)
**Used by:** Phase 1 to signal "data is stale, don't trade"  
**Current issue:** 

```python
# halt_flag_manager.py lines 69-122
# Multiple paths can set/check this flag:
# 1. Phase 1 sets it when prices are stale
# 2. Orchestrator checks it at every phase
# 3. Auto-clears at market open next day
```

**Problem:**
- Halt flag persists through entire trading day (9:30 AM - 4:00 PM)
- If Phase 1 (2 AM) detects stale prices, flag blocks Phase 5-8 (9:30 AM+)
- But stale data might have refreshed by 9:30 AM - flag should be context-aware

**Root cause:** Halt flag is "fire and forget" - doesn't re-evaluate freshness  
**Result:** Trading can stay halted for hours due to overnight stale data that's now fresh

---

### Flag System #5: Phase Skip Flags (`skip_phases`, `always_run`, `skip_if_halted`)
**Used by:** Phase executor to determine which phases to run  
**Current issue:** Multiple conflicting skip conditions

```python
# phase_executor.py lines 301-329
# A phase can be skipped by:
if phase_num in self.skip_phases:  # Line 303
    continue
if halted and not phase_def.always_run:  # Line 320
    continue
if not phase.always_run and phase.skip_if_halted and self.halt_check_fn():  # Line 209
    continue
```

**Problem:**
- 3 different skip mechanisms, any can bypass others
- If halt flag is stale, phase executor might skip correctly-runnable phases
- Session 192: CheckConcurrency was blocking even non-overlapping runs

**Root cause:** No unified "should this phase run?" decision point  
**Result:** Phases silently skip when they should run, or run when they should skip

---

## Historical Cascade of Flag Failures

| Session | Issue | Root Cause | Impact |
|---------|-------|-----------|--------|
| 192 | Concurrency checks blocking ALL pipelines | Multiple status flags checked too early | 48h data freeze |
| 193 | ValueMetrics silent failure | Tasks OOM, never set completion_pct=0 | 78.5% coverage, 1015 stocks missing |
| 194 | Still waiting for pipeline to fix Session 193 | ECS resources increased but flag system unchanged | Data still at risk |

**Pattern:** Flag system broke in different ways each time because:
1. Flags weren't centrally managed
2. Silent failures weren't caught (no validation)
3. Stale flag values weren't cleared correctly
4. Different loaders interpreted status differently

---

## The Integration Problem

```
Loader A starts           Loader B crashes         Orchestrator checks status
    ↓                          ↓                              ↓
SET status="running"    (never sets status)        SELECT status FROM ...
SET completion_pct=0    ↓                          ↓
                        ??? (NULL or stale?)       "Does loader_status.status='running'?"
                                                   ??? (unclear if hung, errored, or DB issue)
```

Each flag system works in isolation:
- Loader writes to `data_loader_status`
- Orchestrator reads `data_loader_status` + checks `halt_flag`
- Phase executor checks `skip_if_halted` flag
- Dashboard reads all of the above

But **they don't validate each other**. A loader can crash (completion_pct=0) while status="running", and orchestrator treats it as "still loading" instead of "failed".

---

## Why This Happens

1. **No single source of truth for loader state:** Should be one table, one schema, one update pattern
2. **No schema validation:** Loaders can set status="random_string" and nothing catches it  
3. **Silent failures masked by flags:** ValueMetrics didn't log failures, just left status="running"
4. **Stale halt flag:** Phase 1 (2 AM) sets halt, Phase 5 (9:30 AM+) still respects it even though data is fresh
5. **Three skip mechanisms in executor:** each can override others unpredictably

---

## Solution Strategy (Not Yet Implemented)

### Quick Fixes (1-2 hours)
1. ✅ Centralize `data_loader_status.status` enum (Session 194 did this partially for ValueMetrics)
2. Validate all status updates against known set: `{"starting", "running", "completed", "failed", "error"}`
3. Add `started_at` timestamp to distinguish "never started" from "started but crashed"

### Medium Fixes (3-4 hours)
4. Add explicit error_message logging to `data_loader_status`
5. Make halt flag context-aware: re-check data freshness before blocking phases
6. Unify phase skip logic into single `should_phase_run()` function

### Long-term Fixes (1-2 days)
7. Create loader result schema (required: status, completion_pct, error_message, timestamps)
8. Enforce schema validation at orchestrator level before continuing
9. Add metric: "flag consistency score" to detect divergence early

---

## Next Steps

1. **Identify which specific flag is causing today's issue:**
   - `data_loader_status` status inconsistency?
   - Stale halt flag from overnight?
   - Phase skip logic preventing correct phases?

2. **Search for silent failures:**
   ```sql
   -- Find loaders with status="running" for >2 hours
   SELECT * FROM data_loader_status 
   WHERE status = 'running' 
   AND last_updated < NOW() - INTERVAL '2 hours'
   ```

3. **Check for divergent status values:**
   ```sql
   SELECT table_name, COUNT(DISTINCT status) as unique_statuses, 
          STRING_AGG(DISTINCT status, ',') as all_values
   FROM data_loader_status 
   GROUP BY table_name 
   HAVING COUNT(DISTINCT status) > 1
   ```

---

## Key Insight

**The problem isn't any single flag—it's that we have 5 flag systems with no arbiter.**

When Phase 1 sets halt_flag, nobody questions it until market open.  
When ValueMetrics crashes, data_loader_status stays "running" forever.  
When phase_executor skips a phase due to halt_flag, it doesn't re-validate that the flag is still current.

We need:
- **One loader state schema** (not 5 independent flags)
- **Validation at each state transition** (not "set it once and hope")
- **Context-aware flag evaluation** (not "halt once, blocks everything")
- **Explicit error logging** (not "NULL means error was set somewhere")
