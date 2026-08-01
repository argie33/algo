# CRITICAL BUGS FOUND - Schema Mismatches

## Summary
The orchestrator "passes" all 9 phases but the underlying code/database mismatch prevents functionality. Verified by running diagnostics and checking actual database schemas vs code queries.

## Critical Issues Found

### Issue 1: algo_config Column Name Mismatch
**Severity**: CRITICAL
**Impact**: Config lookups fail, system falls back to defaults

- **Table**: `algo_config`
- **Actual columns**: id, key, value, value_type, description, updated_at, updated_by
- **Code expects**: `config_value` column
- **Actual column name**: `value`
- **Files affected**: Need to search for "config_value" queries

### Issue 2: algo_portfolio_snapshots Column Mismatch  
**Severity**: HIGH
**Impact**: Portfolio state queries fail, dashboard can't show portfolio value

- **Table**: `algo_portfolio_snapshots`
- **Code expects**: `portfolio_value`, `cash`, `num_positions`
- **Actual columns**: `total_portfolio_value`, `total_cash`, `position_count`
- **Files affected**: Need to search for queries using wrong column names

### Issue 3: algo_metrics_daily Schema Mismatch
**Severity**: HIGH
**Impact**: Trade execution tracking queries fail

- **Table**: `algo_metrics_daily`
- **Code expects**: Individual trade records with `action_type` column
- **Actual structure**: Aggregate daily counts (date, entries, exits, total_actions)
- **Files affected**: Code queries for `WHERE action_type IN ('entry', 'exit')`

### Issue 4: orchestrator_phase_results Table Missing
**Severity**: HIGH
**Impact**: Phase result tracking queries fail

- **Code expects**: `orchestrator_phase_results` table with detailed phase results
- **Actual**: Results stored as JSONB in `orchestrator_execution_log.phase_results`
- **Files affected**: Queries trying to fetch from non-existent table

### Issue 5: portfolio_positions Table Missing
**Severity**: MEDIUM  
**Impact**: Position tracking queries fail

- **Code expects**: `portfolio_positions` table
- **Actual**: Correct table is `algo_positions`
- **Files affected**: Queries using wrong table name

## Verification Steps Performed
1. ✓ Queried information_schema.columns for all affected tables
2. ✓ Confirmed column name mismatches
3. ✓ Confirmed missing tables
4. ✓ Confirmed orchestrator logs show all phases "pass" despite queries failing

## Root Cause
Code was written for a different schema version, but database was migrated or redesigned. The mismatch was never caught because:
- Orchestrator phases don't all actually use the config values (some fall back to defaults)
- Phase logging captures exceptions but reports phases as "ok" anyway
- Dashboard/metrics queries silently fail but don't halt orchestration

## Next Steps
1. Find all affected code files
2. Update column name references
3. Test each fix
4. Verify orchestrator still passes with corrected queries
5. Run end-to-end tests

## Files to Check
- algo/orchestrator/*.py (all phase files)
- algo/trading/*.py (execution code)
- dashboard/*.py (dashboard panels)
- lambda/api/dev_server.py (API endpoints)
- utils/db/*.py (database utilities)
- loaders/*.py (data loading code)
