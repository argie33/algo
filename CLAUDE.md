# Stock Analytics Platform

Real-time algorithmic trading system: Ingest market data → Calculate signals → Filter → Execute trades → Monitor risk.

**Entry:** `python3 algo/algo_orchestrator.py` (live) or `--dry-run` (plan without trades)

**Deploy:** Push to `main` → auto-deploys via GitHub Actions: https://github.com/argie33/algo/actions

## Local Setup

PostgreSQL 17 on localhost:5432 (already installed). Environment variables configured in PowerShell profile.

```powershell
python3 init_database.py      # Create schema + indexes
python3 run-all-loaders.py    # Load market data (40 loaders)
python3 algo/algo_orchestrator.py --dry-run  # Verify full pipeline
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

## Rules

1. **All loaders must be integrated** into `run-all-loaders.py` — no orphaned loader files
2. **No unintegrated scripts** at root — dev utilities go in `scripts/` directory or delete
3. **No one-time diagnostics** — temporary debug/audit files do not belong in repo
4. **Credentials** — no .env, secrets, or hardcoded API keys — use AWS Secrets Manager
5. **Test expiration** — mark skipped tests with expiration date or delete when expired
6. **Real data only** — no mock endpoints or fake data sources
7. **Dependencies** — before adding anything, document WHERE it's used and WHY

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
