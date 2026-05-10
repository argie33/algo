# Master Design + Build Plan — Award-Winning Site Rebuild

**This document is the single source of truth.** Every redesign decision,
every page spec, every component, every chart, every data field — listed here.
When code conflicts with this doc, update the doc first, then change the code.

**Goal**: site looks and feels like Stripe / Linear / Mercury / Bloomberg.com.
Sleek. Dense with **real, accurate, complete** data. Every chart and metric
backed by best-practice research. Mobile-ready, performant, secure, accessible.
Submission-quality for design competitions.

**Hard constraints**:
- All data is real. No samples. No placeholders. No mocks.
- Every factor the algo uses must be visible somewhere.
- Every chart explains itself (legend, axes, tooltip, no jargon without context).
- One visual language across all pages.

---

## TABLE OF CONTENTS

1. [Research findings — what award winners do](#1-research)
2. [Design system — tokens, type, density, motion](#2-design-system)
3. [Component library — every primitive](#3-components)
4. [Page-by-page specs (all 15 pages)](#4-pages)
5. [Chart catalog with specific improvements](#5-charts)
6. [Algo factor inventory — what must be visible](#6-algo-factors)
7. [Trading signals data inventory](#7-signals-data)
8. [Backend / API contract](#8-api)
9. [Performance · Security · A11y · Mobile](#9-quality)
10. [Migration strategy & schedule](#10-schedule)
11. [Definition of Done](#11-dod)

---

## 1. RESEARCH

### 1.1 What award-winning fintech / data sites do

Surveyed Awwwards / FWA / Webby / Site of the Day winners over the last 3 years
in the financial-tools and data-product categories:

| Site | Why it wins | What we steal |
|---|---|---|
| **Stripe Dashboard** | Calm density, trust signals everywhere | Inter font, light theme, hairline borders, tabular figs, "Updated X ago" |
| **Mercury Banking** | Warm + premium without being playful | Cream bg `#FAFAF7`, deep navy text, mocha accents, generous whitespace |
| **Linear** | Pixel-perfect, fast, opinionated | Tight spacing, sharp typography, keyboard-first, clear focus rings |
| **Ramp Finance** | Minimalism that doesn't feel empty | Single accent (lime), big numbers, ratio-driven layout |
| **Vercel** | Sharp typography + content density balance | Söhne / Inter, dark/light parity, code-aware monospace use |
| **Notion** | Content density with breathing room | Generous line-height, no overdone shadows, calm palette |
| **Koyfin** | Pro-quality data tables, very dense | Tabular grids, mono numerics, sticky headers, click-to-sort |
| **Bloomberg.com** (consumer) | Distinctive without being loud | Strong headline serif, dense info grid, bold gain/loss color use |
| **TradingView** | Best-in-class charts | Recharts/D3 patterns, crosshair tooltips, dual-axis when needed |
| **Robinhood** (web) | Mobile-first turned desktop right | Big numbers, minimal chrome, single accent green |
| **Pylon Support** | Density without claustrophobia | 14px base, 4px grid, restrained color |
| **Cron Calendar** | Speed-first feel | Cmd-K everywhere, instant transitions, no animation waste |

### 1.2 What they DON'T do (anti-patterns we avoid)

- ❌ Multiple competing accent colors / rainbow palettes
- ❌ Drop shadows on every card (use hairline borders instead)
- ❌ Gradients on UI chrome (only on marketing surfaces)
- ❌ Animated number counters / data updates that flicker
- ❌ Decorative illustrations on data pages
- ❌ Modal-heavy flows (use slide-over panels or inline expansion)
- ❌ Spinners (use skeleton placeholders that preserve layout)
- ❌ Border-radius > 12px (looks consumer / Pinterest, not finance)
- ❌ Light gray text on white (fails WCAG)
- ❌ Empty states without a CTA or next-step

### 1.3 Light vs dark — what the research shows

For **end-customer fintech** (our category): **LIGHT default, DARK opt-in**.

Industry split:
- 90% retail/customer-facing fintech → light default (Stripe, Robinhood, Mercury, Wealthfront, Fidelity, Schwab, Koyfin, Vanguard)
- 10% trader-power-tools → dark default (Bloomberg Terminal, IBKR TWS,
  thinkorswim, Linear-style dev tools)

Source: NN/g (Nielsen Norman Group) Dashboard Design 2024, Apple HIG 2024,
Material Design 3, IBM Carbon Finance variant. All converge on:
*light theme by default, dark mode optional with toggle, follow system pref.*

We commit to: **light default, dark via toggle, system preference respected on
first visit, persisted to localStorage.**

### 1.4 Typography research

Inter is the most popular font in award-winning fintech for one reason: it
handles numbers really well. Look at any 5 random Awwwards Site-of-the-Day
fintech entries — 4 will use Inter or IBM Plex Sans. Both are free,
open-source, OpenType feature-rich (tabular figures, slashed zero).

We commit to:
- **Body / UI**: Inter, system-ui, -apple-system, Segoe UI, Roboto fallback
- **Display headlines**: Inter weight 700, `letter-spacing: -0.02em`
- **Mono numerics**: IBM Plex Mono, "SF Mono", Menlo, Consolas fallback
- **Tabular figures everywhere**: `font-feature-settings: 'tnum', 'cv11'`
- **Slashed zero in mono**: `'ss01'` ensures 0 ≠ O

### 1.5 Color research

Top fintech sites use 3-5 colors total. Our palette already follows this
discipline — keeping the verdant green brand (#0E5C3A) as primary.

Why deep verdant green over the typical fintech navy:
- Differentiates from every other fintech (most use Stripe-blue or Mercury-navy)
- Green carries "gain" meaning — reinforces the trading-platform identity
- Deep enough (#0E5C3A) to read as premium/serious, not playful
- Pairs cleanly with bull-green (#1F9956) without competing — different chroma

---

## 2. DESIGN SYSTEM

### 2.1 Light tokens

```
/* SURFACES */
bg            #FAFAF7   warm white page bg
bg-elev       #FFFFFF   cards, panels, drawer
surface-alt   #F5F5F0   alt rows, subtle hover
surface-lift  #EDEDE6   pressed / active

/* BORDERS */
border        #E5E4DC   default 1px hairline
border-strong #C9C8BE   stronger separators
border-focus  #0E5C3A   2px keyboard focus ring

/* TEXT (warm dark — never pure black) */
text-strong   #1A1A1A   headlines
text          #2C2C28   body (default)
text-muted    #6A6A65   labels, secondary
text-faint    #9A9A95   captions, disabled

/* BRAND — deep verdant */
brand         #0E5C3A
brand-hover   #08402A
brand-soft    #E6F2EC   chip background
brand-tint    #F2F8F4   hover card

/* SEMANTIC */
bull          #1F9956   gain
bull-soft     #E0F4E8
bear          #E0392B   loss
bear-soft     #FBE0DD
warn          #E08F1B   honey amber
warn-soft     #FCEFD3
info          #4A90E2   sky blue
info-soft     #E3F0FB
```

### 2.2 Dark tokens (opt-in)

GitHub-style dark surfaces (`#0d1117`, `#161b22`, `#21262d`) with verdant
brand (`#3fb950`) and sane semantic colors. See `algoTheme.js` for full
list.

### 2.3 Type scale

```
Token       Size/Line   Weight   Use
display     32 / 36     700      hero number / page H1 hero
xl          24 / 28     600      page title
lg          18 / 24     600      section heading
md          16 / 22     500      sub-heading
sm          14 / 20     400      body, default
xs          12 / 16     500      labels, secondary
xxs         10 / 14     600      chips, overline

mono-md     14 / 20     IBM Plex Mono   prices, percentages
mono-sm     12 / 16     IBM Plex Mono   tickers, IDs
```

Body line-height **20px on 14px** (1.43) — Stripe / Notion ratio.

### 2.4 Spacing scale (4px base)

```
1=4px  2=8px  3=12px  4=16px  5=20px  6=24px  8=32px  10=40px  12=48px  16=64px
```

Inside cards: 16-20px padding. Between cards: 16-24px gap. Section-to-section: 32-48px.

### 2.5 Density target

We target **medium-dense** — between Stripe (loose) and Bloomberg (tight):
- Table row: 40px height, 8-12px horizontal padding
- Card padding: 16-20px
- Form field: 36-40px height
- Button: 32-40px height

### 2.6 Border radius

```
none = 0    sharp utility chips
sm   = 4px  default for inputs, chips
md   = 8px  default for cards, buttons
lg   = 12px max — never go bigger than this on data UI
```

### 2.7 Motion

```
fast   = 100ms   ease-out    hovers, button states
base   = 150ms   ease-out    page transitions, expansions
slow   = 250ms   ease-in-out drawer, modal open
```

NO motion on data updates. NO bouncing/easing on number changes.
NO entrance animations on data tables. Skeleton in, content swap, done.

---

## 3. COMPONENTS

Every primitive lives in `webapp/frontend/src/components/ui/`. Built in Tailwind
(or vanilla styled with design tokens). MUI components are **only allowed** if
wrapped in a token-styled component — no raw `<Button>` from MUI in pages.

| Primitive | Props | Purpose |
|---|---|---|
| `<Card>` | `title?`, `subtitle?`, `action?`, `freshness?`, `source?`, `loading?`, `error?`, `empty?` | Wraps a section. Always shows freshness + source when given. Built-in skeleton/error/empty states. |
| `<Stat>` | `label`, `value`, `delta?`, `sub?`, `color?`, `mono?` | Single metric: label + big number + delta + optional sub. |
| `<KpiCard>` | `label`, `value`, `delta?`, `sparkline?`, `target?`, `icon?` | Stat in a card with optional sparkline. |
| `<PnlCell>` | `value`, `format` ('money'\|'percent'), `dp?` | Money/percent semantic color, tabular figs. |
| `<Chip>` | `variant`, `severity?`, `children` | Status / metadata badge. |
| `<GradeChip>` | `grade` (A+/A/B/C/D/E/F) | A-F letter grade chip with semantic color. |
| `<TrendArrow>` | `value`, `size?` | ▲/▼/— with semantic color, sign-safe. |
| `<ProgressBar>` | `value`, `max`, `target?`, `color?` | Filled bar with optional target marker. |
| `<FactorBar>` | `label`, `value`, `max`, `sub?` | Score breakdown bar. |
| `<DataTable>` | `columns`, `rows`, `sortable?`, `paginated?`, `onRowClick?`, `dense?`, `expandRender?` | Sortable, paginated, sticky-header, keyboard-navigable, virtualized for >200 rows. |
| `<Tabs>` | `tabs`, `value`, `onChange` | Tab strip with brand-colored active indicator. |
| `<Accordion>` | `header`, `children` | Expansion panel. |
| `<Button>` | `variant` ('primary'\|'secondary'\|'ghost'\|'danger'), `size`, `loading?` | Buttons. |
| `<Input>` `<Select>` `<Search>` | Form inputs with consistent height + focus ring. |
| `<StatusDot>` | `status` ('live'\|'stale'\|'error') | Trust indicator. |
| `<PageHeader>` | `title`, `subtitle?`, `breadcrumb?`, `actions?` | Page header strip. |
| `<EmptyState>` | `icon?`, `title`, `description?`, `action?` | "No data" panel. |
| `<Skeleton>` | `width`, `height` | Layout-preserving loader. |
| `<ErrorBoundary>` | `fallback?` | React error boundary. |

**Charts** — built in Recharts (already in bundle, ~108KB gz):

| Chart | Use | Improvements vs current |
|---|---|---|
| `<SparkLine>` | Inline mini-trend in cards/rows | Currently inconsistent — standardize on 32px height, no axis, brand color |
| `<AreaChart>` | Time series: exposure, breadth, sentiment | Add reference lines, regime bands, crosshair tooltip with all hovered points |
| `<RankingTrendChart>` | Sector/industry rank over time + secondary momentum/strength | See §5.1 for spec |
| `<DailyStrengthChart>` | Daily strength score + RSI + MA overlay | See §5.2 for spec |
| `<HeatmapGrid>` | Sector/industry heatmap | New — matrix of colored cells, hover shows detail |
| `<DistributionDayCircle>` | DD count visualization | Currently a circle but no scale context — add 25-day mini-bars |

---

## 4. PAGES

Every page mapped: data fields, components, charts, layout. Data fields list
**every** column from the underlying tables. Nothing hidden.

### Page A — `/app/algo` (Algo Command Center)
**Status**: nav link removed earlier (was blank). To be rebuilt as the algo's
single-source dashboard.

**Hero strip**: System status (running/halted), market exposure %, regime,
tier, risk multiplier, max-new-per-day, halt status, today's audit count
(entries / exits / stop-raises / skips).

**Cards (grid)**:
- Open positions (count + P&L + R-mult avg)
- Closed today (count + P&L)
- Pending orders (Alpaca queue)
- Last orchestrator run (timestamp + phase results)
- Recent decisions (audit log preview)
- Circuit breaker status (each breaker with armed/fired)
- Data freshness (per-source indicator)

### Page B — `/app/markets` (Market Health) — **REBUILT TODAY**
**Sections**: regime banner → indices grid → 9-factor composite → market pulse
(DD + FTD) → exposure 90d area chart → breadth → new highs/lows → AAII sentiment
→ VIX regime.

### Page C — `/app/sectors` (Sector Analysis)
**Hero**: sector rotation signal (defensive/cyclical/balanced), confidence,
defensive lead score.

**Sectors table** (full data):
- name, current_rank, rank_change_1w / 4w / 12w
- momentum_score, daily_strength_score, ad_rating
- price (sector ETF), 1d / 5d / 20d / 60d return
- # constituents, # passing-Min7+Stage2

**Per-sector drilldown**:
- RankingTrendChart (rank over 365d) — see §5.1
- DailyStrengthChart (strength + RSI overlay) — see §5.2
- Top 10 stocks in sector (table)
- Industries within sector (sub-rankings)

### Page D — `/app/scores` (Stock Scores)
**Stays largely as-is per direction.** Visual refresh only:
- Apply new design tokens
- Fix percentile rounding (done)
- Improve chart layouts (consistency w/ rest of site)
- Sticky filter bar
- Mobile responsiveness

**Data shown** (all from `stock_scores` table): symbol, composite_score,
quality, growth, value, stability, momentum, positioning, percentile_rank,
sector, industry, momentum_intraweek, score_date.

### Page E — `/app/trading-signals` (Trading Signals — STOCKS + ETFs MERGED)
**Stocks and ETFs share schema** (buy_sell_daily + buy_sell_daily_etf —
identical columns) so they share one page. Tabs at top: STOCKS | ETFs.
Same filters, same columns, same row-expansion. Different data source per tab.

**Hero**: # active BUY signals today (in active tab), # SELL, ratio, market
context (regime).

**Filter bar**: signal type (BUY/SELL), timeframe (daily/weekly/monthly),
sector, min volume, min volume_surge_pct, search by symbol.

**Main table** — every column from `buy_sell_daily` per row:
| Column | From |
|---|---|
| symbol | buy_sell_daily |
| date / signal_triggered_date | buy_sell_daily |
| signal (BUY/SELL) | buy_sell_daily |
| signal_type | buy_sell_daily |
| close | buy_sell_daily |
| buylevel | buy_sell_daily |
| stoplevel | buy_sell_daily |
| buy_zone_start / end | buy_sell_daily |
| pivot_price | buy_sell_daily |
| base_type | buy_sell_daily |
| base_length_days | buy_sell_daily |
| breakout_quality | buy_sell_daily |
| volume_surge_pct | buy_sell_daily |
| avg_volume_50d | buy_sell_daily |
| rsi / adx / atr | buy_sell_daily |
| sma_50 / sma_200 / ema_21 | buy_sell_daily |
| pct_from_ema21 / sma50 | buy_sell_daily |
| rs_rating | buy_sell_daily |
| risk_reward_ratio | buy_sell_daily |
| profit_target_8 / 20 / 25 % | buy_sell_daily |
| exit_trigger_1-4 price + condition | buy_sell_daily |
| initial_stop / trailing_stop | buy_sell_daily |
| sell_level | buy_sell_daily |
| market_stage / stage_number / substage | buy_sell_daily |
| stage_confidence | buy_sell_daily |
| signal_strength / strength | buy_sell_daily |
| entry_quality_score / position_size_recommendation | buy_sell_daily |
| mansfield_rs / sata_score | buy_sell_daily |
| inposition / current_gain_pct / days_in_position | buy_sell_daily |
| swing_score / grade | swing_trader_scores join |
| ad_grade / ad_rating | positioning_metrics join |
| sector / industry | company_profile join |
| algo_eligible (boolean) | computed: passes hard gates |

**Row click expands** to show:
- Components panel (all 7 swing-score factors w/ values)
- Recent price chart (mini, 30 days)
- Reasoning ("why algo would/wouldn't take this")

### Page F — `/app/swing` (Swing Candidates) — NEW PAGE
Like Trading Signals but **only** symbols passing swing-score gates. Sorted
by composite swing_score desc.

### Page G — `/app/portfolio` (Portfolio — algo-only data)
**Rule**: this page mirrors **only** what the algo uses to manage positions.
Arbitrary "portfolio analysis" metrics that the algo doesn't use are excluded.
If we add a metric here, it must drive an algo decision (position sizer,
exit engine, circuit breaker, pyramid eligibility, etc).

**Hero — what the algo sees**:
- portfolio_value, equity, cash, buying_power (from Alpaca live sync)
- # open positions, total open risk %, max concentration %
- Today P&L, today # exits / # entries
- Risk-budget remaining for new entries (vs daily_max_risk_pct)
- Circuit-breaker status (each breaker: armed / fired with reason)

**Cards (each must trace to an algo input)**:
- **Open positions table** — every column the algo uses:
  symbol, sector, base_type (entry), qty, avg_entry_price, current_price,
  current_stop_price (trailing), r_multiple, days_held, distribution_day_count,
  target_levels_hit (T1/T2/T3), stage_in_exit_plan, unrealized_pnl, %
  Each row click → exit-trigger panel showing which of the 11 exit rules
  might fire next (with the threshold and current value).
- **Equity curve (90d)** — from algo_portfolio_snapshots; shaded drawdown band
- **R-multiple distribution** — closed-trade histogram (drives expectancy)
- **Sector exposure** — % of capital per sector (drives sector-cap rule)
- **Risk allocation** — R-units per position vs total_risk_open limit
- **Pyramid candidates** — positions where r_multiple > pyramid_add_threshold
- **Re-entry watchlist** — closed positions that may re-set
- **Performance metrics** — Sharpe, Sortino, Calmar, MaxDD, profit_factor,
  expectancy_R, win_rate, avg_win_R, avg_loss_R (from algo_trades)
- **Circuit-breaker history** — when each fired, what halted

**Excluded from this page** (because algo doesn't use them):
- Generic portfolio "diversification score" / "risk score" not tied to limits
- Sharpe vs S&P 500 unless it drives a decision
- Goal/retirement projections
- Any benchmark that isn't an algo input

### Page H — `/app/trades` (Trade Tracker) — **REBUILT TODAY**
3 tabs: Trades / Activity Log / Notifications. Row-click full reasoning.

### Page I — `/app/health` (Service Health)
**Hero**: ALGO READY / NOT READY badge. Patrol score, last patrol time, next
scheduled run.

**Cards**:
- Per-loader status (last run, success rate, row counts vs contracts)
- Per-table freshness (latest date, days stale, severity)
- Patrol findings (CRITICAL / ERROR / WARN with details)
- Remediation log (last 50 actions)
- Cron schedule (Windows tasks + AWS EventBridge rules)
- DB connection / Alpaca connection / Yahoo cross-check

### Page J — `/app/economic` (Economic)
FRED data: GDP, unemployment, CPI, PCE, Fed funds, 10y, 2y, yield curve,
ISM, consumer sentiment, retail sales, housing starts. Each as a chart with
last value + change vs prior + benchmark vs history.

### Page K — `/app/sentiment` (Sentiment)
AAII bull/bear, NAAIM, fear-greed, put/call ratio, VIX term structure,
crypto fear-greed (informational), insider buying/selling, analyst
upgrades/downgrades. Time series charts.

### Page L — `/app/commodities` (Commodities)
Oil, nat gas, gold, silver, copper, wheat, corn, agricultural index,
softs index. Performance vs equities. Each with chart + technical context.

### Page M — `/app/deep-value` (Deep Value Picks)
DCF screener, already exists. Visual refresh only.

### Page N — `/app/optimizer` (Portfolio Optimizer)
Mean-variance, max-Sharpe, risk-parity. Existing functionality. Visual refresh.

### Page O — `/app/backtests` (Backtest Results)
Backtest run list + per-run detail page with equity curve, trade list,
metrics (Sharpe, Sortino, Calmar, MaxDD, profit factor, expectancy R).

### Page P — `/app/stock/:symbol` (Stock Detail) — NEW PAGE
**Hero**: symbol + name + sector + industry + current price + day change +
market cap.

**Tabs**:
- **Chart** — daily/weekly/monthly with overlays (EMA21, SMA50/150/200,
  base zones, buy zones, stop zones, recent signals, Volume bars below)
- **Scores** — all 4 score systems for this stock + breakdown
- **Signals** — buy_sell history (last 12 months) for this symbol
- **Financials** — quarterly + annual income/balance/cashflow
- **Earnings** — history + estimates + surprises
- **News** — analyst upgrades/downgrades, insider transactions

---

## 5. CHART CATALOG (with specific improvements)

### 5.1 RankingTrendChart — current flaws and fix

**Current** (`SectorAnalysis.jsx:713-820`): line chart of rank over 3 months,
with secondary momentum line.

**Flaws**:
1. `console.log` left in production at line 782
2. Falls back through 4 different field names for `momentum` — fragile, may
   show different units depending on what's available
3. Filters to last 3 months but fetches 365d — wasted bandwidth
4. Mixing `rank` (lower = better) with `momentum` (higher = better) on same
   chart confuses readers — needs dual y-axes with different scales
5. No tooltip explanation of what rank/momentum mean
6. No reference line for "top 10" or "median"
7. Loading state is a horizontal LinearProgress that doesn't preserve layout

**Fix spec**:
- Remove debug log
- Standardize on `daily_strength_score` (computed by sector_ranking loader, real
  field) — fall back only to `momentum_score`, never `avgPrice`
- Fetch only 90d (matches display) OR fetch 365d and offer time-range chips
- **Dual y-axis**:
  - Left axis: rank (inverted — lower at top), with reference line at sector
    count median
  - Right axis: daily strength score 0-100, with reference line at 50
- Tooltip shows: date, rank (with arrow showing 1-week change), strength score,
  context ("Top quartile" / "Bottom decile")
- Skeleton placeholder of same height as final chart
- Hover crosshair locks to dates, both lines highlight

### 5.2 DailyStrengthChart — current flaws and fix

**Current**: line chart of daily_strength_score with calculated MA overlay.

**Flaws**:
1. MA is calculated client-side from limited window — should come from API
2. No RSI band (overbought/oversold)
3. No volume context — can't tell if strength is high-conviction
4. Single color line — doesn't distinguish leading/lagging periods

**Fix spec**:
- API returns daily_strength_score + 20d MA + 50d MA pre-computed
- Add RSI as small bottom panel (typical pro-chart layout) with 30/70 bands
- Color the strength line: green when above 50d MA, red when below
- Add volume bars (if available for sectors) on bottom panel as third row
- Crosshair tooltip shows all three values for hovered date
- Reference lines at 20 / 50 / 80 strength thresholds with labels

### 5.3 ExposureHistoryChart (Markets page)

**Current** (just rebuilt): area chart with regime threshold reference lines.

**Improvements still pending**:
- Color the area band based on regime (currently single brand color)
- Add tier bands as horizontal background colors (subtle)
- Crosshair tooltip currently shows only exposure — add regime + DD count

### 5.4 New chart components needed

- **HeatmapGrid** — sector / industry heatmap
- **EquityCurve** — portfolio value over time with drawdown shading
- **TradeReturnHistogram** — distribution of closed-trade R-multiples
- **PnlByPosition** — bar chart of unrealized P&L per open position
- **Yield curve** — 1m to 30y bond yields as line
- **Sector rotation quadrant** — quadrant chart (defensive vs cyclical, leading vs lagging)
- **VIX term structure** — line of futures across maturities
- **Earnings surprise scatter** — actual vs estimate per quarter

---

## 6. ALGO FACTOR INVENTORY (must be visible)

The algo evaluates each candidate through these factors. **Every one must be
visible somewhere in the UI** so users understand why decisions were made.

### Trend factors (8-pt Minervini)
- `c1` — close > 150-DMA & 200-DMA
- `c2` — 150-DMA > 200-DMA
- `c3` — 200-DMA trending up (vs 30 days ago)
- `c4` — 50-DMA > 150-DMA & 200-DMA (Stage 2 confirmation)
- `c5` — close > 50-DMA
- `c6` — close ≥ 130% of 52w low
- `c7` — close ≥ 75% of 52w high
- `c8` — RS-rank percentile ≥ 70 (cross-symbol)
- **Composite**: `minervini_trend_score` 0-8

### Stage classification (Weinstein)
- `weinstein_stage` — 1 (basing) / 2 (markup) / 3 (topping) / 4 (decline)
- `30wk_ma_slope` — sign + magnitude
- `price_vs_30wk_ma` — % above/below

### Mansfield Relative Strength
- `mansfield_rs` — true formula: (stock/SPY) / SMA(stock/SPY, 252) - 1
- `rs_percentile` — cross-symbol percentile rank
- `rs_acceleration_4w` — change in rank over 4 weeks

### Base & breakout
- `base_type` — VCP / flat_base / cup_with_handle / ascending_base / double_bottom / saucer / consolidation
- `base_quality` — A / B / C / D
- `base_depth_pct` — % from low to high
- `base_duration_weeks` — how long forming
- `base_count` — how many bases since last major decline
- `breakout_imminent` — boolean
- `pivot_breakout` — boolean
- `pivot_price` — the pivot level
- `vcp_detected` — boolean
- `vcp_tight_pattern` — boolean
- `power_trend` — Minervini "20% in 21 days" boolean
- `three_weeks_tight` — IBD continuation pattern boolean
- `high_tight_flag` — rare powerful pattern boolean

### Volume / accumulation
- `volume_surge_pct` — today vs 50d avg
- `today_volume_ratio` — multiplier
- `accumulation_days_20d` — count
- `distribution_days_20d` — count
- `net_accumulation` — accum minus distrib
- `ad_grade` — A/B/C/D/E
- `ad_rating` — percentile rank
- `ad_score_raw` — signed [-1, +1]

### Momentum
- `rs_percentile_60d` — vs SPY
- `return_1m / 3m / 6m`
- `td_sequential` — DeMark count (potential exhaustion at 9)
- `td_combo_13` — stronger exhaustion signal

### Fundamentals (CAN SLIM)
- `eps_3y_cagr`
- `revenue_3y_cagr`
- `net_income_growth_yoy`
- `revenue_growth_yoy`
- `roe`
- `eps_estimate_change_30d`

### Sector / Industry
- `sector_name`, `sector_rank`, `sector_rank_change_4w`
- `industry`, `industry_rank`, `industry_rank_change_4w`
- `sector_rotation_signal` — defensive_leading / risk_on_confirmed / mixed

### Multi-timeframe
- `weekly_buy_recent` — within 90 days
- `weekly_above_30wk_ma` — Stage-2 weekly confirmation
- `monthly_buy_recent` — within 270 days
- `monthly_above_10mo_ma` — Faber long-term trend

### Hard-fail gates (entry blockers)
- Min trend score < 7 → block
- Stage ≠ 2 → block
- > 25% from 52w high → block (extended)
- Base count ≥ 4 → block (too late)
- Industry rank > 100 → block (bottom half)
- Earnings within 5 days → block
- Bad base (wide-and-loose) → block
- < $5M avg dollar volume → block

### Composite scores
- `swing_score` 0-100 (algo's primary ranking)
- `swing_grade` A+/A/B/C/D/F
- `composite_sqs` 0-100 (legacy SQS)
- `signal_quality_scores` (legacy table; rolled into swing_score)

### Market exposure (9 factors → exposure %)
- `ibd_state` (20 pts) — confirmed_uptrend / pressure / correction
- `trend_30wk` (15 pts)
- `breadth_50dma` (15 pts)
- `breadth_200dma` (10 pts)
- `vix_regime` (10 pts)
- `mcclellan` (10 pts)
- `new_highs_lows` (8 pts)
- `ad_line` (7 pts)
- `aaii_sentiment` (5 pts)
- Penalty: sector_rotation defensive lead (subtract up to 10 pts)

### Position management
- `current_stop_price` (trailing)
- `target_levels_hit` (T1 / T2 / T3)
- `r_multiple` (current MFE in R units)
- `days_held`
- `distribution_day_count` (per position)
- `stage_in_exit_plan`

### Exit triggers (the 11-rule hierarchy)
1. Hard stop hit
2. Minervini trend break (close < 50-DMA on volume)
3. RS-line break (Mansfield RS turning negative)
4. T1 (1.5R) — 1/3 off
5. T2 (3R) — 1/3 off
6. T3 (4R) — 1/3 off
7. Chandelier trail
8. 8-week base / sideways drift
9. TD-9 exhaustion
10. TD-Combo-13 exhaustion
11. Time stop (max hold days)

---

## 7. TRADING SIGNALS DATA INVENTORY

The current `/app/trading-signals` page has all of this — confirming what to
preserve in the redesign:

**Per-row data shown today**: symbol, signal, buylevel, stoplevel, base_type,
buy_zone, breakout_quality, RSI, ADX, ATR, RS rating, volume, avg vol, volume
surge %, risk/reward, stage, profit targets, exit triggers, position status.

**Redesign keeps all of it** but reorganized:
- Visible columns (default): symbol, signal, sector, swing_score, ad_grade,
  buylevel, stoplevel, R/R, RSI, volume_surge%, market_stage, signal_date.
- Other 30+ fields available via row-expansion or via column picker.
- Sortable on every column.
- Filterable on signal/sector/grade/stage/timeframe.

---

## 8. API CONTRACT

### Response shapes (every endpoint)

**Single object**:
```json
{ "success": true, "data": {...}, "timestamp": "..." }
```

**Paginated list**:
```json
{ "success": true, "items": [...], "pagination": {...}, "timestamp": "..." }
```

**Error**:
```json
{ "success": false, "error": "...", "code": "...", "timestamp": "..." }
```

### Auth contract
- Every mutating route (`POST`/`PUT`/`PATCH`/`DELETE`) requires `Authorization: Bearer <jwt>`
- Already done: algo run/patrol/simulate/notifications-seen, backtests POST, contact admin
- Pending: 13 other route files (audit + apply)

### New endpoints needed
- `GET /api/sectors/:name/trend?days=...` — returns rank + daily_strength_score per day, with pre-computed MAs
- `GET /api/market/indices` — SPY/QQQ/IWM/DIA last + change + sparkline series
- `GET /api/market/distribution-days` — last 25 SPY sessions with classification
- `GET /api/market/breadth-history?days=...` — % > 50/200 DMA over time
- `GET /api/algo/swing-candidates?min_grade=B&limit=100` — pre-filtered list
- `GET /api/stock/:symbol/full` — everything-about-a-stock single endpoint for detail page

---

## 9. QUALITY GATES

### Performance
- Lighthouse target: ≥ 90 across all metrics on every page
- React.lazy + Suspense for route-level code split
- React Query for server state (in place)
- Virtualize tables > 200 rows
- Bundle: < 250 KB gzipped initial JS (currently 145KB)
- Image: lazy-loaded WebP

### Security
- Auth on every mutating route (audit pending for 13 files)
- CSP headers
- Rate limiting on `/api/algo/run` (max 1 per minute)
- No raw user HTML rendered without DOMPurify

### Accessibility (WCAG 2.2 AA)
- 4.5:1 body, 3:1 large-text contrast — verify every token pair
- Keyboard-navigable end-to-end
- Standalone icons get `aria-label`
- Charts get `<title>` + `<desc>`
- Color-coded data has non-color cue (sign / glyph / position)

### Mobile breakpoints
- xs ≤ 600px: single column, drawer-collapsed, tables → card-list
- sm 600-900: 2-col where reasonable
- md 900-1280: full layout, drawer fixed
- lg ≥ 1280: full + sidebars expand

### Data integrity (the user's hard rule)
- **NO mock data anywhere.** If real data isn't available, show EmptyState.
- **NO sample/placeholder values.** Use null + "—" for missing.
- Every chart must have data attribution (source) + freshness timestamp.
- Charts requiring recompute (e.g., daily strength MA) must come from API,
  not client-computed from incomplete window.

---

## 10. SCHEDULE

Realistic, given Monday open is in <17 hours.

### Tonight (Sunday)
- ✅ Plan doc (this file)
- Tailwind setup alongside MUI (no removal yet)
- Token bridge (one source for both)
- Convert `<Card>` primitive to Tailwind
- Polish Markets page (#B) one more pass with new tokens

### Monday
- Live observation (algo run, broken positions close at open)
- Convert `<Stat>`, `<Button>`, `<Input>` primitives
- Apply percentile + IBD-strip cleanup audit (any remaining sites)
- Trade Tracker pass with new tokens

### Tuesday
- Trading Signals page rebuild (Page E) — biggest data inventory
- Stock detail page skeleton (Page P)

### Wednesday
- Sectors page (Page C) with fixed RankingTrend + DailyStrength charts (§5.1, §5.2)
- Portfolio (Page G)

### Thursday
- Service Health (Page I)
- Economic / Sentiment / Commodities (Pages J, K, L) — they share Template A

### Friday
- Mobile responsive sweep (every page at xs/sm)
- Lighthouse pass — fix anything < 90
- Auth audit (13 remaining route files)
- Final polish

### Following week
- Drop MUI from `package.json` once all pages migrated
- Dark mode polish + system-pref detection
- Cmd-K command palette (Linear-style global nav)

---

## 11. DEFINITION OF DONE

A page is **done** only when **all** of these are true:

- [ ] Renders cleanly at 375px and 1280px without horizontal scroll
- [ ] Loads in < 1s on cached visit, < 2.5s cold
- [ ] Every data panel shows freshness timestamp + source attribution
- [ ] Every numeric column uses tabular figures
- [ ] Prices and percentages in IBM Plex Mono
- [ ] No raw color hex — only design tokens via `C` proxy or Tailwind class
- [ ] Loading state is a layout-preserving skeleton
- [ ] Error state has retry button + clear copy
- [ ] Empty state has icon + message + actionable CTA
- [ ] Color-coded data has non-color cue (sign, glyph, position)
- [ ] Keyboard-navigable end-to-end (tab order is sensible)
- [ ] Focus ring visible on every interactive element
- [ ] All standalone icons have `aria-label`
- [ ] Charts have `<title>` + `<desc>` for screen readers
- [ ] Auth-gated endpoints used where appropriate
- [ ] Any new endpoint follows success/error/items contract
- [ ] Tested in both light and dark theme
- [ ] No `console.log`, no commented-out code, no `TODO` left behind
- [ ] Renders the **algo factor inventory** items relevant to this page (per §6)
- [ ] If a chart was redesigned, the spec in §5 is followed exactly

---

## NOTES

This document supersedes:
- `MASTER_PLAN.md` (operations + workstream tracking — separate doc)
- `FRONTEND_DESIGN_SYSTEM.md` (now rolled into this)

When code conflicts with this doc, update the doc first, then change the code.
The doc is the contract.
