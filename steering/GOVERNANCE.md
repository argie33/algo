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

**See:** `steering/LINT_POLICY.md` for type safety layers and enforcement.

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

**Status:** All fail-fast patterns implemented and tested. See git log for remediation commits: `git log --all --oneline | grep -i "fail-fast\|fallback"`

---

## Trading Safety (Non-Negotiable)

**Three layers of gates** (all hot-reloadable via `algo_config` table):

1. **Entry quality:** Signal score ≥60, swing score ≥55, completeness ≥70%, volume ≥300k, dollar volume ≥$500k
2. **Earnings blackout:** 7 days before, 3 days after
3. **Quality gates (warn-only):** RS slope, volume decay

**NEVER set any threshold to zero.** Doing so bypasses all guards.
**NEVER accept scores with <50% data completeness.** Degraded data biases position sizing.

**Pre-deployment:** Run `python scripts/verify_safety_thresholds.py --strict` before production.

---

## Orchestrator Phases (9 Total)

Orchestrator executes all 9 phases in sequence per `algo/orchestrator/phase_registry.py`:

1. **Data Freshness Check** — Validates upstream loader data freshness; halts if >1 trading day stale. Always runs (skips if halted: NO)
2. **Circuit Breakers** — Checks 8 risk metrics (drawdown ≥20%, daily loss ≥2%, loss streak ≥3, open risk ≥4%, VIX ≥35, market stage=4, weekly loss ≥5%, win rate <40%); sets halt flag. Always runs (skips if halted: NO)
3. **Position Monitor** — Reviews open positions, checks against risk limits, validates data integrity. Skipped if halted (skip_if_halted: YES)
4. **Reconciliation** — Reconciles broker positions vs. algo_trades table. Skipped if halted (skip_if_halted: YES)
5. **Exposure Policy Actions** — Enforces sector/exposure limits, may liquidate excess. Skipped if halted (skip_if_halted: YES)
6. **Exit Execution** — Executes stop-loss/target exits unblocked by halt. Always runs (always_run: YES, skip_if_halted: NO)
7. **Signal Generation & Ranking** — Generates BUY/SELL signals from technical + fundamental scores. Skipped if halted (skip_if_halted: YES)
8. **Entry Execution** — Executes BUY trades from ranked signals. Skipped if halted (skip_if_halted: YES)
9. **Reconciliation & Snapshot** — Final portfolio reconciliation, creates snapshot for dashboard. Always runs (always_run: YES, skip_if_halted: NO)

**Key Principle:** Phases 1, 2, 6, 9 always run (exits/halts/reporting unblocked by circuit breaker). Phases 3-5, 7-8 skip if halt flag set (trading entry/exposure management blocked).

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

- **Positions:** Single source = `algo_trades` table. View: `algo_positions_with_risk` (refreshed Phase 7)
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

**Local:** PostgreSQL setup + `python scripts/apply-database-schema.py` (one-time), then `scripts/refresh-aws-credentials.ps1` if expired.

**Production:** `git push main` → deploy-all-infrastructure.yml (auto)

**Rotation:** Quarterly (first Monday), immediately if leaked. No `.env` files ever.

---

## Rule Enforcement & Audit

See "Code Cleanliness" section above for protected rules. Weekly audit: `steering/LINT_POLICY.md`.

---

See `CLAUDE.md` for quick reference and task routing.
