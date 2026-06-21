# Standardized Circuit Breaker Patterns for Data Loaders

## Problem Statement

Before this standardization, loaders handled API outages inconsistently:

1. **load_fear_greed_index.py**: Explicit retries with 418 block handling, fails after 3 attempts
2. **load_market_health_daily.py**: Gracefully degrades for optional enrichments (VIX, put/call)
3. **load_prices.py**: Complex rate limiting with circuit breaker, but unclear fallback behavior
4. **position_sizer.py**: Silently uses stale portfolio snapshots (up to 2 days old)
5. **Position sizing**: Uses 9-day-old VIX for risk calculations if current data unavailable

**Impact**: Users can't distinguish between:
- Fresh data vs stale cache
- Optional enrichments vs required data
- Temporary API lag vs persistent outages

## Solution: Three-Tier Criticality Model

### Tier 1: CRITICAL Data (Fail-Fast)

**Definition**: Data required for position sizing, risk limits, or avoiding catastrophic losses.

**Examples**:
- **VIX level** (markets.py): Required to size positions correctly. Using stale VIX → wrong position size → unintended risk exposure
- **Portfolio value** (position_sizer.py): Required to calculate position size. Using stale snapshot → wrong position size
- **Market close data** (load_prices.py): For daily price loader, must verify data is current before proceeding
- **SPY price** (position_monitor.py): Required to calculate returns and trigger risk limits

**Behavior on Outage**:
1. Retry with exponential backoff (2s, 4s, 8s, 16s, 32s → fail)
2. If retries exhausted, FAIL IMMEDIATELY with error
3. Phase orchestrator catches error and triggers failsafe (retry phase later)
4. **NEVER silently use stale cache**

**Code Pattern**:
```python
from utils.infrastructure.circuit_breaker import CircuitBreaker, DataImportance

breaker = CircuitBreaker(
    name="yfinance_vix",
    failure_threshold=3,
    recovery_timeout_sec=300,
    importance=DataImportance.CRITICAL
)

vix_level = breaker.execute(
    fetch_func=lambda: yfinance.get("^VIX"),
    importance=DataImportance.CRITICAL
)
# If outage: raises RuntimeError → phase fails
# If recovered: returns vix_level
```

### Tier 2: REQUIRED Data (Fail with Context)

**Definition**: Data needed to complete a computation, but not used for risk decisions.

**Examples**:
- **Financial statements** (load_growth_metrics.py): Needed to compute growth scores
- **Technical indicators** (load_technical_data_daily.py): Needed for signal generation
- **Market breadth** (load_market_health_daily.py): Part of market health computation

**Behavior on Outage**:
1. Retry with exponential backoff
2. If retries exhausted, fail with clear context
3. Phase orchestrator can decide to skip this phase or retry later
4. **Never try to continue without this data**

**Code Pattern**:
```python
breaker = CircuitBreaker(
    name="financial_statements",
    failure_threshold=3,
    recovery_timeout_sec=300,
    importance=DataImportance.REQUIRED
)

financials = breaker.execute(
    fetch_func=lambda: fetch_income_statement(symbol),
    importance=DataImportance.REQUIRED
)
# If outage: raises RuntimeError → phase fails cleanly
# If recovered: returns financials
```

### Tier 3: OPTIONAL Enrichment (Graceful Degradation)

**Definition**: Additional data that improves computation but isn't required for correctness.

**Examples**:
- **Put/call ratio** (load_market_health_daily.py): Enriches market health, but signal generation works without it
- **Yield curve slope** (load_market_health_daily.py): Enriches market regime, but not required for position sizing
- **Sector rotation** (dashboard): Adds context but portfolio works without it

**Behavior on Outage**:
1. Try to fetch with timeout (short, not full retry loop)
2. If fails, log warning and continue with None value
3. Downstream code checks for None and skips enrichment
4. **User sees that enrichment is missing**, not stale data

**Code Pattern**:
```python
breaker = CircuitBreaker(
    name="vix_enrichment",
    failure_threshold=3,
    recovery_timeout_sec=300,
    importance=DataImportance.OPTIONAL
)

vix = breaker.execute(
    fetch_func=lambda: yfinance.get("^VIX"),
    importance=DataImportance.OPTIONAL,
    fallback_value=None
)
# If outage: logs warning, returns None
# If recovered: returns vix
# Downstream code: if vix is None: skip enrichment
```

## Implementation Checklist

For each data loader:

1. **Identify criticality** of each data source
   - Is it used for position sizing? → CRITICAL
   - Is it required to complete the computation? → REQUIRED
   - Can the computation proceed without it? → OPTIONAL

2. **Create circuit breaker instance**
   ```python
   from utils.infrastructure.circuit_breaker import CircuitBreaker, DataImportance
   
   self._breaker = CircuitBreaker(
       name="your_data_source_name",
       failure_threshold=3,
       recovery_timeout_sec=300,
       importance=DataImportance.CRITICAL  # or REQUIRED, OPTIONAL
   )
   ```

3. **Wrap fetch calls**
   ```python
   data = self._breaker.execute(
       fetch_func=lambda: your_fetch_function(),
       importance=DataImportance.CRITICAL
   )
   ```

4. **Handle return value appropriately**
   - CRITICAL/REQUIRED: Will raise on failure (you don't need to handle)
   - OPTIONAL: Check for None before using
   ```python
   if vix_level is not None:
       health_metrics["vix"] = vix_level
   else:
       logger.debug("VIX enrichment skipped (optional, unavailable)")
   ```

5. **Document in loader docstring**
   ```python
   class MarketHealthDailyLoader(OptimalLoader):
       """Market health metrics loader.
       
       Critical data: SPY prices (market_health computation cannot proceed without)
       Optional enrichments: VIX (improves metrics, but missing is OK)
       """
   ```

## Migration Path

### Phase 1: Critical Data (VIX, prices, portfolio value)
- Loaders: load_prices.py, load_market_health_daily.py (VIX fetch only)
- Timeline: Complete by 2026-06-27
- Impact: Position sizing will fail cleanly instead of using 9-day-old VIX

### Phase 2: Required Data (financial statements, technical indicators)
- Loaders: load_stock_scores.py, load_technical_data_daily.py
- Timeline: Complete by 2026-07-04
- Impact: Score generation will fail cleanly instead of using stale data

### Phase 3: Optional Enrichments (put/call, yield curve, sector rotation)
- Loaders: load_market_health_daily.py, dashboard fetchers
- Timeline: Complete by 2026-07-11
- Impact: Dashboard will clearly show when enrichments are missing

## Testing the Circuit Breaker

### Test outage handling:
```bash
# 1. Simulate API unavailability
# Stop yfinance responses or return 503 errors

# 2. Run loader
python3 loaders/load_prices.py

# 3. Verify:
# - Logs show "CIRCUIT OPEN" after 3 failures
# - Phase fails cleanly with RuntimeError (not silent stale data)
# - Logs show clear reason and recovery time
```

### Test graceful degradation:
```bash
# 1. Simulate optional data unavailability
# Stop VIX endpoint only, leave SPY prices available

# 2. Run loader
python3 loaders/load_market_health_daily.py

# 3. Verify:
# - SPY prices load successfully
# - Logs show warning that VIX enrichment skipped
# - Market health data has vix_level=NULL (not filled with stale value)
# - Signal generation proceeds with market health data
```

## Monitoring & Alerting

Circuit breaker state transitions should be logged with high visibility:

- **CLOSED → OPEN**: Critical alert (API outage detected)
  ```
  [CIRCUIT_BREAKER:yfinance_vix] ⚠️  CIRCUIT OPEN: 3/3 failures detected. 
  Will retry in 300s. API: yfinance_vix appears unavailable.
  ```

- **OPEN → HALF_OPEN**: Info level (recovery attempt)
  ```
  [CIRCUIT_BREAKER:yfinance_vix] Recovery timeout elapsed, 
  transitioning to HALF_OPEN to test API recovery
  ```

- **HALF_OPEN → CLOSED**: Info level (recovery successful)
  ```
  [CIRCUIT_BREAKER:yfinance_vix] API recovered, 
  transitioning from HALF_OPEN to CLOSED
  ```

CloudWatch alarms should trigger on:
- Circuit breaker OPEN for CRITICAL data (immediate escalation)
- Circuit breaker OPEN for REQUIRED data (high priority)
- Repeated circuit breaker transitions (API flapping — check status page)

## FAQ

**Q: Why not use "last known good" data when API is down?**
A: Because you can't distinguish between:
- 1-day-old data (probably fine)
- 9-day-old data (too stale for position sizing)

Stale data + unclear age = silent risk exposure. Better to fail explicitly.

**Q: Can I make critical data optional?**
A: No. If position sizing depends on it, it's critical. Update the data source quality instead.

**Q: What if the API is down for hours?**
A: Phase orchestrator catches the failure and retries later. If critical data is unavailable all day:
1. Signals don't generate (no new positions)
2. Existing positions are managed by exit engine (existing data is valid)
3. When API recovers, normal operation resumes
4. Operator is alerted about the outage (see Monitoring & Alerting)

**Q: How do I test if my loader is truly fail-fast?**
A: Try these scenarios:
1. Cut network to API server → loader should fail within 30s (not timeout for 5+ minutes)
2. API returns 503 service unavailable → loader should retry 3x then fail (not use stale cache)
3. Database is down → loader should fail (not read from cache without verification)

If your loader doesn't fail clearly in these scenarios, it's using silent fallbacks.
