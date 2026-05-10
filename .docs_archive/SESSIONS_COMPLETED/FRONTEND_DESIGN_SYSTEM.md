# Bullseye — Frontend Design System & IA Strategy

This is the contract that prevents what we have today (24 inconsistent pages,
scattered data, weird page-to-page transitions, "bulky" feel).

Every page from here forward is built against these rules. No exceptions.

---

## Information Architecture — Consolidation Plan

**Today: 24 pages.** Many overlap, many are too narrow, no clear hierarchy.

**Target: 8 purpose-built pages.** Every page has a clear job. Data lives where
it logically belongs and is reachable from one obvious place.

### The 8 Pages

| Path | Purpose | Replaces / Merges |
|---|---|---|
| `/app/algo` | **Command Center** — daily trading workflow | AlgoTradingDashboard |
| `/app/markets` | **Market Health** — all market-level data | MarketOverview + Sentiment + Economic + Sectors + Commodities |
| `/app/stocks` | **Stock Universe** — browse/filter all stocks | ScoresDashboard + TradingSignals + DeepValueStocks + FinancialData |
| `/app/stock/:symbol` | **Stock Detail** — one stock deep-dive | (new — replaces drill-downs) |
| `/app/portfolio` | **Portfolio** — positions + performance + tools | PortfolioDashboard + Optimizer + HedgeHelper + TradeHistory |
| `/app/research` | **Research Hub** — backtests, ideas | BacktestResults + EarningsCalendar |
| `/app/health` | **System Health** — data, audit, settings | ServiceHealth + Settings + APIDocs |
| `/` | **Landing/Home** | (existing marketing) |

### Why This Works
- **No more "where's the X data?"** — one logical home per data type.
- **Tabs WITHIN pages** organize sub-views without forcing 5 menu clicks.
- **Mobile-friendly** — 8 menu items fit any screen.
- **App-ready** — same IA translates 1:1 to iOS/Android nav.

---

## Design Language

### Theme Strategy: **Light by Default, Dark on Toggle**

Per Bloomberg/Stripe/Koyfin research: light themes win for max data clarity in
financial UIs. Dark is a preference toggle (long-session/low-light), not the
default. localStorage persists user choice.

### Color System

**Tokens only.** Never hardcode colors anywhere. Import from `theme/algoTheme.js`.

```
SURFACES:
  bg          — page background (#f6f8fa light / #0d1117 dark)
  bgElev      — sidebar, header (#ffffff / #161b22)
  card        — content card (#ffffff / #21262d)
  cardAlt     — alt rows, hovered (#f6f8fa / #1c232c)

TEXT:
  textBright  — headers, important values
  text        — body
  textDim     — labels, secondary
  textFaint   — hints

SEMANTIC (financial):
  bull        — gains/positive
  bear        — losses/negative
  warn        — caution
  brand       — Bullseye green (#0d8a3e light / #3fb950 dark)
  blue        — informational accent

PALETTES:
  bullSoft / bearSoft / warnSoft / blueSoft — backgrounds for status pills
```

### Typography

```
Body:    Inter — UI text, headers
Numbers: JetBrains Mono — ALL numeric values, dates, IDs, codes
Display: Inter heavy — page titles, hero numbers

Sizes (responsive):
  xxs(0.65) → xs(0.7) → sm(0.81) → base(0.875) → md(0.94) → lg(1.125)
  → xl(1.5) → xxl(2) → xxxl(2.5) → hero(3.25)
```

**Rule: every number in the app uses `font-family: F.mono`.** This single rule
gives the app its institutional feel.

### Spacing & Layout

```
Page padding (responsive):
  xs:     1.5 (24px)   mobile
  sm/md:  2-3 (32-48px) tablet/desktop

Card radius:    8px
Section gap:    16-24px
Grid gutters:   16px
```

---

## Component Library

**Every component is in `components/ui/AlgoUI.jsx`. Pages compose. They don't
re-implement.**

| Component | Purpose | Example |
|---|---|---|
| `<SectionCard title="..." action={...}>` | Primary content container | Wraps any data section |
| `<Stat label="..." value="..." color={...}>` | Labelled numeric value | KPI displays |
| `<KpiCard label value sub accent>` | Bordered stat with accent stripe | Top-of-page metrics |
| `<PnlCell value format="..." />` | Auto-colored P&L number | Tables, summaries |
| `<GradeChip grade="A+">` | Letter grade pill | Score displays |
| `<SeverityChip severity="warn">` | Status pill | Alerts, statuses |
| `<TrendArrow value>` | Up/down/neutral indicator | Trend columns |
| `<ProgressBar value max>` | Fill bar with semantic color | Score visualizations |
| `<FactorBar label pts max>` | Labelled progress for breakdowns | 9-factor exposure |
| `<DataTable columns rows>` | Stylized table primitive | Any tabular data |
| `<StatusDot severity>` | Tiny colored dot | Inline status indicators |
| `<PageHeader title subtitle actions>` | Top of every page | Page chrome |
| `<EmptyState message icon action>` | "No data" message | Empty tables |

### Adding a New Component
1. Build in `AlgoUI.jsx`
2. Use only theme tokens (`C.brand`, `F.mono`, etc.)
3. Document its props at the top of the function
4. Use it across at least 2 pages before promoting

---

## Page Templates

Different content types need different layouts. **Don't force every page into
the same shell.**

### Template A: **Workflow Dashboard** (e.g., Algo Command Center)
```
[ Page Header ]
[ Status strip (4 KPI cards) ]
[ Tier policy banner (if active) ]
[ Tabs ─────────────────────── ]
[ Tab content (purpose-built) ]
```
Uses the algo dashboard pattern — tabs for related sub-views, status strip
always visible.

### Template B: **Data Browser** (e.g., Stock Universe)
```
[ Page Header with search + filters ]
[ Filter chips row ]
[ Stat strip (counts, averages) ]
[ Sortable table (full-screen) ]
[ Drill-down panel (right side, optional) ]
```
For pages where the user is exploring/filtering many records.

### Template C: **Detail Page** (e.g., Stock Detail)
```
[ Hero: symbol + price + key change ]
[ Quick stats row ]
[ Tabs: Chart / Scores / Financials / News / etc ]
[ Tab content (chart-centric or table) ]
```
For drilling into one entity. Hero-up-top, tabs for sections.

### Template D: **Multi-Section Dashboard** (e.g., Markets Health)
```
[ Page Header ]
[ Top: 1-row status of overall market ]
[ Grid of cards: each card = one data area ]
   - Indices  - Breadth  - Sentiment  - Sectors  - Economic
[ Each card has its own loading/error state ]
```
For pages showing many parallel data areas at once.

### Template E: **System / Settings**
```
[ Page Header ]
[ Sidebar nav (sub-sections) ]
[ Detail panel ]
```
For configuration / system pages.

---

## Cross-Cutting Standards

### Loading States
- Skeleton loaders, not spinners (preserves layout)
- Each card has its own loading state — don't block the whole page

### Error Handling
- Inline `<Alert severity="error">` per data area
- Never an empty page; always show what loaded + flag what didn't

### Empty States
- Always meaningful: "No qualifying setups today — market in caution tier"
- Provide context, not just "no data"

### Numbers
- Always monospace
- Color-coded P&L (green/red/dim)
- Always include unit ($ / % / R)
- Right-align in tables

### Dates
- ISO 8601 in tooltips (machine-readable)
- "Apr 24" / "Jun 12, 2026" in display (human-readable)
- "9d ago" / "2h ago" for recency

### Tables
- Sticky headers when scrollable
- Hover row highlight
- Click row → navigate to detail
- Alternate row background optional (off by default)

### Mobile
- Horizontal scroll for wide tables (not collapse)
- Drawer nav (already implemented)
- Bottom-sheet for filters/actions
- Touch targets ≥ 40px

---

## Responsive Breakpoints

```
xs (0+)      mobile portrait
sm (600+)    tablet portrait / mobile landscape
md (900+)    tablet landscape / small desktop
lg (1200+)   desktop
xl (1536+)   wide desktop
```

**Rule: every page tested at xs and lg minimum.** Never break on mobile.

---

## App-Readiness (iOS / Android future)

The design system is built so that:
1. Color tokens map 1:1 to React Native StyleSheet objects
2. Typography uses system font fallbacks that work on iOS/Android
3. Spacing is in MUI units (8px base) → translates directly
4. Component primitives (Stat, KpiCard, PnlCell) port to RN with same props
5. Routes match: `/app/algo` becomes `AlgoStack` in RN navigation
6. No layout uses fixed pixel widths — flex/grid only

When we ship mobile, we re-implement primitives in RN; pages stay structurally
identical.

---

## Build Discipline

- **No new pages without a template.** Pick A/B/C/D/E.
- **No hardcoded colors anywhere.** Use tokens.
- **No `<Typography>` with bare `fontSize`.** Use F scale.
- **No copy-pasted `<Card>` patterns.** Use `<SectionCard>`.
- **Every page imports from `theme/algoTheme.js` and `components/ui/AlgoUI.jsx`.**

This is what stops the "weird scattered pages" problem.

---

## Delivery Plan

1. ✅ Theme module (light + dark, hybrid)
2. ✅ AlgoUI component library
3. ✅ AppLayout refresh (light theme + nav)
4. **/app/algo** — already done, retheme to light
5. **/app/markets** — Template D, consolidates 5 pages
6. **/app/stocks** — Template B, consolidates 4 pages
7. **/app/stock/:symbol** — Template C
8. **/app/portfolio** — Template A, consolidates 4 pages
9. **/app/health** — Template E, consolidates 4 pages
10. **/app/research** — Template B
11. Old route redirects (`/app/sentiment` → `/app/markets#sentiment` etc.)

After all 8 are built, we delete the 16+ deprecated page files in one PR.
