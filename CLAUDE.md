# Multi-Project Workspace Router

This workspace supports multiple projects: **algo** in `.` (see `steering/algo.md` for system details).

## QUICK START

**If you see:** `Error: The security token included in the request is invalid` or any AWS credential error when troubleshooting:

```powershell
scripts/refresh-aws-credentials.ps1
```

This fetches fresh credentials from IaC (Secrets Manager) and updates your local profile. See `steering/algo.md` → **LOCAL AWS CREDENTIALS** for details.

## STEERING PRINCIPLES

**Goal:** Steering docs are the single source of truth for how systems work. They must be clear, complete, and verifiable so people can understand and debug the system without relying on stale memory.

**Rules:**

1. **Content:** System map, credentials, deploy procedures, resources, schedule, key files, and debugging/troubleshooting procedures. NO live operational status ("currently broken", "just deployed", "as of 3pm"). That goes in GitHub Actions logs.
2. **Clarity over brevity:** Write for understanding first. Spell out times (4:00 AM ET, not 4A ET). Say "Lambda" not "Λ". If an abbreviation requires decoding, don't use it. Long sentences that are clear beat short sentences that confuse.
3. **Length:** No arbitrary limits. A 250-line steering doc that's clear is better than a 100-line one that requires guessing.
4. **Procedures, not status:** Document "how to debug X" (verifiable steps), not "X is broken" (stale status).
5. **Update in same commit:** When code changes, update steering doc in the same commit. No async updates.

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

**Critical thresholds** in `algo/infrastructure/config.py` DEFAULTS prevent the system from trading low-quality signals.
Never set these to zero or disable them for "testing" — doing so will trade any stock regardless of quality, including during earnings surprises:

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

## Security Baseline

All projects follow:
- ❌ NO `.env` files. Ever.
- ✅ Local: PowerShell profile env vars
- ✅ CI: GitHub Secrets (for deploy tokens only)
- ✅ Production: AWS Secrets Manager
- ✅ Rotate credentials quarterly
- ✅ If leaked: rotate immediately

See project steering docs for specifics.
