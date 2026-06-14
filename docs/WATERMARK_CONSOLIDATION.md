# Watermark & Freshness Consolidation (2026-06-14)

## Problem Statement

The codebase had **4 different watermark/freshness tracking systems** with unclear dependencies and conflicting thresholds:

1. **utils/loaders/** — Per-loader watermark handling (incremental loads)
2. **utils/data/watermark.py** — `WatermarkManager` for database watermark tracking
3. **utils/validation/freshness_config.py** — Comprehensive freshness rules (8 critical tables, per-table thresholds)
4. **utils/validation/freshness.py** — Simple single-threshold approach (one global `max_data_staleness_days`)
5. **utils/data/ops.py** — Direct use of old freshness.py functions
6. **lambda/api/routes/utils.py** — `check_data_freshness()` with hardcoded `warning_days` per caller
7. **algo/risk/circuit_breaker.py** — Hardcoded trading-day freshness logic
8. **algo/orchestrator/phase1_data_freshness.py** — Hardcoded price freshness checks

**Impact:** Unclear ground truth for "is data stale?" — different systems disagreed on thresholds, leading to risk of serving stale data.

## Solution: Unified DataAgeValidator

Created **`utils/data/age_validator.py`** — single source of truth that:

1. **Uses centralized rules** from `freshness_config.py` (8 critical tables, 1-30 day thresholds)
2. **Queries tables** for actual latest data date
3. **Calculates age** with weekend adjustment (Friday data fresh through Sunday)
4. **Returns complete info**: age, freshness rule, staleness status, message

## Architecture

```
GROUND TRUTH: freshness_config.py (RULES ONLY)
    ↓
DataAgeValidator
    ├── check(table_name) → Dict with is_fresh, age_days, rule, message
    ├── check_multiple(tables) → Aggregate results
    ├── is_fresh(table_name) → bool
    ├── get_loader_watermark() → Optional[date]
    └── record_loader_watermark() → bool

BACKWARDS COMPATIBILITY:
    ├── freshness.py → re-exports from DataAgeValidator (deprecated)
    ├── is_fresh() → DataAgeValidator wrapper
    └── check_freshness() → DataAgeValidator wrapper
```

## What Changed

### Created
- **utils/data/age_validator.py** — Unified validator (500 lines, complete)
- **tests/test_watermark_consolidation.py** — Test suite

### Updated
- **utils/validation/freshness.py** — Now deprecation shim (re-exports from age_validator)
- **utils/validation/__init__.py** — Exports `DataAgeValidator`
- **algo/risk/circuit_breaker.py** — `_check_data_freshness()` now uses `DataAgeValidator.check()`

### Kept (No Changes Needed)
- **utils/validation/freshness_config.py** — Authority on rules (unchanged)
- **utils/data/watermark.py** — Database tracking (unchanged)
- **loaders/load_prices.py** — Still uses `WatermarkManager` directly (unchanged, uses it correctly)

## Usage Guide

### For New Code
```python
from utils.validation import DataAgeValidator

# Quick check
if DataAgeValidator.is_fresh('price_daily'):
    use_data()

# Detailed check
result = DataAgeValidator.check('algo_portfolio_snapshots')
if not result['is_fresh']:
    logger.warning(f"Stale: {result['message']}")
    # result['age_days'] = how old
    # result['rule']['max_age_days'] = threshold
    # result['is_critical'] = halt if stale?
```

### For Existing Code
No changes required. Old functions still work:
```python
from utils.validation import check_freshness, is_fresh

# Still works, but uses old generic 3-day threshold
result = check_freshness(last_loaded_date, data_type='price')
```

## Freshness Rules (Source of Truth)

All thresholds come from `freshness_config.FRESHNESS_RULES`:

### Critical Tables (Halt if stale)
- `price_daily`: 1 day
- `algo_portfolio_snapshots`: 1 day
- `algo_performance_daily`: 1 day
- `algo_risk_daily`: 1 day
- `buy_sell_daily`: 1 day
- `swing_trader_scores`: 1 day
- `market_health_daily`: 1 day
- `market_exposure_daily`: 1 day

### Important Tables (Warning if stale)
- `technical_data_daily`: 7 days
- `trend_template_data`: 7 days
- `grade_distribution_daily`: 7 days
- `algo_config`: 30 days

### Supporting Tables (Optional)
- `sector_ranking`: 14 days
- `economic_data`: 14 days
- `algo_trades`: 1 day

## Next Steps

### Phase 2: Eliminate Remaining Redundancy
1. Update API routes (`lambda/api/routes/*.py`) to use `DataAgeValidator.check()` instead of `routes/utils.check_data_freshness()`
2. Update Phase 1 (`algo/orchestrator/phase1_data_freshness.py`) to use validator for critical tables
3. Remove hardcoded checks from orchestrator phases

### Phase 3: Deprecation
1. Mark `utils/validation/freshness.py` for removal (after 1 quarter)
2. Migrate all callers to `DataAgeValidator`
3. Remove old functions

## Testing

Run test suite:
```bash
pytest tests/test_watermark_consolidation.py -v
```

Validates:
- Freshness rules are defined
- Critical tables marked correctly
- No duplicate/conflicting thresholds
- Backwards compatibility works

## Weekend Adjustment Detail

The validator accounts for trading day schedules:

| Day | Friday Data Age | Adjusted Threshold | Status |
|-----|-----------------|-------------------|--------|
| Fri | 0 days | 1 day | Fresh ✓ |
| Sat | 1 day | 1+1=2 days | Fresh ✓ |
| Sun | 2 days | 1+2=3 days | Fresh ✓ |
| Mon | 3 days | 1 day | Stale ✗ |

This prevents false "stale" warnings when markets closed for weekends.

## References

- **CLAUDE.md:** Steering principles (single source of truth for rules, no live status)
- **freshness_config.py:** Complete rule definitions (15+ tables with clear thresholds)
- **watermark.py:** Database watermark tracking (loader-specific, incremental loads)
