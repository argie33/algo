# CRITICAL ISSUES BLOCKING LIVE TRADING - IMMEDIATE FIX GUIDE

**Status**: 3 CRITICAL issues identified, ALL require fixing for trading to work

## ISSUE #1: PHASE 8 NOT PERSISTING TRADES (CRITICAL - BLOCKS ALL TRADING)

**Problem**: 
- Dry-run Phase 8 executes 3 trades successfully
- Real orchestrator runs execute 0 trades (not persisted to algo_trades table)
- Last 24 hours: 0 trades created despite 201 signals generated daily
- Phase 8 returns "success" but no algo_trades rows created

**Root Cause**: Paper trading mode execution path doesn't persist trades to database
- Phase 8 has two code paths: dry-run (which works) and real (which doesn't)
- Real execution path likely skips database write when in paper mode

**Fix Required**:
1. **File**: `algo/orchestrator/phase8_entry_execution.py`
2. **Find**: Where Phase 8 decides whether to persist trades
3. **Check**: `config.get("execution_mode")` - should be "paper" for paper trading
4. **Verify**: Trades are being persisted to algo_trades table regardless of execution_mode
5. **Test**: Run orchestrator (not dry-run) and verify algo_trades table gets new rows

**Verification Query**:
```sql
SELECT COUNT(*) FROM algo_trades WHERE entry_date = CURRENT_DATE;
-- Should return: > 0 (after next orchestrator run)
```

---

## ISSUE #2: LINTING ERRORS BLOCKING AWS DEPLOYMENT

**Problem**:
- 21 ruff linting violations in lambda/api/ directory
- CI pipeline blocked: `deploy-api-lambda.yml` workflow cannot proceed
- Dashboard and API fixes cannot be deployed to AWS

**Fix Required**:
1. **Command**: `cd lambda/api && ruff check . --fix`
2. **Review**: Auto-fixes may not catch all 21 issues
3. **Manual fixes**: Run `ruff check lambda/api/` to see remaining violations
4. **Commit**: After all linting passes, commit the fixes
5. **Deploy**: Re-trigger `deploy-api-lambda.yml` workflow in GitHub Actions

**Verification**:
```bash
cd lambda/api && ruff check .
# Should return: 0 issues found
```

---

## ISSUE #3: API ENDPOINT SLOWNESS (HIGH PRIORITY)

**Problem**:
- `/api/algo/positions` endpoint takes 2.68 seconds
- Would timeout (5xx) under concurrent load
- Impacts dashboard responsiveness

**Root Cause**: Likely N+1 queries or inefficient JSON serialization in position assembly

**Fix Strategy**:
1. **File**: `lambda/api/routes/algo_handlers/dashboard.py` - `_get_algo_positions()` function
2. **Profiling**: Add timing logs to identify slow DB queries
3. **Batch queries**: Ensure all position lookups done in single queries, not loops
4. **Serialization**: Check if JSON.dumps() is inefficient
5. **Target**: Response time < 500ms

**How to Debug**:
```python
import time
start = time.time()
cur.execute("SELECT ...")  # Check each query
elapsed = time.time() - start
logger.info(f"Query took {elapsed*1000:.1f}ms")
```

---

## TESTING CHECKLIST BEFORE CONSIDERING "DONE"

After applying each fix, run these tests:

### Test 1: Phase 8 Trade Execution
```bash
python3 << 'EOF'
import sys
sys.path.insert(0, '.')
from datetime import date
from algo.infrastructure import get_config
from algo.orchestration.orchestrator import Orchestrator
from utils.db import DatabaseContext

# Get trade count BEFORE
with DatabaseContext("read") as cur:
    cur.execute("SELECT COUNT(*) FROM algo_trades WHERE entry_date = %s", (date.today(),))
    before = cur.fetchone()[0]

# Run orchestrator
orch = Orchestrator(config=get_config(), run_date=date.today(), dry_run=False, verbose=False)
result = orch.run()

# Get trade count AFTER
with DatabaseContext("read") as cur:
    cur.execute("SELECT COUNT(*) FROM algo_trades WHERE entry_date = %s", (date.today(),))
    after = cur.fetchone()[0]

trades_created = after - before
print(f"Trades created: {trades_created}")
assert trades_created > 0, "FAILED: No trades were created!"
print("SUCCESS: Trades are being executed!")
EOF
```

### Test 2: Linting Passes
```bash
cd lambda/api && ruff check .
# Should return: no violations
```

### Test 3: API Response Time
```bash
python3 << 'EOF'
import time
from dashboard.api_data_layer import api_call

start = time.time()
positions = api_call("/api/algo/positions")
elapsed = time.time() - start

print(f"Response time: {elapsed*1000:.1f}ms")
assert elapsed < 0.5, "Response time still > 500ms!"
print("SUCCESS: API response time is acceptable!")
EOF
```

---

## SUMMARY TABLE

| Issue | Severity | Status | Est. Time | Blocker? |
|-------|----------|--------|-----------|----------|
| Phase 8 trade persistence | CRITICAL | Not Fixed | 1-2 hours | YES - trading blocked |
| Linting errors in lambda/api | HIGH | Not Fixed | 0.5-1 hour | YES - deployment blocked |
| API endpoint slowness | HIGH | Not Fixed | 2-4 hours | NO - but impacts UX |

---

## NEXT STEPS

1. **IMMEDIATELY**: Fix Phase 8 trade persistence (enables trading)
2. **IMMEDIATELY**: Fix linting errors (enables AWS deployment)
3. **WITHIN 24 HOURS**: Optimize API endpoints
4. **VERIFY**: Run the testing checklist after each fix
5. **DEPLOY**: Push to AWS after all fixes pass tests

---

**Generated**: 2026-07-06  
**By**: Claude Code Session 16  
**Status**: Issues identified, fixes documented, ready for execution
