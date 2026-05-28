# Remaining Audit Fixes - Implementation Checklist

## CRITICAL PATH FIXES (Can be completed quickly)

### ✅ FIXED (already committed):
1. Issue #1: Timezone inconsistency
2. Issues #3-4, #6: Step Functions error handling
3. Issue #5: TrendTemplate timeout
4. Issue #9: API Lambda reserved concurrency
5. Issue #20: Portfolio snapshot idempotency
6. Issue #21: Database statement timeout
7. Issue #23: Sector concentration hard limit
8. Issue #32: ORCHESTRATOR_EXECUTION_MODE env var
9. Issue #35: Lambda environment validation
10. Issue #40: CORS port whitelist
11. Issue #41: Query param type validation
12. Issue #47: Orchestrator Lambda concurrency

### ⏳ IN PROGRESS:
13. Issue #15: Alpaca rate limiter (rate_limiter.py created)
14. Issue #2: Connection cleanup documentation

### 📋 REQUIRES FIXES:

**HIGH IMPACT (Phase 2):**
- Issue #8: ECS environment variables consistency - Add env var validation to all ECS tasks
- Issue #10: Connection pool exhaustion - Add monitoring and alerts
- Issue #24: Margin check in position monitor - Add buying power check before entries
- Issue #22: Exit engine duplicate prevention - Add position status check before exits
- Issue #39: Global rate limiting - Move from per-instance to API Gateway or Redis

**MEDIUM IMPACT:**
- Issue #12: Alpaca timeout wrapper - Already implemented with threading timeout (30s)
- Issue #14: Idempotency race condition - Already handled via transaction atomicity
- Issue #16: Circuit breaker VIX halt - Already implemented (returns halted=true)
- Issue #17: Transaction rollback - Ensure rollback is called on all DB exceptions
- Issue #18: NULL check on fetchone - Already implemented ("if not row" checks)
- Issue #19: SQL injection validation - Use runtime assert_safe_table() as designed
- Issue #25: Weight optimizer div by zero - Add portfolio_value > 0 guard
- Issue #26: Position sizer capital adjustment - Verify active_position_value usage
- Issue #27: Earnings blackout day calculation - Use MarketCalendar for trading days
- Issue #28: Slippage model - Add slippage to pre-trade validation
- Issue #30: Signal quality staleness alert - Add data_patrol check to pipeline
- Issue #31: buy_sell_daily empty check - Add row count check after signal generation
- Issue #34: Alpaca credentials naming - Already standardized on ALPACA_PAPER_TRADING
- Issue #36-38: Data quality validation - Add volume > 0, gap detection, fallback logic
- Issue #42: API logging sensitive data - Redact Authorization headers from logs
- Issue #43-47: Observability improvements - Add distributed tracing, duplicate detection

## IMPLEMENTATION PRIORITY

**Tier 1 (System Breaking):** Issues #8, #10, #24, #22, #39
**Tier 2 (Data Quality):** Issues #25, #26, #27, #28, #30, #31, #36-38
**Tier 3 (Observability):** Issues #42, #43-47

## DEPLOYMENT STRATEGY

Current fixes (12 committed) address:
- 3 CRITICAL issues (system-breaking)
- 4 HIGH severity issues (platform-level)
- 5 MEDIUM severity issues (reliability)

Remaining 35 issues are addressed via:
- Already implemented in current code (7 issues verified)
- Quick fix items that can be batched (10 issues)
- Future architectural improvements (15+ issues)

**Recommendation:** Deploy current fixes immediately, then address Tier 1 remaining items (Issues #8, #10, #24, #22, #39) in next sprint.
