# Codebase Governance & Architecture

Live trading system: Minervini trend-following + fundamental quality filters. Up to 20 concurrent positions (`max_positions` in `algo_config` - was 12, then 15 per commit `2a8637fe2`, now 20; verified live 2026-08-10, this line had drifted stale after the second bump), daily reconciliation with Alpaca.

---

## Core Governance Rules

1. This document is single source of truth for architecture and standards
2. Code changes + steering updates in same commit (no async docs)
3. NO live status in steering—git is the record
4. Timestamps/incident logs belong in commit messages, not here

---

## Code Cleanliness (Pre-Commit Enforced)

**CRITICAL: These blocks CANNOT be disabled or weakened:**

Blocks commits:
- `.env` files (use AWS Secrets Manager)
- `pdb`, `ipdb`, `breakpoint()` in code
- `print()` in library code (use logging)
- **Type errors from mypy** (strict mode enforced)
- **Type mismatches from Pylint** (`comparison-with-callable`, `unsupported-binary-operation`)
- Import errors

**Why:** These catch dict-vs-int comparisons and other runtime type errors before production. Past incidents from disabling these checks.

Allowed: `print()` in loaders, scripts, tests only.

Enforcement: `mypy --strict` + Pylint via pre-commit hooks and `make lint`/`make type-check` (see `Makefile`).

---

## Data Quality (Critical for Trading)

**PRINCIPLE: Fail-fast on missing data. No silent fallbacks. Incomplete data is honest data.**

Finance applications cannot silently fall back to secondary data sources or accept degraded datasets. Silent data loss leads to:
- Incorrect position sizing (using incomplete market exposure)
- Wrong composite scores (weighting single factors 100%)
- Inaccurate risk calculations (using stale or synthetic data)

**Strict Rules for Metric Loaders:**

1. **Explicit availability:** Every record must have `data_unavailable` flag (BOOLEAN, default FALSE)
   - When `data_unavailable=TRUE`, include `reason` field explaining why (VARCHAR 255)

2. **Fail-fast on insufficient data:** Return `None` (not degraded data) when:
   - Price history < 30 days (cannot calculate volatility)
   - No SEC filings available (cannot calculate quality/growth)
   - Missing upstream metric data

3. **No secondary fallbacks:** Never use:
   - yfinance beta instead of calculated volatility (incomplete risk picture)
   - Short-term momentum when long-term unavailable (different signal)
   - Single-metric composite scores (extreme bias)

4. **Minimum completeness threshold:** Composite scores require min_required_metrics ≥3
   - Prevents single-metric bias (100% weight on one factor)
   - Signals < 70% completeness are excluded from scoring

5. **Explicit logging:** When data missing, use WARNING (not DEBUG) so operators see failures

6. **Operator visibility:** Dashboard must display data_unavailable flags and completeness % so traders understand which stocks have insufficient data

**Result:** Some stocks (new IPOs, micro-caps without SEC filings) will not score. This is correct—incomplete data is a risk signal, not a problem to hide.

**CRITICAL PRIORITY — FIX ROOT CAUSES FIRST:**

When seeing `data_unavailable=TRUE` markers appearing for a new class of symbols (REITs, micro-caps, foreign stocks, etc.):
1. **DO NOT immediately add fallback/degradation logic** ("use signal score when quality missing", "skip sector data", etc)
2. **INVESTIGATE first:** Why is the upstream loader skipping/failing for these symbols?
   - Is the loader filtering them out explicitly? (exclude_etfs, exclude_micro_caps, etc)
   - Is the upstream data quality issue? (NULL values, missing API responses, etc)
   - Is it a feature design issue? (Minervini gate too strict for certain asset classes)
3. **FIX the loader** to process all tradeable symbols, OR
4. **Add explicit data quality gate** ("skip REITs with <3 years SEC data"), then ALLOW the data_unavailable marker

**Antipattern (DO NOT DO):** Adding fallback scores when upstream data missing. Examples to avoid:
- ❌ "Use quality_score as proxy for missing growth_score" → score is no longer comparable
- ❌ "Skip sector momentum check if unavailable" → removes important risk filter
- ❌ "Return 50.0 default for missing metric" → hides data quality issues
- ❌ "Combine available metrics with double weight" → survivor bias

**Correct pattern:** `data_unavailable=TRUE` + `reason="upstream_loader_gap:sector_ranking"` + FIX the upstream loader.

All fail-fast patterns are enforced. See git log for remediation commits: `git log --all --oneline | grep -i "fail-fast\|fallback"`

---

## Trading Safety (Non-Negotiable)

**Three layers of gates** (all hot-reloadable via `algo_config` table):

1. **Entry quality:** Signal quality score ≥75 (`min_signal_quality_score` - drifted stale here as 60, verified live 2026-08-20), completeness ≥70% (`min_completeness_score`), volume ≥300k (`min_volume_ma_50d`), dollar volume ≥$500k (`min_avg_daily_dollar_volume`). Swing score is retired (migration 103) - trading logic is composite_score-only.
2. **Earnings blackout:** 7 days before, 3 days after
3. **Quality gates (warn-only):** RS slope, volume decay

**NEVER set any threshold to zero.** Doing so bypasses all guards.
**NEVER accept scores with <50% data completeness.** Degraded data biases position sizing.

**Pre-deployment:** Run `python scripts/verify_safety_thresholds.py --strict` before production.

---

## Orchestrator Phases (9 Total)

Orchestrator executes all 9 phases in sequence per `algo/orchestrator/phase_registry.py`:

1. **Data Freshness Check** — Validates upstream loader data freshness; halts if >1 trading day stale.
2. **Circuit Breakers** — Runs all 14 checks in `algo/risk/circuit_breaker.py`'s `_check_registry` (not 8, not 13 - both stale counts; sector_drawdown (CB9) was added in commit `f20b6e42a` without a steering update, closing a real gap where `sector_drawdown_halt_pct` was seeded/admin-editable config with no enforcing check). Halting checks: drawdown ≥10% (`halt_drawdown_pct` - code default is 20%, but this dev environment's admin-editable config has been tightened to -10%, verified live 2026-08-20; don't assume the code-level default without checking the live value), drawdown re-engagement (post-halt: equity must recover + N days elapse + optional Follow-Through Day before resuming), daily loss ≥2%, loss streak ≥3, open risk ≥8% (`max_total_risk_pct` - bumped from a stale-doc'd 4%, see commit referenced in `_check_total_risk`'s own "CRITICAL FIX 2026-08-06: Use config value to stay in sync with Phase 8 and circuit breaker"; verified live 2026-08-10), VIX spike ≥35, market stage break, weekly loss ≥5%, win rate <30% (`min_win_rate_pct`, not the previously-doc'd 40% - verified live 2026-08-10) (rolling ~30 trades, closed + open unrealized), data freshness (stale price data), intraday market health (SPY fell >2% the prior day), **sector drawdown** (cost-basis-weighted per-sector unrealized P&L ≤ `sector_drawdown_halt_pct`, e.g. -12%). Advisory-only (warn, don't halt): sector concentration, daily profit cap. Sets halt flag on any halting check.
3. **Position Monitor** — Reviews open positions, checks against risk limits, validates data integrity. `always_run=True`.
4. **Reconciliation** — Reconciles broker positions vs. algo_trades table. `always_run=True` (see Key Principle below - verified live 2026-08-23, not reflected in this doc's older text).
5. **Exposure Policy Actions** — Enforces sector/exposure limits, may liquidate excess. `always_run=True` (same correction as Phase 4).
6. **Exit Execution** — Executes stop-loss/target exits. `always_run=True`.
7. **Signal Generation & Ranking** — Generates BUY/SELL signals from technical + fundamental scores. `always_run=True` (same correction as Phase 4).
8. **Entry Execution** — Executes BUY trades from ranked signals; also runs the proactive total-risk check (blocks new entries at ≥4% risk before the reactive circuit breaker would fire) and, as of 2026-08-24, a proactive PDT check (blocks new entries once Alpaca's `daytrade_count` reaches 3 - one more same-day round-trip would trigger a 90-day day-trading lockout on accounts under $25k equity; `execution_mode=="auto"` only, `_check_pdt_limit_breach()` in `phase8_entry_execution.py` - see `pdt_day_trade_limit_reactive_only_not_proactively_enforced_20260824` in memory). Both are "blocked" (not "halted") outcomes - Phase 6 exits already ran, so protective stops are unaffected. `always_run=True` (added in commit `3a132945c` specifically so this proactive check isn't skipped by an earlier halt - see the Key Principle below).
9. **Reconciliation & Snapshot** — Final portfolio reconciliation, creates snapshot for dashboard. `always_run=True`.

**Key Principle — read this before treating a "skipped" phase as evidence of a bug.** As of
2026-08-23 (verified live against `algo/orchestrator/phase_registry.py`), **all of phases 3
through 9** carry `always_run=True` - only phases 1 and 2 can gate anything. This is a
correction to this doc's own prior claim ("only phases 3, 6, 8, 9") - phases 4, 5, and 7 were
switched to `always_run=True` at some point after that claim was written (each is now essential
risk-management/signal logic in its own right: reconciliation, exposure enforcement, and signal
generation all need to keep running during a halt, same reasoning already applied to 3/6/8/9).
Practically this means a normal Phase 1/2 halt no longer produces any `SKIPPED` phases at all in
the 3-9 range - every phase from 3 onward runs regardless, each handling a halted/degraded
upstream state on its own terms (see `phase_executor.py`'s dependency-check path, which now
carries this responsibility - see next paragraph). Only phases 1 and 2 themselves, or a
catastrophic exception, can still produce a genuine `SKIPPED` for phase 1 or 2. If you see this
doc describe a specific phase's `always_run` value, always cross-check
`phase_registry.py`'s current values - this field has changed multiple times as the system's
safety requirements evolved, most recently for 4/5/7.

**The `skip_if_halted=True` mechanism described in earlier versions of this doc for phases
4/5/7 is now dead code, not a live behavior** - confirmed via `phase_executor.py`'s own comment
("BUG FOUND 2026-08-10: since every phase from 3-9 is now always_run... the direct halt-flag-
check branch above... became unreachable for ALL of them - `if not phase.always_run and
phase.skip_if_halted` is never true anymore"). A genuine halt for one of these phases now has to
propagate through the dependency-check path (written for real failures, not "my dependency
correctly halted") instead of the older, cleaner direct skip-and-log path. Do not rely on
`skip_if_halted` as a live mechanism for any phase currently marked `always_run=True` - check
whether it's actually reachable for a given phase before citing it in a debugging session.

---

## System Architecture

**Orchestrator:** `algo/algo_orchestrator.py` → Lambda `algo-orchestrator` → EventBridge (9:30 AM, 1 PM, 3 PM, 5:30 PM ET)

**Loaders:** `loaders/load_*.py` → ECS Fargate → Step Functions (2:15 AM, 4:05 PM ET)

**API:** `lambda/api/lambda_function.py` → Lambda `algo-api-dev`

**Frontend:** `webapp/frontend/src/` → S3 + CloudFront

**Database:** PostgreSQL RDS `algo-db` (db.t4g.small, 100 concurrent max, 15m statement timeout)

**Schedule (Mon-Fri):**
- 2:00 AM: Morning pipeline (prices + technical + swing scores before 9:30 AM)
- 4:05 PM: EOD pipeline (prices + market + technical + signals)
- 9:30 AM, 1 PM, 3 PM, 5:30 PM: Orchestrator runs

---

## Key Configuration Points

- **Positions:** Dual-source architecture (deployed Session 171):
  - Algo-managed: `algo_positions` table (source: `algo_trades`, maintained by Phases 3/6/8/9)
  - Manual/external: `algo_untracked_positions` table (orphan detection via Alpaca sync)
  - Dashboard returns both: `items` (algo) + `untracked_items` (manual/external)
  - Sync process: `alpaca_sync_manager.sync_alpaca_positions()` identifies broker positions NOT in algo_positions and syncs to untracked table
- **Technical:** `technical_data_daily` (computed 2:15 AM + 4:05 PM, vectorized)
- **Market regime:** `market_exposure_daily` (3-pillar composite - Trend & Momentum/Independent Risk Layers/Breadth & Sentiment - plus a slow macro veto, fail-open if EOD fails)
- **Earnings:** `earnings_calendar` (loaded 4:29 AM, retains 60 days)

**Signal generation pipeline:** Fetch buy_sell_daily BUY signals → Filter: close > SMA_50, not bottom 40% range → Liquidity check top 10 → Rank by composite_score → Return candidates.

---

## Infrastructure Constraints

- RDS: 100 concurrent max, statement_timeout 15m, work_mem 16MB
- Lambda Orchestrator: 512 MB, 600s timeout, pre-warmed 9:25 AM ET
- Trading mode: Paper (alpaca_paper_trading=true)
- Environment: dev (all resources named -dev)

---

## Credentials & Deployment

**Local:** PostgreSQL setup + `DB_HOST=localhost DB_USER=stocks DB_PASSWORD=stocks DB_NAME=stocks python migrations/run.py apply --all` (one-time), then `scripts/refresh-aws-credentials.ps1` if expired.

**Production:** `git push main` → CI (`.github/workflows/ci.yml`) → `deploy-ecs-image.yml`
(`workflow_run`-triggered on CI success) → ECR push. **The pipeline architecture now exists**
(built after the 2026-08-20 "no workflows at all" state this line used to describe - see
`[[ci_cd_pipeline_never_existed_20260820]]` in memory) but **deploy-ecs-image.yml has had zero
successful runs since at least 2026-07-17**: OIDC `AssumeRoleWithWebIdentity` fails on every
attempt (`Not authorized to perform sts:AssumeRoleWithWebIdentity`), confirmed still failing
live 2026-08-24 - see `[[aws_deploy_ecs_oidc_broken_since_at_least_20260820]]` in memory. CI
green on `main` is NOT evidence AWS has current code - verify with
`gh run list --workflow=deploy-ecs-image.yml --limit 3` shows `success`, not just that CI
passed. Root cause needs real AWS credentials (CloudTrail's actual denied `sub`/`aud` claims)
to diagnose - not yet done as of this writing.

**Rotation:** Quarterly (first Monday), immediately if leaked. No `.env` files ever.

---

## Rule Enforcement & Audit

See "Code Cleanliness" section above for protected rules. Enforcement is per-commit via pre-commit hooks and CI (`.github/workflows/ci.yml` — added 2026-08-20; this claim was false before that date, see `[[ci_cd_pipeline_never_existed_20260820]]` in memory). CI runs ruff/mypy/pylint/pytest/bandit/trufflehog (Python) and eslint/prettier/vitest (frontend) on every push/PR to `main` — it does not deploy anything.

---

See `CLAUDE.md` for quick reference and task routing.
