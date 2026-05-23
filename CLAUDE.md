# Multi-Project Workspace Router

This workspace supports multiple projects. When working in this repo, **read the appropriate steering doc** for your project before proceeding.

## Projects

| Project | Location | Steering Doc | Description |
|---------|----------|--------------|-------------|
| **algo** | `.` | `steering/algo.md` | Live stock trading platform (Alpaca + AWS) |

## ⚠️ STEERING COMMANDMENTS

**Future Claudes: Do not deviate. Follow these rules exactly.**

1. No live status/counts (only guidance: system map, credentials, deploy, resources, schedule, key files, troubleshooting). Live state → GitHub Actions, AWS, git log
2. No prose (tables, bullets, one-liners only — no paragraphs)
3. Stay under limits: Root < 50 lines, steering docs < 150 lines
4. Abbreviate aggressively (token burn is critical; see patterns below)
5. Update steering doc in same commit as system changes
6. No layering (all steering in `steering/`, not in subdirs)

## Source of Truth
- **System state** → `steering/algo.md` (updated in-commit, versioned)
- **Blocking work** → GitHub Issues (trackable, linkable)
- **History** → `git log` (never stale)
- **Behavioral rules** → Memory (max 1 file, no status snapshots)

❌ NO status in memory, NO incident logs in memory, NO tracking there.

## Abbreviation Patterns

- Times: `4A ET` not `4:00 AM Eastern Time`
- Arrows: `data → DB` not `data goes to database`
- Paths: `algo/algo_orchestrator.py — 7-phase runner` (path + one-word purpose)
- Emoji: `✅ local`, `❌ AWS` (not prose status)
- Commands: `python3 -m pytest tests/` (actual, runnable)
- Tables: Use for maps, not prose descriptions
- Lists: `RSI, SMA, EMA, ATR` (comma-sep, scannable)

## Adding Projects

1. Create `steering/{name}.md` with: status, system map, credentials, deploy, resource names, schedule, key files, troubleshooting, local dev
2. Add row to project table
3. Verify: root < 50 lines, steering < 150 lines, commit both together

## Code Cleanliness (Pre-Commit Enforced)

⚠️ **These rules are checked on every commit. Violations block merge.**

**BLOCKED:**
- `.env` files (use AWS Secrets Manager)
- Session docs at root (use `memory/`)
- Duplicate configs, test files, generated files, demo code
- `print()` in library code (use `logger.info()`)
- `pdb`/`ipdb` imports or `breakpoint()` calls
- One-time scripts at root (use `scripts/`)
- Files >1MB

**ALLOWED (exempted from print check):**
- `algo_loader_*.py`, `algo_daily_report.py` (CLI tools)
- `scripts/` directory
- `tests/` directory

**Violations caught?** Hook rejects commit. Fix, stage again, re-commit.

## Security Baseline

⚠️ **All projects follow:**
- ❌ NO `.env` files. Ever.
- ✅ Local: PowerShell profile, CI: GitHub Secrets, Production: AWS Secrets Manager
- ✅ Rotate credentials quarterly
- ✅ If secrets leak to git history, rotate immediately

See project steering docs for credential-specific paths and policies.
