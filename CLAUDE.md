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

## Security Baseline

All projects follow:
- ❌ NO `.env` files. Ever.
- ✅ Local: PowerShell profile env vars
- ✅ CI: GitHub Secrets (for deploy tokens only)
- ✅ Production: AWS Secrets Manager
- ✅ Rotate credentials quarterly
- ✅ If leaked: rotate immediately

See project steering docs for specifics.
