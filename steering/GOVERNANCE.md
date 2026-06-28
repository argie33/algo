# Codebase Governance & Architecture

Live trading system: Minervini trend-following + fundamental quality filters. Up to 15 concurrent positions, daily reconciliation with Alpaca.

**AWS credential error?** Run: `scripts/refresh-aws-credentials.ps1`

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

## Trading Safety (Non-Negotiable)

**Three layers of gates** (all hot-reloadable via `algo_config` table):

1. **Entry quality:** Signal score ≥60, swing score ≥55, completeness ≥70%, volume ≥300k, dollar volume ≥$500k
2. **Earnings blackout:** 7 days before, 3 days after
3. **Quality gates (warn-only):** RS slope, volume decay

**NEVER set any threshold to zero.** Doing so bypasses all guards.

**Pre-deployment:** Run `python scripts/verify_safety_thresholds.py --strict` before production.

---

## Orchestrator Phases

1. Data freshness (halt if >1 trading day stale)
2. Circuit breakers (halt on: drawdown ≥20%, daily loss ≥2%, loss streak ≥3, open risk ≥4%, VIX ≥35, market stage=4, weekly loss ≥5%, win rate <40%)
3. Position monitor + exposure policy
4. Execute exits (unblocked by halt)
5. Signal generation (blocked by halt)
6. Trade entries (blocked by halt)
7. Reconciliation + reporting (unblocked by halt)

---

## System Architecture

**Orchestrator:** `algo/algo_orchestrator.py` → Lambda `algo-algo-dev` → EventBridge (9:30 AM, 1 PM, 3 PM, 5:30 PM ET)

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

**Local:** `scripts/setup-local-dev.ps1` (one-time), then `scripts/refresh-aws-credentials.ps1` if expired.

**Production:** `git push main` → deploy-all-infrastructure.yml (auto)

**Rotation:** Quarterly (first Monday), immediately if leaked. No `.env` files ever.

---

## Rule Enforcement & Audit

**These rules CANNOT be disabled or weakened:**
1. `mypy strict = true` with `disallow_any_expr` and `disallow_any_unimported`
2. Pylint: `comparison-with-callable`, `unsupported-binary-operation`

**Pre-commit hook blocks commits that attempt to:**
- Set `disallow_any_expr = false` in pyproject.toml
- Add `# pylint: disable=comparison-with-callable` or `unsupported-binary-operation`

**Why:** These catch dict-vs-int type errors before production. Disabling them has caused production incidents.

**Audit (weekly):** See `steering/LINT_POLICY.md` audit section. Report findings in #eng Slack.

**Enforcement:** PRs that bypass these rules are rejected with note to requestor.

---

## For Detailed Reference

See:
- `steering/LINT_POLICY.md` — Lint discipline, what can/cannot be ignored, audit procedures (critical: enforced per PR)
- `steering/OPERATIONS.md` — CI/CD procedures, deployments, dashboard diagnostics
- `steering/SETUP_CREDENTIALS.md` — Alpaca and Cognito credential setup
