# Remaining Issues Implementation Guide

## Completed (13/23 fixes)
Issues #1, #2, #3, #4, #6, #7, #8, #11, #15, #16, #18, #20-22

## Remaining (10 issues)

### Issue #5: Signal Generation Timeout Coverage (HIGH)
**Status**: ADEQUATE - 3000s (50 minutes) configured
**Action**: VERIFIED - timeout is sufficient for S&P 500 symbol processing
**Location**: terraform/modules/pipeline/main.tf:286

### Issue #9: Trade ID / Recurring ID Mismatch (MEDIUM)
**Status**: CREATED VALIDATION SCRIPT
**Implementation**: scripts/validate_trade_consistency.py
**Next Steps**:
1. Run: `python3 scripts/validate_trade_consistency.py` to audit data
2. If orphaned records found, create migration to clean data
3. Add database constraints to prevent future mismatches

### Issue #10: Configuration Missing for New Loaders (MEDIUM)
**Status**: NEEDS REVIEW
**Implementation Steps**:
1. Review terraform/terraform.tfvars for all loader task definitions
2. Verify each loader has: timeout >= 1800s, memory >= 512MB, CPU >= 256
3. Check Docker image exists for each loader
4. Verify ECS task definition has correct environment variables
5. Add missing loaders: load_swing_trader_scores.py, load_signal_quality_scores.py

**Critical Loaders to Audit**:
- signals_daily (3000s timeout required)
- technical_data_daily (18000s timeout)
- swing_trader_scores (1800s)
- signal_quality_scores (1800s)

### Issue #12: Position P&L Precision Loss (MEDIUM)
**Status**: NEEDS IMPLEMENTATION
**Implementation Steps**:
1. Import Decimal in algo_position_monitor.py
2. Convert all P&L calculations to use Decimal:
   ```python
   from decimal import Decimal, ROUND_HALF_UP
   
   unrealized_pnl = (Decimal(str(cur_price)) - Decimal(str(entry_price))) / Decimal(str(entry_price))
   pnl_pct = float((unrealized_pnl * 100).quantize(Decimal('0.01'), ROUND_HALF_UP))
   ```
3. Test with high-volume positions to verify precision
4. Files to update:
   - algo/algo_position_monitor.py (lines 235, 315)
   - algo/algo_performance.py (P&L aggregations)
   - Database schema: Store pnl_pct as NUMERIC(10,4) instead of FLOAT

### Issue #13: Missing Dry Run State Persistence (MEDIUM)
**Status**: NEEDS SCHEMA CHANGE
**Implementation Steps**:
1. Create new table: `algo_trades_dry_run` (same schema as algo_trades)
2. In Phase 6 entry execution, when `dry_run=True`:
   ```sql
   INSERT INTO algo_trades_dry_run (...) 
   SELECT ... FROM algo_trades_temp
   ```
3. Modify orchestrator to write dry-run trades to separate table
4. Add API endpoint to retrieve dry-run results: `/api/algo/dry-run-results`
5. Implement in algo/orchestrator/phase6_entry_execution.py (after execution loop)

### Issue #14: Orchestrator Deadlock Prevention (MEDIUM)
**Status**: NEEDS IMPLEMENTATION
**Implementation Steps**:
1. Add distributed locking to orchestrator startup:
   ```python
   # In Phase 1 (data freshness check)
   def acquire_execution_lock(cur, timeout_seconds=120):
       lock_id = hash('orchestrator_main') % (2**31)
       cur.execute("SELECT pg_advisory_lock(%s)", (lock_id,))
       logger.info(f"Acquired orchestrator lock {lock_id}")
   
   def release_execution_lock(cur, lock_id):
       cur.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
   ```
2. Add lock timeout handling with retry logic
3. Test with simulated concurrent runs
4. Document lock acquisition order to prevent circular deadlocks

### Issue #17: Missing Target Level Idempotency (MEDIUM)
**Status**: NEEDS SCHEMA CHANGE
**Implementation Steps**:
1. Add columns to algo_positions table:
   - `target_1_hit_time TIMESTAMP WITH TIME ZONE`
   - `target_2_hit_time TIMESTAMP WITH TIME ZONE`
   - `target_3_hit_time TIMESTAMP WITH TIME ZONE`

2. Update exit engine to track hits:
   ```python
   if position['target_1_hit_time'] is None and price >= T1:
       execute_exit()
       position['target_1_hit_time'] = current_timestamp
   ```
3. Ensure multiple target hits on same day don't trigger duplicate exits
4. File: algo/algo_exit_engine.py (Phase 4 exit execution)

### Issue #19: Uninitialized Variable in Error Path (LOW)
**Status**: POSSIBLY ALREADY FIXED
**Check**: Search for variables assigned inside try blocks:
```bash
grep -n "try:" lambda/api/routes/*.py | while read line; do
  num=$(echo $line | cut -d: -f2)
  sed -n "${num},$((num+10))p" file
done
```
**If Found**: Initialize variable before try block with empty/None value

### Issue #23: Unused Imports (LOW)
**Status**: VERIFIED OPTIMIZED
**Check Result**: Heavy imports (boto3, pandas) already conditional
**Status**: ✓ COMPLETE

## Implementation Priority
1. **Quick Wins** (30 min):
   - #19: Find and fix uninitialized variables
   - #23: Verify no module-level heavy imports

2. **Medium Effort** (2-3 hours):
   - #10: Audit and update loader configurations
   - #12: Implement Decimal-based P&L calculations
   - #17: Add timestamp columns and update exit logic

3. **Complex** (4-6 hours):
   - #9: Run validation, clean orphaned data, add constraints
   - #13: Create dry-run table, modify orchestrator
   - #14: Implement distributed locking with proper error handling

## Testing Strategy
1. Unit tests for each fix
2. Integration tests with sample data
3. Load tests for concurrency issues (#14)
4. End-to-end tests with dry-run mode (#13)

## Deployment Notes
- Issues #13, #17 require database migration
- Issue #14 requires PostgreSQL advisory locks available
- All changes should be backwards compatible
