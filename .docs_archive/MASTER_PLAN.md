# Master Plan — From "Far From Ideal" to "Best in Class"

**Last refreshed:** 2026-05-03 (Sunday afternoon, day before market open)

This is the single source of truth for what's wrong, what we're doing about
it, and in what order. It is honest — no inflation, no celebration of work
that isn't actually done.

---

## Honest current state (2026-05-03)

### What's working
- **Algo orchestrator**: 8 phases run end-to-end. PID lock prevents double-runs.
  Auth on mutating endpoints. Verified in dry-run with both fresh and stale data.
- **Alpaca paper account**: ACTIVE, $75K portfolio, $240K buying power. 7 legacy
  positions (3 broken-stop ones queued to close at Monday open).
- **Swing trader scores**: full-universe loader (`loadswingscores.py`) running
  daily on ~3,800 symbols with sufficient data, scores persisted to
  `swing_trader_scores`. 87 passers on 5/1 (top: LOCO C 57.6).
- **Mansfield RS + RS percentile**: real computation (252-day SMA of stock/SPY
  ratio, then PERCENT_RANK across symbols per date). Persisted in
  `trend_template_data`.
- **Bulk EOD loader**: `load_eod_bulk.py` uses yfinance batched download (80
  symbols per HTTP call, threaded) — refreshes the full ~5,000-symbol universe
  in ~5 minutes vs the per-symbol throttled version.
- **Data remediation engine**: 8 action recipes wired into the EOD pipeline.
- **Patrol cross-validation**: DB ↔ Alpaca ↔ Yahoo Finance triple check.
- **GitHub Actions CI**: 51-test verification on every push.

### What's broken or missing
- **Per-symbol price loader (`loadpricedaily.py`) yfinance throttle**: stops at
  ~150 symbols. Bulk loader is the workaround for daily top-up; per-symbol is
  retained for backfilling years of history. Both are tracked, neither
  blocks Monday.
- **EOD pipeline scheduling**: `run_eod_loaders.sh` is not yet on cron /
  EventBridge / Task Scheduler. Today it must be triggered manually.
- **Patrol scheduling**: `algo_data_patrol.py` only runs when triggered (via
  EOD wrapper or manually). No standalone heartbeat schedule.
- **Backfill window short**: `signal_quality_scores` and `trend_template_data`
  have ~15 dates of history (4/6 → 5/1). For statistically meaningful
  backtest metrics we need 90-180 days.
- **Loader inventory**: 62 `load*.py` files vs the 39 documented as official.
  Audit pending.
- **Frontend theme mismatch**: light theme tokens but layout reads dark to
  the user. Theme + layout unification pending. Per finance UX research,
  light should be default with dark optional.
- **Frontend page rebuild**: 24 scattered pages → target 8 purpose-built. Only
  `MarketsHealth` started; not yet wired with all data sections.
- **Alpaca MCP server**: not yet configured. Only `stocks-algo` MCP exists
  (Linux path that doesn't match Windows machine).

---

## What we delivered today (2026-05-03)

| Item | Why it matters |
|---|---|
| Auth middleware on `/algo/run|/patrol|/simulate|/notifications/seen` | These trigger trades / expensive jobs — now require token |
| Auth on `backtests.js` POST + `contact.js` admin routes | Closed 4 more unprotected mutating endpoints |
| PID concurrency lock in orchestrator | Prevents double-runs that could double-place trades |
| Real Mansfield RS + RS-rank percentile + Minervini c8 | True 8-criterion trend template (was missing c8) |
| `loadswingscores.py` (full-universe runner) | `swing_trader_scores` was 4 rows total — now 87 passers + 3,698 fail-reason rows on 5/1 |
| Multi-timeframe windows tuned (30→90d weekly, 90→270d monthly + MA fallbacks) | Average mtf score 0.1 → 4.0; Stage-2 setups had weekly BUY weeks ago, not last 30 days |
| Momentum return blend tuned (30/15/5 → 20/10/3) | Calibrated for Stage-2 consolidation behavior |
| Walk-forward backtester producing real metrics | Was finding 2 trades, now finds 8 (over 15-day window) |
| `load_eod_bulk.py` — batched yfinance loader | 5,000 symbols in ~5 min; replaces throttled per-symbol path for daily top-ups |
| Wire MarketsHealth into `/app/markets` route | New page reachable; legacy paths preserved |
| `--skip-freshness` orchestrator flag | Test end-to-end on stale data without bypassing the gate in production |
| 3 broken-stop Alpaca positions queued to close | NFLX/AVGO/NVDA market sells at Monday open free 6% open risk budget |
| `MONDAY_RUNBOOK.md` | Step-by-step pre-market / open / EOD instructions |
| `FRONTEND_DESIGN_SYSTEM.md` (research-backed) | NN/g + Apple HIG + Material + IBM Carbon + finance industry analysis → light default, sleek elaborate aesthetic |

---

## The 12 workstreams (current status)

### W1. Loader cleanup
**Status:** Most done. 39 official loaders documented. Per-symbol price loader
fixed to use canonical `stock_symbols` table. Bulk loader added for daily top-ups.
**Remaining:** Audit 62 vs 39 to identify which extras are dead code (#85).

### W2. Loader run schedule
**Status:** Documented in `LOADER_SCHEDULE.md`. `run_eod_loaders.sh` updated to
use bulk loader.
**Remaining:** Install Windows Task Scheduler entries (#88).

### W3. Data patrol hardening
**Status:** Per-loader contracts (11 checks), Yahoo cross-validation, auto-
remediation all wired.
**Remaining:** Schedule patrol heartbeat (currently manual / EOD-triggered only).

### W4. Algo final validation
**Status:** Backfill + backtester producing real metrics. Orchestrator phases
all execute. Real Mansfield + c8. Swing scores full-universe.
**Remaining:** Live Alpaca trade in `auto` mode after Monday open. Will know
Monday whether algo found qualifying entries (likely no, candidates max C).

### W5. API endpoint consolidation
**Status:** Auth on dangerous routes. Response contract documented in CLAUDE.md.
**Remaining:** Audit all routes for contract compliance, deprecate legacy.

### W6. Frontend theme + component library
**Status:** Light/dark hybrid tokens in `algoTheme.js`. 13 UI primitives in
`AlgoUI.jsx`. Design system doc written.
**Remaining:** Verify components on mobile breakpoints. AppLayout was built
"sleek dark" — needs alignment with light-default decision (#91).

### W7. AppLayout
**Status:** Sleek nav, header status bar, exposure pill, notification badge,
toast on new alerts. Polls `/algo/markets` and `/algo/notifications` every 30s.
**Remaining:** Theme unification, mobile drawer state, theme toggle in user menu.

### W8-W12. The 8 pages

| # | Path | Status |
|---|---|---|
| W8 | `/app/algo` Command Center | Existing AlgoTradingDashboard, needs retheme |
| W9 | `/app/markets` Market Health | Wired into routes, needs all data sections (#61) |
| W10 | `/app/stocks` Stock Universe | Not started |
| W11 | `/app/stock/:symbol` Detail | Not started |
| W12.a | `/app/swing` Swing candidates | New page modeled on DeepValueStocks (planned) |
| W12.c | `/app/portfolio` | Not started (#63) |
| W12.d | `/app/health` Service health | Not started (#65) |
| W12.e | `/app/research` Hub | Not started |

`/app/scores` (the existing 6-factor `ScoresDashboard`) **stays as-is per user
direction** — we are NOT rebuilding that one. Other scoring systems get their
own dedicated pages.

---

## Order of execution (post-Monday)

**Top of the queue** — these have the biggest payoff per hour of work:

1. **Patrol scheduled runner** (#88) — install Windows Task Scheduler entries
   for both EOD pipeline (5:30pm ET weekdays) and a patrol heartbeat (9:25am
   ET weekdays).

2. **Theme + AppLayout unification** (#91) — make light theme the consistent
   default across nav, header, drawer, all pages. Per FRONTEND_DESIGN_SYSTEM.md.

3. **Backfill extension to 180 days** (#87) — for statistically meaningful
   backtest metrics. SQL window functions can do this fast (~30-60 min).

4. **Configure official Alpaca MCP server** — gives me direct broker tools.

5. **Loader inventory cleanup** (#85) — 62 vs 39, delete the dead code.

6. **MASTER_PLAN.md update** (#86) — done in this commit.

7. **Frontend page rebuilds** — `/app/swing`, `/app/portfolio`, `/app/health`,
   then drilldowns.

---

## What "best in class" looks like

- **Loader layer**: 39 canonical loaders, all run cleanly, all monitored, all
  on a schedule. Bulk top-up + per-symbol backfill paths.
- **Algo layer**: 8-phase orchestrator, real backtest validation, live Alpaca
  trades, audit trail, automatic remediation.
- **API layer**: every endpoint follows contract, error states clear, paginated
  where appropriate, mutating routes auth-gated.
- **Frontend layer**: 8 purpose-built pages, light theme default per finance
  UX research, mobile-responsive, design-system-driven, ALL data displayed.
- **Operations**: Task Scheduler runs the daily pipeline, monitoring catches
  every silent failure, MCP gives direct broker control.
- **Documentation**: every layer's design + decisions captured, every research
  source cited.

---

## What's NEXT (right now, post-Monday)

**Priority 1**: Verify Monday morning operations went as planned.
Specifically: did the 3 broken positions close at open? Did the orchestrator
run cleanly? Did patrol find anything actionable?

**Priority 2**: Install Windows Task Scheduler so the EOD pipeline runs
automatically each market day.

**Priority 3**: Theme + AppLayout unification — kill the light/dark
mismatch, make every page look like Stripe × Koyfin (sleek, elaborate,
information-dense, light-default).

These three items will make the system self-running and visually coherent.
Everything else is content and polish.
