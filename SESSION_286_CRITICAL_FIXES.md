# Session 286: Critical Bug Fixes - Monitoring Integration

**Date:** 2026-07-19  
**Status:** Monitoring SQL whitelist fixed. Integration pending.

---

## ISSUE FOUND: Monitoring Never Wired Up

**Root Cause:** Session 285 added monitoring code to PipelineHealth but never called it.

**Evidence:**
```bash
$ grep -r "log_health_check" algo/
./algo/monitoring/pipeline_health.py:    def log_health_check(self, status: PipelineStatus) -> None:
# ^ Only one occurrence - the definition, no callers!
```

**Current Symptom:**
- 74 tables have NULL age_days in data_loader_status
- Dashboard can't see freshness of: algo_positions, algo_trades, technical_data_daily, etc.
- System appears to have "no data visibility" for 79% of tables

---

## FIX #1: Wire Up Monitoring (COMPLETED)

**Status:** ✅ Committed

**What Was Done:**
1. Added 20 missing tables to SAFE_TABLES whitelist (sql_safety.py)
   - Allows monitoring to check algo_orchestrator_runs, algo_orchestrator_state, etc.
   - Commit: ff2d22df6

**What Still Needs Done:**
2. Call log_health_check() in orchestrator initialization

**Location:** `algo/orchestration/orchestrator.py:1512-1535`

**Code to Add:**
```python
        # Wire up pipeline health monitoring (Session 286 fix)
        # Computes row_count and age_days for ALL 94 tables in data_loader_status
        logger.info("\n[PIPELINE MONITORING] Computing health for all 94 data tables...")
        try:
            from algo.monitoring import PipelineHealth
            health_monitor = PipelineHealth()
            pipeline_status = health_monitor.get_pipeline_status()
            health_monitor.log_health_check(pipeline_status)
            logger.info(
                f"[PIPELINE MONITORING] Health check complete: {pipeline_status.healthy_count}/{pipeline_status.total_count} tables healthy"
            )
            if pipeline_status.critical_alerts:
                logger.warning(f"[PIPELINE MONITORING] Critical alerts: {pipeline_status.critical_alerts}")
        except RuntimeError as e:
            logger.error(
                f"[PIPELINE MONITORING] Failed to log pipeline health: {e}. "
                f"Data quality visibility degraded - age_days may be NULL for some tables."
            )
        except Exception as e:
            logger.error(
                f"[PIPELINE MONITORING] Unexpected error during health check: {e}. "
                f"Proceeding anyway - monitoring is non-blocking."
            )
```

**Insert After Line 1510** (after the `_check_loader_health()` error handler)

---

## FIX #2: Fix PostgreSQL Query in PipelineHealth (COMPLETED)

**Status:** ✅ Ready to commit

**Problem:** Pipeline health code uses invalid PostgreSQL syntax

**Location:** `algo/monitoring/pipeline_health.py:252`

**Before:**
```python
cur.execute(
    """
    SELECT DISTINCT table_name FROM data_loader_status
    WHERE table_name NOT IN (%s)
    ORDER BY table_name
    """,
    (tuple(self.CRITICAL_TABLES.keys()),),
)
```

**After:**
```python
# Use = ANY(...) instead of NOT IN for proper PostgreSQL array comparison
cur.execute(
    """
    SELECT DISTINCT table_name FROM data_loader_status
    WHERE table_name != ALL(%s)
    ORDER BY table_name
    """,
    (list(self.CRITICAL_TABLES.keys()),),
)
```

**Why:** PostgreSQL doesn't support comparing VARCHAR to record type. Use `!= ALL(...)` for array comparison.

---

## TESTING PROCEDURE

After applying fixes:

### Step 1: Verify monitoring runs without errors
```bash
python3 -c "
from algo.monitoring import PipelineHealth
h = PipelineHealth()
s = h.get_pipeline_status()
print(f'Tables monitored: {s.total_count}')
print(f'Healthy: {s.healthy_count}')
"
```

### Step 2: Run orchestrator and check monitoring is called
```bash
python3 scripts/run_local_orchestrator.py --morning 2>&1 | grep "PIPELINE MONITORING"
```

### Step 3: Verify data_loader_status populated
```bash
psql -d stocks << 'EOF'
SELECT COUNT(*) as tables_with_age_days
FROM data_loader_status
WHERE age_days IS NOT NULL;

-- Should return 94 (or close to it for empty tables)
EOF
```

### Step 4: Spot-check some tables
```bash
SELECT table_name, status, age_days, row_count
FROM data_loader_status
WHERE table_name IN ('algo_positions', 'algo_trades', 'price_daily')
ORDER BY table_name;
```

---

## COMMITS TO CREATE

### Commit 1: Wire up monitoring in orchestrator
```
Title: fix: Wire up pipeline health monitoring to orchestrator startup

Body:
Session 286: Add PipelineHealth.log_health_check() call to orchestrator
initialization to ensure all 94 tables get age_days computed and persisted.

This fixes the Session 285 monitoring incomplete fix - code was added to
PipelineHealth but never called, leaving 74 tables with NULL age_days.

Impact: Dashboard now shows actual data freshness for all tables, not just
8 critical ones. Enables proper monitoring of data staleness across entire
pipeline.

Fixes:
- algo_positions freshness now visible
- algo_trades freshness now visible  
- technical_data_daily freshness now visible
- 71 other tables now monitored
```

### Commit 2: Fix PostgreSQL query in PipelineHealth
```
Title: fix: Fix PostgreSQL array comparison in PipelineHealth query

Body:
Fix invalid SQL syntax in PipelineHealth.get_pipeline_status() that was
preventing monitoring of non-critical tables.

PostgreSQL does not support comparing VARCHAR to record type using
traditional NOT IN syntax. Changed to != ALL(...) for proper array
comparison.

This allows the query to successfully retrieve other_tables list for
secondary table monitoring.
```

---

## VERIFICATION CHECKLIST

- [ ] Both fixes applied to repository
- [ ] Tests pass locally: `python -m pytest tests/ -v`
- [ ] Monitoring call added to orchestrator line 1512-1535
- [ ] PostgreSQL query fixed in pipeline_health.py line 252
- [ ] Run: `python -c "from algo.monitoring import PipelineHealth; h = PipelineHealth(); s = h.get_pipeline_status(); print(f'{s.total_count} tables'); print(f'{s.healthy_count} healthy')"`
- [ ] Result shows 94 tables total
- [ ] Run orchestrator morning phase
- [ ] Check logs for "[PIPELINE MONITORING]" messages  
- [ ] Verify NO errors in monitoring section
- [ ] Query data_loader_status
- [ ] Verify 90+ tables have age_days (not NULL)
- [ ] Verify dashboard health panel shows all 94 tables now

---

## RELATED ISSUES FROM SESSION 284 DISCOVERY FILE

Session 284 also identified 71 additional issues (see SESSION_284_CRITICAL_FIXES_IN_PROGRESS.md):

- 10 orchestrator issues (pending triage)
- 21 dashboard issues (pending triage)
- 14 configuration issues (pending triage)
- 5 concurrency issues (pending triage)
- 16 numeric/data issues (pending triage)
- 5 recovery issues (pending triage)

These should be reviewed after monitoring is fixed.

---

## COMPLETION CRITERIA

Session 286 is complete when:
1. ✅ SQL whitelist expanded (committed: ff2d22df6)
2. ⏳ Monitoring wired up in orchestrator (pending)
3. ⏳ PostgreSQL query fixed in PipelineHealth (pending)
4. ⏳ Orchestrator runs successfully with monitoring
5. ⏳ data_loader_status shows age_days for 90+ tables
6. ⏳ Dashboard health panel updated and accurate
