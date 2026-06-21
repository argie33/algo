# Codebase Governance

## Quick Start

AWS credential error? Run: `scripts/refresh-aws-credentials.ps1`

For system architecture, operations, and patterns, see `steering/system.md`.

## Governance Rules

1. **System docs** (`steering/system.md`): Single source of truth for architecture, safety config, data patterns, troubleshooting
2. **Code changes + steering updates together:** No async documentation. If code behavior changes, update steering in same commit
3. **NO live status in steering:** Timestamps, incident logs, "as of" — only permanent design/procedures/troubleshooting
4. **Git is the record:** What happened and why lives in commit messages, not steering

## Code Cleanliness (Pre-Commit Enforced)

**Blocks commits:**
- `.env` files (use AWS Secrets Manager)
- `pdb`, `ipdb`, `breakpoint()` left in code
- `print()` statements in library code (use logging)
- Type errors from mypy, import errors

**Allowed:** `print()` in `algo_loader_*.py`, `algo_daily_report.py`, `scripts/`, `tests/`

**Type checking:** `python -m mypy <file>.py --ignore-missing-imports` before committing

## Exception Handling (Unified Standard)

All exceptions inherit from `AlgoError` (see `algo/exceptions.py`).

**When to use each:**
- `DataLoadError`: Failed to fetch data from database/API/files. Set `retry_eligible=True` for network, `False` for schema
- `ValidationError`: Field missing, type error, or business logic violation
- `ConfigError`: Configuration key missing/invalid (never recoverable)
- `CircuitBreakerError`: Too many failures — automatic retry waits for recovery
- `PortfolioError`: Portfolio/cash/position inconsistency
- `PositionError`: Position-specific trading error

**Error responses in APIs:** Return `{"_error": "message"}` only on failure. Never mix error dict with fallback fields. Client checks `has_error(data)` before accessing fields.

## Validation & Fail-Fast

**At boundaries (once):** Validate all inbound data (API responses, database data, configuration).

**Inside code:** Assume valid. No defensive wrapping. Let exceptions propagate.

**Two-tier validation:**
- **Lambda outbound:** `ResponseValidator` from `shared_contracts/response_validator.py` (generic schema-based)
- **Dashboard inbound:** Specialized validators in `tools/dashboard/response_validators.py` (fail-fast, 15+ endpoint-specific)

DO NOT use one validator type in the other's context.

## Data Loader Patterns

**Three-tier criticality:**
1. **CRITICAL** (VIX, portfolio value, prices): Fail-fast, no stale cache. Use `DataImportance.CRITICAL`
2. **REQUIRED** (financials, technical): Fail cleanly. Use `DataImportance.REQUIRED`
3. **OPTIONAL** (put/call, yield curve): Return None on failure. Use `DataImportance.OPTIONAL`

All use canonical `CircuitBreaker` from `utils.infrastructure.circuit_breaker`. See `steering/system.md` → **Circuit Breaker Patterns**.

## Security Baseline

- NO `.env` files. Credentials: AWS Secrets Manager (production), PowerShell profile (local)
- CI: GitHub Secrets for deploy tokens only
- Rotate quarterly (first Monday), immediately if leaked
- All secrets in Secrets Manager, never in code/config files

## Trading Safety

**Three layers of safety gates** (all hot-reloadable via `algo_config` table):
1. **Entry quality thresholds:** Signal score ≥60, swing score ≥55, completeness ≥70%, volume ≥300k shares, dollar volume ≥$500k
2. **Earnings blackout:** 7 days before, 3 days after (avoid gap risk)
3. **Quality gates (warn-only):** RS slope, volume decay (don't hard-gate — legitimate consolidations show these)

**NEVER set any threshold to zero** — doing so bypasses all guards.

**Pre-deployment:** Run `python scripts/verify_safety_thresholds.py --strict` before production deploys. Failing safety checks blocks deployment (intentional).

## Orchestrator Phases

1. **Phase 1:** Data freshness validation (halt if >1 trading day stale)
2. **Phase 2:** Circuit breakers (halt on: drawdown ≥20%, daily loss ≥2%, consecutive ≥3, open risk ≥4%, VIX ≥35, market stage=4, weekly loss ≥5%, win rate <40%)
3. **Phase 3:** Position monitor + exposure policy
4. **Phase 4:** Execute exits (unblocked by halt)
5. **Phase 5:** Signal generation (blocked by halt)
6. **Phase 6:** Trade entries (blocked by halt)
7. **Phase 7:** Reconciliation + reporting (unblocked by halt)

See `steering/system.md` → **Orchestrator Phases** for detailed data architecture, signal generation, loader config.
