# Working with This Project

## Quick Start

**Phantom files — do not invoke these or tell users to; if referenced anywhere, it's stale, fix it:**
- `start_dashboard_dev.py`, `check_system_health.py` — never existed / deleted. Use `scripts/monitor_data_staleness.py` instead.
- `steering/OPERATIONS.md`, `QUICKSTART_LOCAL.md` — deleted / never existed. Use `steering/GOVERNANCE.md` or this file instead.

**Local dev components (separate processes):**
```bash
python lambda/api/dev_server.py                         # Local API server (port 3001)
python -m dashboard --local                              # Dashboard TUI, reads local API (see dashboard/README.md)
python -m dashboard                                       # Dashboard TUI, AWS RDS mode (default, needs AWS_PROFILE)
python scripts/local_loader_scheduler.py --now metrics   # Load data locally — never run individual loaders directly
```

**Test orchestrator logic locally:**
```bash
python scripts/run_local_orchestrator.py [--morning|--afternoon|--preclose|--evening] [--date YYYY-MM-DD] [--force]
```
- Loads `.env.local` — `DB_NAME` there must be `stocks` (real local dev DB), not `algo_trading` (pytest-only DB).
- `--date`/`--force` do **not** bypass the market-hours guard — outside real market hours, a `--date` run silently `skip`s with `halt_reason: "outside_market_hours"` and never reaches Phase 1. Set `ALLOW_OUTSIDE_MARKET_HOURS=true` to actually exercise phase logic for a historical date.
- Phase 1 halts if DataPatrol hasn't run within 8h (missing/stale/CRITICAL finding in `data_patrol_log`). `run_local_orchestrator.py` never runs DataPatrol itself — run `python algo/algo_data_patrol.py` first, or set `ALLOW_MISSING_DATA_PATROL=true` (local/dev only; forced off in `execution_mode="auto"`).

**Troubleshooting data issues:**
```bash
python scripts/monitor_data_staleness.py               # Check freshness (simple elapsed-time buckets)
python scripts/verify_eventbridge_scheduler.py --fix   # Repair scheduler if stuck
```
`monitor_data_staleness.py` and Phase 1 (`algo/orchestrator/phase1_data_freshness.py`) use different freshness methodologies — Phase 1 is date-aware (requires TODAY's data after market close, YESTERDAY's otherwise), the monitor is not. A table can show FRESH in the monitor and still halt Phase 1 later the same day. Don't substitute the monitor for actually running the orchestrator.

**XBRL / price data-quality second-opinion layers** — periodic, sample-based cross-checks that are NOT part of every DataPatrol run (rate-limit/subprocess-cost reasons); run by hand or via their Windows Task Scheduler entries:
| Script | Checks | Notes |
|---|---|---|
| `scripts/xbrl_concept_coverage_scan.py --exclude-noise --min-companies 100` | us-gaap/dei concepts real filers tag vs. our loader allowlist | `--dismiss "us-gaap:Concept" --reason "..."` persists to `scripts/xbrl_concept_coverage_dismissed.json` (checked in) |
| `scripts/xbrl_yfinance_crosscheck.py` | Our SEC-XBRL numbers vs. yfinance (>2x divergence = WARN) | 25-symbol daily rotating sample |
| `scripts/xbrl_calculation_linkbase_check.py` | Filer's own declared XBRL summation relationships vs. their own reported facts | 15-symbol sample; primary-statement roles only (note-schedule dimensional facts produce false mismatches) |
| `scripts/xbrl_dqc_arelle_check.py` | Industry-standard DQC ruleset via Arelle | needs `pip install -r requirements-xbrl-dqc.txt` + `arelleCmdLine` on PATH; raises loudly if missing rather than reporting false-clean |
| `scripts/xbrl_segment_sum_reconciliation.py` | Segment revenue sums vs. consolidated total (>10% divergence = WARN) | monthly, full universe, uses SEC's dimensional Financial Statement and Notes Data Sets |
| `scripts/score_realized_ic_monitor.py` | Spearman IC between score columns and subsequent returns, logged to `score_realized_ic_log` | local-only, no network calls |
| `scripts/price_source_crosscheck.py` | Our `price_daily_split_adjusted.close_adjusted` vs. yfinance close (>1% divergence = WARN) | 25-symbol daily sample; also flags NULL `data_source` rows |

All support `--symbols`, `--limit`, `--dry-run`. `scripts/setup_windows_schedule.ps1` registers the periodic ones as Windows Task Scheduler tasks; `scripts/verify_windows_schedule.ps1` checks them for LogonType/battery-setting drift.

**Never force-kill a `local_loader_scheduler.py` or loader child process without checking liveness first.** `%TEMP%/algo-scheduler.lock` records `pid=/pipeline=/started=` — run `tasklist /FI "PID eq <n>"` to confirm the PID is actually dead before touching it. If alive, wait or ask.

**Execution mode changes require a full orchestrator/API restart.** `EXECUTION_MODE` (paper/dry/review/auto) is read once at process startup, not re-read mid-run. Restart both `lambda/api/dev_server.py` and the orchestrator together after changing it, and check the `[EXECUTOR] mode=...`/`[STARTUP]` log lines to confirm.

**Options sleeve is off by default** — `OPTIONS_SLEEVE_ENABLED=true` gates only the screener surface (`/api/options`, dashboard options panel), not `phase8_guards.py`'s `check_options_sleeve_overlap` capital-safety check, which always runs. Restart `lambda/api/dev_server.py` after changing.

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

**Cleanup:**
```bash
# Session artifacts
rm *.log                                       # Remove orchestrator test logs
rm -r __pycache__ .pytest_cache .mypy_cache   # Python cache (regenerated)

# Git optimization
# NOT `git stash clear` - the stash stack is shared across every worktree/session in this
# repo; clearing it can destroy another session's in-progress work with no recovery.
git gc --aggressive --prune=now                # Compact .git

# Memory system
# Delete old session-scoped findings from memory/
# Keep only load-bearing rules referenced in MEMORY.md index
```

**Agent worktree hygiene:**
```bash
python scripts/check_worktree_health.py   # lists every worktree's uncommitted files + ahead/behind vs main
```
Run before deleting ANY worktree — nothing automated catches abandoned worktrees today. A worktree is only safe to delete once its work is merged (commit uncommitted changes first, then merge/cherry-pick, verify tests, THEN delete) or explicitly confirmed superseded by reading main's current code (not just commit messages — message-grepping alone has produced false "superseded" verdicts). An agent that spins up a worktree should merge or explicitly hand off before considering its task done. Also check for orphaned worktree directories `git worktree list` no longer shows (can happen if `git worktree remove` fails partway) — compare against `ls .claude/worktrees/` directly.

**What to keep:** Source code, tests, IaC, config, current session active findings.
**What to delete:** `.log` files, old audit reports, Python cache, debug scripts, dated session findings from memory, .terraform cache (auto-regenerated).
