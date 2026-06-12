# Medium Issues - Fixes & Centralization

**Status:** ✅ COMPLETED (commit TBD)

This document describes the fixes for 5 medium issues identified in the codebase that affect reliability and consistency across the platform.

## Issue #1: Inconsistent Freshness Checking

### Problem
Some places checked data freshness using `max_data_staleness_days` from AlgoConfig, others had hardcoded thresholds or no check at all. This inconsistency meant:
- Different parts of the system had different definitions of "stale"
- Freshness checks couldn't be updated at runtime
- No consistent logging of freshness decisions

### Solution
**Created:** `utils/freshness_validator.py`

Centralizes all freshness checking with:
- `is_fresh(last_loaded_date, data_type)` - Quick yes/no check
- `check_freshness(last_loaded_date, data_type)` - Detailed diagnostic
- `assert_fresh(last_loaded_date, data_type)` - Fail-fast validation
- Automatic use of `AlgoConfig.max_data_staleness_days` (currently 3 days)

### Usage
```python
from utils.freshness_validator import is_fresh, check_freshness
from datetime import date

# Before: scattered, hardcoded checks
age_days = (today - watermark_date).days
if age_days > 3:  # Hardcoded threshold
    refresh_data()

# After: centralized, runtime-configurable
if not is_fresh(watermark_date, 'price', context='AAPL'):
    refresh_data()

# With diagnostics
freshness = check_freshness(watermark_date, 'price', context='AAPL')
if not freshness['is_fresh']:
    logger.warning(f"{freshness['message']} (age: {freshness['age_days']}d)")
```

### Migration Path
1. Search for hardcoded staleness thresholds (3, 5, 7 in date comparison logic)
2. Replace with calls to `freshness_validator`
3. Remove duplicate staleness checking logic

---

## Issue #2: Fallback Chains Everywhere

### Problem
Fallback chains were scattered throughout the codebase, undocumented, and inconsistent:
- Database: credential_manager had fallback to env vars
- VIX: circuit_breaker had fallback computation
- Prices: dashboard had API + DB fallback
- No way to understand system behavior in degraded mode
- Silent failures that masked real problems

### Solution
**Created:** `utils/fallback_registry.py`

Documents **all 7 fallback chains** in the platform:
1. **Database Credentials** - Secrets Manager → env vars → legacy names
2. **VIX Data** - API → historical DB → computed from SPY → neutral 20.0
3. **Performance Metrics** - API → database cache → hardcoded defaults
4. **Alpaca Credentials** - Secrets Manager → credential cache → env vars
5. **Database Connection** - Direct → retries with backoff (no localhost)
6. **Price Data** - Fresh API → watermark incremental → full historical
7. **Market Data** - Real-time API → previous day → computed indicators

Each chain specifies:
- Primary source
- Fallback order and conditions
- Logging pattern
- Metrics tracked
- Recovery condition

### Usage
```python
from utils.fallback_registry import log_fallback_usage, FallbackTrigger

try:
    vix = fetch_live_vix()
except APIError:
    log_fallback_usage(
        resource='vix_data',
        fallback_step='historical_database',
        trigger=FallbackTrigger.PRIMARY_UNAVAILABLE,
        context='market_close',
        error=e
    )
    vix = fetch_vix_from_database()
```

### Benefits
- Users understand system resilience and failure modes
- Fallback behavior is testable and verifiable
- Metrics can track fallback frequency (indicates problems)
- New team members don't need to read 10 files to understand behavior

---

## Issue #3: Database Connection Defaults

### Problem
Migrations defaulted to `localhost` when `DB_HOST` was unset:
```python
# WRONG - silent localhost fallback
host = os.getenv('DB_HOST', 'localhost')  # Will use localhost if unset!
```

But `credential_manager.py` explicitly rejects localhost for safety:
```python
if not db_host:
    raise ValueError("DB_HOST not set in environment")
```

This inconsistency meant:
- Migrations could accidentally run against wrong database
- Different code paths had different defaults
- Safety guarantees were uneven

### Solution
**Fixed in 4 files:**
1. `migrations/run.py` - Now requires DB_HOST, exits if missing
2. `migrations/versions/012_add_date_indexes.py` - Enforces DB_HOST requirement
3. `migrations/versions/027_optimize_slow_api_endpoints.py` - Enforces DB_HOST requirement
4. `migrations/versions/032_add_data_patrol_log_index.py` - Enforces DB_HOST requirement

All now follow the same pattern:
```python
db_host = os.getenv('DB_HOST')
if not db_host:
    raise ValueError("DB_HOST environment variable is required (no localhost fallback for safety)")
```

### Impact
- **Positive:** Prevents accidental localhost connections
- **Requires:** DB_HOST must be set before running migrations
- **Verification:** CI/CD must provide DB_HOST for migration steps

---

## Issue #4: Minimal Caching Strategy

### Problem
Only credentials were cached (5-minute TTL). Other expensive operations ran on every request:
- Technical indicator calculations (SMA, EMA, RSI, ATR) - recomputed each page load
- Market aggregates (breadth, up/down volume) - queried from full scans
- Company fundamentals - fetched via API for every dashboard load
- Result: N+1 queries, wasted API calls, slow dashboards

### Solution
**Created:** `utils/query_cache.py`

General-purpose in-process cache with:
- **TTL-based expiration** - Configurable per-query-type (default 300s)
- **LRU eviction** - Automatic cleanup when cache full
- **Statistics tracking** - Hit rate, stale hits, evictions
- **Context-aware logging** - Know which queries are cache hits

### Recommended Caches
```python
from utils.query_cache import get_or_create_cache

# Technical indicators (compute once, reuse within 60s)
cache = get_or_create_cache('technical_indicators', ttl_seconds=60, max_entries=5000)

# Market aggregates (slow queries, cache for 30s)
cache = get_or_create_cache('market_aggregates', ttl_seconds=30, max_entries=100)

# Company fundamentals (rarely changes, cache for 3600s)
cache = get_or_create_cache('company_fundamentals', ttl_seconds=3600, max_entries=10000)
```

### Usage
```python
cache = get_or_create_cache('technical_indicators', ttl_seconds=300)

sma50 = cache.get_or_compute(
    key=('AAPL', 'SMA50'),
    compute_fn=lambda: calculate_sma('AAPL', 50),
    context="computing SMA50 for AAPL chart"
)
```

### Caching Philosophy
- **Fast is better than accurate.** Cache slightly-stale data rather than slow.
- **Log cache usage.** Track which queries have high hit rates (easy wins).
- **Invalidate manually.** When data is updated, explicitly invalidate cache.
- **Measure cache effectiveness.** Report hit rates and avg times monthly.

---

## Issue #5: Scattered Data Validation

### Problem
Data validation was scattered across the codebase:
- Some places used `safe_float()` from `safe_data_conversion.py`
- Others had inline `try/except float()` blocks
- Some had no validation at all
- No guidance on which pattern to use where
- Validation logic duplicated across files

### Solution
**Created:** `utils/data_validation_registry.py`

Provides:
1. **Decision tree** - Which validator to use for each data type
2. **Migration guide** - How to replace inline try/except blocks
3. **Central registry** - All validators listed with signatures
4. **Schema validation** - Validate entire record against schema

### Validation Decision Tree
```
Numeric Values
├─ float: safe_float() or safe_float_strict()
└─ int: safe_int()

Dates/Times
├─ date: safe_parse_date()
└─ datetime: safe_parse_datetime_et()

Strings
├─ JSON: safe_json_loads()
├─ URL: utils.url_validator
└─ CSV: utils.csv_sanitizer

Structural
├─ Schema: utils.schema_validator.validate_row()
└─ Alpaca: utils.alpaca_response_validator
```

### Migration Examples
```python
# BEFORE: Inline try/except (scattered, hard to maintain)
try:
    price = float(row['price'])
except ValueError:
    price = 0.0

# AFTER: Centralized (consistent, logged, testable)
from utils.safe_data_conversion import safe_float
price = safe_float(row['price'], default=0.0, context=f"symbol={symbol}")
```

### Record Validation
```python
from utils.data_validation_registry import validate_record

schema = {
    'price': 'float',
    'volume': 'int',
    'date': 'date'
}

validated = validate_record(
    record=row,
    schema=schema,
    context=f"AAPL historical data"
)
```

---

## Integration Guide

These 5 fixes work together to create a cohesive system:

### Data Loading Pipeline
1. **Source data** from API or database
2. **Validate** using `data_validation_registry`
3. **Check freshness** using `freshness_validator`
4. **Log fallback usage** if needed (via `fallback_registry`)
5. **Cache result** using `query_cache` for next reuse

### Example: Loading Price Data
```python
from utils.freshness_validator import check_freshness
from utils.fallback_registry import log_fallback_usage, FallbackTrigger
from utils.data_validation_registry import validate_record
from utils.query_cache import get_or_create_cache

def load_prices(symbol: str) -> List[Dict]:
    cache = get_or_create_cache('prices', ttl_seconds=300)

    # Try cache first
    cached = cache.get_or_compute(
        key=('prices', symbol),
        compute_fn=lambda: _fetch_and_validate_prices(symbol),
        allow_stale=True  # Accept stale data if fetch fails
    )
    return cached

def _fetch_and_validate_prices(symbol: str) -> List[Dict]:
    # Try primary source (API)
    try:
        raw_prices = fetch_prices_api(symbol)
    except APIError as e:
        # Log fallback and use secondary source
        log_fallback_usage(
            resource='price_data',
            fallback_step='database_load',
            trigger=FallbackTrigger.PRIMARY_UNAVAILABLE,
            context=symbol,
            error=e
        )
        raw_prices = fetch_prices_database(symbol)

    # Validate each record
    schema = {'date': 'date', 'close': 'float', 'volume': 'int'}
    validated_prices = [
        validate_record(row, schema, context=f"{symbol} on {row['date']}")
        for row in raw_prices
    ]

    # Check freshness
    freshness = check_freshness(
        validated_prices[-1]['date'],
        'price',
        context=symbol
    )
    if not freshness['is_fresh']:
        logger.warning(f"Price data {freshness['message']}")

    return validated_prices
```

---

## Testing These Fixes

### Test Freshness Checking
```python
from utils.freshness_validator import check_freshness
from datetime import date, timedelta

# Test fresh data
three_days_ago = date.today() - timedelta(days=3)
result = check_freshness(three_days_ago, 'price')
assert result['is_fresh'] == True

# Test stale data
five_days_ago = date.today() - timedelta(days=5)
result = check_freshness(five_days_ago, 'price')
assert result['is_fresh'] == False
```

### Test Cache Hit Rate
```python
from utils.query_cache import QueryCache

cache = QueryCache('test', ttl_seconds=300)
for i in range(100):
    cache.get_or_compute(
        key=('test', i % 10),  # Only 10 unique keys
        compute_fn=lambda: i * 2
    )

stats = cache.stats()
assert stats.hit_rate() > 80  # Should be high with 10 keys, 100 lookups
```

### Test Database Connection Rejection
```python
import os
from migrations.run import _load_credentials

# Should fail if DB_HOST not set
os.environ.pop('DB_HOST', None)
try:
    _load_credentials()
    assert False, "Should have raised error"
except SystemExit:
    pass  # Expected
```

---

## Metrics & Monitoring

Track these metrics to verify the fixes are working:

### Freshness Checking
- `freshness_checks_total` - Total freshness checks performed
- `freshness_stale_detected` - Count of stale data detected
- `freshness_max_age_days` - Maximum age of data accepted

### Fallback Usage
- `fallback_uses_total` - Count of fallback activations (should be rare)
- `fallback_duration_by_type` - How long fallbacks take vs primary source
- `fallback_primary_availability` - % of time primary source is available

### Caching
- `cache_hit_rate_by_type` - Hit rate for each cache type
- `cache_avg_compute_time_ms` - Average computation time for misses
- `cache_stale_hits` - Serving stale data from cache

### Database Connections
- `db_host_validation_errors` - Should be 0 after fix
- `db_connection_retries_total` - Exponential backoff retries

---

## Files Changed

### Modified (4 files)
- `migrations/run.py` - Enforces DB_HOST requirement
- `migrations/versions/012_add_date_indexes.py` - Enforces DB_HOST
- `migrations/versions/027_optimize_slow_api_endpoints.py` - Enforces DB_HOST
- `migrations/versions/032_add_data_patrol_log_index.py` - Enforces DB_HOST

### Created (4 files)
- `utils/freshness_validator.py` - Centralized freshness checking
- `utils/fallback_registry.py` - Documented fallback chains
- `utils/data_validation_registry.py` - Data validation patterns
- `utils/query_cache.py` - General-purpose caching layer

### Documentation
- `steering/MEDIUM_ISSUES_FIXES.md` - This file

---

## Next Steps

### Phase 1: Enforcement (this commit)
1. All new code must use these utilities
2. Pre-commit hook validates no inline try/except for float()
3. Code review enforces DB_HOST requirement in migrations

### Phase 2: Adoption (1-2 weeks)
1. Migrate top 20 query patterns to use caching
2. Measure cache hit rates
3. Update dashboard to display fallback status

### Phase 3: Measurement (ongoing)
1. Daily reports of cache hit rates by type
2. Monthly freshness check compliance audit
3. Quarterly review of fallback frequency

---

## Debugging Guide

### "Data is stale" warnings
1. Check `max_data_staleness_days` in AlgoConfig
2. Verify watermark is advancing (check loader logs)
3. Check data source availability (API failures?)

### "Using fallback" messages
1. Check which fallback is being used (logged clearly)
2. Check why primary source failed (error message in logs)
3. Is this the expected fallback behavior? (check fallback_registry.py)

### Cache hit rates low?
1. Check if cache TTL is too short (increase it)
2. Check if key patterns are changing (use consistent parameters)
3. Check cache size (may be evicting too aggressively)

### DB_HOST validation errors
1. Ensure DB_HOST environment variable is set
2. Check CI/CD configuration provides DB_HOST
3. Cannot run migrations without explicit host specification
