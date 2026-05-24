# Multi-Project Workspace Router

This workspace supports multiple projects. When working in this repo, **read the appropriate steering doc** for your project before proceeding.

## Projects

| Project | Location | Steering | Checklists |
|---------|----------|----------|-----------|
| **algo** | `.` | `steering/algo.md` | `DEPLOY_CHECKLIST.md`, `LIVE_TRADING_CHECKLIST.md` |

## ⚠️ STEERING COMMANDMENTS

**Future Claudes: Do not deviate. Follow these rules exactly.**

1. No live status/counts (only guidance: system map, credentials, deploy, resources, schedule, key files, troubleshooting). Live state → GitHub Actions, AWS, git log
2. No prose (tables, bullets, one-liners only — no paragraphs)
3. Stay under limits: Root < 50 lines, steering docs < 150 lines
4. Abbreviate aggressively (token burn is critical; see patterns below)
5. Update steering doc in same commit as system changes
6. No layering (all steering in `steering/`, not in subdirs)

**Quick reference:** `STEERING_CHECKLIST.md` lists red flags before committing steering edits.

## Where Each Thing Goes
| What | Where | Why |
|------|-------|-----|
| Static config (paths, ports, credentials, deploy) | `steering/{project}.md` | Versioned, discoverable |
| Operational status (live errors, deployments, blockers) | GitHub Issues / GitHub Actions | Real-time, not stale |
| History (commits, changes) | `git log --oneline` | Authoritative |
| Behavioral guidance (team patterns) | Memory (1 file max, <50 lines) | Evolves with learnings |

**NEVER add to steering:** status, blockers, errors, timestamps, "as of X", anything temporary.
**NEVER add to memory:** status snapshots, incident logs, live state of any kind.

## Abbreviation Patterns

- Times: `4A ET` not `4:00 AM Eastern Time`
- Arrows: `data → DB` not `data goes to database`
- Paths: `algo/algo_orchestrator.py — 7-phase runner` (path + one-word purpose)
- Emoji: `✅ local`, `❌ AWS` (not prose status)
- Commands: `python3 -m pytest tests/` (actual, runnable)
- Tables: Use for maps, not prose descriptions
- Lists: `RSI, SMA, EMA, ATR` (comma-sep, scannable)

## Adding Projects

1. Create `steering/{name}.md` with: system map, credentials, deploy, resource names, schedule, key files, troubleshooting, local dev (**NO status**)
2. Add row to project table
3. Verify: root < 50 lines, steering < 150 lines, commit both together

## Code Cleanliness (Pre-Commit Enforced)
⚠️ **Violations block commit:** .env, session docs at root, test files, `print()` in lib code, pdb/breakpoint, 1-way scripts at root, >1MB files.
**Exempt from print():** `algo_loader_*.py`, `algo_daily_report.py`, `scripts/`, `tests/`. See `.git/hooks/pre-commit`.

## Security Baseline

⚠️ **All projects follow:**
- ❌ NO `.env` files. Ever.
- ✅ Local: PowerShell profile, CI: GitHub Secrets, Production: AWS Secrets Manager
- ✅ Rotate credentials quarterly
- ✅ If secrets leak to git history, rotate immediately

See project steering docs for credential-specific paths and policies.
