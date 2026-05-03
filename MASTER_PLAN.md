# Master Plan — From "Far From Ideal" to "Best in Class"

**Honest audit:** A lot was built iteratively without planning, leaving real
architectural debt. This document is the systematic plan to fix it. It is the
single source of truth for what's wrong, what we're doing about it, and in
what order.

---

## Honest Audit — What's Actually Wrong

### Loader Layer
- **63 .py loader files** but CLAUDE.md says max 39 official
- **3 versions of the same loader**: `loadpricedaily.py`, `loadpricedaily_optimal.py`, `loadpricedaily_refactored.py`
- **20+ unofficial loaders** outside the canonical list
- `DATA_LOADING.md` has its own audit flagging `loadbuyselldaily.py` as "97.8% None signals — NEEDS FIX"
- No loaders have actually run recently — data is 9 days stale
- Cleanup discipline broken — accumulating tech debt

### Algo Layer
- **Mostly solid** (51/51 verification, 116/125 commitments delivered)
- **Real concern**: backtester needs historical score backfill to actually validate strategy
- **Not yet tested live**: bracket order placement to Alpaca in `auto` mode
- **Loaders feeding the algo** are the weakest link — algo can be perfect, but if data is stale/wrong/incomplete, decisions are bad

### API Layer
- 17 algo endpoints exist, but...
- Some old endpoints (`/api/sentiment` random Math.random() per CLAUDE.md note)
- Frontend uses `/api/*` but some endpoints inconsistent in naming/format
- No clear pattern for which endpoints should serve which page

### Frontend Layer
- **24 pages, scattered, inconsistent** — user describes as "looking like shit"
- Built page-by-page over time without unified design system
- Many pages are 1500-2900 lines with mixed concerns
- Data lives in weird places (e.g., commodities has v1 and v2)
- No mobile responsive discipline
- No iOS/Android readiness

### Documentation Layer
- `CLAUDE.md` — good
- `DATA_LOADING.md` — official loader list, partly outdated
- `ALGO_ARCHITECTURE.md` — written, comprehensive
- `LOADER_SCHEDULE.md` — written, references loaders that may not exist
- `FRONTEND_DESIGN_SYSTEM.md` — written, lays out IA + standards
- `MASTER_PLAN.md` — this document

---

## Strategy — How We Get to "Best in Class"

### Principle 1: Plan Before Build
No more random tactical work. Each item below has a defined scope and exit
criteria before any code is written.

### Principle 2: Consolidate, Don't Add
Before building new, delete what's broken. 63 loaders → 39. 24 pages → 8.

### Principle 3: Cross-Layer Coherence
Loaders feed the right tables. Tables back the right endpoints. Endpoints
back the right pages. Every layer aware of the other.

### Principle 4: Best Practice Wins
When in doubt, look at how Bloomberg/Stripe/Koyfin/IBD does it. We are
building for institutional quality.

### Principle 5: All Data, Best Display
Every page shows ALL the relevant data, not a subset. The display chooses
the best layout for that specific data.

---

## The 12 Workstreams

Ordered by **upstream-first priority** — fix data, then algo, then endpoints,
then frontend.

### W1. Loader Cleanup & Consolidation (CRITICAL UPSTREAM)
**Status:** Not started. Most pressing.

**Problems:**
- 63 .py files, max should be 39
- Duplicate loaders (`_optimal`, `_refactored`, `_v2`)
- Unofficial loaders outside canonical list
- `loadbuyselldaily.py` flagged broken in DATA_LOADING.md

**Tasks:**
1. **Audit each of 63 loaders**: official, duplicate, or unofficial?
2. **Pick canonical version** of each duplicated loader (likely the one most recently touched)
3. **Delete duplicates** in one PR
4. **Document remaining 39** in DATA_LOADING.md (update its outdated table)
5. **Fix `loadbuyselldaily.py`** — only insert real Buy/Sell, never "None"
6. **Verify each loader runs** — exit 0, populates expected rows

**Exit criteria:** 39 loaders, all documented, all run cleanly, no duplicates.

### W2. Loader Run Schedule Validation (BLOCKED ON W1)
**Status:** Schedule documented in `LOADER_SCHEDULE.md` and wrapper scripts written
(`run_eod_loaders.sh`, `run_intraday.sh`), but they reference loaders by names
that may not match what actually exists.

**Tasks:**
1. After W1, update `run_eod_loaders.sh` to reference the canonical names
2. Test pipeline end-to-end on yesterday's data
3. Add error handling: if loader X fails, retry once, then notify
4. Add per-loader timing metrics to `data_loader_status` table
5. Build cron / EventBridge expressions for production

**Exit criteria:** `bash run_eod_loaders.sh` runs all canonical loaders cleanly.

### W3. Data Patrol Hardening (BLOCKED ON W1)
**Status:** Built, working, finds CRITICAL stale data correctly.

**Tasks:**
1. After loaders are clean, expand patrol to validate per-loader contracts
   (e.g., `loadpricedaily` should produce ≥ 4900 distinct symbols/day)
2. Add cross-source validation against Yahoo (free) for top symbols
3. Surface failures more prominently in UI (red banner not just toast)
4. Auto-trigger patrol after every loader runs

**Exit criteria:** Patrol catches every silent failure mode of every loader.

### W4. Algo Final Validation
**Status:** 116/125 commitments delivered. Real gaps closed.

**Remaining:**
1. Run `backfill_historical_scores.py --days 180` after W1+W2 (data must be fresh)
2. Run backtester on fresh historical data — generate real Sharpe/win-rate
3. Test live Alpaca `auto` execution with one tiny test trade
4. Verify all 8 orchestrator phases survive a real run (currently only dry-run)

**Exit criteria:** First real algo trade placed in Alpaca paper account, full
audit trail visible, no silent failures.

### W5. API Endpoint Consolidation
**Status:** 17 algo endpoints + many legacy endpoints in `/api/*`. Inconsistent.

**Tasks:**
1. Audit every endpoint in `webapp/lambda/routes/` — purpose, response format,
   pagination, error handling
2. Document the contract: success/error/items/pagination format (CLAUDE.md
   already specifies this — verify all endpoints comply)
3. Build the 8-page-aligned endpoints (some may be new, some consolidate
   existing): one per IA page
4. Deprecate legacy endpoints (mark, don't delete yet)
5. Update CLAUDE.md "Known Endpoints" table

**Exit criteria:** Every endpoint follows the response contract, every page
maps cleanly to its endpoints.

### W6. Frontend Theme + Component Library
**Status:** Done. Light + dark hybrid, 13 UI primitives.

**Refinement tasks:**
1. Verify components on mobile breakpoints (xs, sm)
2. Add accessibility labels (aria-*) per Whatsforlunch reference
3. Document each primitive's props at top of `AlgoUI.jsx`

### W7. Frontend AppLayout
**Status:** Refreshed with sleek nav + brand + status bar + toasts.

**Refinement tasks:**
1. Add theme toggle button (light ↔ dark) in user menu
2. Mobile drawer state persists across nav

### W8. Page 1 — `/app/algo` Command Center
**Status:** Existing AlgoTradingDashboard, dark-themed.

**Tasks:**
1. Re-theme to light (default) using new tokens
2. Verify all 9 tabs render with new design system
3. Mobile-test
4. Polish loading/error states

### W9. Page 2 — `/app/markets` Market Health (PROOF OF CONCEPT)
**Status:** Started this round (`MarketsHealth.jsx` written but not wired into
routes). Template D, multi-section dashboard.

**Tasks:**
1. Finish wiring into App.jsx routes
2. Add the missing data sections (indices, breadth, economic, commodities)
3. Mobile responsive check
4. Replace old MarketOverview, Sentiment, EconomicDashboard, SectorAnalysis,
   CommoditiesAnalysis routes (redirect)
5. Delete deprecated page files in cleanup PR

### W10. Page 3 — `/app/stocks` Stock Universe
**Status:** Not started. Template B (Data Browser).

**Tasks:**
1. Build page from scratch using design system
2. Server-side pagination with smart filters
3. Combined display: stock_scores, swing_trader_scores, value_trap_scores,
   signal_quality_scores all visible per row
4. Click row → `/app/stock/:symbol`
5. Replace old ScoresDashboard, TradingSignals, DeepValueStocks, FinancialData

### W11. Page 4 — `/app/stock/:symbol` Stock Detail
**Status:** Not started. Template C (Detail Page).

**Tasks:**
1. New page — replaces drill-downs
2. Hero: symbol + price + day change + key indicators
3. Tabs: Chart, Scores, Signals, Financials, Earnings, News
4. All data from existing endpoints

### W12. Page 5-8 (Portfolio, Research, Health, Landing)
**Status:** Not started.

**Tasks:**
1. Portfolio (Template A) — algo-aware metrics, R-multiples, base type per position
2. Research Hub (Template B) — backtests, earnings calendar
3. Health (Template E) — data patrol, audit log, settings, Alpaca status
4. Landing (existing marketing) — keep, light retheme

---

## Order of Execution

```
W1 (loader cleanup)
  └─ W2 (run schedule) ──┐
  └─ W3 (patrol)         ├─ W4 (algo final validation)
                         │
                         └─ W5 (API consolidation)
                              │
                              └─ W6+W7 (theme, layout) [DONE]
                                   │
                                   ├─ W8  (algo page retheme)
                                   ├─ W9  (markets page) [in progress]
                                   ├─ W10 (stocks universe)
                                   ├─ W11 (stock detail)
                                   └─ W12 (portfolio, research, health, landing)
```

W1-W3 unblocks everything else. **Loader cleanup is the immediate next task.**

---

## Definition of Done (per workstream)

A workstream is **done** only when:
1. ✅ All tasks completed and committed
2. ✅ Every artifact tested end-to-end
3. ✅ Documentation updated (CLAUDE.md, DATA_LOADING.md, ALGO_ARCHITECTURE.md)
4. ✅ User-visible piece works at xs (mobile) and lg (desktop)
5. ✅ No regressions to other workstreams (regression test = `FULL_BUILD_VERIFICATION.py`)

---

## What "Best in Class" Looks Like

- **Loader layer**: 39 canonical loaders, all run cleanly, all monitored
- **Algo layer**: 8-phase orchestrator, real backtest validation, live Alpaca trades, audit trail
- **API layer**: every endpoint follows contract, error states clear, paginated where appropriate
- **Frontend layer**: 8 purpose-built pages, light theme default, mobile-responsive, design-system-driven, ALL data displayed
- **Operations**: cron schedules running, AWS-ready, monitoring catches every silent failure
- **Documentation**: every layer's design + decisions captured, every research source cited

---

## What's NEXT (right now)

**Priority 1**: Execute W1 — loader cleanup. Identify 24 unofficial loaders,
pick canonical versions, delete duplicates. Update DATA_LOADING.md.

This unblocks everything else. Without clean data flow, no other layer can
trust its inputs.
