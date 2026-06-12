# Migration Guide: Using Centralized Utilities

This guide shows how to migrate existing code to use the new centralized utilities for freshness checking, fallback handling, data validation, and caching.

## Quick Start: Before & After Examples

### Pattern 1: Freshness Checking

**BEFORE: Scattered, hardcoded thresholds**
```python
# Different files have different thresholds (1, 2, 3, 5 days)
if exp_age is not None and exp_age > 1:
    logger.warning(f"Exposure data is {exp_age} days old")
```

**AFTER: Centralized, runtime-configurable**
```python
from utils.freshness_validator import check_freshness
freshness = check_freshness(exp_date, 'exposure')
if not freshness['is_fresh']:
    logger.warning(freshness['message'])
```

### Pattern 2: Data Validation

**BEFORE: Inline try/except blocks**
```python
try:
    min_score = float(min_score_str) if min_score_str else None
except (ValueError, TypeError):
    return error_response(400, 'bad_request', 'min_score must be numeric')
```

**AFTER: Centralized validation**
```python
from utils.safe_data_conversion import safe_float_strict
min_score = safe_float_strict(min_score_str, context='query param')
if min_score_str and min_score is None:
    return error_response(400, 'bad_request', 'min_score must be numeric')
```

### Pattern 3: Fallback Handling

**BEFORE: Silent fallbacks**
```python
try:
    data = api_call()
except:
    logger.info("API failed, using database")
    data = db_call()
```

**AFTER: Documented fallbacks**
```python
from utils.data_ops import try_with_fallback
data = try_with_fallback(
    primary=api_call,
    fallback=db_call,
    resource='market_data',
    fallback_step='database_fallback'
)
```

## Key Files to Migrate

1. **lambda/api/routes/algo.py** - Inline float validation ← START HERE
2. **tools/dashboard/dashboard.py** - Manual age calculations
3. **algo/algo_circuit_breaker.py** - VIX fallback handling
4. **loaders/** - Watermark freshness checks

## Import Patterns

```python
# Freshness
from utils.freshness_validator import check_freshness, is_fresh

# Fallbacks
from utils.fallback_registry import log_fallback_usage, FallbackTrigger

# Validation
from utils.safe_data_conversion import safe_float, safe_float_strict, safe_int

# Caching
from utils.query_cache import get_or_create_cache

# All-in-one
from utils.data_ops import (
    load_with_freshness, try_with_fallback, get_or_cache, validate_and_log
)
```

See `steering/MEDIUM_ISSUES_FIXES.md` for full details.
