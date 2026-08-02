# Project

```bash
python start_dashboard_dev.py                          # Local dev
python scripts/run_local_orchestrator.py               # Test orchestrator
```

**Data not available?** → Check staleness, then run orchestrator tests

**Rules:** Type-safe. No `.env`/`pdb`. Data integrity first. Always use `start_dashboard_dev.py` for local dev.

**Data staleness:** `python scripts/monitor_data_staleness.py` + `python scripts/verify_eventbridge_scheduler.py --fix`

**Orchestrator testing:** `python scripts/run_local_orchestrator.py [--afternoon|--evening]`

---

## Architecture & Navigation

### Two Orchestration Directories
- `algo/orchestration/` → Runtime execution (orchestrator.py 145KB, halt_flag_manager, regime_manager, etc.)
- `algo/orchestrator/` → Phase implementations (phase1-9, 12,382 LOC total, phase7/8 are refactoring candidates)

---

## Token Optimization

**Keep context lean:** Session-specific docs/logs/audits belong in memory, not root. Delete after sessions.

**Monthly maintenance:** 
```bash
git stash clear                          # Clear uncommitted work storage
git gc --aggressive --prune=now          # Compact .git (frees 50-100 MB)
```

**What to keep:** Code, tests, IaC, config. **What to delete:** .log files, audit reports, debug scripts, worktree branches.

**Memory best practice:** Only load-bearing rules in memory (safety gates, bugs, patterns). Session findings → delete when session ends.
