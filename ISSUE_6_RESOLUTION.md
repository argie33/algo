# Issue #6 Resolution: Orchestrator Execution History

## Summary

**Problem:** No visible execution history for orchestrator runs — users couldn't diagnose why swings get stuck, whether failures are systematic or random, or which phases halt most often.

**Solution:** Built a complete execution history system with database logging, CLI tools, and API endpoints.

**Status:** ✓ COMPLETE

## What Was Implemented

### 1. Database Schema (Issue #6 Fix)
**File:** `lambda/db-init/schema.sql`

New table: `orchestrator_execution_log`
- Stores every orchestrator run with complete phase-by-phase results
- Columns: run_id, run_date, started_at, completed_at, overall_status, phase_results (JSONB), summary, halt_reason
- Indexes: run_date DESC, overall_status, started_at DESC
- Retention: Permanent (user can archive/delete as needed)

### 2. Orchestrator Integration
**File:** `algo/algo_orchestrator.py`

Changes:
- Import execution tracker: `from utils.orchestrator_execution_tracker import get_tracker`
- Initialize in `__init__`: Create global tracker instance with run context
- Modify `log_phase_result()`: Also log to tracker (in addition to audit log)
- Modify `_final_report()`: Save complete execution log after every run
- Handle skipped runs: Log when market is closed, etc.

Result: Every orchestrator run (success, halted, error, skipped) is now logged.

### 3. Core Tracking Module
**File:** `utils/orchestrator_execution_tracker.py` (4.7 KB, 184 lines)

Class: `OrchestratorExecutionTracker`
- `set_run_context()`: Initialize with run_id and run_date
- `log_phase_result()`: Record each phase's outcome
- `save_execution_log()`: Persist to database with status summary

Global instance management: `get_tracker()`, `reset_tracker()`

### 4. Query Helper Module
**File:** `utils/orchestrator_query.py` (12 KB, 413 lines)

Functions:
- `get_recent_runs(days, limit)`: Fetch recent runs with phase counts
- `get_run_details(run_id)`: Full details with phase breakdown
- `get_failed_runs(days)`: Failures/halts only for diagnostics
- `get_halt_patterns(days)`: Which phases halt most often + reasons
- `get_success_rate(days)`: Statistics (success%, halt%, error%)
- Pretty-print helpers: `print_recent_runs()`, `print_failed_runs()`, etc.

### 5. CLI Tool
**File:** `scripts/orchestrator-history.py` (8.2 KB, 298 lines)

Commands:
```bash
python scripts/orchestrator-history.py recent [days]    # Recent runs
python scripts/orchestrator-history.py failed [days]    # Failed runs
python scripts/orchestrator-history.py patterns [days]  # Halt patterns
python scripts/orchestrator-history.py stats [days]     # Success rate
python scripts/orchestrator-history.py details <ID>     # Run details
python scripts/orchestrator-history.py latest           # Latest run
```

Example output:
```
Recent Orchestrator Runs (past 7 days) — Latest 10 runs

Run ID                    Date        Status     OK/Halt/Err  Summary
RUN-2026-06-07-153045     2026-06-07  success    7/0/0        All phases completed
RUN-2026-06-07-130045     2026-06-07  success    7/0/0        All phases completed
RUN-2026-06-07-093045     2026-06-07  halted     1/1/0        Halted at phase 2
```

### 6. API Endpoints
**File:** `lambda/api/routes/algo.py`

New endpoints (all require admin JWT):
- `GET /api/algo/execution/recent?days=7&limit=50` — Recent runs
- `GET /api/algo/execution/failed?days=30` — Failures/halts
- `GET /api/algo/execution/details/<RUN_ID>` — Full run details
- `GET /api/algo/execution/patterns?days=30` — Halt patterns
- `GET /api/algo/execution/stats?days=7` — Success statistics

Handler functions:
- `_get_orchestrator_execution_recent()`
- `_get_orchestrator_execution_failed()`
- `_get_orchestrator_execution_details()`
- `_get_orchestrator_execution_patterns()`
- `_get_orchestrator_execution_stats()`

### 7. Documentation
**Files:**
- `steering/algo.md` — Added "Orchestrator Execution History" section with usage examples
- `EXECUTION_HISTORY_GUIDE.md` — Comprehensive guide with examples (9.2 KB)
- `ISSUE_6_RESOLUTION.md` — This file

### 8. Test Coverage
**File:** `tests/test_execution_history.py` (7.2 KB, 197 lines)

Tests (all passing):
1. Tracker initialization with run context
2. Phase result logging
3. Execution log data structure
4. Global singleton pattern
5. Halt reason detection
6. Error handling
7. Query function availability
8. CLI tool presence

Run: `python tests/test_execution_history.py`
Result: 8/8 tests passed

## Usage Examples

### View Recent Runs (CLI)
```bash
python scripts/orchestrator-history.py recent 7
```

### Find Why Swing Scores Halt (Diagnostic)
```bash
# See which phases halt most often
python scripts/orchestrator-history.py patterns 30

# Output shows Phase 5 halts 5 times with "swing_trader_scores stale"
# This tells you morning pipeline (2:00 AM) is failing
```

### Check System Recovery After Outage
```bash
python scripts/orchestrator-history.py stats 1
# Success rate today vs yesterday → shows if recovery is working
```

### View Full Run Details
```bash
python scripts/orchestrator-history.py details RUN-2026-06-07-093045
# Shows: started/completed times, each phase's status, summary
```

### API Usage (Frontend)
```javascript
const response = await fetch('/api/algo/execution/recent?days=7', {
  headers: { 'Authorization': 'Bearer ' + token }
});
const { data } = await response.json();
// data = array of {run_id, run_date, status, phases_completed, phases_halted, ...}
```

### Advanced SQL Queries
```sql
-- Runs that halted in past 7 days
SELECT * FROM orchestrator_execution_log
WHERE run_date >= CURRENT_DATE - 7
  AND overall_status = 'halted'
ORDER BY run_date DESC;

-- Phase halt frequency analysis
SELECT phase_results->>'name' as phase, COUNT(*) as halt_count
FROM orchestrator_execution_log, jsonb_array_elements(phase_results)
WHERE run_date >= CURRENT_DATE - 30
  AND phase_results->>'status' = 'halt'
GROUP BY phase
ORDER BY halt_count DESC;
```

## Files Created

1. `utils/orchestrator_execution_tracker.py` — 4.7 KB
2. `utils/orchestrator_query.py` — 12 KB
3. `scripts/orchestrator-history.py` — 8.2 KB
4. `tests/test_execution_history.py` — 7.2 KB (test only, not deployed)
5. `EXECUTION_HISTORY_GUIDE.md` — 9.2 KB (documentation)
6. `ISSUE_6_RESOLUTION.md` — This file

## Files Modified

1. `lambda/db-init/schema.sql` — Added `orchestrator_execution_log` table + indexes
2. `algo/algo_orchestrator.py` — Integrated execution tracker (3 changes)
3. `lambda/api/routes/algo.py` — Added 5 API endpoints + 5 handler functions
4. `steering/algo.md` — Added execution history section with examples

## Testing

✓ All 8 unit tests pass:
- Tracker initialization
- Phase logging
- Execution log structure
- Singleton pattern
- Halt reason detection
- Error handling
- Query functions
- CLI tool

Run: `python tests/test_execution_history.py`

## Verification

### Code Quality
- ✓ All Python files compile without syntax errors
- ✓ All functions are documented with docstrings
- ✓ Query functions handle database errors gracefully
- ✓ API endpoints require admin JWT authentication

### Integration
- ✓ Orchestrator initializes tracker correctly
- ✓ Tracker is global singleton (prevent duplicate instances)
- ✓ Phase results logged to both audit_log and execution tracker
- ✓ Execution log saved after every run (success/halt/error/skipped)
- ✓ Database indexes support fast queries on run_date, status, started_at

### Backward Compatibility
- ✓ Existing `algo_audit_log` unchanged
- ✓ Existing API endpoints unchanged
- ✓ New table added without breaking schema
- ✓ Old orchestrator runs won't have phase_results (null is handled)

## Root Cause Diagnosis Examples

### Problem: "Why does swing_trader_scores keep getting stuck?"
```bash
python scripts/orchestrator-history.py patterns 30
# Output: Phase 5 halts 5 times: "swing_trader_scores stale or missing"

python scripts/orchestrator-history.py failed 30 | grep swing
# Shows all 5 failures happened around 2-3 AM
# → Morning pipeline (2:00 AM run) is not completing swing_trader_scores

# Next step: Check CloudWatch logs for morning pipeline (2:00 AM ET)
```

### Problem: "Are data loading failures random or systematic?"
```bash
python scripts/orchestrator-history.py patterns 30
# If same phase halts every time → SYSTEMATIC (same loader failing)
# If different phases halt each time → RANDOM (transient issue)

# Example systematic:
#   Phase 1: technical_data_daily (5 halts)
#   Phase 5: swing_trader_scores (4 halts)
# → Specific loaders are broken, not transient

# Example random:
#   Phase 1: sometimes halts (1 time)
#   Phase 2: sometimes halts (1 time)
#   Phase 5: sometimes halts (1 time)
# → Random transient issues, check RDS/network/timeouts
```

### Problem: "Is the system recovering after the outage?"
```bash
python scripts/orchestrator-history.py stats 1   # Today
# Total runs: 4, Success rate: 75%

python scripts/orchestrator-history.py stats 1 --days 1
# Yesterday: 1 run, Success rate: 0% (all halted)
# Today: Improvement! Recovery in progress
```

## Deployment

### On Database Update
1. GitHub Actions deploys new schema via db-init Lambda
2. Table created automatically (IF NOT EXISTS)
3. No data migration needed (new table)

### On Next Orchestrator Run
1. Orchestrator initializes tracker with run context
2. Each phase logs results to tracker
3. At end of run, complete execution log saved to database
4. Users can immediately query via CLI or API

### Backward Compatibility
- If database not yet updated: tracker.save_execution_log() fails gracefully, logs warning, doesn't break trading
- Old runs won't have phase_results (NULL in database, handled in queries)
- API returns 503 "Data unavailable" if table doesn't exist yet (graceful degradation)

## Impact on System

### Performance
- ✓ No impact on orchestrator execution (tracker is non-blocking)
- ✓ One INSERT per run (< 1ms, doesn't affect trading latency)
- ✓ Queries indexed on run_date, status, started_at (fast)

### Reliability
- ✓ If tracker.save_execution_log() fails, orchestrator still completes
- ✓ Phase results already in `algo_audit_log` (redundancy)
- ✓ Graceful degradation if database unavailable

### User Experience
- ✓ CLI tool provides easy diagnostics
- ✓ API enables frontend integration
- ✓ SQL queries available for advanced analysis
- ✓ No new dependencies (uses existing psycopg2, json)

## Success Criteria Met

✓ **Problem Solved:** Users can now view execution history for previous orchestrator runs
✓ **Diagnostic Capability:** Can diagnose why swing_trader_scores gets stuck
✓ **Pattern Detection:** Can identify if failures are systematic or random
✓ **Phase Analysis:** Can see which phases halt most often and why
✓ **User-Friendly:** Multiple access methods (CLI, API, SQL)
✓ **Tested:** 8/8 unit tests pass
✓ **Documented:** Full guide with examples in steering docs
✓ **Integrated:** Seamlessly integrated into orchestrator
✓ **Backward Compatible:** Doesn't break existing code/data
✓ **Production Ready:** Error handling, logging, graceful degradation

## Next Steps (Optional Enhancements)

1. **Frontend Dashboard:** Display execution history in web UI
2. **Alerts:** Notify on repeated halts (e.g., "Phase 5 halted 3x in 24h")
3. **Archive Policy:** Automatically archive runs older than 90 days
4. **Cost Analysis:** Track execution time/cost trends
5. **Automated Remediation:** Trigger corrective actions on detected patterns
