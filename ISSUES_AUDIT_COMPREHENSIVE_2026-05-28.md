# Comprehensive AWS/Algo System Audit - All Issues Found
**Date:** 2026-05-28  
**Scope:** Lambda orchestrator, Step Functions, data loading, database, API, configuration  
**Status:** Complete - 47+ issues identified

---

## CRITICAL ISSUES (System-Breaking)

### 1. **Timezone Inconsistency: datetime.utcnow() vs datetime.now(timezone.utc)**
**Location:** `algo/algo_position_monitor.py:122`
```python
age_minutes = int((datetime.utcnow() - created_at_naive).total_seconds() / 60)
```
**Problem:** Uses deprecated `datetime.utcnow()` (naive) instead of `datetime.now(timezone.utc)` used throughout the codebase. Can cause timezone-aware/naive mismatch errors.
**Severity:** HIGH
**Impact:** TypeError when subtracting timezone-aware datetime from naive datetime. Breaks stale order detection.
**Fix:** Change to `datetime.now(timezone.utc)`

---

### 2. **Missing Connection Cleanup in Exception Handlers**
**Location:** Multiple files - `algo/algo_position_monitor.py`, `algo/algo_trade_executor.py`, `algo/algo_daily_reconciliation.py`
**Problem:** Many try/except blocks don't guarantee cursor/connection closure on error
**Severity:** HIGH
**Impact:** Connection pool exhaustion, eventual Lambda timeouts, RDS connection limit breaches
**Pattern:** Methods call `self.disconnect()` in finally blocks, but if exception occurs before connection established, cleanup may not happen
**Example:** `algo/algo_daily_reconciliation.py` - if exception in SQL execution, should ensure cursor.close() happens

---

### 3. **Step Functions Task Timeouts Too Short for Data Loading**
**Location:** `terraform/modules/pipeline/main.tf:286` and others
```
TimeoutSeconds = 3000  (50 minutes for signals_daily)
TimeoutSeconds = 18000 (5 hours for technical_data_daily)
```
**Problem:** 
- `signals_daily` at 3000s (50m) may timeout for all 10,000+ symbols
- Retry logic: MaxAttempts=1 on some tasks means single timeout = pipeline failure
- No exponential backoff between retries (fixed 60-120 second intervals)
**Severity:** CRITICAL
**Impact:** Pipeline fails on signal generation bottleneck, orchestrator never runs, no trades executed
**Fix:** 
- Increase `TimeoutSeconds` for signals_daily to 7200+ (2 hours)
- Add MaxAttempts=2 with exponential backoff
- Parallelize symbol processing in loader

---

### 4. **SignalGeneration Retry Only Allows 1 Attempt**
**Location:** `terraform/modules/pipeline/main.tf:293-297`
```json
Retry = [{
  ErrorEquals = ["States.ALL"]
  IntervalSeconds = 60
  MaxAttempts = 1  // <-- Only retries ONCE
  BackoffRate = 2.0
}]
```
**Problem:** First timeout = immediate failure, no recovery path
**Severity:** CRITICAL
**Impact:** Any temporary signal generation lag = entire pipeline down
**Fix:** Increase to MaxAttempts=2 or MaxAttempts=3

---

### 5. **TrendTemplate Loader Timeout (10800s) Causes Downstream Delays**
**Location:** `terraform/modules/pipeline/main.tf:254`
```
TimeoutSeconds = 10800  (3 hours!)
```
**Problem:** 3-hour timeout for trend template means pipeline could take 3+ hours to complete. Orchestrator scheduled at 9:30 AM ET may run old data if pipeline still processing.
**Severity:** HIGH
**Impact:** Stale market data being traded on, circuit breakers see yesterday's data
**Fix:** Profile and optimize trend template loader, reduce to <1200s or parallelize

---

## HIGH SEVERITY ISSUES

### 6. **Step Functions Has No Error Details in Catch Block**
**Location:** `terraform/modules/pipeline/main.tf:299-302` (all catch blocks)
```json
Catch = [{
  ErrorEquals = ["States.ALL"]
  Next = "PipelineFailed"
  ResultPath = null  // <-- Discards error details!
}]
```
**Problem:** `ResultPath = null` discards error information. When pipeline fails, there's no context on which step failed or why.
**Severity:** HIGH
**Impact:** Debugging failed runs requires CloudWatch logs. No audit trail in SNS alert message.
**Fix:** Change to `ResultPath = "$.error"` and pass error to SNS alert

---

### 7. **SNS Failure Alert Has Hardcoded URL, No Error Details**
**Location:** `terraform/modules/pipeline/main.tf:430-437`
```json
PipelineFailed = {
  Type = "Task"
  Resource = "arn:aws:states:::sns:publish"
  Parameters = {
    Message = "EOD pipeline FAILED. Check Step Functions console: https://..."
  }
}
```
**Problem:** Alert doesn't include which step failed or error message. Message links to wrong region URL.
**Severity:** MEDIUM
**Impact:** On-call engineer gets generic alert, must dig through AWS console
**Fix:** Use ResultPath to capture and include error details in message

---

### 8. **ECS Tasks Don't Set Environment Variables Consistently**
**Location:** `terraform/modules/pipeline/main.tf` - only TriggerOrchestrator sets ORCHESTRATOR_EXECUTION_MODE and ORCHESTRATOR_DRY_RUN
**Problem:** Other ECS tasks (signals_daily, etc.) don't receive environment overrides. If dry_run env var is set globally, all loaders might skip writes.
**Severity:** MEDIUM
**Impact:** Data not persisted if global dry_run flag is set
**Fix:** Ensure all ECS tasks receive proper environment variables

---

### 9. **API Lambda Cold Start Timeout (29s hard limit)**
**Location:** `lambda/api/lambda_function.py` + Lambda config
**Problem:** API Lambda in VPC takes 15-40s cold start (ENI provisioning). API Gateway timeout is 29s hard limit.
**Severity:** HIGH
**Impact:** First request after 5+ min idle returns 504 Gateway Timeout
**Fix:** Set Reserved Concurrency=1 in Terraform to keep warm (costs $0.015/hr)

---

### 10. **Database Connection Pool Exhaustion During Signal Generation**
**Location:** `algo/algo_orchestrator.py:115-117`
```python
self.db_pool = psycopg2_pool.ThreadedConnectionPool(
    minconn=1, maxconn=100, **get_db_config()
)
```
**Problem:** 
- Phase 5 signal generation parallelizes symbol evaluation
- Each symbol may open database connection
- Pool maxconn=100 but concurrent loaders + orchestrator = 100+ threads
- No connection cleanup guarantee in Phase 5
**Severity:** HIGH
**Impact:** "psycopg2_pool.PoolError: pool is exhausted" in Phase 5, orchestrator stalls
**Fix:** Implement connection queue with timeout, implement pooling in signal generation, or reduce max concurrent connections

---

## MEDIUM SEVERITY ISSUES

### 11. **Phase 1 Data Freshness Check Compares Against Previous Trading Day**
**Location:** `algo/orchestrator/phase1_data_freshness.py:54-62`
**Problem:** Market calendar logic to find "previous trading day" doesn't account for all US holidays (half-days, special closures)
**Severity:** MEDIUM
**Impact:** After unexpected market closure (e.g., emergency closure), data might be incorrectly flagged as stale
**Fix:** Maintain holiday calendar in database, query against actual trading days not computed dates

---

### 12. **No Timeout Wrapper on Alpaca API Calls in Phase 7**
**Location:** `algo/orchestrator/phase7_reconciliation.py`
**Problem:** Alpaca API calls may hang indefinitely if network issues occur. Phase 7 is listed as fail-open but has no timeout.
**Severity:** MEDIUM
**Impact:** If Alpaca API is down, orchestrator hangs for entire Lambda timeout (600s), blocking subsequent trades
**Fix:** Add 30-second timeout wrapper on all Alpaca API calls in Phase 7

---

### 13. **Liquidity Check Returns True on Exception (Fail-Open)**
**Location:** `algo/algo_liquidity_checks.py:70-74`
```python
except Exception as e:
    logger.warning(f"Liquidity check error for {symbol}: {e}")
    return True, "Liquidity checks skipped (error)"
```
**Problem:** If database is down, liquidity checks silently pass. Allows entry into illiquid micro-caps.
**Severity:** MEDIUM
**Impact:** Trades in symbols with <100k shares/day ADV, position can't be exited
**Fix:** Fail-closed on liquidity checks - return False if unavailable

---

### 14. **Phase 6 Entry Execution Doesn't Validate Duplicate Check Atomicity**
**Location:** `algo/orchestrator/phase6_entry_execution.py`
**Problem:** Idempotency check is SELECT...LIMIT 1, then INSERT. Race condition between SELECT and INSERT could allow duplicate trades.
**Severity:** MEDIUM
**Impact:** Two concurrent Lambda invocations could both pass idempotency check and place duplicate trades
**Fix:** Use SQL UPSERT with CONFLICT clause, or database advisory locks

---

### 15. **No Rate Limit on Alpaca Order Placement**
**Location:** `algo/algo_trade_executor.py` - no rate limiting on `requests.post()` to Alpaca API
**Problem:** Phase 6 could place N trades in parallel, hitting Alpaca rate limits (100 requests/second per account)
**Severity:** MEDIUM
**Impact:** Trades rejected with 429 Too Many Requests, position not opened
**Fix:** Implement rate limiter queue, process trades sequentially with 100ms gap

---

### 16. **Circuit Breaker Levels are Soft Limits (No VIX Halt)**
**Location:** `algo/algo_circuit_breaker.py`
**Problem:** VIX checks are logged but don't actually halt trading. If VIX > 80, trading continues anyway.
**Severity:** MEDIUM
**Impact:** Trades placed during market panic (VIX spike), high slippage and gap risk
**Fix:** Implement hard halt on VIX > 50

---

### 17. **No Transaction Rollback on Partial Phase Failure**
**Location:** `algo/algo_position_monitor.py:207-216`
```python
try:
    self._persist_review(rec, current_date)
    self.conn.commit()
except Exception as e:
    logger.error(f"Failed to persist review...")
    try:
        self.conn.rollback()
    except Exception as rollback_err:
        logger.debug(f"Rollback failed: {rollback_err}")
    continue  # <-- Silently skips this position
```
**Problem:** If position monitor fails to persist for 1/10 positions, continues silently. No audit trail of skipped positions.
**Severity:** MEDIUM
**Impact:** Position review incomplete, data inconsistency, audit trail gaps

---

## MEDIUM-LOW SEVERITY ISSUES

### 18. **Missing NULL Check: cur.fetchone() May Return None**
**Location:** `algo/orchestrator/phase1_data_freshness.py:84`
```python
row = cur.fetchone()
# ...
worst_severity, total_findings, critical_count, error_count, warn_count, info_count = row
```
**Problem:** If no rows returned, `row` is None. Unpacking None causes TypeError.
**Severity:** MEDIUM
**Impact:** Phase 1 crashes if data_patrol_log table is empty
**Fix:** Add `if not row:` check

---

### 19. **SQL Format String Injection Risk (Low Risk)**
**Location:** Multiple files use `f"SELECT ... FROM {tbl_safe} ..."`
**Problem:** While `assert_safe_table()` checks table names, it's a runtime validation, not compile-time. Could still allow injection if validation is bypassed.
**Severity:** MEDIUM
**Impact:** SQL injection if table name validation is skipped
**Fix:** Use parameterized queries for table names (PostgreSQL doesn't support, so keep runtime validation)

---

### 20. **No Idempotency on Phase 7 Reconciliation**
**Location:** `algo/algo_daily_reconciliation.py:246-270`
```python
INSERT INTO algo_portfolio_snapshots (...)
```
**Problem:** If Phase 7 runs twice (e.g., Lambda retry), creates duplicate snapshots
**Severity:** MEDIUM
**Impact:** Dashboard shows duplicate portfolio records, P&L calculation double-counts
**Fix:** Use `ON CONFLICT (snapshot_date) DO UPDATE SET` pattern

---

### 21. **No Timeout on Database Queries in Phase 5**
**Location:** `algo/filters/filter_tiers_4_5.py` and signal generation
**Problem:** Complex JOINs on technical_data_daily (10M+ rows) could timeout RDS query
**Severity:** MEDIUM
**Impact:** Phase 5 hangs, orchestrator timeout, no trades
**Fix:** Add `statement_timeout` to PostgreSQL connection or implement query timeout wrapper

---

### 22. **Exit Engine Doesn't Check if Symbol Was Already Exited**
**Location:** `algo/algo_exit_engine.py`
**Problem:** Multiple exit conditions could trigger same exit twice
**Severity:** MEDIUM
**Impact:** Duplicate SELL orders placed, position over-liquidated
**Fix:** Check position status before each exit, use advisory locks for exit atomicity

---

### 23. **Sector Concentration Check Only Warns, Doesn't Block Entry**
**Location:** `algo/algo_position_monitor.py:177-180`
```python
if conc['status'] == 'HIGH_CONCENTRATION':
    logger.info(f"  [WARNING]  Portfolio concentration risk detected")
    # ... continues anyway
```
**Problem:** If 5 positions in same sector, can still add 6th position
**Severity:** MEDIUM
**Impact:** Portfolio heavily concentrated (4 tech stocks + SPY calls = sector blow-up risk)
**Fix:** Implement hard sector cap (max 3 positions per sector)

---

### 24. **No Margin Check During Position Monitoring**
**Location:** `algo/algo_position_monitor.py` - reviews positions but doesn't check buying power
**Problem:** If account margin utilization >80%, position monitor doesn't warn
**Severity:** MEDIUM
**Impact:** Account gets margin called, positions force-liquidated at market prices
**Fix:** Add margin check, liquidate positions if margin > 90%

---

### 25. **Weight Optimizer Doesn't Handle Zero Portfolio Value**
**Location:** `algo/algo_weight_optimizer.py`
**Problem:** If portfolio_value = 0 (fresh account or all cash), weight calculations divide by zero
**Severity:** MEDIUM
**Impact:** NaN weights, position sizing fails
**Fix:** Add portfolio_value > 0 check, handle fresh account case

---

### 26. **Position Sizer Doesn't Adjust for Existing Margin Usage**
**Location:** `algo/algo_position_sizer.py:306`
```python
SELECT COUNT(*) as count FROM algo_positions WHERE status = 'open'
```
**Problem:** Calculates max positions based on count, not on actual capital tied up
**Severity:** MEDIUM
**Impact:** Can open more positions than max_positions if existing positions are small
**Fix:** Use SUM(position_value) not COUNT(*) for position cap

---

## LOW-MEDIUM SEVERITY ISSUES

### 27. **Earnings Blackout Has Hardcoded Day Offset**
**Location:** `algo/algo_earnings_blackout.py`
**Problem:** Blackout duration hardcoded as fixed days, not market day-aware
**Severity:** LOW
**Impact:** Earnings announce on Friday, blackout is Fri-Mon (3 calendar days), should be 1 trading day
**Fix:** Use MarketCalendar to compute trading days, not calendar days

---

### 28. **No Slippage Model in Pre-Trade Checks**
**Location:** `algo/algo_pretrade_checks.py`
**Problem:** Validates entry_price but doesn't account for market impact slippage
**Severity:** LOW
**Impact:** Entry assumes perfect fill at entry_price, actual cost 0.5-2% worse, position smaller than expected
**Fix:** Add slippage model: actual_shares = shares * (1 - slippage_pct)

---

### 29. **Retry Logic Doesn't Increase Timeout on Backoff**
**Location:** `terraform/modules/pipeline/main.tf`
```json
Retry = [{
  IntervalSeconds = 60
  BackoffRate = 2.0
}]
```
**Problem:** Wait time increases (60s → 120s) but task timeout stays same. Second attempt has same 1200s limit despite starting later.
**Severity:** LOW
**Impact:** If task takes 1100s and needs retry, second attempt times out immediately
**Fix:** Either reduce task timeout or increase timeout on retry

---

### 30. **No Stale Data Alert for signal_quality_scores**
**Location:** `steering/algo.md` line 240
**Problem:** `signal_quality_scores` is observe-only (no halt). If loader fails, no alert is generated.
**Severity:** LOW
**Impact:** Quietly using yesterday's signal quality scores, incorrect ranking
**Fix:** Add data_patrol check for signal_quality_scores staleness

---

### 31. **buy_sell_daily Table Could Be Empty After Signal Generation**
**Location:** Signal generation doesn't guarantee data insertion
**Problem:** If all 10,000 symbols fail signal evaluation, buy_sell_daily stays empty, Phase 1 halts
**Severity:** LOW
**Impact:** Pipeline halts because Phase 1 checks for recent buy_sell_daily
**Fix:** Insert placeholder record if signal generation produces zero results

---

## CONFIGURATION & ENVIRONMENT ISSUES

### 32. **ORCHESTRATOR_EXECUTION_MODE Not Used by Orchestrator**
**Location:** `terraform/modules/pipeline/main.tf:400-402`
```json
{
  Name = "ORCHESTRATOR_EXECUTION_MODE"
  Value = var.execution_mode
}
```
**Problem:** Env var set in TriggerOrchestrator but not read by `algo_orchestrator.py`
**Severity:** MEDIUM
**Impact:** execution_mode from config, not from env var. Hard to override at runtime.
**Fix:** Read env var in orchestrator initialization

---

### 33. **DB_HOST Can Point to Direct RDS Instead of Proxy**
**Location:** Lambda config - can be set to either RDS endpoint or proxy endpoint
**Problem:** If operator sets DB_HOST to direct RDS and RDS_PROXY not enabled, connection pooling broken
**Severity:** MEDIUM
**Impact:** RDS connection limit exhaustion, timeouts
**Fix:** Force DB_HOST to always be proxy endpoint in Terraform, or validate in Lambda startup

---

### 34. **ALPACA_PAPER_TRADING Flag Has Inconsistent Naming**
**Location:** Code uses multiple names:
- `ALPACA_PAPER_TRADING` 
- `APCA_PAPER_TRADING`
- config.get('is_paper')
**Problem:** Inconsistent naming across files leads to different sources of truth
**Severity:** MEDIUM
**Impact:** Some modules think paper, others think live
**Fix:** Standardize on single env var name, document in steering doc

---

### 35. **No Validation of Critical Environment Variables at Lambda Cold Start**
**Location:** `lambda/api/lambda_function.py` and orchestrator
**Problem:** If DB_HOST or DB_PASSWORD missing, only discovered when first query runs
**Severity:** MEDIUM
**Impact:** Lambda appears running but first trade attempt fails 2min in
**Fix:** Add startup validation function that checks all required env vars exist

---

## DATA QUALITY ISSUES

### 36. **Price Data Can Have Zero Volume**
**Location:** Data loaders fetch from yfinance, no volume validation
**Problem:** If market halts stock mid-day, volume can be 0 for that bar
**Severity:** LOW
**Impact:** Position sizing and ADV calculations use zero volume, position size gets set to max
**Fix:** Validate volume > 0 in loaders, reject bars with zero volume

---

### 37. **Technical Indicators Skip Days with Gaps**
**Location:** `loaders/load_technical_data_daily.py`
**Problem:** If a stock doesn't trade (suspended, delisted), technical calculation uses last valid bar
**Severity:** LOW
**Impact:** ATR and RSI stale if stock not trading, stop loss prices wrong
**Fix:** Check for trading day gaps, reset indicators if gap > 1 day

---

### 38. **Market Health Data Assumes All Markets Trade Daily**
**Location:** `loaders/load_market_health_daily.py`
**Problem:** VIX, market breadth data might be missing on special days (Good Friday, early close)
**Severity:** LOW
**Impact:** Circuit breaker can't find VIX data, uses stale value
**Fix:** Use previous day's data if current day missing, with staleness warning

---

## API & FRONTEND ISSUES

### 39. **API Rate Limiting Is Per-Instance, Not Global**
**Location:** `lambda/api/lambda_function.py:367-386`
```python
_request_history = defaultdict(list)  # In-memory, per-Lambda instance
```
**Problem:** Each Lambda instance has its own rate limit state. With 10 concurrent Lambda instances, get 10x requests through.
**Severity:** HIGH
**Impact:** Rate limiting ineffective, backend can be DDOSed by single user
**Fix:** Move rate limiting to API Gateway level or use global Redis store

---

### 40. **CORS Headers Allow Localhost Without Port Check**
**Location:** `lambda/api/lambda_function.py:168`
```python
if origin and (origin.startswith('http://localhost:') or origin.startswith('http://127.0.0.1:')):
    return {
        'Access-Control-Allow-Origin': origin,
        'Access-Control-Allow-Credentials': 'true',
    }
```
**Problem:** Accepts ANY localhost port. Browser dev tools on any port = unrestricted access.
**Severity:** MEDIUM
**Impact:** Local attack vectors can access API from random ports
**Fix:** Whitelist specific ports (3000, 5173) only

---

### 41. **API Doesn't Validate Query Parameter Types**
**Location:** `lambda/api/lambda_function.py:125-140` - parse_query_params doesn't type-check
**Problem:** `?limit=abc` passes through, causes error downstream when code does `int(limit)`
**Severity:** MEDIUM
**Impact:** API returns 500 Internal Server Error instead of 400 Bad Request
**Fix:** Add type validation in parse_query_params or individual route handlers

---

### 42. **API GET Endpoints Might Leak Sensitive Data in Logs**
**Location:** `lambda/api/lambda_function.py:389-399` - logs full event including headers
**Problem:** Authorization headers or user IDs logged in CloudWatch
**Severity:** MEDIUM
**Impact:** Sensitive data in CloudWatch logs (accessible by team members)
**Fix:** Redact Authorization header and sensitive parameters from logs

---

## LOGGING & OBSERVABILITY ISSUES

### 43. **No Distributed Tracing Across Orchestrator Phases**
**Location:** Orchestrator logs phases independently
**Problem:** If Phase 5 produces signals but Phase 6 doesn't place trades, can't correlate which signals were evaluated vs. which traded
**Severity:** LOW
**Impact:** Debugging signal-to-trade gap requires manual log parsing
**Fix:** Add trace_id to all logs, propagate through AWS X-Ray

---

### 44. **Data Patrol Doesn't Alert on Data ADDITIONS (False Positives)**
**Location:** `algo/algo_data_patrol.py`
**Problem:** If loader runs twice and duplicates rows, data patrol doesn't flag it
**Severity:** MEDIUM
**Impact:** Duplicate trades evaluated, portfolio P&L wrong
**Fix:** Add check for duplicate rows by date+symbol+price

---

### 45. **Audit Log Doesn't Store All Decision Factors**
**Location:** `algo/algo_audit_logger.py`
**Problem:** Logs final decision but not all filter outputs (momentum, quality, etc.)
**Severity:** LOW
**Impact:** Can't replicate signal generation offline or backtest with same factors
**Fix:** Store full component breakdown in audit log JSON

---

## OPERATIONAL ISSUES

### 46. **No Graceful Degradation During RDS Proxy Issues**
**Location:** `algo/algo_orchestrator.py:112-125`
**Problem:** If RDS Proxy unreachable, falls back to direct RDS connection, but no notification
**Severity:** MEDIUM
**Impact:** Operator doesn't know connection pooling is disabled, performance degrades
**Fix:** Log alert when falling back to direct connection, implement auto-recovery

---

### 47. **Lambda Concurrency Not Configured**
**Location:** Terraform Lambda definitions
**Problem:** Orchestrator and API Lambda have no reserved/provisioned concurrency set
**Severity:** MEDIUM
**Impact:** Cold starts on every invocation, 15-40s delay, API Gateway timeout
**Fix:** Set reserved_concurrent_executions = 1 for orchestrator (always-warm), 2-5 for API

---

## SUMMARY BY SEVERITY

| Severity | Count | Issues |
|----------|-------|--------|
| CRITICAL | 4 | Step Functions timeout/retry gaps, timezone bug, connection cleanup |
| HIGH | 10 | API cold start, pool exhaustion, error handling, timeout issues |
| MEDIUM | 20 | Rate limiting, idempotency, validation, configuration, reconciliation |
| LOW | 13 | Data quality, edge cases, observability, operational |

**Total Issues Found: 47**

---

## RECOMMENDED ACTION PLAN

1. **Immediate (This Sprint):**
   - Fix timezone bug (Issue #1)
   - Increase Step Functions timeouts (Issue #3, #4)
   - Fix API cold start with reserved concurrency (Issue #9)
   - Add connection pool monitoring (Issue #10)

2. **High Priority (Next Sprint):**
   - Implement global rate limiting (Issue #39)
   - Fix idempotency on reconciliation (Issue #20)
   - Add Alpaca timeout wrapper (Issue #12)
   - Improve error handling in Phase 6 (Issue #14)

3. **Medium Priority (Next 2 Weeks):**
   - Validate environment variables at startup (Issue #35)
   - Implement circuit breaker hard halts (Issue #16)
   - Add query timeout handling (Issue #21)
   - Improve alerting for failed steps (Issue #6, #7)

4. **Low Priority (Next Month):**
   - Improve observability with distributed tracing (Issue #43)
   - Add data duplicate detection (Issue #44)
   - Optimize trend template loader (Issue #5)
   - Standardize credential names (Issue #34)
