# Working with This Project

## Quick Start

**Local development — always use this entry point:**
```bash
python start_dashboard_dev.py                          # Starts loaders + API + dashboard
```

**Test orchestrator logic locally:**
```bash
python scripts/run_local_orchestrator.py [--afternoon|--evening]
```

**Troubleshooting data issues:**
```bash
python scripts/monitor_data_staleness.py               # Check freshness
python scripts/verify_eventbridge_scheduler.py --fix   # Repair scheduler if stuck
```

## Core Rules (Non-Negotiable)

**Data integrity first.** These rules prevent real bugs:
- Type-safe code (mypy pass required)
- No `.env` committed; use `.env.local` for secrets
- No `pdb` in production code
- Always use `start_dashboard_dev.py` for dev (not raw orchestrator)
- Load-bearing rules in `MEMORY.md` apply directly — don't question, verify in code

**Why:** This system runs production trading logic. Mistakes compound fast. The rules in memory exist because we've debugged those bugs before.

---

## Architecture & Navigation

### Two Orchestration Directories
- `algo/orchestration/` → Runtime execution (orchestrator.py 145KB, halt_flag_manager, regime_manager, etc.)
- `algo/orchestrator/` → Phase implementations (phase1-9, 12,382 LOC total, phase7/8 are refactoring candidates)

---

## Memory System

**Load-bearing rules live in `MEMORY.md`** — organized by domain (Database, Phases, Infrastructure, Git, etc.). Before touching code in those areas, check the relevant rule and apply it.

**Session-specific findings get deleted when the session ends:**
- Status reports, audit logs, temp debug findings → remove when done
- Only permanent code-level rules stay

**Before saving memory:**
- Verify the claim in DB/code (don't trust descriptions)
- Read the "Why" so you understand the actual bug being prevented
- Use the memory safety protocol from `MEMORY.md`

---

## Repository Maintenance

**Monthly cleanup:**
```bash
git stash clear                                # Clear uncommitted work storage  
git gc --aggressive --prune=now                # Compact .git (frees 50-100 MB)
```

**What to keep:** Code, tests, IaC, config files.
**What to delete:** `.log` files, audit reports, debug scripts, worktree branches, dated session findings from memory.
