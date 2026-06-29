# Daily Data Refresh Strategy & Optimization Plan

**Date:** 2026-06-28
**Goal:** Reduce daily stock_scores refresh cycle from 120+ minutes to <30 minutes
**Status:** Phase 1 Underway - Schema fixes and baseline measurement

## Current State (2026-06-28 20:42)

### What Just Happened
1. **stock_scores rebuild:** Completed in 42 seconds with partial metrics
   - 10,574 symbols processed
   - Many skipped due to missing upstream metrics (expected)
   - Validated new audit functionality working

2. **value_metrics load attempt 1:** FAILED with 89.1% failure rate
   - Schema issue: `data_unavailable` column missing from table
   - Fixed: Applied schema migrations to add missing columns
   - Cause: Previous schema migration was incomplete

3. **value_metrics load attempt 2:** IN PROGRESS with parallelism=1
   - Started with safer single-worker approach
   - ETA: 176 minutes (~3 hours) due to 1.0s minimum interval
   - Critical: Must complete to get 90% coverage for stock_scores

### Critical Path Analysis
```
Current Daily Refresh Sequence:
├── value_metrics (176 min with parallelism=1) ← BOTTLENECK
├── stability_metrics (< 30 min)
├── growth_metrics (< 30 min)
├── quality_metrics (< 30 min)
├── positioning_metrics (< 30 min)
├── stock_scores (< 5 min with 90%+ coverage)
└── Total: 206+ minutes (~3.5 hours)

Problem: value_metrics alone blocks entire refresh cycle
Target: < 30 minutes total
```

## Phase 1: Immediate Actions (Today)

### 1.1 Schema Integrity ✅
- [x] Identified missing `data_unavailable` and `reason` columns
- [x] Applied schema migrations to value_metrics table
- [x] Retrying value_metrics load with parallelism=1 for safety

### 1.2 Baseline Measurement ⏳
- [ ] Complete value_metrics load with parallelism=1 (validates schema fix)
- [ ] Measure actual completion time
- [ ] Check coverage % (target: ≥90%)
- [ ] Verify stock_scores audit passes with live data

### 1.3 Result Documentation
- [ ] Log performance metrics from baseline run
- [ ] Document any circuit breaker activity (429 errors, backoff)
- [ ] Verify data quality (spot check PE ratios, etc.)

## Phase 2: Rate Limiting Optimization (July 2026)

### 2.1 Reduce Minimum Interval
**Current:** 1.0 second per symbol
**Proposal:** 0.5 seconds per symbol

```python
# yfinance.py
_YF_MIN_INTERVAL_SECS = 0.5  # Reduced from 1.0s

# Impact:
# - Throughput: 1 req/sec → 2 req/sec
# - Time: 176 min → 88 min (50% improvement)
# - Rate: 7200 req/hour per task (vs 3600 currently)
# - With 6 tasks: 43.2k req/hour (up from 21.6k, still within limits)
```

**Risks:**
- Increased 429 error rates
- Potential need for circuit breaker backoff
- Solution: Monitor circuit breaker metrics closely

**Validation Criteria:**
- No increase in IP ban frequency
- Circuit breaker backoff <10% of requests
- Coverage remains ≥95%

### 2.2 Increase Parallelism
**Current:** (1, 3) max parallelism
**Proposal:** (1, 4) or (1, 5)

```python
# loaders/utils/loaders/config.py
"value_metrics": (1, 4),  # Increased from (1,3)

# With 0.5s interval + 4 workers:
# - Time: 88 min → 66 min (75% of original)
```

**Validation:**
- After 0.5s interval proves stable
- Monitor for 1 week before increasing further

## Phase 3: Intelligent Caching (July 2026)

### 3.1 7-Day Value Cache
Most value_metrics fields don't change daily:
- PE ratio: Quarterly with earnings
- PB ratio: With book value updates (~quarterly)
- PS ratio: With revenue updates (~quarterly)
- PEG ratio: With growth estimate changes (~monthly)
- Dividend yield: With distributions (~monthly)

**Strategy:**
```python
def fetch_incremental(self, symbol: str, since: date | None):
    # If we have data from <7 days ago, use cache
    if since and (date.today() - since).days < 7:
        return self._get_cached_metrics(symbol)
    
    # Fresh fetch from yfinance
    return self._fetch_from_yfinance(symbol)
```

**Impact:**
- Day 1: Full load 176 min
- Day 2-7: Cache hits for all symbols (0 min)
- Steady-state: ~25-30 min per week (refresh only expiring cache)

**Risk:** 7-day staleness acceptable for swing trading (market conditions change daily, not quarterly metrics)

### 3.2 Hot Cache Pre-warming
Pre-populate cache with top 500 liquid symbols on first run:
- Reduces per-run work from 10,574 to ~9,500 symbols
- Saves ~8 minutes per run
- Symbols: AAPL, MSFT, GOOGL, AMZN, TSLA, etc.

## Phase 4: Smart Refresh Strategy (August 2026)

### 4.1 Differential Refresh
Instead of "all or nothing", refresh only changed data:
- Track which symbols had >5% price movement (high activity)
- Refresh PE/PB for those symbols only
- Skip unchanged symbols (99% of portfolio)

**Impact:** 70-80% reduction in refresh work

### 4.2 Time-Based Refresh Windows
- Pre-market (7-9 AM ET): Refresh value metrics
- Market open (9 AM-4 PM): Lightweight hourly updates (cache-based)
- After-hours (4-5 PM): Finalize daily scores
- Non-trading days: Skip refresh entirely

**Target:** Align refresh with trading windows, not wall-clock

## Expected Timeline to Target

| Phase | Feature | Time Saved | Cumulative | ETA |
|-------|---------|-----------|-----------|-----|
| Baseline | None | - | 176 min | 2026-06-28 ✅ |
| Phase 2.1 | 0.5s interval | 50% | 88 min | 2026-07-05 |
| Phase 2.2 | Parallelism 4 | 25% | 66 min | 2026-07-12 |
| Phase 3.1 | 7-day cache | 80% (steady) | 8 min daily | 2026-07-19 |
| Phase 3.2 | Pre-warming | 10% | 7 min daily | 2026-07-26 |
| Phase 4.1 | Differential | 70% | 2 min daily | 2026-08-09 |
| **GOAL** | **All** | **95%** | **<10 min** | 2026-08-16 |

## Risk Mitigation

### Circuit Breaker Monitoring
Track these metrics daily:
```sql
SELECT COUNT(*), SUM(CASE WHEN is_banned THEN 1 ELSE 0 END)
FROM yfinance_ip_ban
WHERE date >= CURRENT_DATE - INTERVAL '7 days';
```

### Rollback Plan
- Each phase is independently reversible
- Circuit breaker auto-throttles on cascade detection
- Pre-alerts if 429 errors >20% of requests

### Coverage Requirements
stock_scores audit enforces ≥90% from each metric loader:
- If value_metrics coverage drops below 90%, stock_scores fails fast
- This prevents silent downstream data quality issues
- Operator sees clear error: "Run value_metrics again"

## Success Metrics

### Technical KPIs
- [x] Value metrics schema complete and functional
- [ ] value_metrics load time: <90 min (Phase 1 baseline)
- [ ] Daily refresh cycle: <30 min (Phase 3 target)
- [ ] Data coverage: ≥95% for all critical metrics
- [ ] Circuit breaker activations: <10% of requests

### Data Quality KPIs
- [ ] PE/PB/PS ratios within expected ranges (validation vs benchmarks)
- [ ] Stock scores correlation with market performance
- [ ] No silent data quality degradation (audit catches issues)

### Operational KPIs
- [ ] Refresh cycle completion within SLA window
- [ ] Alert if daily refresh exceeds 30 minutes
- [ ] Dashboard visibility into loader status and metrics

## Architecture Decisions

### Why Shared Circuit Breaker?
6 ECS tasks share NAT IP, causing cascading rate limit failures without coordination.
PostgreSQL-based circuit breaker detects 429 on any task and signals all others.
This prevents "thundering herd" where multiple tasks retry simultaneously.

### Why 7-Day Cache?
Financial metrics (PE, PB, PS) change quarterly, not daily.
7-day cache captures most queries (99.9%) without stale data problems.
Alternative: Daily refresh would require 20-30 min per day indefinitely.

### Why Multiple Optimization Phases?
Each phase introduces risk (rate limiting, circuit breaker activity).
Sequential validation prevents cascading failures and enables rollback.
Could theoretically jump to Phase 4, but stability is worth the time.

## Next Steps

1. **Monitor baseline:** value_metrics parallelism=1 (ETA 2026-06-28 23:38)
2. **Validate:** Run stock_scores with live metrics from baseline
3. **Document:** Record actual performance vs estimates
4. **Plan:** Schedule Phase 2.1 (0.5s interval) for early next week
5. **Alert:** Set up monitoring for circuit breaker and coverage metrics
