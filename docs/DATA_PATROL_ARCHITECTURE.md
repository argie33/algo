# Data Patrol Architecture

## Overview

The data patrol system monitors data integrity across the algo trading platform. It runs periodic checks on all data tables and logs findings to enable quick problem detection and debugging.

**Problem solved:** The original implementation was a monolithic 2,500-line class with 40+ methods doing completely different things. The new modular architecture separates concerns, improves testability, and makes adding new checks straightforward.

## Architecture

### Modular Approach

Each check type is a separate class inheriting from `BaseCheck`:

```
algo/monitoring/data_patrol/
├── __init__.py              # Main DataPatrol orchestrator
├── base.py                  # BaseCheck abstract class
├── config.py                # PatrolConfig - loads thresholds from DB
├── logger.py                # PatrolLogger - writes results to DB
└── checks/
    ├── staleness.py         # StalenessChecker - data age validation
    ├── quality.py           # QualityChecker - NULL, OHLC, zero-value checks
    ├── price_sanity.py      # PriceSanityChecker - extreme moves, gaps
    ├── coverage.py          # CoverageChecker - symbol coverage, loader contracts
    ├── alignment.py         # AlignmentChecker - cross-table consistency
    └── specialized.py       # SpecializedChecker - earnings, fundamentals, trades
```

### Key Classes

#### BaseCheck (base.py)
Abstract base for all checks. Subclasses implement `run(cur)` to return a list of `CheckResult` objects.

```python
class BaseCheck(ABC):
    def __init__(self, config: PatrolConfig):
        self.config = config
        self.results: List[CheckResult] = []
    
    @abstractmethod
    def run(self, cur) -> List[CheckResult]:
        pass
    
    def log(self, check_name, severity, target, message, details):
        result = CheckResult(...)
        self.results.append(result)
        return result
```

#### PatrolConfig (config.py)
Loads thresholds from `algo_config` table with sensible defaults. Provides typed getters for all configuration values:

```python
config = PatrolConfig(cur)
staleness_cfg = config.get_staleness_windows()  # Dict of table -> days
coverage_cfg = config.get_coverage_thresholds()  # error_pct, warn_pct
```

#### DataPatrol (__init__.py)
Main orchestrator. Instantiates check classes, runs them, and logs results:

```python
patrol = DataPatrol()
summary = patrol.run(quick=False, validate_alpaca=False)
# Returns: {
#   "run_id": "PATROL-20260616-121530",
#   "counts": {"info": 45, "warn": 3, "error": 0, "critical": 0},
#   "ready": True,
#   "flagged": [...],
#   "all_results": [...]
# }
```

### Check Classes

Each check class focuses on a single concern:

#### StalenessChecker
Verifies data is fresh within configured windows (7 days for daily, etc.). Monitors 14 tables including prices, signals, earnings, fundamentals.

**Key methods:**
- Loads latest date for each table
- Compares against max_days threshold from config
- Alerts on stale critical signal tables via notifications

#### QualityChecker
Detects data anomalies: NULL spikes, suspicious OHLC patterns, zero values, volume extremes.

**Key methods:**
- `check_null_anomalies()` - sudden NULL% increase
- `check_zero_or_identical()` - zero volume/price or all-identical OHLC
- `check_ohlc_sanity()` - high<OHLC relationships
- `check_volume_sanity()` - extreme low/high volume symbols

#### PriceSanityChecker
Detects price corruption: extreme day-over-day moves, corporate actions, sequence gaps.

**Key methods:**
- `check_price_moves()` - >50% move detection
- `check_corporate_actions()` - >30% single-day drops
- `check_sequence_continuity()` - gaps in trading days (using SPY as canary)

#### CoverageChecker
Validates symbol coverage and loader output contracts.

**Key methods:**
- `check_universe_coverage()` - % symbols in today's load vs baseline
- `check_loader_coverage()` - symbol coverage % for critical tables
- `check_loader_contracts()` - row count contracts for each loader
- `check_signal_quality_ratio()` - BUY/SELL signal cleanness

#### AlignmentChecker
Cross-table validation ensuring dependent tables stay in sync.

**Key methods:**
- `check_signal_source_alignment()` - SQS vs buy_sell_daily
- `check_signal_data_alignment()` - every signal has price + technical data
- `check_trade_alignment()` - every filled trade has price history
- `check_score_freshness()` - computed scores >= raw data dates
- `check_cross_table_alignment()` - all tables cover same symbols as price_daily

#### SpecializedChecker
Domain-specific checks for earnings, fundamentals, technical indicators, sentiment.

**Key methods:**
- `check_earnings_data()` - freshness of earnings tables
- `check_fundamental_data()` - financial statement freshness
- `check_derived_metrics()` - technical indicator bounds (RSI 0-100, no NaN)
- `check_sentiment_aggregate()` - sentiment table structure + freshness
- `check_trade_recorder_columns()` - trade table schema validation

## Execution Flow

```
1. DataPatrol.run()
   ├── Load PatrolConfig from algo_config table
   ├── Create PatrolLogger with run_id
   ├── Log configuration snapshot
   │
   ├── _run_checks() - execute all checks
   │   ├── StalenessChecker.run(cur) → [CheckResult, ...]
   │   ├── QualityChecker.run(cur) → [CheckResult, ...]
   │   ├── PriceSanityChecker.run(cur) → [CheckResult, ...]
   │   ├── CoverageChecker.run(cur) → [CheckResult, ...]
   │   ├── AlignmentChecker.run(cur) → [CheckResult, ...]
   │   └── SpecializedChecker.run(cur) → [CheckResult, ...]
   │
   ├── Log all results to data_patrol_log table
   ├── Log performance metrics
   ├── Update DynamoDB completion status
   │
   └── summarize() - generate report
       ├── Count findings by severity
       ├── Log summary to stdout
       └── Return dict with results
```

## Configuration

All thresholds are configurable via `algo_config` table. Defaults are hardcoded as fallback.

### Common Config Keys

```
patrol_staleness_price_daily          # days before price_daily is stale (default: 7)
patrol_staleness_buy_sell_daily       # days before signals are stale (default: 7)
patrol_max_null_pct_threshold         # max % NULLs in price_daily (default: 5)
patrol_new_zero_symbols_error         # threshold for ERROR on new zeros (default: 10)
patrol_new_zero_symbols_warn          # threshold for WARN on new zeros (default: 5)
patrol_low_volume_threshold           # minimum volume count (default: 1000)
patrol_max_daily_move_pct             # max day-over-day % move (default: 50%)
patrol_coverage_error_threshold_pct   # min symbol coverage (default: 95%)
patrol_coverage_warning_threshold_pct # min symbol coverage WARN (default: 90%)
patrol_price_daily_14d_min            # min rows for 14-day price (default: 40000)
```

See `PatrolConfig` class for complete list.

## Severity Levels

- `INFO` - Normal operation, conditions within expected ranges
- `WARN` - Minor issue, degraded service but functional
- `ERROR` - Significant data issue, trades may be impacted
- `CRITICAL` - Severe problem, algo should halt

## Output

Results are logged to `data_patrol_log` table:

```sql
SELECT * FROM data_patrol_log
WHERE patrol_run_id = 'PATROL-20260616-121530'
ORDER BY created_at DESC;

-- Columns:
-- patrol_run_id, check_name, severity, target_table, message, details
```

## Running Data Patrol

### Manual Trigger
```bash
python algo/algo_data_patrol.py
```

### With Options
```bash
python algo/algo_data_patrol.py --quick              # Critical checks only
python algo/algo_data_patrol.py --validate-alpaca   # Cross-validate vs Alpaca
python algo/algo_data_patrol.py --json              # JSON output
```

### ECS Task
Configured to run on schedule. Triggered by orchestrator or manual API call:
```
POST /api/algo/monitoring/data-patrol
```

## Comparison: Old vs New

### Old (Monolithic)
- Single 2,500-line class
- 40+ methods doing unrelated things
- Code duplication (config loading, logging)
- Hard to test individual checks
- Difficult to add new checks

### New (Modular)
- 6 focused check classes
- Each class handles one concern
- Configuration centralized in PatrolConfig
- Logging centralized in PatrolLogger
- Easy to unit test individual checks
- New checks: 50 lines + registration in orchestrator
- Clear extension points (inherit BaseCheck, implement run())

## Adding a New Check

1. Create `checks/new_check.py`:
```python
from ..base import BaseCheck, CheckResult
from ..config import INFO, WARN, ERROR

class MyNewChecker(BaseCheck):
    def run(self, cur) -> List[CheckResult]:
        self.results = []
        # Do checks...
        self.log("my_check", WARN, "my_table", "Message", {"detail": "value"})
        return self.results
```

2. Export in `checks/__init__.py`:
```python
from .new_check import MyNewChecker
__all__ = [..., "MyNewChecker"]
```

3. Register in `DataPatrol._run_checks()`:
```python
checks.extend([
    ("my_new_check", MyNewChecker(self.config)),
])
```

## Testing

Each check can be tested independently:

```python
from algo.monitoring.data_patrol import PatrolConfig
from algo.monitoring.data_patrol.checks import StalenessChecker

config = PatrolConfig()
checker = StalenessChecker(config)
results = checker.run(cur)

assert len(results) > 0
assert results[0].severity in ("info", "warn", "error", "critical")
```

## Migration from Old System

The old monolithic implementation (`data_patrol_legacy.py.bak`) is backed up for reference. All functionality has been ported to the new modular architecture:

- **Staleness**: StalenessChecker
- **NULL anomalies**: QualityChecker.check_null_anomalies()
- **Zero/identical OHLC**: QualityChecker.check_zero_or_identical()
- **OHLC sanity**: QualityChecker.check_ohlc_sanity()
- **Volume**: QualityChecker.check_volume_sanity()
- **Price moves**: PriceSanityChecker.check_price_moves()
- **Corporate actions**: PriceSanityChecker.check_corporate_actions()
- **Sequence gaps**: PriceSanityChecker.check_sequence_continuity()
- **Coverage**: CoverageChecker
- **Alignment**: AlignmentChecker
- **Specialized**: SpecializedChecker

Entry point (`algo_data_patrol.py`) correctly routes to new implementation.

## Performance

Typical patrol execution:
- Quick (critical checks): 30-45 seconds
- Full (all checks): 90-120 seconds
- Slow threshold: >120 seconds (logged with warning)

Check-level timing tracked in `check_timings` dict.
