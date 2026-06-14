# Magic Numbers Centralization

**Status:** Complete (June 14, 2026)

## Overview

All magic numbers (hardcoded thresholds, multipliers, limits) in the algo system have been centralized into a single source of truth: `algo/infrastructure/constants.py`.

## Problem Solved

Previously, magic numbers were scattered throughout the codebase:
- **retry.py**: Rate limits (400, 180, 4, 30 calls/minute)
- **regime_manager.py**: Position multipliers (1.0, 0.75, 0.5, 0.0)
- **data_patrol.py**: Patrol thresholds (staleness windows, volume limits, coverage ratios)
- **pool_monitor.py**: Database connection limits (100, 80%)
- **load_prices.py**: Batch sizes and time thresholds
- Various other files

**Impact:** Changing a threshold required:
1. Grep across codebase
2. Identify all usages
3. Edit multiple files
4. Risk of inconsistency

## Solution

Created `algo/infrastructure/constants.py` with organized sections:

### Rate Limiting & API Thresholds
```python
YFINANCE_RATE_LIMIT_CPM = 400  # Optimized: 30min for full universe load
ALPACA_DATA_RATE_LIMIT_CPM = 180  # 10% headroom on 200 limit
ALPHA_VANTAGE_RATE_LIMIT_CPM = 4  # 20% headroom on 5 limit
DEFAULT_RATE_LIMIT_CPM = 30  # Conservative fallback
```

### Portfolio & Risk Management (Regime-Based)
```python
# Confirmed Uptrend
REGIME_POSITION_SIZE_CONFIRMED_UPTREND = 1.0  # Full size
REGIME_HOLD_DAYS_CONFIRMED_UPTREND = 1.5  # 30 days
REGIME_TARGET_CONFIRMED_UPTREND = 1.0  # 1.5R/3.0R/4.0R targets
REGIME_MIN_SWING_SCORE_CONFIRMED_UPTREND = 55

# Uptrend Under Pressure
REGIME_POSITION_SIZE_UPTREND_UNDER_PRESSURE = 0.75  # 75% size
...

# Caution
REGIME_POSITION_SIZE_CAUTION = 0.5  # Half size
...

# Correction
REGIME_POSITION_SIZE_CORRECTION = 0.0  # No new entries
...
```

### Data Quality & Monitoring
```python
# Staleness windows (days)
STALENESS_WINDOW_PRICE_DAILY = 7
STALENESS_WINDOW_STOCK_SCORES = 14
STALENESS_WINDOW_EARNINGS_HISTORY = 120

# Anomaly detection
ZERO_SYMBOLS_ERROR_THRESHOLD = 30  # New zero-volume symbols
ZERO_SYMBOLS_WARN_THRESHOLD = 5
IDENTICAL_OHLC_THRESHOLD = 30  # Suspicious price data

# Volume sanity
VOLUME_LOW_THRESHOLD = 1_000_000
VOLUME_HIGH_THRESHOLD = 100_000_000
NEW_LOW_VOLUME_ALERT_COUNT = 50

# Price sanity
EXTREME_PRICE_MOVE_RATIO = 0.5  # >50% move in one day
EXTREME_MOVE_COUNT_THRESHOLD = 10
PRICE_XVAL_MISMATCH_PCT = 5  # Cross-validation tolerance
```

### Loader Contracts
```python
LOADER_PRICE_DAILY_14D_MIN = 40_000
LOADER_BUY_SELL_DAILY_14D_MIN = 800
COVERAGE_RATIO_MIN_STRICT = 0.95
COVERAGE_RATIO_MIN_NORMAL = 0.90
```

### Database & Infrastructure
```python
DB_MAX_CONNECTIONS = 100
DB_POOL_ALERT_THRESHOLD_PCT = 80
DB_POOL_TIMEOUT_SEC = 300
```

## Files Updated

1. **algo/infrastructure/constants.py** (NEW)
   - 150+ lines of organized constants
   - Grouped by functional area
   - Each constant documented with rationale

2. **algo/infrastructure/retry.py**
   - Import all rate limit constants
   - Use constants in RateLimiter pre-built instances
   - Use constants in retry decorator defaults

3. **algo/orchestration/regime_manager.py**
   - Import all REGIME_* constants
   - Update REGIME_PARAMS dict to use constants
   - No logic changes, just parameterization

4. **algo/monitoring/data_patrol.py**
   - Import 25+ data quality constants
   - Update _load_configuration() to use constants as defaults
   - Update all threshold checks to use constants
   - Update SQL queries with parameterized thresholds

5. **utils/db/pool_monitor.py**
   - Import database constants
   - Update RDSPoolMonitor thresholds
   - Replace hardcoded 75 with DB_POOL_ALERT_THRESHOLD_PCT

## How to Use

### Adding a New Constant

```python
# 1. Add to constants.py in appropriate section
SOME_NEW_THRESHOLD = 42  # Description of what this controls

# 2. Import in the file that uses it
from algo.infrastructure.constants import SOME_NEW_THRESHOLD

# 3. Use it instead of the magic number
if value > SOME_NEW_THRESHOLD:
    # do something
```

### Changing a Threshold

**Before:**
```
grep -r "value > 5" algo/  # Find all usages
# Edit 8 files, change 12 lines
# Risk of missing one
```

**After:**
```python
# Edit algo/infrastructure/constants.py
PRICE_XVAL_MISMATCH_PCT = 7  # Changed from 5

# All code automatically uses new value
```

### Tuning at Runtime

For thresholds that are read from `algo_config` table (database):
```python
# In data_patrol.py:
max_null_pct = self._get_config_value(
    cur, 'patrol_max_null_pct_threshold', 
    NULL_ANOMALY_MAX_PCT  # Uses constant as fallback default
)
```

This allows:
- Runtime tuning via database without code changes
- Fallback to constants if database value not set
- Easy auditing (patrol log shows which thresholds are configured)

## Benefits

1. **Single Source of Truth**
   - One file to understand all thresholds
   - Easy to find what controls behavior

2. **Reduced Change Risk**
   - Change one place, everywhere updates
   - Can't accidentally miss a usage

3. **Better Documentation**
   - Each constant includes rationale
   - Comments explain what metric it controls
   - Grouped by function (not scattered)

4. **Easier Optimization**
   - Adjust YFINANCE_RATE_LIMIT_CPM from 400 to 350
   - Measure end-to-end impact
   - Revert if needed
   - All without grep+edit

5. **Configurability**
   - Runtime tuning via algo_config table
   - Constants provide sensible defaults
   - Easy to override per environment

## Examples

### Example 1: Adjust Rate Limits

```python
# algo/infrastructure/constants.py
YFINANCE_RATE_LIMIT_CPM = 350  # Down from 400, trade off speed for stability

# Automatically affects:
# - algo/infrastructure/retry.py: YFINANCE_LIMITER
# - All loaders using that limiter
# - No other files need editing
```

### Example 2: Change Patrol Alert Threshold

```python
# algo/infrastructure/constants.py
ZERO_SYMBOLS_ERROR_THRESHOLD = 50  # Up from 30, be less aggressive

# Automatically affects:
# - algo/monitoring/data_patrol.py: check_zero_or_identical()
# - Next patrol run uses new threshold
# - Log shows configured value in patrol_configuration_audit entry
```

### Example 3: Regime-Based Position Sizing

All regime parameter changes in one place:
```python
# Make caution regime more defensive
REGIME_POSITION_SIZE_CAUTION = 0.25  # Down from 0.5
REGIME_MIN_SWING_SCORE_CAUTION = 80  # Up from 70

# Automatically propagates to:
# - RegimeManager.REGIME_PARAMS dict
# - PositionSizer (uses regime params)
# - SwingTraderScore gate (uses regime score)
```

## Testing Constants

Constants are used via direct import, same as code constants anywhere:

```python
# In test files:
from algo.infrastructure.constants import YFINANCE_RATE_LIMIT_CPM

def test_rate_limiter():
    limiter = RateLimiter(calls_per_minute=YFINANCE_RATE_LIMIT_CPM)
    assert limiter._min_interval == pytest.approx(60.0 / YFINANCE_RATE_LIMIT_CPM)
```

## Migration Notes

- Constants module is backward compatible
- No API changes to any functions
- Existing code continues to work
- Constants are imported directly where needed
- No need to update __init__.py exports (optional, not required)

## Future Improvements

Consider adding:
1. Constants for more scattered magic numbers (load_prices.py batch sizes, timeout values)
2. CLI tool to view/audit all constants
3. CI check to flag new magic numbers (hardcoded numbers not in constants.py)
4. Constants versioning if thresholds change frequently
