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

1. **One loader per data source**, integrated into `run-all-loaders.py` — else delete
2. **No one-time scripts** — delete backfills, diagnostics, utilities immediately (Rule 2 in CLAUDE.md)
3. **No unintegrated code** — if not in main orchestration, it doesn't exist
4. **Dependencies used or deleted** — show WHERE and WHY before adding
5. **Test expiration dates** — `@pytest.mark.skip(reason="... (2026-06-15)")` or delete when expired
6. **No mock endpoints** — real data or delete completely
7. **No .env files, hardcoded secrets, or .env.local** — use AWS Secrets Manager; set env vars locally only

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
