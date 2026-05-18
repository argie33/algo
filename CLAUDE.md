# Stock Analytics Platform

Push to `main` → auto-deploys via GitHub Actions. Watch: https://github.com/argie33/algo/actions

## Rules

1. **One loader per data source**, integrated into `run-all-loaders.py` — else delete
2. **No one-time scripts** — delete backfills, diagnostics, utilities immediately
3. **No unintegrated code** — if not in main orchestration, it doesn't exist
4. **Dependencies used or deleted** — show WHERE and WHY before adding
5. **Test expiration dates** — `@pytest.mark.skip(reason="... (2026-06-15)")` or delete when expired
6. **No mock endpoints** — real data or delete completely
7. **No .env files, hardcoded secrets, or .env.local** — use AWS Secrets Manager; set `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` as env vars locally

## Local Dev (4 Steps)

1. PostgreSQL on localhost:5432
2. Set env vars: `DB_HOST=localhost DB_PORT=5432 DB_NAME=stocks DB_USER=stocks DB_PASSWORD="" ALPACA_API_KEY=... ALPACA_SECRET_KEY=...`
3. `python3 init_database.py`
4. `python3 run-all-loaders.py`

Test: `python3 algo/algo_orchestrator.py --dry-run`

## Core Architecture

### Orchestration Engine
- `algo.algo_orchestrator.Orchestrator` → 7-phase execution: validate → load → signal → filter → position → execute → reconcile
- Entry: `python3 algo/algo_orchestrator.py` (live trading) or `--dry-run` (plan without trades)

### Signal & Filtering Pipeline
- `algo.algo_signals.SignalCalculator` → All 50+ technical indicators, momentum, mean-reversion signals
- `algo.algo_filter_pipeline.FilterPipeline` → Sector rotation, liquidity filters, earnings blackout, circuit breaker
- Both return DataFrame with `(symbol, signal_type, value, timestamp)` structure

### Risk & Execution
- `algo.algo_trade_executor.TradeExecutor` → Order placement, position management, slippage modeling
- `algo.algo_position_monitor.PositionMonitor` → Track open positions, margin, exposure per sector/symbol
- `algo.algo_var.ValueAtRisk` → 95% VaR calculation, position-level and portfolio-level

### Data Pipeline (40 Loaders)
- All loaders in `loaders/*.py`, each inherits from OptimalLoader
- Output: PostgreSQL tables in schema `public`
- Run all: `python3 run-all-loaders.py`
- Each loader: idempotent, handles backfill + incremental loads

### Database Schema
Key tables: `prices`, `signals`, `positions`, `trades`, `earnings_calendar`, `market_events`, `sector_rotation`
- Indexes on (symbol, date) for price lookups
- Connect via `config.credential_manager.CredentialManager` (reads AWS Secrets Manager)
