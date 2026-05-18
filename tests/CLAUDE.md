# Test Suite

24 test files organized by type. All tests MUST have expiration dates.

## Test Organization

```
tests/
├── unit/              — Fast, isolated unit tests
├── integration/       — Full flow tests (database required)
├── edge_cases/        — Boundary conditions, extreme values
├── backtest/          — Algorithm backtests (slow)
├── performance/       — Load & latency tests
└── load/              — Data loading validation
```

## Test Markers

- `@pytest.mark.unit` — Unit tests (fast)
- `@pytest.mark.integration` — Integration tests
- `@pytest.mark.slow` — Backtests, performance tests
- `@pytest.mark.skip(reason="... (2026-MM-DD)")` — Temporary skip with expiration
- `@pytest.mark.db` — Requires database

## Expiration Rule

Every skip marker MUST have date:
```python
@pytest.mark.skip(reason="Waiting for market API fix (2026-06-15)")
def test_market_data():
    pass
```

If expired → DELETE immediately.
