# Trading System Architecture & Operations

Live trading system: Minervini trend-following + fundamental quality filters. Up to 15 concurrent positions, daily reconciliation with Alpaca.

## System Map

- **Orchestrator** (7 phases): `algo/algo_orchestrator.py` → Lambda `algo-algo-dev` → EventBridge 9:30 AM/1 PM/3 PM/5:30 PM ET
- **Loaders**: `loaders/load_*.py` → ECS Fargate → Step Functions (2:15 AM, 4:05 PM ET)
- **API**: `lambda/api/lambda_function.py` → Lambda `algo-api-dev`
- **Frontend**: `webapp/frontend/src/` → S3 + CloudFront
- **Database**: PostgreSQL RDS `algo-db` (db.t4g.small, 100 concurrent max)

## Schedule (Daily, Mon-Fri)

- **2:00 AM ET:** Morning pipeline (5-5.5h) — loads prices + technical data + swing scores before 9:30 AM deadline
- **2:40 AM ET:** Load constituents (EventBridge)
- **4:05 PM ET:** EOD pipeline (3-4h) — loads prices, market health, technical, signals
- **4:29 AM ET:** Load earnings calendar
- **4:30 PM ET:** Compute circuit breaker metrics
- **4:45 PM ET:** Compute performance metrics
- **9:30 AM, 1 PM, 3 PM, 5:30 PM ET:** Orchestrator runs (7 phases)

## Orchestrator Phases

1. **Phase 1:** Data freshness validation (halt if data >1 trading day stale)
2. **Phase 2:** Circuit breakers (halt on: drawdown ≥20%, daily loss ≥2%, consecutive losses ≥3, open risk ≥4%, VIX ≥35, market stage=4, weekly loss ≥5%, win rate <40%)
3. **Phase 3:** Position monitor + exposure policy
4. **Phase 4:** Execute exits (unblocked by halt)
5. **Phase 5:** Signal generation (blocked by halt)
6. **Phase 6:** Trade entries (blocked by halt)
7. **Phase 7:** Reconciliation + reporting (unblocked by halt)

## Data Architecture

**Positions:** Single source of truth = `algo_trades` table. Views: `algo_positions_with_risk` (materialized, refreshed Phase 7), `open_positions` (OPEN/PARTIALLY_FILLED).

**Technical Indicators:** `technical_data_daily` table (RSI, MACD, ATR, Bollinger, RS, etc.). Computed twice daily (2:15 AM + 4:05 PM) via vectorized loader (15-25 min). If incomplete (<70% coverage), post-load enrichment backfills NULL columns.

**Market Regime:** `market_exposure_daily` table (12 quantitative factors → market regime). Computed twice daily (3:30 AM + 4:30 PM). Orchestrators use most recent. Graceful degradation if EOD fails (morning regime covers).

**Earnings Calendar:** `earnings_calendar` table (symbol, earnings_date, announce_time). Loaded daily 4:29 AM via yfinance. Keeps 60 days history for blackout window gating.

## Signal Generation (Phase 5)

Pivot-breakout BUY signals filtered by quality ranking. Pipeline: (1) Check halt + market regime + exposure gates, (2) Fetch buy_sell_daily BUY signals (primary) or stock_scores fallback, (3) Filter: close > SMA_50, not in bottom 40% of range, (4) Liquidity check top 10, (5) Rank by composite_score, (6) Return candidates.

**Ranking:** composite_score (quality 25%, growth 20%, value 20%, positioning 15%, stability 12%, momentum 8%).

**Position limits:** Max 8 sector, max 5 industry (configurable).

**Data Validation (Critical for Accuracy):**
- Market regime: If market_exposure_daily is missing or exposure_pct is NULL, halt entries (fail-closed)
- Signal completeness: Each candidate validated for required fields (symbol, composite_score, entry_price, close, sma_50, signal_strength). Incomplete signals logged with reason and filtered. Phase 6 receives only complete signals.
- Halt flag check: Verifies Phase 1 data freshness gates are met before generating signals
- Liquidity checks: Top candidates validated for min volume/dollar volume before entry

All validation failures are explicitly logged (no silent skips). Operators see CloudWatch logs for every filtered signal with reason.

## Loader Configuration

**6 Core Loaders (FAIL-CLOSED):** Symbols, prices, swing scores, market health, trend template data. **50 Supporting Loaders (FAIL-OPEN):** Earnings, sentiment, technical, economic, sector. Continue if they fail.

**Parallelism:** Adaptive per-loader based on RDS connection pool saturation.
- stock_prices_daily: min=1, max=3 (yfinance rate limit protection)
- technical_data_daily: min=1, max=2 (prevents RDS hangs)
- Analytics loaders: min=1, max=8

**Rate Limiting Mitigation:**
- yfinance: batch_size=150, exponential backoff (5 max retries)
- Alpaca: High rate limits, current parallelism safe
- FRED: Single endpoint, low volume

**RDS Connection Pool:** Multiplexes 24 loaders (48-96 connections) to 20-30 persistent connections. AWS Proxy defaults: max_connections=100. Morning prep: <30 connections expected. EOD: 20-30 expected. Alert threshold: >80% of max.

## Trading Safety Configuration

**Three layers of safety gates.** All configured via `algo_config` table (hot-reloadable). **NEVER set any threshold to zero — doing so bypasses all guards.**

**Pre-Deployment Verification:** Run `python scripts/verify_safety_thresholds.py --strict` before production deploys. This script:
- Checks minimum safe thresholds (rejects configs that would bypass quality gates)
- Verifies earnings blackout is active (>0 days before/after)
- Detects if quality scores or volume filters are disabled (= 0)
- In strict mode, ensures no deviation from expected defaults

Failing safety checks blocks deployment. This is intentional — misconfigured thresholds = uncontrolled trading.

### Layer 1: Entry Quality Thresholds (Hard Gates)

These reject signals that fail minimum quality criteria. If ANY threshold is unmet, entry is blocked.

- `min_signal_quality_score` = 60 (0-100 SQS scale)
- `min_swing_score` = 55.0 (setup quality)
- `min_completeness_score` = 70 (% price/technical data)
- `min_volume_ma_50d` = 300,000 shares
- `min_avg_daily_dollar_volume` = $500,000

**Impact if zeroed:** Trades garbage (gap risk, weak setups, penny stocks, incomplete data).

### Layer 2: Earnings Blackout (Hard Gate)

Prevents entries 7 days before and 3 days after earnings to avoid gap risk from earnings surprises.

- `earnings_blackout_days_before` = 7 trading days
- `earnings_blackout_days_after` = 3 trading days

**Why:** Earnings gaps are #1 cause of stop-loss blowups beyond ATR. Disabling = high-variance catastrophic loss risk.

### Layer 3: Entry Quality Gates (Warn-Only)

Configured as warn-only (not hard-gates) because consolidating bases legitimately show these patterns.

- `rs_slope_gate_enabled` = false (consolidating bases show flat RS)
- `volume_decay_gate_enabled` = false (accumulation shows declining volume)

**Rationale:** Hard-gating these would reject ~30% of legitimate Minervini setups. Warn-only allows human judgment.

### Verification & Restoration

Check current settings: `python scripts/verify_safety_thresholds.py --show`

If zeroed unintentionally:
```bash
python migrations/runner.py up 032  # Restore migration defaults
# OR manually: UPDATE algo_config SET value = '60' WHERE key = 'min_signal_quality_score'; ...
```

If database corrupted: `AlgoConfig.DEFAULTS` in `algo/infrastructure/config.py` provides hardcoded safe values.

## API Configuration

**Lambda:** `algo-api-dev` (Python 3.12, 256 MB, 25s timeout, provisioned concurrency=1)
- VPC: 2 private subnets, Secrets Manager connect timeout 10s
- Layers: API deps + psycopg2 + shared (numpy/pandas/scipy)
- Health endpoint: `/api/health` (no auth, returns health + RDS pool state)

**Rate Limiting:** Three-layer strategy: API Gateway (10k RPS hard limit), per-endpoint public limits (via `check_public_rate_limit()`), per-user admin limits (via `check_admin_rate_limit()`), external API adaptive limits.

**Error Handling:** All endpoints return HTTP error codes (503/504/500) with details, never 200 OK with empty data. `db_route_handler` decorator enforces this. Frontend must handle 503/504/500 as actual errors.

## Lambda Deployment

**Source of truth:** `lambda/{api,algo_orchestrator,db-init}/` directories (version controlled).

**ONE-WAY deployment:** `lambda/` source → CI/CD builds ZIP → Terraform deploys to AWS.

**NEVER edit:** `terraform/lambda_*.zip` or `terraform/modules/services/` (overwritten on next deploy).

**Verify:**
```bash
ls -lh terraform/lambda_api.zip  # Generated by CI/CD
ls -la lambda/api/                # What you edit
unzip -l terraform/lambda_api.zip | head -30  # What's deployed
```

## Security & Scanning

**Multi-layer strategy:**
- **Pre-commit:** Linting, type checking, import validation, credential blocking (dev machine)
- **CI/CD:** Secrets detection (TruffleHog), SAST (Bandit), dependency scanning (pip-audit), IaC scanning (tfsec)
- **Runtime:** AWS WAF, IAM least-privilege, VPC isolation, CloudWatch monitoring

**Key points:**
- Pre-commit hook blocks commits with `.env` files, debug code, session docs
- CI/CD fails if secrets, high-confidence security issues, or vulnerable dependencies found
- Bandit B608 (SQL injection) warnings are false positives here (all queries use parameterized values)

## Code Quality Standards

**Three-Layer Assurance:**
1. **Local:** Pre-commit hook blocks commits with mypy errors, import failures. Run: `./scripts/check-quality.sh` (~60s)
2. **CI:** ci-fast-gates.yml (~12m: security, lint, type check, tests, coverage) — must pass before merge
3. **Production:** CloudWatch error rates, type coverage trending, test coverage tracked quarterly

**Type Safety:** `python -m mypy algo/ loaders/ lambda/ --ignore-missing-imports`

**Enforcement:** mypy includes Lambda API and executor (highest-risk modules). Pre-commit hook blocks on type errors in algo/orchestration, algo/trading/executor, lambda/api (core financial paths). Loaders and tools have relaxed checking for prototyping speed.

**Test Coverage Targets:** algo/ 80%, loaders/ 70%, lambda/ 60%. Coverage is a guide, not the goal.

**Linting:** Black (format), isort (imports), flake8 (lint) — non-blocking. Security: TruffleHog (blocks on secrets), pip-audit, bandit — TruffleHog blocks; others informational.

**Config:** mypy/pytest in `pyproject.toml`, CI in `.github/workflows/ci-fast-gates.yml`, pre-commit in `.git/hooks/pre-commit`.

## Credentials & Secrets

**Local setup:** `scripts/setup-local-dev.ps1` (fetches credentials from Secrets Manager).

**If expired:** `scripts/refresh-aws-credentials.ps1`

**Rules:** Rotate quarterly (first Monday), immediately if leaked. No `.env` files. GitHub Actions uses AWS OIDC.

**Credential locations:** `algo/dashboard-config`, `algo/database`, `algo/alpaca` (paper trading), `algo/fred`

**Terraform outputs:** `.terraform-outputs.json` (auto-saved by CI/CD, <24h = fresh)

**Deployment:** `git push main` → deploy-all-infrastructure.yml. DB schema via GitHub Actions (avoids races).

## Infrastructure Constraints

**RDS:** db.t4g.small (2GB RAM, 100 concurrent max), statement_timeout 15m, work_mem 16MB, effective_cache_size 768MB.

**Lambda Orchestrator:** 512 MB, 600s timeout. Pre-warmed 9:25 AM ET.

**Trading mode:** Paper (alpaca_paper_trading=true). Switch via terraform.tfvars.

**Environment:** dev (all resources named -dev).

## Fail-Fast Pattern

Never silently return defaults (0, None, [], {}, False). Raise exception with context on missing/failed data. Silent failures compound into cascading errors.

**Rule:** REQUIRED data → raise exception. OPTIONAL data → log WARNING + return None (document in docstring).

**Implementation:** Circuit breaker, position sizing, exit logic, data loaders all raise ValueError/RuntimeError on unavailability.

## Database Transactions & Atomicity

**Multi-Step Operations:** All operations affecting trades and positions must be atomic:
- Entry: Trade entry + position creation + audit log all commit together or rollback together
- Exit: Trade status update + position quantity update + stop price adjustment + audit log are atomic
- Reconciliation: Alpaca sync + position status updates + profit/loss calculation are atomic

**Row-Level Locking:** Multi-step updates use `FOR UPDATE` to lock rows and prevent concurrent modifications during transaction. Example: executor.py locks both algo_trades and algo_positions rows before executing partial exits.

**Rowcount Verification:** After each critical UPDATE, verify `cursor.rowcount == 1` (exactly one row updated). Mismatch indicates lost update or concurrency violation — transaction rolls back.

**Connection Context:** All database operations use `DatabaseContext` which auto-commits on success and rollbacks on any exception. Never manually commit or close connections.

**Savepoints in Error Handling:** Loaders use named savepoints for recoverable errors. On failure, rollback to savepoint (not full transaction) and continue with next record. On critical error, exception propagates and full rollback occurs.

## Troubleshooting

**AWS credential error:** `scripts/refresh-aws-credentials.ps1`

**Lambda 502 (VPC cold-start):** Provisioned concurrency should prevent. Check: `aws lambda get-provisioned-concurrency-config --function-name algo-api-dev`. Retry with backoff.

**Lambda 5xx:** Check logs: `aws logs tail /aws/lambda/algo-api-dev --follow`. Verify RDS Proxy reachable (security groups), Lambda layer deployed (psycopg2).

**Phase 1 halts (stale data):** Check DATA_FRESHNESS_MAX_HOURS in algo_config. Check morning prep: `scripts/orchestrator-history.py recent 1`. Check yfinance CloudWatch logs for rate limiting.

**RDS connections saturated:** Check CloudWatch DatabaseConnections (expect <30 morning, 20-30 EOD). Slow queries: RDS Performance Insights. Reduce parallelism: `scripts/update-loader-parallelism.py`.

**Orchestrator lock timeout:** Check: `aws ecs list-tasks --cluster algo-cluster` (no stuck tasks). Check CloudWatch for "Lock acquisition failed".

**Market regime halts entries:** Phase 5 halts when market_exposure_daily sets `is_entry_allowed=false`. Common triggers: 6+ heavy-volume down days in 25 sessions, VIX > 40 with rising trend, SPY below 30-week MA, HY credit spread > 8.5%. Check current: `SELECT date, is_entry_allowed, halt_reasons FROM market_exposure_daily WHERE date = CURRENT_DATE ORDER BY date DESC LIMIT 1`. Entries resume automatically when conditions improve (next morning computation). This is a designed risk control.

**Missing scheduled orchestrator runs:** If <4 runs in a trading day (expect 9:30 AM, 1 PM, 3 PM, 5:30 PM ET), check AWS EventBridge Scheduler console:
- `algo-algo-schedule-morning-dev` (9:30 AM ET) → ENABLED
- `algo-algo-schedule-afternoon-dev` (1:00 PM ET) → ENABLED
- `algo-algo-schedule-preclose-dev` (3:00 PM ET) → ENABLED
- `algo-algo-schedule-dev` (5:30 PM ET) → ENABLED

If disabled: `cd terraform/ && terraform apply -var-file=terraform.tfvars`. Verify Lambda permissions: EventBridge Scheduler must have `lambda:InvokeFunction` on `algo-orchestrator-dev`.

## GitHub Actions Workflows

**Production Auto (4):** deploy-all-infrastructure.yml, deploy-staging.yml, ci-fast-gates.yml, build-push-ecr.yml

**Scheduled (3):** run-fred-loader.yml (5 AM ET), rotate-credentials.yml (quarterly, first Monday), verify-both-envs.yml (6h)

**Infrastructure (2):** build-lambda-layer.yml, verify-and-init-db.yml (manual dispatch)

**Credentials (4):** rotate-credentials.yml (primary quarterly), rotate-credentials-simple.yml (fallback), update-credentials.yml (API key sync), check-credential-status.yml (audit). Local: `scripts/refresh-aws-credentials.ps1`.

**Manual (3):** manual-invoke-loaders.yml, manual-invoke-orchestrator.yml, test-and-debug.yml

**Test (1):** reset-cognito-test-user.yml

## Key Files

- `algo/algo_orchestrator.py` — 7-phase orchestrator
- `lambda/api/lambda_function.py` — REST API
- `terraform/main.tf` — infrastructure as code
- `lambda/db-init/schema.sql` — database schema
- `loaders/load_*.py` — data loaders
- `tools/dashboard/` — terminal dashboard
- `run-dashboard.ps1` — convenience wrapper

## Dashboard Setup

**Browser (Vite):** `scripts/setup-local-dev.ps1` (one-time). Then: `cd webapp/frontend && npm run dev`. Public pages load immediately; protected pages redirect to /login. Vite proxy routes /api/* to AWS.

**Terminal:** `.\run-dashboard.ps1` (live view), `.\run-dashboard.ps1 -Watch 60` (auto-refresh), `.\run-dashboard.ps1 -Legend` (guide). If expired: `scripts/refresh-aws-credentials.ps1`.
