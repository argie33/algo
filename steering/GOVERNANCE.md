# Codebase Governance & Architecture

Live trading system: Minervini trend-following + fundamental quality filters. Up to 15 concurrent positions, daily reconciliation with Alpaca.

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

1. **Entry quality:** Signal quality score ≥60 (`min_signal_quality_score`), completeness ≥70% (`min_completeness_score`), volume ≥300k (`min_volume_ma_50d`), dollar volume ≥$500k (`min_avg_daily_dollar_volume`). Swing score is retired (migration 103) - trading logic is composite_score-only.
2. **Earnings blackout:** 7 days before, 3 days after
3. **Quality gates (warn-only):** RS slope, volume decay

**NEVER set any threshold to zero.** Doing so bypasses all guards.
**NEVER accept scores with <50% data completeness.** Degraded data biases position sizing.

**Pre-deployment:** Run `python scripts/verify_safety_thresholds.py --strict` before production.

---

## Orchestrator Phases (9 Total)

Orchestrator executes all 9 phases in sequence per `algo/orchestrator/phase_registry.py`:

1. **Data Freshness Check** — Validates upstream loader data freshness; halts if >1 trading day stale.
2. **Circuit Breakers** — Runs all 14 checks in `algo/risk/circuit_breaker.py`'s `_check_registry` (not 8, not 13 - both stale counts; sector_drawdown (CB9) was added in commit `f20b6e42a` without a steering update, closing a real gap where `sector_drawdown_halt_pct` was seeded/admin-editable config with no enforcing check). Halting checks: drawdown ≥20%, drawdown re-engagement (post-halt: equity must recover + N days elapse + optional Follow-Through Day before resuming), daily loss ≥2%, loss streak ≥3, open risk ≥4%, VIX spike ≥35, market stage break, weekly loss ≥5%, win rate <40% (rolling ~30 trades, closed + open unrealized), data freshness (stale price data), intraday market health (SPY fell >2% the prior day), **sector drawdown** (cost-basis-weighted per-sector unrealized P&L ≤ `sector_drawdown_halt_pct`, e.g. -12%). Advisory-only (warn, don't halt): sector concentration, daily profit cap. Sets halt flag on any halting check.
3. **Position Monitor** — Reviews open positions, checks against risk limits, validates data integrity. `always_run=True`.
4. **Reconciliation** — Reconciles broker positions vs. algo_trades table.
5. **Exposure Policy Actions** — Enforces sector/exposure limits, may liquidate excess.
6. **Exit Execution** — Executes stop-loss/target exits. `always_run=True`.
7. **Signal Generation & Ranking** — Generates BUY/SELL signals from technical + fundamental scores.
8. **Entry Execution** — Executes BUY trades from ranked signals; also runs the proactive total-risk check (blocks new entries at ≥4% risk before the reactive circuit breaker would fire). `always_run=True` (added in commit `3a132945c` specifically so this proactive check isn't skipped by an earlier halt - see the Key Principle below).
9. **Reconciliation & Snapshot** — Final portfolio reconciliation, creates snapshot for dashboard. `always_run=True`.

**Key Principle — read this before treating a "skipped" phase as evidence of a bug.** Only phases 3, 6, 8, 9 (`always_run=True`) are guaranteed to execute every single run. Every other phase (1, 2, 4, 5, 7) runs **only until the first one halts** — the instant any non-`always_run` phase fails or halts (`algo/orchestrator/phase_executor.py::OrchestratorPhaseExecutor.run()`), every remaining non-`always_run` phase for that cycle is marked `status="skipped"` and never executes, regardless of whether it individually "always runs" per its own docstring. This is why a halted run's health-panel detail commonly shows one phase `HALTED`, several phases `SKIPPED`, and phases 3/6/8/9 still `COMPLETED` - this is the designed cascade protecting against catastrophic losses (position monitoring, exit execution, proactive entry risk enforcement, and portfolio reconciliation must continue during emergencies), not a bypass or an inconsistency. (Phase 8 joined this group later than 3/6/9 - see commit `3a132945c` - so an example run predating that commit would legitimately show Phase 8 skipped; check `phase_registry.py`'s current `always_run` values, not an old log, if in doubt.)

Separately, phases 4/5/7 also carry `skip_if_halted=True`, which independently skips them if a **persistent** halt flag is already active from a prior event (e.g. an unexpired drawdown-recovery cooldown) even when phases 1-2 both succeed in the current run. Phase 8 no longer carries `skip_if_halted=True` (also changed in `3a132945c`) precisely so its proactive risk check keeps running under that same condition.

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
- **Market regime:** `market_exposure_daily` (12 quantitative factors, fail-open if EOD fails)
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

**Production:** `git push main` → deploy-all-infrastructure.yml (auto)

**Rotation:** Quarterly (first Monday), immediately if leaked. No `.env` files ever.

---

## Rule Enforcement & Audit

See "Code Cleanliness" section above for protected rules. Enforcement is per-commit via pre-commit hooks and CI (`.github/workflows/ci.yml`).

---

See `CLAUDE.md` for quick reference and task routing.
