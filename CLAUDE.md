# Working with This Project

## Quick Start

**`start_dashboard_dev.py` does not exist** — it's referenced in old log messages and comments
across the repo but was never a real file (confirmed via `git log --all`, 2026-08-09). Don't
invoke it or tell users to. The real local dev components are separate processes:

```bash
python lambda/api/dev_server.py                         # Local API server (port 3001)
python -m dashboard --local                              # Dashboard TUI, reads local API (see dashboard/README.md)
python -m dashboard                                       # Dashboard TUI, AWS RDS mode (default, needs AWS_PROFILE)
python scripts/local_loader_scheduler.py --now metrics   # Load data locally (see feedback_always_use_pipeline_scheduler_for_backfills memory — never run individual loaders)
```

**Test orchestrator logic locally:**
```bash
python scripts/run_local_orchestrator.py [--morning|--afternoon|--preclose|--evening] [--date YYYY-MM-DD] [--force]
```
This loads `.env.local` — `DB_NAME` there must be `stocks` (the real local dev DB with actual
config/scores/trades). `algo_trading` is a different, near-empty DB reserved for the pytest
suite (`tests/conftest.py` hardcodes `DB_NAME=algo_trading`) — if `.env.local` ever points there
instead, local orchestrator runs will silently execute against a barren DB and any "verified
locally" claim from that session is worthless. This exact drift happened and was fixed 2026-08-09.

**`--date YYYY-MM-DD` does not bypass the market-hours guard.** `algo/orchestration/orchestrator.py`
checks the *real* current wall-clock ET time against real market hours on every run, regardless
of `--date` or `--force` — this is intentional (prevents pre/post-market runs from corrupting
production state), not a bug. Outside real market hours (which is most of the time you'd be
testing locally, including all weekends), a `--date` run for a past trading day will silently
`skip` with `halt_reason: "outside_market_hours: HH:MM:SS ET"` and never reach Phase 1 at all —
easy to mistake for the loader/data problem you were actually trying to reproduce. To actually
exercise phase logic for a historical date outside real market hours, set
`ALLOW_OUTSIDE_MARKET_HOURS=true` in the environment first.

**Troubleshooting data issues:**
```bash
python scripts/monitor_data_staleness.py               # Check freshness
python scripts/verify_eventbridge_scheduler.py --fix   # Repair scheduler if stuck
```

`monitor_data_staleness.py` and Phase 1 (`algo/orchestrator/phase1_data_freshness.py`) use
**different freshness methodologies** — a table can show FRESH in the monitor and still halt
Phase 1 minutes later:
- `monitor_data_staleness.py`: simple elapsed-time buckets (fresh/stale/critical at
  24h/36h/48h for most tables).
- Phase 1: date-aware — requires TODAY's data once market close has passed, YESTERDAY's data
  otherwise (`is_after_market_close` check), not just "loaded within N hours".
An operator checking the monitor at 4 PM can see FRESH on yesterday's data that Phase 1 will
correctly halt on at 5 PM once market close makes today's data the requirement. This is
expected — not a bug in either script — but don't use the monitor's output as a substitute for
running the orchestrator itself when you need to know if Phase 1 will pass.

## Core Rules (Non-Negotiable)

**Data integrity first.** These rules prevent real bugs:
- Type-safe code (mypy pass required)
- No `.env` committed; use `.env.local` for secrets
- No `pdb` in production code
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

**Monthly cleanup** (runs ~2026-08-07 cleaned 1,850 MB):
```bash
# Session artifacts
rm *.log                                       # Remove orchestrator test logs
rm -r __pycache__ .pytest_cache .mypy_cache   # Python cache (regenerated)

# Git optimization
git stash clear                                # Clear uncommitted work storage
git gc --aggressive --prune=now                # Compact .git (frees 50-100 MB)

# Memory system
# Delete old session-scoped findings from memory/
# Keep only load-bearing rules referenced in MEMORY.md index
```

**What to keep:** Source code, tests, IaC, config, current session active findings.
**What to delete:** `.log` files, old audit reports, Python cache, debug scripts, dated session findings from memory, .terraform cache (auto-regenerated).

**Recent cleanup (2026-08-07):**
- Memory: 70+ files (250 KB) → 32 files (111 KB)
- Logs: 80 files (39 MB deleted)
- Python cache: 26 dirs (13 MB deleted)
- Terraform cache: 3 dirs (1,785 MB deleted)
- Git gc: 6 MB additional packing
- **Total: 1,850 MB freed**
