# Working with This Project

## Quick Start

**`start_dashboard_dev.py` does not exist** — it's referenced in old log messages and comments
across the repo but was never a real file (confirmed via `git log --all`, 2026-08-09). Don't
invoke it or tell users to.

**`check_system_health.py` also does not exist** — same bug class, different phantom file
(confirmed deleted at some point via `git log --all --diff-filter=D`, and via a full-repo search,
2026-08-23). It was still being suggested as a real troubleshooting step in two user-facing
spots — `dashboard/dashboard.py`'s "no data loaded" console message and
`webapp/frontend/FRONTEND_SETUP.md` — both fixed to point at `scripts/monitor_data_staleness.py`
instead. Don't invoke `check_system_health.py` or tell users to; if you see it referenced
anywhere else in the repo, it's stale and should be corrected the same way.

**`steering/OPERATIONS.md` and `QUICKSTART_LOCAL.md` also don't exist** — same bug class again.
`OPERATIONS.md` was deliberately deleted 2026-07-26 (commit `6e81a267c`, "AWS-only, local dev
doesn't use"); `QUICKSTART_LOCAL.md` appears to have never existed. Both were still linked from
`steering/COMMON_OPERATIONS.md` (3 places) and referenced in a code comment in
`algo/monitoring/data_patrol/checks/staleness.py` (found and fixed 2026-08-24) — if you see
either referenced anywhere else, it's stale and should be corrected the same way, pointing at
`steering/GOVERNANCE.md` or this file instead as appropriate.

The real local dev components are separate processes:

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

**Phase 1 now halts if DataPatrol hasn't run recently (FIXED 2026-09-07).** `algo/orchestrator/
phase1_data_freshness.py`'s `_check_data_patrol_results` queries `data_patrol_log` for the
latest DataPatrol run and halts if it's missing, more than 8h stale, or has any CRITICAL/ERROR
finding (tie-out identity checks, staleness, XBRL concept gaps, statistical anomalies - the
whole DataPatrol suite). In production this is always fresh (terraform's pipeline DAG runs the
DataPatrol ECS step immediately before triggering the orchestrator), but
`scripts/run_local_orchestrator.py` never invokes DataPatrol itself — run
`python algo/algo_data_patrol.py` first, or set `ALLOW_MISSING_DATA_PATROL=true` (local/dev
only; forced off in `execution_mode="auto"` regardless, same as `ALLOW_OUTSIDE_MARKET_HOURS`)
to downgrade a missing/stale patrol run to a warning instead of a halt.

**Troubleshooting data issues:**
```bash
python scripts/monitor_data_staleness.py               # Check freshness
python scripts/verify_eventbridge_scheduler.py --fix   # Repair scheduler if stuck
```

**Finding missing XBRL concepts systematically (not one bug report at a time):**
```bash
python scripts/xbrl_concept_coverage_scan.py --exclude-noise --min-companies 100
```
Diffs every us-gaap/dei concept real filers actually tag (read from the on-disk SEC EDGAR
companyfacts cache under `%TEMP%/algo-sec-edgar-cache/companyfacts` — already populated by
normal loader runs, no extra fetching) against the allowlist our loader source files
(`utils/external/sec_income_statement.py`, `sec_balance_sheet.py`, `sec_cash_flow.py`,
`sec_custom_xbrl_concepts.py`, etc.) actually know how to fetch, ranked by how many distinct
companies tag each missing concept. This is how the `accounts_payable` gap (confirmed missing
from the whole schema, independently rediscovered by
`algo/research/quality_asset_turnover_piotroski_candidates.py`) got found — 3,392 filers tag
`AccountsPayableCurrent` and it was never in the allowlist at all. Re-run this periodically
(new symbols entering the universe, filers adopting newly-effective taxonomy tags in future
10-Ks) rather than waiting for the next "implausible value" bug report to point at a gap.
Review a batch, then record anything genuinely out of scope with `--dismiss "us-gaap:Concept"
--reason "..."` (persisted in `scripts/xbrl_concept_coverage_dismissed.json`, checked into
git) so future scans only surface what's actually new instead of re-litigating the same
already-reviewed footnote/schedule concepts every time.

**Independent second-opinion cross-check against yfinance (not a bug-report-driven thing,
run it periodically):**
```bash
python scripts/xbrl_yfinance_crosscheck.py               # samples 25 symbols, writes findings
python scripts/xbrl_yfinance_crosscheck.py --limit 50
python scripts/xbrl_yfinance_crosscheck.py --symbols AAPL,MSFT,KO
python scripts/xbrl_yfinance_crosscheck.py --dry-run      # print only, don't write to data_patrol_log
```
tie_out.py and statistical_anomaly.py both validate our own SEC-XBRL-derived numbers against
themselves (arithmetic identities, own trailing history) - neither can catch an extraction/
mapping bug that's internally self-consistent and doesn't stand out against history either.
This script fetches yfinance's independently-parsed financials (reuses the existing
`utils/external/yfinance_financials.py` fallback fetch and its currency/circuit-breaker
handling, never a value source for real tables - same discipline as `sec_valuations_checks.py`'s
market_cap/shares_outstanding cross-checks) and flags a >2x divergence on revenue/net_income/
total_assets/stockholders_equity/operating_cash_flow as a WARN finding, which flows into the
same `data_patrol_review` triage workflow as every other DataPatrol check. Deliberately NOT
part of every DataPatrol run - it makes live per-symbol yfinance network calls through the
same shared-IP rate limit every loader depends on, so a full-universe version every run would
risk the same self-triggered ban `yfinance_validation_calls_self_triggered_ban_during_reload_20260903`
describes. Run it by hand every so often (or from a low-frequency schedule) on a small
rotating sample - the daily pseudo-random sample means broad coverage accumulates over many
runs rather than needing to cover the whole universe in one pass.

**Layers 4/5 now run on their own weekly schedule, not just "by hand" (added 2026-09-10):**
`scripts/xbrl_second_opinion_weekly.py` calls `xbrl_yfinance_crosscheck.run()` and
`xbrl_calculation_linkbase_check.run()` back-to-back with their normal periodic-sample
defaults (25 / 15 symbols). It's the ECS command for a new, fully independent
`aws_cloudwatch_event_rule`/`aws_ecs_task_definition` pair in
`terraform/modules/loaders/main.tf` (`xbrl_second_opinion*`) firing Sunday 10:00 UTC —
deliberately its own task, NOT folded into the DataPatrol ECS task, because DataPatrol runs
twice daily on a hard 600s Step Functions timeout gating Phase 1, and these two checks make
live outbound SEC EDGAR/yfinance calls with unpredictable latency that could turn an
optional WARN-only check into an accidental trading halt. **This terraform is written but
NOT applied** — run `terraform plan`/`apply` in `terraform/` to actually turn the schedule
on; until then these two layers are still manual-only in practice, same as before.

**Calculation-linkbase self-consistency check (5th and final layer of the XBRL data-quality
architecture, added 2026-09-10 - not a bug-report-driven thing, run it periodically):**
```bash
python scripts/xbrl_calculation_linkbase_check.py               # samples 15 symbols, writes findings
python scripts/xbrl_calculation_linkbase_check.py --limit 30
python scripts/xbrl_calculation_linkbase_check.py --symbols AAPL,MSFT,KO
python scripts/xbrl_calculation_linkbase_check.py --dry-run      # print only, don't write to data_patrol_log
```
Unlike the other four layers (self-consistency of our own derived fields, statistical/peer
outliers, DQC-style negative-value guards, yfinance second-opinion), this one never touches
our own tables at all - it parses each sampled symbol's latest 10-K's XBRL calculation
linkbase (`utils/external/sec_calculation_linkbase.py`, fetched via
`SecEdgarClient.get_calculation_linkbase_xml`) to get the filer's OWN declared summation-item
relationships (e.g. `Assets = AssetsCurrent + AssetsNoncurrent`), then checks those against
the filer's own reported us-gaap fact values (matched by accession number, from the already-
cached companyfacts payload) for that exact filing. A mismatch means the FILING itself doesn't
tie, independent of anything our extraction code does. Restricted to primary-statement
extended link roles only (role name has no "Details"/"Tables" suffix) - SEC's companyfacts API
collapses all dimensional facts for a concept into one flat list with no axis/member info, so
note-schedule concepts reused across dimensional breakdowns (lease maturity tables, debt
schedules, segment detail) produce false "mismatches" that are really just companyfacts
losing the dimensional context, not a real filing error (live-confirmed on AAPL's FY2025
10-K before this filter was added: all 3 raw mismatches were note-schedule concepts, 0 were
face-financial-statement concepts). Same rate-limit posture as the yfinance script - not part
of every DataPatrol run, small rotating sample only.

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

**Never force-kill a `local_loader_scheduler.py` or loader child process without checking
liveness first.** A "stuck" PID may belong to a concurrent session's genuinely in-progress work
— live-witnessed 2026-08-17: a session force-killed a loader ~1.5h into a real run plus its
parent scheduler, destroying that progress and orphaning several tables' status rows (see
`concurrent_sessions_live_collision_20260817` / `scheduler_lock_owner_liveness_check_fix_20260817`
in memory). `%TEMP%/algo-scheduler.lock` now records `pid=/pipeline=/started=` for exactly this
reason — before killing anything, run `tasklist /FI "PID eq <n>"` (or `ps -ef | grep <n>`) to
confirm the PID in that lock file is actually dead, not just slow. If it's alive, it's not
stuck — wait for it, or ask before touching it.

**Execution mode changes require a full orchestrator/API restart.** `EXECUTION_MODE`
(paper/dry/review/auto) is read and logged once at process startup (`algo/trading/
executor_strategies.py`'s `validate_and_log_initialization`, `orchestrator.py`'s `[STARTUP]`
log line) — it is not re-read mid-run. Changing the config or env var without restarting both
`lambda/api/dev_server.py` and the orchestrator process leaves them running against
inconsistent assumptions about which mode is active (e.g. the API server still reporting
"paper" while the orchestrator process was restarted into "auto"), which can desync what the
dashboard shows from what the orchestrator is actually doing. Always restart both processes
together after an execution-mode change, and check the `[EXECUTOR] mode=...`/`[STARTUP]` log
lines to confirm the mode you expect actually took effect.

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
