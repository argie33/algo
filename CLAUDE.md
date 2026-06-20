# Multi-Project Workspace Router

This workspace supports multiple projects: **algo** in `.` (see `steering/algo.md` for system details).

## QUICK START

**If you see:** `Error: The security token included in the request is invalid` or any AWS credential error when troubleshooting:

```powershell
scripts/refresh-aws-credentials.ps1
```

This fetches fresh credentials from IaC (Secrets Manager) and updates your local profile. See `steering/algo.md` → **LOCAL AWS CREDENTIALS** for details.

## STEERING RULES

1. **Content:** System map, credentials, procedures, resources, debugging/troubleshooting. NO live status ("currently broken", "just deployed", timestamps, incident logs). That lives in GitHub Actions logs and git commit messages.
2. **Clarity:** Spell out times (4:00 AM ET). Avoid abbreviations that need decoding. Complete sentences beat brevity.
3. **Procedures not status:** Document "how to debug X" (verifiable steps), never "X is broken" (stale status).
4. **Update in same commit:** Code changes + steering doc updates in one commit. No async updates.

## Where Information Goes

| What | Where | Why |
|------|-------|-----|
| How systems work, procedures, credentials | `steering/{project}.md` | Single source of truth, versioned with code |
| Current operational state, errors happening now | GitHub Actions logs, AWS console | Real-time, authoritative, automatic |
| Git history and commits | `git log` with good commit messages | Permanent, immutable record |

**NEVER in steering:** Live status, timestamps, incident logs, "as of", blockers.

## Code Cleanliness (Pre-Commit Enforced)

**Blocks commits:**
- `.env` files (use AWS Secrets Manager instead)
- Session-specific docs at root (`EXECUTION_*.md`, `*_STATUS.md`, etc.)
- One-time scripts at root (put in `scripts/` or `tests/`)
- `pdb`, `ipdb`, `breakpoint()` left in code
- `print()` statements in library code (use logging instead)
- Files > 1MB (binaries, artifacts, dumps)

**Allowed:**
- `print()` in: `algo_loader_*.py`, `algo_daily_report.py`, `scripts/`, `tests/`
- Configuration files that are generated/static

**Type checking & import validation (enforced by hook):**
- Type errors from mypy BLOCK commits — no exceptions
- Code must be importable (no NameError at runtime)
- Before committing, verify locally:
  ```bash
  python -m mypy <file>.py --ignore-missing-imports --no-error-summary
  python -m pytest tests/ -x --tb=short
  ```

## Documentation Management (Preventing Accumulation)

**Steering docs** (`steering/*.md`): PERMANENT only.
- ✅ System architecture, infrastructure constraints, permanent procedures, troubleshooting, how-to guides
- ❌ Session logs, incident status, "we did X on date Y", dated lists, timestamps (except in examples)
- Lifetime: Until the system/procedure changes (rewrite, don't append dates)
- Enforcement: Code review must reject dated language ("2026-06-01", "currently", "last", "just deployed")

**Memory files** (`.claude/projects/*/memory/*.md`): Actionable NOW or delete.
- ✅ Ongoing feedback/guidance, current project context, references to external systems
- ❌ Historical incidents, completed fixes (they're in git log), resolved status, past dates
- Process: After a fix ships, delete the memory file immediately. All context belongs in git commit history + steering docs if it becomes permanent procedure.
- Enforcement: Pre-commit hook prevents committing memory files > 90 days old with "completed/fixed/resolved" in filename

**Root-level files**: No session docs, logs, or one-time scripts (pre-commit enforced).
- ❌ `STATUS_*.md`, `EXECUTION_*.md`, `*.log`, `test_*.py` (belongs in `tests/`), `check_*.py` (belongs in `scripts/`)
- ✅ `CLAUDE.md`, `package.json`, `requirements.txt`, `Dockerfile`, `docker-compose.yml`

**Quarterly cleanup** (first Monday of each quarter, during credential rotation day):
1. Scan `memory/` for files matching `*_*.md` with past dates (use `git log --follow`)
2. Delete completed incident/fix/status memory files
3. Scan `steering/` for dated language (grep for `2026-`, `as of `, `currently `, `just `, `last `)
4. Rewrite any dated sections as permanent procedures or delete

**Git log is authoritative.** When a fix ships:
- Good commit message = source of truth for "what happened and why"
- Memory file = temporary context holder only, delete after commit
- Steering doc = permanent procedure if discovery is useful long-term, otherwise leave it to git history

## Rate Limiting Strategy

**Unified rate limiting** is documented in `steering/rate-limiting-strategy.md`.

Three-layer approach:
1. **API Gateway:** 10,000 RPS global limit (Terraform-configured)
2. **Application:** Per-endpoint limits in `utils/rate_limiting.py`
   - Public endpoints: Global limits (prevent DoS)
   - Admin endpoints: Per-user limits (prevent abuse of expensive operations)
3. **External APIs:** yfinance/FRED limits in `utils/validation/rate_limit.py`

Quick reference:
- Add new endpoint limit: Edit `ADMIN_RATE_LIMITS` or `PUBLIC_RATE_LIMITS` in `utils/rate_limiting.py`
- Enforce limit in route handler: `check_admin_rate_limit()` or `check_public_rate_limit()`
- See `steering/rate-limiting-strategy.md` for endpoint list and rationale

## Trading Safety Configuration

**CRITICAL ISSUE FIXED (Migration 033):** All safety thresholds were set to ZERO in the database, completely disabling quality gates and earnings protection. This has been restored to safe defaults. See `steering/safety-configuration.md` for full details.

**Critical thresholds** in `algo/infrastructure/config.py` DEFAULTS prevent the system from trading low-quality signals.
**NEVER** set these to zero or disable them for "testing" — doing so will trade any stock regardless of quality, including during earnings surprises:

**Entry Quality Thresholds (Hard Gates):**
- `min_signal_quality_score`: 60 (0-100 scale) — rejects signals below this SQS
- `min_swing_score`: 55.0 (default, regime manager may raise higher) — score gate for entry setup quality
- `min_completeness_score`: 70 (%) — reject stocks with incomplete price/technical data
- `min_volume_ma_50d`: 300,000 (shares) — liquidity gate
- `min_avg_daily_dollar_volume`: 500,000 (dollars) — liquidity gate for position sizing

**Earnings Risk Gates (Hard Gate):**
- `earnings_blackout_days_before`: 7 (days) — block entries 7 days before earnings
- `earnings_blackout_days_after`: 3 (days) — block entries 3 days after earnings
- **Why:** Prevents gap risk from earnings surprises; critical for stop-loss validity

**Entry Quality Gates (Warn-Only, Not Hard-Gates):**
- `rs_slope_gate_enabled`: false (warn-only, not hard-gate)
- `volume_decay_gate_enabled`: false (warn-only, not hard-gate)
- **Why:** Consolidating bases naturally show flat RS-line and declining volume (institutional accumulation), which are legitimate Minervini setups. Hard-gating these would reject high-probability trades. Set to warn-only per migration-007.

**If any threshold is zero or disabled unintentionally:**
1. Check git log: `git log -- algo/infrastructure/config.py migrations/`
2. Verify against migration-032 defaults (source of truth)
3. Restore via: `python migrations/runner.py up 032` (or manually set in algo_config table)

See `steering/algo.md` → **Entry Quality Gates** for detailed threshold rationale.

## Cluster 6: Database Connection Pool Exhaustion Risk (FIXED)

**Problem:** RDS Proxy has 100-connection limit. With 6 ECS tasks x 8 loaders x 2 parallelism = 96 connections hitting simultaneously + long-running backfill transactions = pool exhaustion → timeout → circuit breaker fires → trading halted.

**Solution Implemented:**
1. **Default parallelism reduced to 1** (`utils/loaders/config.py`): Start conservative, scale up via RDS-aware adaptive adjustment
2. **Adaptive thresholds lowered for 100-connection Proxy**: Reduce parallelism at 70% (70 conn) and 85% (85 conn) saturation
3. **Alert threshold lowered from 80% to 70%** (`algo/monitoring/connection_monitor.py`): Earlier warning on pool pressure
4. **Connection pool monitoring enabled in orchestrator**: Checks for stuck connections (>5 min) before each phase

**Prevention:**
- Each loader starts with parallelism=1 (not the previous max=6/8)
- Adaptive system increases parallelism only if RDS Proxy has headroom
- Loader parallelism can be overridden per-loader via DynamoDB `loader-config` table (e.g., `stock_prices_daily: {"parallelism": 2}`)
- Connection monitor warns at 70 connections, escalates to minimum at 85 connections

**Troubleshooting:**
- See orchestrator logs for `[RDS_POOL]` warnings indicating pool saturation
- Check connection pool status: `python -c "from algo.monitoring import get_pool_status; print(get_pool_status())"`
- If pool exhaustion occurs during loader runs: Check `data_loader_status` table for stuck/hung tasks
- Kill long-running tasks: Orchestrator automatically runs `_kill_long_running_loaders()` during pre-flight checks

## Cluster 7: Silent Failures — No Alerts or Observability (FIXED)

**Problem:** Circuit breaker fires (CB1-CB13), phase execution fails, but no Slack/email notification. Alerts only log to database. No aggregation/escalation. Ops team doesn't notice until next morning.

**Solution Implemented:**
1. **Alert sends are now non-blocking** (`algo/reporting/alerts.py`): Email/webhook/SMS failures no longer halt orchestration
2. **Alert methods return gracefully** instead of raising exceptions: `_send_webhook()`, `_send_webhook_simple()` now log and return
3. **Try-except wrapping on all alert calls**: `send_position_alert()`, `send_patrol_alert()`, `send_loader_alert()`, `critical()`
4. **Phase 2 circuit breaker alerts still execute** even if webhook/email config is missing

**Configuration:**
- Email alerts: Set `ALERT_EMAIL_TO`, `ALERT_SMTP_HOST`, `ALERT_SMTP_PORT`, `ALERT_SMTP_USER`, `ALERT_SMTP_PASSWORD`
- Slack/Teams/Discord: Set `ALERT_WEBHOOK_URL` environment variable
- SMS alerts: Set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`, `ALERT_PHONE_NUMBERS`

**Alert hierarchy** (attempted in order):
1. Email (via SMTP)
2. Webhook (Slack/Teams/Discord)
3. SMS (via Twilio)
4. Database audit log (always, fallback)

**Troubleshooting:**
- Check orchestrator logs for `[ALERT]` or `[NOTIF]` entries
- Missing configuration? See logs for `Email alert failed`, `Webhook alert failed`, `SMS alert failed`
- Database alerts always logged to `algo_phase_results` and `algo_audit_log` tables (source of truth)

## Frontend: Float vs Decimal Precision

**Problem:** Backend sends financial values as Decimal (Python), but JSON deserializes them as floats. JavaScript floats have precision limits (IEEE 754 64-bit), causing display errors like $1.0001 instead of $1.00 and rounding errors in portfolio calculations.

**Solution Implemented:**

1. **Decimal Math Utility** (`webapp/frontend/src/utils/decimalMath.js`): Safe financial arithmetic
   - Import: `import { add, multiply, toFixed, percentageChange } from '../utils/decimalMath'`
   - All functions preserve 2 decimal place precision
   - Example: `const sum = add('123.45', '67.89')` returns `'191.34'`

2. **Endpoint Schema Markup** (`webapp/frontend/src/utils/endpointSchemas.js`): Tag financial fields
   - Add `decimalFields: ['price', 'quantity', 'value', ...]` to endpoint schema
   - useApiQuery automatically formats these fields to 2 decimals

3. **API Response Post-Processing** (`webapp/frontend/src/hooks/useApiQuery.js`):
   - `formatDecimalFields()` normalizes all decimal fields after fetching
   - Applies `.toFixed(2)` to preserve precision
   - Runs before caching and before returning to components

**Using It:**

- **In calculations:** Use decimalMath utility instead of direct arithmetic
  ```javascript
  // Bad: portfolio.value + position.value
  // Good:
  import { add } from '../utils/decimalMath';
  const total = add(portfolio.value, position.value, 2);
  ```

- **In formatters:** Values already formatted by useApiQuery, use parseFloat() + .toFixed(2)
  ```javascript
  const formatted = parseFloat(value).toFixed(2);
  ```

- **For portfolio calculations:** Accumulate with add()
  ```javascript
  const total = positions.reduce((sum, p) => 
    add(sum, p.position_value, 2), '0'
  );
  ```

**Testing:** See `useApiQuery.unhandledRejection.test.jsx` → "should format decimal fields for financial precision"

## Security Baseline

All projects follow:
- ❌ NO `.env` files. Ever.
- ✅ Local: PowerShell profile env vars
- ✅ CI: GitHub Secrets (for deploy tokens only)
- ✅ Production: AWS Secrets Manager
- ✅ Rotate credentials quarterly
- ✅ If leaked: rotate immediately

See project steering docs for specifics.
