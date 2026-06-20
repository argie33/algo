# Codebase Governance

## QUICK START

AWS credential error? Run: `scripts/refresh-aws-credentials.ps1`

For system architecture and config, see `steering/system.md`.

## STEERING RULES

1. **Content:** System map, procedures, architecture, troubleshooting. NO live status, timestamps, or incident logs.
2. **Clarity:** Complete sentences. Spell out times (4:00 AM ET).
3. **Procedures:** Document "how to debug X" with verifiable steps, never "X is broken" (stale status).
4. **Updates:** Code changes + steering updates in same commit. No async updates.

## Where Information Goes

| What | Where | Why |
|------|-------|-----|
| System design, procedures, config | `steering/system.md` | Single source of truth |
| Current state, errors happening now | GitHub Actions logs, AWS console | Real-time |
| What happened and why | `git log` with good commit messages | Permanent record |

**NEVER in steering:** Live status, timestamps, incident logs, "as of", blockers.

## Code Cleanliness (Pre-Commit Enforced)

**Blocks commits:**
- `.env` files (use AWS Secrets Manager)
- `pdb`, `ipdb`, `breakpoint()` left in code
- `print()` statements in library code (use logging)
- Files > 1MB (binaries, artifacts)

**Allowed:**
- `print()` in: `algo_loader_*.py`, `algo_daily_report.py`, `scripts/`, `tests/`

**Type checking & imports (enforced):**
- Type errors from mypy BLOCK commits
- Code must be importable (no NameError)
- Before committing: `python -m mypy <file>.py --ignore-missing-imports`

## Documentation Lifecycle

**Steering docs** (`steering/system.md`): PERMANENT only.
- ✅ Architecture, procedures, thresholds, troubleshooting
- ❌ Status, incident logs, "completed/fixed" with dates

**Memory files** (`.claude/projects/*/memory/*.md`): Actionable NOW or delete.
- ✅ Ongoing feedback, current context, references
- ❌ Historical incidents, completed fixes (they're in git log)

**Rule:** After a fix ships → delete the memory file. Git log is the record.

## Security Baseline

- NO `.env` files. Ever.
- Credentials: AWS Secrets Manager (production), PowerShell profile (local)
- CI: GitHub Secrets for deploy tokens only
- Rotate quarterly (first Monday), immediately if leaked
- Auditable: All secrets in Secrets Manager, never in code or config files

See `steering/system.md` → **Credentials & Secrets** for procedures.
