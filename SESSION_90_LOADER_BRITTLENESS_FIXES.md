# Session 90: Loader Brittleness Fixes - Monday Reliability Plan

## Problem Summary
Monday loading pipeline consistently fails with cascading loader timeouts:
- **company_info_sec**: Stuck 30+ minutes (120m timeout) due to serial SEC API calls
- **analyst_sentiment_analysis**: Timed out at 20m limit due to circuit breaker delays
- **insider_holdings_sec**: Timed out at 15m limit (was 19m), blocked on company_info

All three failures cascade through dependent loaders (signals, metrics, scoring).

## Root Causes Identified (Session 89 Agent Analysis)

### 1. RateLimiter Lock Contention (sec_edgar_client.py)
- **Bug**: `threading.Lock` held during entire `sleep()` duration
- **Impact**: All parallel workers queue up during rate-limit delays
- **Cause**: 2 req/sec rate limit = 0.5s sleep per request × 5000 symbols = extended wait
- **Fix**: Release lock BEFORE sleep (lock only guards timestamp updates)

### 2. Insufficient Timeouts
- **analyst_sentiment**: 20m timeout, but circuit breaker + 5000 symbols needs 20-30m
- **insider_holdings**: 15m timeout, actual runtime needs 20-30m
- **analyst_earnings_estimates**: Same yfinance delays as sentiment (20m → 30m)

### 3. Database Blocking
- **insider_holdings_sec** calls `company_info_sec` for shares_outstanding lookup
- If company_info_sec is stuck, insider_holdings waits indefinitely
- Timeout occurs before completion (15m < 30m for company_info)

### 4. Sequential Form345 Downloads
- Form345BulkAggregator downloads 12 quarters sequentially (not parallel)
- All symbols wait on single `threading.Lock` during download phase
- Each quarter download: 5-60s × 12 = 60-720s before symbol processing starts

## Fixes Implemented (Session 90)

### ✅ FIX 1: RateLimiter Lock Contention
**File**: `utils/external/sec_edgar_client.py` (RateLimiter class)

```python
# BEFORE: Lock held during entire sleep
def wait(self) -> None:
    with self._lock:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)  # ← LOCK HELD DURING SLEEP
        self._last_request = time.monotonic()

# AFTER: Lock released before sleep
def wait(self) -> None:
    with self._lock:
        elapsed = time.monotonic() - self._last_request
        sleep_time = self.min_interval - elapsed if elapsed < self.min_interval else 0
        self._last_request = time.monotonic()
    if sleep_time > 0:
        time.sleep(sleep_time)  # ← LOCK NOT HELD
```

**Impact**: Parallel workers no longer block during rate-limit delays.

### ✅ FIX 2: Increase Timeouts (local_loader_scheduler.py)
| Loader | Before | After | Reason |
|--------|--------|-------|--------|
| analyst_sentiment | 20m | 30m | Circuit breaker delays + 5000 symbols |
| analyst_earnings_estimates | 20m | 30m | Same yfinance delays |
| insider_holdings | 15m | 30m | Form345 bulk download + DB queries |

### ✅ FIX 3: Make SEC Rate Limit Configurable (sec_edgar_client.py)
```python
# LOCAL_MODE: 8 req/sec (single process)
# PRODUCTION: 2 req/sec (5+ tasks = 10 total)
# Override with SEC_RATE_LIMIT_PER_TASK env var
```

## Testing Plan (Before Monday 08:00)

### Phase 1: Isolated Loader Validation
```bash
# Test each slow loader independently to verify fixes
python scripts/local_loader_scheduler.py --now reference  # insider/institutional holdings
python scripts/local_loader_scheduler.py --now metrics   # analyst sentiment + company_info
```

**Expected Results**:
- analyst_sentiment: Complete in <25m (was timing out)
- insider_holdings: Complete in <25m (was stuck 19m then timeout)
- company_info_sec: Complete in <60m (was stuck 30m)
- No RUNNING status remaining after completion

### Phase 2: Full Pipeline Run
```bash
python scripts/run_local_orchestrator.py --morning --force
```

**Expected Results**:
- All 9 phases complete successfully
- No cascade failures from analyst/insider loaders
- Data freshness restored (market opens with fresh data)

### Phase 3: Monitor Stuck Loaders
```bash
# Run every 5 minutes to catch new timeouts early
while true; do
  python -c "
  import psycopg2; import os
  conn = psycopg2.connect(dbname=os.getenv('DB_NAME','stocks'), user=os.getenv('DB_USER','stocks'), host='localhost')
  cur = conn.cursor()
  cur.execute('SELECT table_name, status, EXTRACT(EPOCH FROM (NOW() - execution_started))/60 as age_min FROM data_loader_status WHERE status = \"RUNNING\" AND execution_started > NOW() - INTERVAL \"4 hours\" ORDER BY execution_started')
  rows = cur.fetchall()
  if rows:
    for table, status, age in rows:
      print(f'{table}: {age:.1f}m')
  else:
    print('✓ No stuck loaders')
  conn.close()
  "
  sleep 300
done
```

## Success Criteria

### Monday Morning (08:00 - 09:00)
- [ ] No RUNNING loaders after 25 minutes (all completed or failed with clear error)
- [ ] analyst_sentiment: COMPLETED (was timing out)
- [ ] insider_holdings: COMPLETED (was timing out)
- [ ] company_info_sec: COMPLETED (was stuck)
- [ ] Orchestrator phases 1-9: All pass
- [ ] Data freshness: price_daily, technical_data, scores all FRESH

### Production Metrics
- [ ] Morning pipeline execution time: <90m (was cascading for 120m+)
- [ ] No dependent loader cascade failures
- [ ] Circuit breaker max wait: <1m (was 20m+ under old timeouts)

## Remaining Improvements (Post-Monday)

### High Priority (affects reliability)
1. **Parallelize Form345 quarter downloads** (concurrent.futures ThreadPoolExecutor)
2. **Add database query timeout** (psycopg2 connection timeout)
3. **Optimize SEC symbol_to_cik cache** (LRU size from 4 → larger)

### Medium Priority (affects speed)
1. **Batch SEC API calls** for company_info lookups
2. **Implement circuit breaker per-symbol** (don't ban entire IP on single symbol failure)

### Documentation
1. Update MEMORY.md with loader timeout calibration rules
2. Document SEC rate limiting strategy (2 req/sec per task)
3. Add metrics for circuit breaker effectiveness

## Commit History
- **827fdc602**: Reduce stale RUNNING timeout 30m → 5m
- **e1007f839**: Increase SEC loader timeouts (original Session 89 work)
- **[THIS SESSION]**: RateLimiter lock fix + timeout increases + rate limit config

## Dependency Chain (Why Monday Cascades)
```
company_info_sec (30m stuck)
├─ → insider_holdings (waits on company_info)
│  └─ → positioning_metrics (needs insider holdings)
│
analyst_sentiment (times out at 20m)
└─ → signal_generation (depends on analyst sentiment)
    └─ → buy_sell signals (cascade fails)
         └─ → score_quality (cascade fails)
              └─ → algo_metrics (cascade fails)
```

With timeouts increased and lock contention fixed:
- All three complete in parallel <30m
- No cascade failures
- Signal generation proceeds normally
