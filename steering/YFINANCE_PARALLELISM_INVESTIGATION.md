# Yfinance Parallelism Investigation & Optimization Plan

**SUPERSEDED 2026-08-17**: CLAUDE.md's Core Rules now state `LOADER_PARALLELISM must be 1`
as a non-negotiable, current-day rule (yfinance blocks even at parallelism=2 — see memory
`analyst_loaders_reloaded_and_local_parallelism_ban_20260810`). The "Phase 1: Test
Parallelism=2" plan below predates that rule and proposes re-running an experiment the
project has since settled as unsafe. Don't act on this doc's Phase 1/2 without first
checking whether that rule has since been relaxed in CLAUDE.md — the rate-limit math and
root-cause analysis below are still accurate background, just not the current plan.

## Current State (Analysis 2026-08-12)

### Problem
- **Current**: LOADER_PARALLELISM forced to 1 to avoid yfinance shared IP circuit breaker
- **Impact**: Analyst pipeline takes 6+ hours (analyst_sentiment, analyst_upgrades, analyst_earnings, positioning_metrics, value_metrics all yfinance-dependent)
- **Trade-off**: Complete reliability (parallelism=1) vs. fast incompleteness (parallelism=4)

### Root Cause
1. **6 ECS tasks** share the same NAT IP address when accessing yfinance
2. With **parallelism=P**: each task spawns P worker threads → 6 × P concurrent yfinance requests
3. With **parallelism=4**: 6 × 4 = 24 concurrent requests
4. Yahoo's rate limiter (undisclosed threshold, empirically ~10-15 req/sec) detects abuse
5. Responds with **HTTP 429 Too Many Requests**
6. Circuit breaker (yfinance_circuit_breaker.py) detects 429 and sets exponential backoff:
   - Initial: 10s backoff
   - Each failure: 10s → 20s → 40s → 80s → ... → max 30 min
7. **Result**: Sustained 429 errors keep IP banned for extended periods
8. Completion rate plummets from 95%+ to 66.5% (commit 38c982876)

### Rate Limit Math
- Yahoo rate limit: ~15 req/sec (empirical estimate from prior incidents)
- Safe ceiling per ECS task: ~2.5 req/sec per task × 6 tasks = 15 req/sec total
- With parallelism=P: throughput = P threads × task_request_rate req/sec per thread
- **Parallelism=1**: 1 × 2.5 = 2.5 req/sec per task, safe
- **Parallelism=2**: 2 × 2.5 = 5 req/sec per task, likely safe (12 total across 6 ECS)
- **Parallelism=3**: 3 × 2.5 = 7.5 req/sec per task, risky (45 total across 6 ECS - will trigger ban)
- **Parallelism=4**: 4 × 2.5 = 10 req/sec per task, confirmed to trigger ban (60 total across 6 ECS)

### Affected Loaders (yfinance-dependent)
```
positioning_metrics:         (1, 1)  # Can't increase - locked to 1
value_metrics:              (1, 1)  # Can't increase - locked to 1
analyst_sentiment:          (1, 2)  # Could test at 2
analyst_upgrades:           yfinance-based (currently 1)
analyst_earnings_estimates: yfinance-based (currently 1)
growth_metrics:             yfinance-dependent (earnings data)
quality_metrics:            yfinance-dependent (eps data)
```

## Investigation Plan (Priority Order)

### Phase 1: Test Parallelism=2 (High Confidence)
**Hypothesis**: Parallelism=2 keeps requests below rate limit threshold

**Steps**:
1. Deploy with `analyst_sentiment: (1, 2)` and `analyst_upgrades: (1, 2)` only (not value_metrics/positioning)
2. Run morning pipeline with 4900+ symbol universe
3. Monitor:
   - HTTP 429 errors in logs (should be 0 or very rare)
   - Completion %: should stay above 95%
   - Duration: measure full analyst pipeline time (target: 2-3 hours vs current 6h)
4. If successful: document as safe configuration
5. If failed (429 errors): revert to parallelism=1

**Success Criteria**:
- 0% HTTP 429 errors in logs
- 95%+ completion rate
- 3h or better runtime (50%+ speedup from 6h)

### Phase 2: Gradual Rollout
If Phase 1 succeeds, test additional loaders in sequence:
1. Week 1: analyst_sentiment + analyst_upgrades at parallelism=2
2. Week 2: Add analyst_earnings_estimates at parallelism=2
3. Week 3: Consider value_metrics at parallelism=2 (if not already locked)

### Phase 3: Rate Limit Monitoring
Add to data_loader_status tracking:
- http_status_code: track 429 errors specifically
- rate_limit_quota: capture rate-limit headers if available
- Create dashboard alert: "If 429 errors detected, log yfinance circuit breaker state"

## Implementation Details

### 1. Update loader configuration (loaders/loader_dynamic_config.py)
```python
LOADER_CONSTRAINTS = {
    ...
    "analyst_sentiment": (1, 2),     # Test at parallelism=2
    "analyst_upgrades": (1, 2),      # Test at parallelism=2
    # value_metrics/positioning locked to (1,1) until verified safe
}
```

### 2. Monitor Circuit Breaker State
Add logging to phase1_failsafe_retry.py or new monitoring script:
```bash
python scripts/check_yfinance_circuit_breaker_state.py
```

### 3. Create Test harness
```bash
# Test script that runs analyst pipeline at controlled parallelism
python scripts/test_yfinance_parallelism.py --parallelism 2 --max-symbols 500 --dry-run

# Production test
python scripts/local_loader_scheduler.py --now metrics --LOADER_PARALLELISM=2
```

## Risk Mitigation

1. **Staged rollout**: Test 2 loaders before 4, test small sample first
2. **Revert plan**: If 429 errors detected, immediately revert to parallelism=1
3. **Fallback**: Circuit breaker already has exponential backoff (handles sustained failures)
4. **Monitoring**: Add HTTP 429 to standard loader health checks

## Expected Timeline

- **Today (2026-08-12)**: Design & plan
- **Tomorrow (2026-08-13)**: Test analyst_sentiment + analyst_upgrades at parallelism=2
- **If successful (2026-08-14+)**: Gradual rollout, monitor
- **Potential gain**: 2-3 hour analyst pipeline vs current 6+ hours = 50-67% speedup

## Notes

- **Circuit breaker handles retries**: Even if we trigger 429, circuit breaker's exponential backoff will retry (no data loss, just slower)
- **Per-symbol timeouts already in place**: analyst loaders have 20-30 min timeouts, independent of parallelism
- **Not a permanent fix**: This is an optimization within yfinance's undisclosed rate limit. If they lower their limit, we may need to reduce parallelism again
- **Alternative considered**: Implement request batching/caching (higher effort, lower confidence)
- **Alternative considered**: Use yfinance alternative library (Polygon.io) - requires infrastructure change

## References

- circuit_breaker: utils/external/yfinance_circuit_breaker.py (IP ban state tracking)
- Configuration: loaders/loader_dynamic_config.py (LOADER_CONSTRAINTS dictionary)
- Analyst loaders: loaders/load_analyst_*.py (sentiment, upgrades, earnings)
- Prior incidents: Memory #analyst_loaders_reloaded_and_local_parallelism_ban_20260810
