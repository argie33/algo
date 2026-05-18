# Algo Execution Engine

Core orchestrator and signals. All algo code must inherit from `OptimalLoader` or use `AlgoBase` parent class.

## Signals & Trade Rules

- **Signals:** Entry/exit via loadbuyselldaily.py
- **Position sizing:** Weighted by quality score + volatility
- **Circuit breakers:** Account-level stop-loss at 15% drawdown
- **Reconciliation:** Daily at 15:59 UTC

## Testing

- Backtests use `@pytest.mark.slow` or `@pytest.mark.backtest`
- All tests must have expiration date: `@pytest.mark.skip(reason="... (2026-MM-DD)")`
- Live trade tests forbidden—use `--dry-run` mode only

## Naming

- Filters: `filter_*()` prefix
- Validators: `validate_*()` prefix
- Score calculators: `*_score()` suffix
