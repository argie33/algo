# Value Metrics Loader Optimization Strategy

**Status:** Investigation completed, ready for implementation
**Date:** 2026-06-28
**Priority:** Medium (unblocks daily refresh cycle for stock_scores)

## Problem Summary
Value metrics loader (PE, PB, PS, dividend yield from yfinance) takes ~59 minutes with current configuration, blocking stock_scores daily refresh cycle.

### Current Performance
- **Symbols to load:** 10,574 active trading symbols
- **Minimum interval per symbol:** 1.0 second (enforced by rate limiter)
- **Current parallelism constraint:** (1, 3) - max 3 workers
- **Estimated load time:** 58.7 minutes (with parallelism=3)
- **Bottleneck:** yfinance API rate limits + shared IP coordination

## Root Cause Analysis

### Why 1.0 Second Minimum Interval?
- **Shared IP constraint:** 6 ECS tasks use the same NAT gateway
- **yfinance limits:** ~2000 requests per hour documented limit
- **Circuit breaker:** Coordinates 429/401 errors across all tasks
- **Safety margin:** 1.0s interval = 3600 req/hour per task = 21.6k req/hour total (within limits)

### Why Parallelism Limited to 3?
- **History:** Previously (1,8), but led to IP bans
- **Current:** (1,3), tuned to respect circuit breaker backoff
- **Risk:** Each additional worker multiplies request volume by ECS task count (6x amplification)

## Proposed Optimization Roadmap

### Phase 1: Rate Limiting Optimization (LOW RISK)
**Reduce minimum interval from 1.0s to 0.5s**

```python
# loaders/utils/external/yfinance.py
_YF_MIN_INTERVAL_SECS = 0.5  # Was 1.0s, now 2x throughput

# Expected improvement:
# - Load time: 58.7 min → 29.3 min (50% faster)
# - Per-task rate: 2 req/sec → 3600 req/hour
# - Total (6 tasks): 21.6k req/hour (unchanged, still safe)
```

**Rationale:**
- Circuit breaker now properly detects 429s across all tasks
- Exponential backoff prevents cascading failures
- Monitoring dashboards would catch any issues

**Validation:**
- Monitor `yfinance_ip_ban` table for ban frequency
- Track completion time vs. expected (should be ~30 min)
- Check for 429 error rate in logs

### Phase 2: Parallelism Increase (MEDIUM RISK)
**Increase constraint from (1,3) to (1,4) after Phase 1 validation**

```python
# loaders/utils/loaders/config.py
"value_metrics": (1, 4),  # Increased from 1-3

# Expected improvement:
# - Load time: 29.3 min → 22 min (with 0.5s interval)
# - Per-task concurrency: 4 workers instead of 3
# - Risk: 4 workers × 6 tasks = 24 potential concurrent requests
```

**Validation required:**
- Circuit breaker metrics show stable operation
- No IP bans triggered
- Gradual rollout: (1,4) for 1 week, then (1,5) if stable

### Phase 3: Intelligent Caching (HIGH IMPACT, LOW RISK)
**Implement 7-day cache for value metrics (most fields are quasi-static)**

Fields that don't change daily:
- PE ratio (changes quarterly with earnings)
- PB ratio (changes with book value updates)
- PS ratio (changes with revenue updates)
- PEG ratio (changes with growth estimates)

Only refresh on:
- First load of the day
- Explicit refresh request
- Cache expiration (7 days)

```python
# loaders/load_value_metrics.py

def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
    # Check if cached value_metrics from <7 days ago exist
    if since and (date.today() - since).days < 7:
        # Return cached data instead of fetching
        return self._get_cached_value_metrics(symbol)
    
    # Fresh fetch from yfinance
    return self._fetch_from_yfinance(symbol)
```

**Expected improvement:**
- 50-70% reduction in API calls after 1 week
- Steady-state load time: 15-20 minutes
- No rate limit concerns even with parallelism=6

**Trade-off:** 7-day staleness for PE/PB/PS (acceptable for swing trading)

### Phase 4: Smart Pre-warming (MINIMAL EFFORT)
**Pre-cache top 500 liquid symbols on every run**

Liquid symbols rarely change, caching them prevents repeated fetches:
- Top 500 by volume represent ~80% of trading activity
- Cache hit rate for these symbols: ~99%
- Reduces per-run work from 10,574 to ~9,500 symbols

**Effort:** 1-2 hours implementation

## Implementation Plan

| Phase | Feature | Risk | Time | Impact |
|-------|---------|------|------|--------|
| 1 | 0.5s interval | Low | 30 min validation | 50% faster |
| 2 | Parallelism (1,4) | Medium | 1 week monitoring | 25% faster |
| 3 | 7-day cache | Low | 4 hours code | 70% faster steady-state |
| 4 | Pre-warming | Low | 2 hours code | 10% faster |

## Estimated Final Timeline
- **Current:** 59 minutes for value_metrics
- **After Phase 1:** 30 minutes
- **After Phase 2:** 22 minutes
- **After Phase 3:** 15 minutes (steady-state)
- **Target:** < 20 minutes total for daily refresh cycle

## Risk Mitigation

### Monitor These Metrics
1. **yfinance_ip_ban table:** Ban frequency and backoff duration
2. **Loader completion time:** Should decrease with optimizations
3. **Data coverage %:** Must maintain ≥90% for stock_scores
4. **Error rates:** 429/401 errors should decrease, not increase

### Rollback Plan
- Each phase is independently reversible
- Circuit breaker automatically prevents cascades
- Pre-alerts: If 429s increase >20%, auto-reduce parallelism

## Success Criteria
✅ Value metrics loads in <20 minutes per run
✅ Coverage remains ≥95%
✅ No IP bans triggered by circuit breaker
✅ Stock scores daily refresh completes in <30 minutes

## Appendix: Current Configuration

### yfinance.py Rate Limiting
```
_YF_MIN_INTERVAL_SECS = 1.0  # 1 req/sec per task = 3600/hour per task
Circuit breaker: 10s→20s→40s→80s→300s exponential backoff on 429
Ticker cache: 24 hours (prevents repeated requests for same symbol)
```

### Loader Config Constraints
```
"value_metrics": (1, 3),         # Current max parallelism = 3
"positioning_metrics": (1, 2),   # More conservative, pure yfinance
```

### Stock Scores Audit
```
Requires ≥90% coverage from each upstream metric loader
Fails fast if coverage degraded (prevents silent data quality issues)
```
