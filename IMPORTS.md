# Module Import Reference

Use this guide to find the right import for common operations. Claude Code reads this to resolve symbols more efficiently, reducing context bloat.

## Core Orchestration

**Main entry point for backtesting & paper trading:**
```python
from algo.algo_orchestrator import Orchestrator

# 7-phase execution: validate → load → signal → filter → position → execute → reconcile
strategy = Orchestrator(mode='paper', backtest_dates=['2024-01-01', '2024-12-31'])
strategy.run()
```

## Signals & Filtering

**Signal calculation (50+ indicators):**
```python
from algo.algo_signals import SignalComputer

calc = SignalComputer()
calc.connect()
signals = calc.minervini_trend_template('AAPL', '2024-01-15')
calc.disconnect()
```

**Filter pipeline (sector, liquidity, earnings blackout):**
```python
from algo.algo_filter_pipeline import FilterPipeline

pipeline = FilterPipeline()
pipeline.connect()
filtered = pipeline.apply_all_tiers(candidates, eval_date)
pipeline.disconnect()
```

## Position & Risk Management

**Current position tracking:**
```python
from algo.algo_position_monitor import PositionMonitor

monitor = PositionMonitor()
monitor.connect()
positions = monitor.fetch_all_positions(eval_date)
monitor.disconnect()
```

**Value at Risk (VaR) calculation:**
```python
from algo.algo_var import ValueAtRisk

var = ValueAtRisk(confidence=0.95, lookback_days=252)
portfolio_var = var.calculate_portfolio(positions)
```

**Trade executor:**
```python
from algo.algo_trade_executor import TradeExecutor

executor = TradeExecutor(config)
executor.execute_trade(symbol='AAPL', entry_price=150.0, shares=100, stop_price=145.0)
```

## Data Loaders

**All 40 loaders follow the same pattern:**
```python
from loaders.loadstockscores import OptimalLoader  # Example

loader = OptimalLoader()
df = loader.load(start_date='2024-01-01', end_date='2024-12-31')
# Output: DataFrame with (symbol, date) index
# Inserted into PostgreSQL table
```

**Run all loaders (orchestrated):**
```bash
python3 run-all-loaders.py
```

## Database & Configuration

**Credential management (reads AWS Secrets Manager):**
```python
from config.credential_manager import CredentialManager

creds = CredentialManager()
alpaca_api_key = creds.get('alpaca_api_key')
db_password = creds.get('database_password')
```

**Database tables:**
- `prices`: (symbol, date) → (close, volume, open, high, low)
- `signals`: (symbol, date) → (signal_type, value, timestamp)
- `positions`: (symbol, date) → (quantity, avg_cost, current_value)
- `trades`: (id, symbol, date) → (quantity, price, side, commission)
- `earnings_calendar`: (symbol, date) → (eps_actual, eps_estimate, eps_surprise)

## Common Patterns

**Error handling with retry:**
```python
from algo.algo_retry import retry_with_backoff

@retry_with_backoff(max_retries=3, initial_delay=1)
def fetch_data():
    pass
```

**Logging:**
```python
from algo.algo_logging import get_logger

logger = get_logger(__name__)
logger.info("Message")
```

## Quick Reference by Task

| Task | Module | Class |
|------|--------|-------|
| Run daily trading | algo_orchestrator | Orchestrator |
| Calculate signals | algo_signals | SignalComputer |
| Filter candidates | algo_filter_pipeline | FilterPipeline |
| Track positions | algo_position_monitor | PositionMonitor |
| Execute trades | algo_trade_executor | TradeExecutor |
| Risk calculations | algo_var | ValueAtRisk |
| Data validation | algo_data_patrol | DataPatrol |
| Alerts & monitoring | algo_alerts | AlertManager |

## Testing

**Run all tests:**
```bash
pytest tests/ -v --run-db
```

**Stress test (all loaders + orchestrator):**
```bash
pytest tests/test_stress_comprehensive.py -v --run-db -s
```
