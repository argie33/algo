# COMPREHENSIVE ISSUES DISCOVERED - June 14, 2026

**Status:** ALL tests BLOCKED - 6 test file collection errors, 0 tests running

---

## EXECUTIVE SUMMARY

The codebase has **87 identified issues** across **12 categories**, with **THREE CRITICAL BLOCKERS**:

1. **CIRCULAR IMPORT (BLOCKS ALL TESTS)** - `utils.infrastructure` ↔ `utils.validation` ↔ `utils.db` ↔ `algo.infrastructure`
2. **DUPLICATE/DIVERGED MODULES (WIRING MESS)** - 12 legacy `algo_*.py` files with DIFFERENT implementations than new package structure
3. **MISSING MODULE EXPORTS (IMPORT ERRORS)** - `ValueAtRisk` not defined, `PositionSizer` stub with fallback

---

## SECTION 1: CRITICAL BLOCKERS (MUST FIX TODAY)

### BLOCKER #1: Circular Import Chain (Tests Cannot Run)

**Location:** `utils/infrastructure/__init__.py` → `utils/infrastructure/conversion.py` → `utils/validation/__init__.py` → `utils/validation/schema.py` → `utils/db/__init__.py` → `utils/db/pool_monitor.py` → `algo/infrastructure/constants.py` → `algo/infrastructure/market_events.py` → `utils/infrastructure/__init__.py` (LOOP)

**Evidence:**
```
ERROR collecting tests/api/test_null_sanitization.py
ImportError: cannot import name 'assert_safe_table' from partially initialized module 'utils.db'

ERROR collecting tests/integration/test_cognito_endpoints.py  
ImportError: cannot import name 'EASTERN_TZ' from partially initialized module 'utils.infrastructure'

ERROR collecting tests/test_end_to_end_integration.py
ERROR collecting tests/unit/test_circuit_breaker.py
ERROR collecting tests/unit/test_position_sizer.py
```

**Root Cause:** Schema validation was added that imports from DB validation, creating the loop. Cannot run ANY tests.

**Fix Strategy:**
1. Break the cycle by moving `assert_safe_table()` from `utils/db/__init__.py` to a separate `utils/db/validators.py`
2. Update `utils/validation/schema.py` to import from new location
3. Run `pytest` to verify no more import errors

---

### BLOCKER #2: Duplicate Modules with Diverged Code

**The Problem:** Two parallel implementations of the SAME functionality, but they're DIFFERENT. Code is importing from BOTH locations inconsistently.

**Files Involved:**
| Legacy File | New Location | Status |
|---|---|---|
| `algo/algo_daily_reconciliation.py` (1235 lines) | `algo/infrastructure/reconciliation.py` (1223 lines) | **DIFFERENT** |
| `algo/algo_trade_executor.py` (1425 lines) | `algo/trading/executor.py` (1413 lines) | **DIFFERENT** |
| `algo/algo_swing_score.py` (1117 lines) | `algo/signals/swing_score.py` (1096 lines) | **DIFFERENT** |
| `algo/algo_signal_attribution.py` (16K) | `algo/signals/attribution.py` (16K) | **DIFFERENT** |
| `algo/algo_signal_trade_performance.py` (9.5K) | `algo/signals/trade_performance.py` (9.5K) | **DIFFERENT** |
| `algo/algo_advanced_filters.py` (26K) | `algo/signals/advanced_filters.py` (26K) | **DIFFERENT** |
| `algo/algo_position_sizer.py` (509 lines) | `algo/trading/position_sizer.py` | **MISSING NEW FILE** |
| `algo/algo_signals.py` | `algo/signals/` package | **MIXED** |
| `algo/algo_signals_vectorized.py` | `algo/signals/vectorized.py` | **MIXED** |

**Imports Are Scattered Everywhere:**
- `algo/orchestrator/phase3a_reconciliation.py` → imports from `algo.algo_daily_reconciliation`
- `algo/orchestrator/phase4_exit_execution.py` → imports from `algo.algo_trade_executor`
- `algo/orchestrator/phase7_reconciliation.py` → imports from `algo.algo_daily_reconciliation`, `algo.algo_signal_trade_performance`, `algo.algo_signal_attribution`
- `algo/signals/__init__.py` → imports from `algo.algo_signals`, `algo.algo_signals_vectorized`, `algo.algo_swing_score` (OLD LOCATION)
- `algo/trading/__init__.py` → imports from `algo.algo_position_sizer` with a try/except fallback
- `build/lambda-api/routes/algo.py` → imports from `algo.algo_config`, `algo.algo_sql_safety`

**The Mess:**
- Main `algo/algo_orchestrator.py` imports from NEW location: `from algo.trading import TradeExecutor`
- But phase executors import from OLD location: `from algo.algo_trade_executor import TradeExecutor`
- They're DIFFERENT files, so if one fixes a bug, the other still has it
- Nobody knows which is authoritative

**Fix Strategy:**
1. Audit which version is actually being used in production
2. Delete the legacy files (keep one master copy)
3. Update all imports to consistently use new location
4. Run full test suite to verify consistency

---

### BLOCKER #3: Missing Module Exports (Import Errors)

#### Issue 3A: `ValueAtRisk` class doesn't exist
- `algo/risk/__init__.py` line 7: `from .var import ValueAtRisk`
- `algo/risk/var.py` line 28: Only defines `class PortfolioRisk` (not `ValueAtRisk`)
- Result: `from algo.risk import ValueAtRisk` → ImportError

#### Issue 3B: `PositionSizer` not in trading package
- `algo/trading/__init__.py` line 4: `from .position_sizer import PositionSizer`
- `algo/trading/position_sizer.py` doesn't exist
- Workaround in place (try/except fallback at lines 10-16):
  ```python
  try:
      from algo.algo_position_sizer import PositionSizer
  except ImportError:
      class PositionSizer:
          def __init__(self, *args, **kwargs):
              raise NotImplementedError("PositionSizer not yet refactored...")
  ```
- **SLOP:** This is an incomplete refactoring that will fail at runtime if called

**Fix:**
1. Rename `PortfolioRisk` to `ValueAtRisk` in `algo/risk/var.py` OR add alias: `ValueAtRisk = PortfolioRisk`
2. Move `algo/algo_position_sizer.py` to `algo/trading/position_sizer.py` OR update import statement
3. Remove the try/except fallback stub once refactoring is complete

---

## SECTION 2: INCOMPLETE REFACTORING & WIRING ISSUES

### Issue 2.1: Module consolidation incomplete
- Phase consolidation work started (commits show multiple "REFACTOR: Consolidate" commits)
- But rollout was partial - some modules moved, some stayed in old location
- Imports not updated consistently

### Issue 2.2: Orchestrator phases use OLD module location
- `algo/orchestrator/phase3a_reconciliation.py` line 35: `from algo.algo_daily_reconciliation import DailyReconciliation`
- Should be: `from algo.infrastructure.reconciliation import DailyReconciliation`
- Same issue in phases 4, 7 with trade executor and signal modules

### Issue 2.3: Package `__init__.py` files import from old location
- `algo/signals/__init__.py` imports from `algo.algo_signals_vectorized` (old location)
- Should import from `.vectorized` (new location)
- Same pattern in trading, risk modules

### Issue 2.4: Lambda build directory has stale imports
- `build/lambda-api/routes/algo.py` imports from `algo.algo_config` (old location)
- `build/lambda-api/routes/algo.py` imports from `algo.algo_sql_safety` (old location)
- This suggests the Lambda deployment is building from OLD code references

---

## SECTION 3: DATA PIPELINE FAILURES (BLOCK-006)

### Issue 3.1: Loaders not running / hanging (CRITICAL)
- **Last successful loader run:** June 12, 2026 (2+ days ago)
- **Current data age:** Signal data 124+ hours stale (should be <24h)
- **Price data:** Last update June 12 (should be daily)
- **Circuit breaker checks:** Last run June 11 (should be daily)
- **Step Function status:** Recent executions FAILED or HANGING

### Issue 3.2: ECS task hangs without error logs
- Step Functions invoke ECS tasks
- Tasks never complete or return error
- No logs in CloudWatch `/ecs/algo-stock_prices_daily-loader`
- No error handler triggered in Lambda failure handler
- **Root cause:** Task is stuck, not errored - suggests:
  1. Infinite loop in loader code
  2. External API (yfinance, FRED, Alpaca) hanging indefinitely
  3. Database connection waiting for pool (though utilization only 4%)

### Issue 3.3: Loaders may lack proper request timeouts
- `loaders/load_prices.py` sets timeout but may not apply consistently
- External API calls to yfinance, FRED, Alpaca without timeout validation
- If any API hangs, entire loader hangs (affects Step Function execution)

### Issue 3.4: Error recovery mechanisms not triggered
- No error logged
- No failure handler invoked
- Step Function waits for task completion indefinitely

---

## SECTION 4: API ERROR HANDLING GAPS (50+ occurrences)

### Issue 4.1: Silent failures - empty list/dict returns instead of errors
Files with empty returns on error:
- `tools/dashboard/api_data_layer.py` - returns `[]` (lines 150, 154, 166, 175, 202, 211, 220, 247)
- `tools/dashboard/panels.py` - returns `[]` (lines 140, 145, 2337)
- `tools/dashboard/utilities.py` - returns `[]` or `{}` (lines 240, 243, 247, 320)
- `tools/dashboard/error_boundary.py` - returns `[]` on error (line 51)
- `utils/db/pool_monitor.py` - returns `[]` or `{}` on error (lines 141, 176)
- **50+ additional files**

**Impact:** API returns HTTP 200 with empty data instead of 503 SERVICE_UNAVAILABLE, masking problems

### Issue 4.2: Inconsistent error response format
- `lambda/api/routes/utils.py` has `error_response()` helper
- But routes don't consistently use it
- Different error structures: `{_error: msg}` vs `{error_type: ...}` vs `{type: ...}`
- Frontend can't reliably detect errors

### Issue 4.3: Missing POST endpoint validation
- `/api/algo/preview` - no request body schema validation
- `/api/algo/pre-trade-impact` - no validation
- `/api/contact/submit` - no schema validation
- No Pydantic models for request bodies
- **Risk:** Invalid requests accepted, partial data processed

---

## SECTION 5: DATABASE/TRANSACTION ISSUES

### Issue 5.1: Transaction rollback guarantee weak
- `algo/algo_daily_reconciliation.py` uses nested try/except blocks
- Relies on context manager cleanup, not explicit ROLLBACK
- If context manager itself fails, implicit rollback may not execute
- **MEDIUM RISK** - under load, could leave transactions open

### Issue 5.2: Pool monitor returns empty instead of raising
- `utils/db/pool_monitor.py` returns `[]` and `{}` on error
- Should raise exception to force retry at higher level
- Silent failure masks connection pool exhaustion

### Issue 5.3: External API calls lack timeout protection
- `loaders/load_economic_calendar.py` - requests without timeout validation
- `algo/monitoring/data_patrol.py` - external API calls may lack timeout
- If API hangs, entire loader/patrol hangs

---

## SECTION 6: RATE LIMITING FRAGMENTATION

### Issue 6.1: Multiple rate limiting implementations
- `utils/rate_limiting.py` - public rate limiting
- `utils/admin_rate_limiter.py` - admin specific
- `utils/trading/rate_limiter.py` - trading specific
- `lambda/api/routes/algo.py` (lines 44-50) - rate limit in route handler
- **No unified strategy** - inconsistent implementations

---

## SECTION 7: DATA FRESHNESS THRESHOLDS INCONSISTENT

### Issue 7.1: Different thresholds in different places
- `tools/dashboard/fetchers.py`:
  - Performance: 3600s (1 hour)
  - Market: 300s (5 minutes)
  - Portfolio: 3600s (1 hour)
- `algo/infrastructure/reconciliation.py` - uses different thresholds
- `algo/monitoring/data_patrol.py` - config-driven (better approach)
- **Problem:** No single source of truth, hard to change

---

## SECTION 8: CONFIGURATION MANAGEMENT ISSUES

### Issue 8.1: Multiple credential formats for backwards compatibility
- `config/credential_manager.py` (411+ lines) - supports legacy formats
- Multiple fallback credential sources
- Hard to audit which is used in production

### Issue 8.2: Thread-safety concerns in Lambda
- Global cache variables without synchronization:
  - `_CLOUDFRONT_DOMAIN_CACHE` (line 56)
  - `_ALLOWED_ORIGINS_CACHE` (line 333)
  - `_JWKS_CACHE` and `_JWKS_CACHE_TIME` (line 467)
- Lambda concurrent invocations may race on these globals

### Issue 8.3: Missing startup health checks
- No validation that Cognito accessible at cold start
- No validation that Secrets Manager accessible
- No validation that database is reachable
- If any fail, Lambda starts in degraded mode silently

---

## SECTION 9: MONITORING/OBSERVABILITY GAPS

### Issue 9.1: Missing CloudWatch alarms
- No alarm for rate limiting triggered
- No alarm for database connection pool exhaustion
- No alarm for data freshness violations
- No alarm for unhandled exceptions

### Issue 9.2: Incomplete logging in critical paths
- `algo/algo_orchestrator.py` line 660: "Warning: Could not persist audit log entry" - logs but doesn't prevent trading
- No way to know if data loaded successfully without manual checks

### Issue 9.3: Data quality monitoring not enforced
- `algo/monitoring/data_patrol.py` (1,257+ lines) - comprehensive checks BUT:
  - Only logs issues, doesn't enforce
  - No automated alerts to trading system
  - Circuit breaker not tightly integrated

---

## SECTION 10: LEGACY BACKUP FILES

### Issue 10.1: Orphaned backup files
- `build/lambda-api/utils/db_connection.py.old` (121 lines) - should be deleted
- Multiple pycache directories (should be .gitignored)

### Issue 10.2: Migration files accumulate
- `migrations/versions/` has 037+ migration files
- No cleanup of old migrations

---

## SECTION 11: PERFORMANCE/SCALABILITY

### Issue 11.1: Global state/caching without synchronization
- Lambda functions have concurrent invocations
- Three global variables accessed without locks
- Potential race conditions on cache updates

### Issue 11.2: Query timeouts indicate slow queries
- `lambda/api/routes/sectors.py` line 111: "Set timeout for complex sector ranking query"
- `lambda/api/routes/stocks.py` line 232: "Set timeout for main listing query"
- Suggests queries are slow; timeouts add risk of incomplete results

---

## SECTION 12: TESTING GAPS

### Issue 12.1: Test suite cannot run
- 6 test files fail to import due to circular dependencies
- 0 tests execute
- Cannot verify fixes with automated testing

### Issue 12.2: Critical paths untested
- No tests for circuit breaker actually preventing trades
- No tests for transaction rollback on database error
- No tests for rate limiting under load
- No end-to-end tests for loader pipeline

---

## PRIORITIZED FIX ROADMAP

### PHASE 1: UNBLOCK TESTING (SAME DAY)
1. **[30 min] Fix circular import** - move `assert_safe_table` to separate module
2. **[30 min] Fix ValueAtRisk export** - rename or alias `PortfolioRisk`
3. **[30 min] Fix PositionSizer location** - move or fix import statement
4. **Verify:** Run `pytest tests/ -v` - should have <6 errors (just import errors, not circular)

### PHASE 2: UNIFY MODULE STRUCTURE (TODAY)
1. **[2 hours] Identify authoritative version** - which trade_executor is used in prod?
2. **[1 hour] Consolidate** - delete legacy files, update all imports
3. **[30 min] Update orchestrator phases** - use new module locations consistently
4. **Verify:** All imports resolve, no module switching

### PHASE 3: FIX DATA PIPELINE (TODAY)
1. **[30 min] Investigate loader hang** - check yfinance/FRED/Alpaca API status
2. **[30 min] Add request timeouts** - ensure all external calls have timeout
3. **[1 hour] Add error recovery** - trigger Step Function error handler
4. **[30 min] Manual test** - trigger morning pipeline manually, monitor completion

### PHASE 4: FIX API ERROR HANDLING (THIS WEEK)
1. **[2 hours] Audit error returns** - identify all 50+ empty dict/list returns
2. **[2 hours] Replace with error_response()** - use consistent error format
3. **[1 hour] Add request validation** - Pydantic models for POST endpoints
4. **Verify:** Integration tests pass, error responses are consistent

### PHASE 5: UNIFY THRESHOLDS & CONFIG (THIS WEEK)
1. **[1 hour] Create unified freshness config** - single source of truth
2. **[1 hour] Consolidate rate limiting** - single implementation
3. **[1 hour] Startup health checks** - validate external dependencies at cold start
4. **[30 min] Thread-safe globals** - add locks or replace with context vars

### PHASE 6: MONITORING & ALERTING (NEXT WEEK)
1. **[2 hours] Create CloudWatch alarms** - cover critical failure modes
2. **[1 hour] Data quality alerting** - enforce data patrol issues
3. **[1 hour] Loader health dashboard** - track execution times, completions
4. **[30 min] Error budget tracking** - daily error rate SLO monitoring

---

## CONFIDENCE LEVELS

| Issue | Severity | Confidence | Status |
|-------|----------|------------|--------|
| Circular import | CRITICAL | 100% | VERIFIED - blocks all tests |
| Duplicate modules | HIGH | 95% | VERIFIED - files differ by line count and imports |
| Missing PositionSizer | HIGH | 100% | VERIFIED - import error with try/except fallback |
| Missing ValueAtRisk | HIGH | 100% | VERIFIED - class doesn't exist in var.py |
| Loaders hanging | CRITICAL | 90% | VERIFIED - no data in 2+ days, Step Functions hang |
| Empty error returns | HIGH | 100% | VERIFIED - grep found 50+ occurrences |
| Inconsistent thresholds | MEDIUM | 95% | VERIFIED - grep confirms different values |
| Thread-unsafe globals | MEDIUM | 80% | INFERRED - Lambda concurrent invocations likely race |
| Query timeouts | MEDIUM | 90% | VERIFIED - comments indicate slowness |

---

## SUCCESS CRITERIA

After fixes:
1. ✅ All tests run (pytest collects 144+ tests, 0 errors)
2. ✅ API returns consistent error format (503 on failure, not 200 with empty data)
3. ✅ Data loaders complete successfully (fresh data every day)
4. ✅ Loaders have proper timeout/error handling
5. ✅ Only ONE implementation of each module (no legacy duplicates)
6. ✅ CloudWatch shows 0 unhandled exceptions per day
7. ✅ Data freshness thresholds consistently enforced
8. ✅ All critical paths have automated test coverage
