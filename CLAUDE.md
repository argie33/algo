# Stock Analytics Platform

Real-time algorithmic trading system: Ingest market data → Calculate signals → Filter → Execute trades → Monitor risk.

**Entry:** `python3 algo/algo_orchestrator.py` (live) or `--dry-run` (plan without trades)

**Deploy:** Push to `main` → auto-deploys via GitHub Actions: https://github.com/argie33/algo/actions

## Local Setup

PostgreSQL 17 on localhost:5432 (already installed).

**Set database env vars before running any loaders/scripts:**
```bash
export DB_HOST=localhost DB_PORT=5432 DB_NAME=stocks DB_USER=stocks DB_PASSWORD=stocks
```

**Then run:**
```powershell
python3 init_database.py      # Create schema + indexes (idempotent)
python3 run-all-loaders.py    # Load market data (22 loaders, ~45 min)
python3 algo/algo_orchestrator.py --dry-run  # Verify full pipeline (no trades)
```

**For pytest:** env vars must be set first
```bash
export DB_HOST=localhost && python3 -m pytest tests/ -v
```

## Architecture

**Orchestrator** (`algo/algo_orchestrator.py`): Validates → Loads → Calculates signals → Filters → Positions → Executes → Reconciles

**Core Modules:**
- `algo_signals.py` – 50+ technical indicators, momentum, mean-reversion
- `algo_filter_pipeline.py` – Sector rotation, liquidity, earnings blackout, circuit breaker
- `algo_trade_executor.py` – Order placement, position management, slippage
- `algo_position_monitor.py` – Track positions, margin, sector exposure
- `algo_var.py` – 95% VaR calculation

**Data Pipeline:**
- `loaders/` – 40 data sources (each inherits OptimalLoader, idempotent)
- PostgreSQL `stocks` database, schema `public`
- Run all loaders: `python3 run-all-loaders.py`

## Testing

```powershell
python3 -m pytest tests/ -v                    # Run all tests
python3 -m pytest tests/test_signals.py -v    # Run signal tests
python3 algo/algo_orchestrator.py --dry-run   # Integration test (no trades)
```

Type checking: `pyright algo/` (enforced in CI)

## Code Standards

- Type annotations required throughout
- Snake_case for functions/variables, PascalCase for classes
- Docstrings for public APIs only (one-liner max, unless WHY is non-obvious)
- No comments explaining WHAT—variable names do that. Only WHY if surprising.
- Pre-commit hook: linting, formatting, type checking (must pass before commit)
