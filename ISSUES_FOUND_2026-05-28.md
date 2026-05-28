# Comprehensive Issue Hunt - May 28, 2026

## Executive Summary
Comprehensive code review and static analysis of the algo trading system. This document catalogs all identified issues by severity and category for prioritization and tracking.

**Total Issues Found**: 23 (across all severity levels)
- CRITICAL: 2
- HIGH: 7
- MEDIUM: 10
- LOW: 4

**Categories**:
- API Handler Issues: 6
- Data Loading Issues: 4
- Database/Schema Issues: 5
- Business Logic/Calculation Issues: 4
- Configuration/Deployment Issues: 2
- Error Handling Issues: 2

---

## CRITICAL ISSUES (Must fix)

### #1: Unsafe Float Conversion in Swing Scores API
**File**: `lambda/api/routes/algo.py:91`
**Severity**: CRITICAL
**Status**: UNFIXED

```python
min_score = float(min_score_str) if min_score_str else None
```

**Problem**: Direct float() conversion without try-except block. If user passes non-numeric min_score parameter, API will crash with ValueError.

**Impact**: API crash on /api/algo/swing-scores endpoint if invalid parameter provided
- Crashes the endpoint
- Returns 500 error instead of 400 bad_request
- Could be exploited for DoS

**Reproduction**: 
```bash
curl "https://api/api/algo/swing-scores?min_score=invalid"
```

**Fix**:
```python
try:
    min_score = float(min_score_str) if min_score_str else None
except (ValueError, TypeError):
    return error_response(400, 'bad_request', 'min_score must be numeric')
```

---

### #2: Missing S&P 500 Index Symbol in Database
**File**: `loaders/load_sp500_constituents.py` (data issue)
**Severity**: CRITICAL
**Status**: UNFIXED

**Problem**: The SPY symbol (or ^GSPC) may not have is_sp500=true flag set in stock_symbols table. This causes:
- Market Health loader to fail Phase 1 data freshness check
- Affects market breadth calculations
- Breaks Tier 2 market gate logic

**Impact**: 
- Data freshness checks may use wrong symbol for S&P 500 verification
- Market health data might be incomplete
- Trading halt conditions may not trigger correctly

**Root Cause**: load_sp500_constituents.py loader may not handle benchmark index symbols properly

**Fix**: Ensure load_sp500_constituents.py explicitly marks SPY and benchmark indices with is_sp500=true

---

## HIGH SEVERITY ISSUES

### #3: Potential Database Cursor Exhaustion
**File**: Multiple files in `algo/orchestrator/`
**Severity**: HIGH
**Status**: UNFIXED

**Problem**: Multiple place where database cursors are obtained from pool but may not be returned if exception occurs:

**Locations**:
- `phase3_position_monitor.py`: Multiple execute() calls without finally blocks
- `phase4_exit_execution.py`: Similar pattern
- `algo_advanced_filters.py`: Connection management unclear

**Impact**: 
- Over time, database connection pool becomes exhausted
- Subsequent operations timeout
- Lambda functions fail with "pool exhausted" errors
- Cascade failures in orchestration phases

**Pattern Found**:
```python
conn = pool.getconn()
cur = conn.cursor()
cur.execute(...)
# If exception occurs before putconn(), connection leaks
```

**Fix**: Use try-finally blocks or context managers:
```python
try:
    conn = pool.getconn()
    cur = conn.cursor()
    cur.execute(...)
finally:
    if cur: cur.close()
    if conn: pool.putconn(conn)
```

---

### #4: Missing Null Checks After Database Queries
**File**: `lambda/api/routes/algo.py` (multiple locations)
**Severity**: HIGH
**Status**: UNFIXED

**Problem**: Array indexing without proper null/empty checks:

```python
# Line 154
pv = float(snap[0] or 0)  # snap could be None or empty list
# Line 709
portfolio_value = float(snap[0]) if snap and snap[0] else 100000.0  # snap[0] could be None
```

**Impact**: 
- IndexError if query returns no rows
- TypeError if column value is None
- Silent failures with default values

**Locations**:
- `lambda/api/routes/algo.py:154` - portfolio value calculation
- `lambda/api/routes/algo.py:157` - daily return calculation  
- `lambda/api/routes/algo.py:252` - P&L calculations
- `lambda/api/routes/algo.py:496-497` - equity curve calculation
- `lambda/api/routes/sectors.py` - sector ranking calculations

**Fix**: Always validate query results:
```python
snap = cur.fetchone()
if not snap:
    return error_response(500, 'error', 'No portfolio data found')
pv = float(snap[0] or 0)
```

---

### #5: Signal Generation Timeout Coverage Gap
**File**: `terraform/modules/pipeline/main.tf`
**Severity**: HIGH
**Status**: PARTIALLY FIXED (5/24 loaders timeout, need more)

**Problem**: While Step Functions timeouts were increased to 3000s for signal generation, individual loader timeout configs may still be too low for full S&P 500 coverage.

**Current State**:
- Step Functions: 3000s (50 min) ✓
- Individual loader ECS timeouts: Need verification

**Impact**: 
- Signal generation still times out on large symbol sets
- Only partial signal coverage (not all S&P 500 symbols)
- Incomplete trading signal universe

**Fix**: Verify all 24 loaders have sufficient timeouts:
```bash
# Check loader ECS task definitions
aws ecs describe-task-definition --task-definition algo-signals-daily-loader
# Should have containerDefinitions[0].environment[timeout] >= 1800
```

---

### #6: Market Calendar Edge Case - Partial Trading Days
**File**: `algo/algo_market_calendar.py`
**Severity**: HIGH
**Status**: UNFIXED

**Problem**: Market calendar doesn't properly handle:
- Half-day trading sessions (day before Thanksgiving, Christmas Eve, etc.)
- Early market closes (2:00 PM ET instead of 4:00 PM ET)
- These affect schedule timing for evening orchestrator run

**Impact**:
- Evening (5:30 PM ET) orchestrator might run after market closes during half-days
- Could cause positions to be evaluated with stale data
- Misalignment of data freshness checks on half-day boundaries

**Current Handling**: Only checks `is_trading_day()` (true/false), doesn't account for partial days

**Fix**: 
1. Add `get_market_close_time(date)` method to MarketCalendar
2. Return '14:00' for half-days, '16:00' for normal days
3. Use in scheduler to adjust evening run time on half-days

---

### #7: Risk Calculation Vulnerability - Missing Sector Aggregate Check
**File**: `algo/algo_position_sizer.py`
**Severity**: HIGH
**Status**: UNFIXED

**Problem**: Position sizing doesn't validate sector concentration after adding new position. Can violate sector limits by race condition:

**Scenario**:
1. Orchestrator calculates 2 simultaneous positions in same sector
2. Phase 6 executes both before rechecking sector limits
3. Ends up 15%+ in single sector (violates 30% config limit)

**Current Code Path**:
- Phase 5 filters candidates through tier constraints
- Phase 6 executes in sequence
- Between execution of 2 same-sector trades, no re-validation

**Impact**: 
- Sector concentration limits violated
- Portfolio risk exposure miscalculated
- Margin requirements exceeded
- Reduced diversification

**Fix**: In Phase 6, re-check sector limits before each execution:
```python
# Before execute_trade() in Phase 6
cur_sector_pct = self._get_current_sector_allocation(symbol)
if cur_sector_pct + new_position_pct > max_sector_pct:
    logger.warning(f"Skipping {symbol}: sector limit would be exceeded")
    continue
```

---

### #8: API Error Response Inconsistency
**File**: `lambda/api/routes/` (multiple files)
**Severity**: HIGH
**Status**: UNFIXED

**Problem**: Error responses inconsistent across handlers:
- Some return `{"statusCode": 500, "errorType": "error"}` 
- Some return `{"error": "...", "message": "..."}`
- Some return raw exceptions

**Impact**:
- Frontend error handling breaks
- Inconsistent HTTP status codes
- Client-side error parsing fails

**Example**: 
- `/api/algo/swing-scores?min_score=bad` should return 400
- Currently would return 500 with traceback
- Other endpoints might handle this gracefully

**Fix**: Standardize all API handlers to use consistent error response format

---

## MEDIUM SEVERITY ISSUES

### #9: Missing Trade ID / Recurring ID Mismatch Check
**File**: `algo/algo_trade_executor.py`
**Severity**: MEDIUM
**Status**: PARTIALLY FIXED (check recent commits)

**Problem**: Database schema has both `trade_id` (primary key) and `recurring_id` fields. Code may confuse which to use:
- Insert uses `trade_id` (UUID)
- Some queries might reference `recurring_id`
- Foreign keys could be inconsistent

**Impact**: Trade linking issues, reconciliation failures

**Check**: Run query to find orphaned records:
```sql
SELECT t.trade_id, t.symbol FROM algo_trades t
LEFT JOIN algo_positions p ON t.trade_id = ANY(p.trade_ids_arr)
WHERE p.position_id IS NULL AND t.status = 'filled';
-- Should return 0 rows
```

---

### #10: Configuration Missing for New Loaders
**File**: `terraform/terraform.tfvars`, `config/algo_config.py`
**Severity**: MEDIUM
**Status**: UNFIXED

**Problem**: Recent loaders added but configuration missing:
- `load_swing_trader_scores.py` - no timeout config in Terraform
- `load_signal_quality_scores.py` - timeout values differ from load_signals_daily.py
- Inconsistent parallelism settings

**Impact**: 
- Loaders timeout with default 300s config
- Inefficient execution (too few parallel workers)
- Incomplete data loading

**Fix**: Verify all loaders have explicit configs in terraform.tfvars and ECS task definitions

---

### #11: Weinstein Stage Missing VIX Multiplier Fallback
**File**: `algo/algo_advanced_filters.py`
**Severity**: MEDIUM
**Status**: PARTIALLY FIXED

**Problem**: When calculating VIX multiplier (line ~X), if VIX data is stale/missing:
```python
vix_score = self._vix_stress_score(eval_date)
# Returns None if no vix_data
# Hard-coded default might not be applied
```

**Impact**: 
- VIX filter silently passes stocks when VIX data missing
- Risk management incomplete during market stress

**Fix**: Ensure explicit fallback:
```python
vix_score = self._vix_stress_score(eval_date)
if vix_score is None:
    vix_score = 0.5  # Conservative default: stress regime
```

---

### #12: Position P&L Calculation Precision Loss
**File**: `algo/algo_position_monitor.py`
**Severity**: MEDIUM
**Status**: UNFIXED

**Problem**: P&L calculations use float arithmetic without rounding:
```python
pnl_pct = ((current_price - entry_price) / entry_price) * 100
```

For small positions or high share counts, floating point precision loss accumulates.

**Impact**: 
- Reported P&L off by 0.01-0.1% per position
- Portfolio-level calculations compound error
- Reconciliation reports mismatch with Alpaca

**Fix**: Use Decimal for all monetary calculations:
```python
from decimal import Decimal, ROUND_HALF_UP
pnl = (Decimal(str(current_price)) - Decimal(str(entry_price))) / Decimal(str(entry_price))
pnl_pct = float((pnl * 100).quantize(Decimal('0.01'), ROUND_HALF_UP))
```

---

### #13: Missing Dry Run Mode State Persistence
**File**: `algo/algo_orchestrator.py`
**Severity**: MEDIUM
**Status**: UNFIXED

**Problem**: Dry-run mode doesn't save results to database:
- Trades marked as 'review' or 'dry_run' status
- Database not updated
- Can't verify dry-run results
- No audit trail

**Impact**:
- Can't validate trading logic without real execution
- No backtest capability using actual production data
- Difficult to test orchestrator changes safely

**Fix**: When `dry_run=True`, save Phase 6 results to separate `algo_trades_dry_run` table:
```python
if self.dry_run:
    cur.execute("""
        INSERT INTO algo_trades_dry_run (...)
        SELECT ... FROM proposed_trades
    """)
```

---

### #14: Orchestrator Deadlock on Concurrent Portfolio Updates
**File**: `algo/algo_orchestrator.py` (Phase 3-4 boundary)
**Severity**: MEDIUM
**Status**: UNFIXED

**Problem**: If two orchestrator runs happen simultaneously (edge case with time zone confusion):
- Both fetch current positions
- Both try to update stops simultaneously
- Deadlock or lost update

**Scenario**:
1. Morning run (9:30 AM ET) starts Phase 3 position monitoring
2. Afternoon run (1:00 PM ET, if enabled) also starts Phase 3
3. Both try to UPDATE algo_positions at same time
4. PostgreSQL row locking causes one to timeout

**Impact**: 
- One orchestrator run completely skipped
- Positions not monitored or exited
- Inconsistent state

**Fix**: Add distributed lock:
```python
# At start of Phase 3
self.cur.execute("SELECT pg_advisory_lock(%s)", (hash('orchestrator_main'),))
try:
    # ... execute phases
finally:
    self.cur.execute("SELECT pg_advisory_unlock(%s)", (hash('orchestrator_main'),))
```

---

### #15: Missing Earnings Calendar Block Window Validation
**File**: `algo/algo_advanced_filters.py` (hard fail H1)
**Severity**: MEDIUM
**Status**: UNFIXED

**Problem**: Hard fail H1 (earnings within block_window) doesn't properly validate:
- Doesn't handle missing earnings_calendar data
- Defaults to "allow trade" if no earnings found (conservative but wrong)
- Should be "block" if earnings unknown

**Current Logic**:
```python
cur.execute("SELECT earnings_date FROM earnings_calendar WHERE symbol = %s")
row = cur.fetchone()
if not row:
    return True  # BUG: Allows trade if no earnings data found
```

**Impact**: 
- Trades into earnings without knowing about them
- Higher gap risk on earnings announcements
- Violates risk management policy

**Fix**:
```python
if not row:
    logger.warning(f"No earnings data for {symbol}, treating as earnings-risky")
    return False  # Block if earnings unknown
```

---

### #16: API Response Timeout Under Load
**File**: `lambda/api/lambda_function.py`
**Severity**: MEDIUM
**Status**: UNFIXED

**Problem**: API Lambda queries database without query-level timeout:
```python
cur.execute("SELECT ... FROM price_daily WHERE ...")
# No timeout - could hang forever if RDS busy
```

**Impact**:
- Long-running queries (e.g., large JOIN operations) block API
- Lambda cold-start timeout (29s API Gateway limit)
- API returns 504 on RDS spike

**Current**: RDS Proxy helps, but no per-query timeout

**Fix**: Add query timeout to all execute() calls:
```python
cur.execute("SET statement_timeout TO '10s'")
cur.execute("SELECT ...")
```

---

### #17: Missing Idempotency Check for Target Level Hits
**File**: `algo/algo_exit_engine.py`
**Severity**: MEDIUM
**Status**: UNFIXED

**Problem**: When target level is hit (T1, T2, T3), the engine tries to execute partial exit. But if the same target level is hit multiple times (price moves above then back below T1, then above again), it might execute twice:

```python
if position['target_levels_hit'] < 1 and price >= T1:
    # Execute 50% exit
    self.executor.execute_exit(...)
    # But what if price jumps above T1 + back + above T1 again?
```

**Impact**: 
- Unintended partial exits
- Position size off
- Portfolio balance incorrect

**Fix**: Track timestamp of last target hit:
```python
if position['target_1_hit_time'] is None and price >= T1:
    # First time hitting T1
    execute_exit()
    position['target_1_hit_time'] = current_date
```

---

## LOW SEVERITY ISSUES

### #18: Missing Pagination Default Validation
**File**: `lambda/api/routes/` (multiple files)
**Severity**: LOW
**Status**: UNFIXED

**Problem**: Some endpoints don't have default limits on pagination:
```python
limit = safe_limit(limit_str, max_val=50000, default=50000)
# default=50000 could return massive result sets
```

**Impact**: 
- Slow API responses
- Memory exhaustion
- Client timeout

**Fix**: Use smaller defaults:
```python
limit = safe_limit(limit_str, max_val=50000, default=100)
```

---

### #19: Uninitialized Variable in Error Path
**File**: `lambda/api/routes/algo.py`
**Severity**: LOW
**Status**: UNFIXED

**Problem**: If database query fails, variable might not be initialized:
```python
try:
    cur.execute("SELECT ... FROM nonexistent_table")
    rows = cur.fetchall()
except:
    pass
return rows  # NameError if exception occurred
```

**Impact**: Rare 500 errors if query fails

---

### #20: Inconsistent Date Formatting
**File**: Multiple API routes
**Severity**: LOW
**Status**: UNFIXED

**Problem**: Dates returned as strings with inconsistent formatting:
- Some: `2026-05-28`
- Some: `05/28/2026`
- Some: `1716892800` (Unix timestamp)

**Impact**: Frontend must handle multiple formats

**Fix**: Standardize on ISO format (2026-05-28)

---

### #21: Missing Input Validation for Symbol Parameter
**File**: `lambda/api/routes/stocks.py`, `prices.py`
**Severity**: LOW
**Status**: UNFIXED

**Problem**: Symbol parameter not validated before using in queries:
```python
symbol = params.get('symbol', [None])[0]
cur.execute("SELECT ... WHERE symbol = %s", (symbol,))
# symbol could be None, empty string, or special characters
```

**Impact**: Unexpected query behavior, potential security issues

**Fix**: Add validation:
```python
if not symbol or not re.match(r'^[A-Z0-9\-\^]{1,10}$', symbol):
    return error_response(400, 'bad_request', 'Invalid symbol')
```

---

### #22: Memory Leak in Alert Manager
**File**: `algo/algo_alerts.py`
**Severity**: LOW
**Status**: UNFIXED

**Problem**: Alert queue never cleared, could grow unbounded:
```python
class AlertManager:
    def __init__(self):
        self.alerts = []  # Never cleared!
    
    def add_alert(self, msg):
        self.alerts.append(msg)  # Grows forever
```

**Impact**: 
- Memory usage grows daily
- After 30 days: 1000+ alerts in memory
- Lambda memory spike

**Fix**: Clear after flushing:
```python
def flush(self):
    # send alerts
    self.alerts.clear()
```

---

### #23: Unused Import Causing Slow Startup
**File**: `lambda/api/lambda_function.py`
**Severity**: LOW
**Status**: UNFIXED

**Problem**: Importing heavy libraries at module level:
```python
import boto3  # Heavy, imported but might not be used on every request
import pandas  # Not used in some code paths
```

**Impact**: 
- Cold-start time increased
- Lambda duration slightly longer

**Fix**: Import only when needed:
```python
if db_secret_arn:
    import boto3
    secrets = boto3.client(...)
```

---

## SUMMARY BY CATEGORY

### API Handler Issues (6)
- #1: Unsafe float conversion (CRITICAL)
- #4: Missing null checks (HIGH)
- #8: Error response inconsistency (HIGH)
- #16: Query timeout (MEDIUM)
- #18: Missing pagination defaults (LOW)
- #21: Missing symbol validation (LOW)

### Data Loading Issues (4)
- #2: Missing S&P 500 flag (CRITICAL)
- #5: Loader timeouts (HIGH)
- #10: Missing loader configs (MEDIUM)
- #11: Missing VIX fallback (MEDIUM)

### Database/Schema Issues (5)
- #3: Connection pool exhaustion (HIGH)
- #9: Trade ID mismatch (MEDIUM)
- #14: Deadlock risk (MEDIUM)
- #22: Memory leak in alerts (LOW)
- #19: Uninitialized variable (LOW)

### Business Logic Issues (4)
- #6: Market calendar half-days (HIGH)
- #7: Sector risk race condition (HIGH)
- #12: P&L precision loss (MEDIUM)
- #15: Earnings validation (MEDIUM)
- #17: Target level idempotency (MEDIUM)

### Configuration Issues (2)
- #20: Date formatting (LOW)
- #23: Slow startup imports (LOW)

---

## PRIORITY ORDER FOR FIXES

### Phase 1 (This Week) - CRITICAL & HIGH
1. #1: Unsafe float conversion (5 min fix)
2. #2: S&P 500 symbol flag (20 min fix)
3. #3: Connection pool exhaustion (1-2 hour refactor)
4. #4: Null checks in API (30 min fix)
5. #7: Sector concentration race (45 min fix)

### Phase 2 (Next Week) - MEDIUM
6. #5: Loader timeout coverage (30 min verification)
7. #6: Market calendar half-days (1-2 hour feature)
8. #9: Trade ID consistency (1 hour audit)
9. #10: Loader configs (45 min setup)
10. #12: P&L precision (1 hour refactor)
11. #14: Deadlock prevention (1 hour)
12. #15: Earnings validation (30 min)
13. #17: Target idempotency (45 min)

### Phase 3 (Later) - LOW
14. #8: Error consistency (2 hour refactor)
15. #11: VIX fallback (20 min)
16. #16: Query timeout (30 min)
17. #18-23: Polish items (1-2 hours total)

---

## Testing Plan

After fixes, verify:
1. Run full test suite: `pytest tests/ -v`
2. API contract tests with edge cases
3. Load test with concurrent requests
4. Orchestrator dry-run with full data set
5. Database connection pool metrics

---

## Status Tracking

- [ ] Fix #1 - Unsafe float
- [ ] Fix #2 - S&P 500 flag  
- [ ] Fix #3 - Connection pooling
- [ ] Fix #4 - Null checks
- [ ] Fix #7 - Sector race
- [ ] ... (continue for all 23)

---

Generated: 2026-05-28 17:00 UTC
Next review: After all CRITICAL/HIGH fixes deployed
