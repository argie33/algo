# Trading Signals Page - Complete Audit Report

**Date:** 2026-05-09  
**Page:** `http://localhost:5173/app/trading-signals`

---

## I. API DATA SOURCES

### A. `/api/signals/stocks` (PRIMARY SIGNAL DATA)

**What it returns:** Pine script trading signals from `buy_sell_daily` table

**Available fields from API:**
- Basic: `id, symbol, signal, date, signal_triggered_date, timeframe`
- Price: `open, high, low, close, volume`
- Levels: `buylevel, stoplevel, strength, signal_strength, pivot_price, buy_zone_start, buy_zone_end`
- Exit targets: `exit_trigger_1/2/3/4_price`
- Stop levels: `initial_stop, trailing_stop, sell_level`
- Technical: `rsi, adx, atr, sma_50, sma_200, ema_21`
- Analysis: `base_type, base_length_days, signal_type, market_stage, breakout_quality`
- Scores: `entry_quality_score, risk_reward_ratio, mansfield_rs, sata_score, rs_rating`
- Volume: `avg_volume_50d, volume_surge_pct`
- Company: `company_name` (from `stock_symbols` JOIN)

**MISSING from API:**
- ❌ **SECTOR** (used in filters, KPI, table)
- ❌ **INDUSTRY** (used in table detail)
- ❌ **SWING_SCORE** (used for SQS column, quality filtering)
- ❌ **PASS_GATES** (used for gates column and filtering)
- ❌ **GRADE** (used for signal quality badge)

---

### B. `/api/algo/swing-scores?limit=2000&min_score=0` (SCORING/GATES DATA)

**What it returns:** Yesterday's swing scores from algo evaluation

**Available fields:**
- `symbol, eval_date, swing_score, grade`
- Component scores: `setup_pts, trend_pts, momentum_pts, volume_pts, fundamentals_pts, sector_pts, multi_tf_pts`
- `pass_gates, fail_reason, components, sector, industry`

**Timing issue:** Only has TODAY's scores (or yesterday's, depending on when algo ran)

---

### C. `/api/prices/history/{symbol}?timeframe=daily&limit=60` (PRICE HISTORY)

**What it returns:** 60 daily bars for forward return calculation

---

## II. FRONTEND DATA ENRICHMENT LOGIC

### Current enrichment (line 117-133):

```javascript
const enriched = useMemo(() => rows.map(r => {
  const g = gateMap.get(r.symbol);  // JOIN signals with swing-scores by symbol
  return {
    ...r,
    _age: daysSince(r.signal_triggered_date || r.date),
    _sqs: sqsOf(r) ?? (g?.swing_score ?? null),
    _pass_gates: g?.pass_gates ?? null,
    _grade: g?.grade ?? null,
    _fail_reason: g?.fail_reason ?? null,
  };
}), [rows, gateMap]);
```

**Problems:**
1. ✅ Correctly enriches with swing scores from gates data
2. ❌ **Does NOT add sector** - gate data has sector but it's never copied to enriched rows
3. ❌ **Does NOT add industry**
4. **Data freshness issue:** Swing scores are only evaluated once per day (evening). Page shows historical signals with TODAY's scores attached.

---

## III. DETAILED ISSUE BREAKDOWN

### **ISSUE #1: SECTOR DATA COMPLETELY MISSING**

**Impact:** HIGH - affects 5+ features

**Locations where sector is used:**
1. Line 79: `allSectors` calculation - tries to extract unique sectors
2. Line 309-331: Sector filter UI - won't work
3. Line 690: Table display - shows "—" instead of sector
4. Line 413: Heatmap tooltip - missing sector info
5. Line 130: `sectorFilter` logic - filters on missing data

**Root cause:** 
- Signals API doesn't return sector
- Frontend tries to use `r.sector` from raw signals data (doesn't exist)
- Swing-scores API DOES have sector but it's in `g.sector` and never copied to `r.sector`

**Expected behavior:** All signals should show sector (from gates data if not in signals)

**Fix needed:** Add `sector: g?.sector ?? null` to enrichment

---

### **ISSUE #2: KPI "Total Signals" SHOULD BE AFTER ENRICHMENT BUT BEFORE FILTERING**

**Current code (lines 159-178):**
```javascript
const kpi = useMemo(() => {
  const buys = filtered.filter(r => (r.signal || '').toUpperCase() === 'BUY');
  // ... uses filtered, not enriched
```

**Problem:** KPI counts match filtered results, not total available signals

**Expected:** Should show:
- Total signals available (all rows from API)
- BUY/SELL counts (from all available)
- Then show filtered counts separately OR label as "filtered"

**Example confusion:**
- User sees "Total Signals: 247" (after filters applied)
- But there might be 500 total if they cleared all filters
- Very confusing for data validation

---

### **ISSUE #3: CROSSING 50/200 MA CALCULATION IS UNCLEAR**

**Current logic (lines 162-175):**
```javascript
const cross50 = filtered.filter(r => {
  const c = Number(r.close);
  const ma = Number(r.sma_50);
  return !isNaN(c) && !isNaN(ma) && c > ma && c < ma * 1.02;
}).length;
```

**Questions:**
1. Is this detecting "currently near MA" or "recently crossed"?
2. Why 2% threshold? Should this be configurable?
3. Does this need prior bar data to detect actual crosses?

**Expected:** Should detect stocks actively crossing the MA, not just "close-ish to it"

**Current meaning:** "close is slightly above MA (within 2%)"

**Problem:** Very loose definition of "crossing"

---

### **ISSUE #4: RECENT PERFORMANCE CHART - DATA AVAILABILITY**

**Current calculation (lines 511-541):**
```javascript
const recentBuys = useMemo(() =>
  rows.filter(r =>
    (r.signal || '').toUpperCase() === 'BUY' &&
    r._age != null && r._age >= 5 && r._age <= 30 &&
    r.symbol && r.close != null
  ).slice(0, 40),  // ← Only uses 40 of possibly N signals
```

**Issues:**
1. ❌ Only samples first 40 signals
2. ❌ Fetches price history for only 25 of those 40
3. ❌ Requires AT LEAST 5 days old (why 5? why not 1?)
4. ❌ Requires AT MOST 30 days old (why 30? configurable?)
5. ❌ If price history fetch fails for a symbol, silently drops it

**Data loss in pipeline:**
- Say there are 150 BUY signals  
- Filters to 5-30d old: maybe 60 remain
- Takes first 40
- Fetches prices for 25
- Price fetch failures: maybe 5-10 fail silently
- Ends up with 15-20 actual data points

**Result:** Stats shown as "n=15" but user doesn't see the filtering pipeline

---

### **ISSUE #5: SQS SCORE NOT DISPLAYED/HIGHLIGHTED CORRECTLY**

**Current status:**
- ✅ Correctly joined from swing scores
- ✅ Correctly displayed in table
- ❌ **NOT used for coloring/highlighting in other contexts**
- ❌ **SQS Histogram** (line 583-634) only shows BUY signals with SQS

**Problem:** If a signal doesn't have a swing score yet (because:
  - Swing score algo hasn't run today
  - Symbol isn't evaluated by algo
  - Fresh signal from this morning
  
Then that row shows "no score" but still appears in table. That's correct. But there's no visual indication across the page about how many signals are missing scores.

---

### **ISSUE #6: BASE TYPE FILTER & DISPLAY INCONSISTENCY**

**Line 282-289:** Base type filter dropdown
```javascript
{allBaseTypes.length > 0 && (
  <select ... value={baseTypeFilter}>
    <option value="all">All base types</option>
    {allBaseTypes.map(bt => <option>{bt}</option>)}
  </select>
)}
```

**Problem:** If `base_type` is missing from API rows, dropdown is empty (no error, just silent)

**Current expected:** `base_type` exists in signals API response

**Verify:** Do all signals have base_type? Check sample response.

---

### **ISSUE #7: GATES DATA FRESHNESS**

**Current code:**
```javascript
const { data: gatesData } = useApiQuery(
  ['signals-gates'],
  () => api.get('/api/algo/swing-scores?limit=2000&min_score=0'),
  { refetchInterval: 120000, enabled: tab === 'stocks' }  // ← 2 min
);
```

**Issue:** Swing scores are evaluated once per day (evening), not per 2 minutes

**What happens:**
- Page loads at 2:47pm ET (before swing score run at 5:30pm ET)
- Shows "no score" for all signals
- User refreshes at 8pm ET (after swap to local time zone... wait, this is EDT/CDT)
- Actually this should be checking 5:30pm ET

**Real issue:** Page refreshes gate data every 2 minutes but algo only runs once daily

**Expected:** Should refetch gates data once after 5:30pm ET, then stop

---

### **ISSUE #8: PERFORMANCE CHART Y-AXIS MISLABELING**

**Line 254:**
```javascript
<RecentPerformance rows={enriched} timeframe={timeframe} />
```

But the performance chart doesn't show:
- What the calculation period is (5d backward vs forward?)
- ✅ Fixed in last commit but verify the label is clear

---

### **ISSUE #9: FILTER STATE NOT PRESERVED ON RELOAD**

**Current:** No URL parameters for filters
- User sets score range to 70-90, sector to "Tech"
- Refreshes page
- Filters reset to defaults

**Expected:** Could serialize filters to URL and restore

---

### **ISSUE #10: EMPTY STATES AND ERROR HANDLING**

**Several endpoints have no error handling:**
1. Price history fetch can fail silently
2. Gates data can be stale/missing
3. Signals API returns 500 error - shows generic "no data"

---

## IV. MISSING DATA SOURCES - ROOT CAUSE ANALYSIS

### Why is sector missing?

**Signals API chain:**
```
buy_sell_daily (has base_type, market_stage, entry_quality_score)
    ↓ LEFT JOIN
stock_symbols (has security_name as company_name)
    ↗ BUT NO SECTOR
```

**Solution:** Need to add sector from `company_profile` table

```sql
LEFT JOIN company_profile cp ON bsd.symbol = cp.ticker
  -- select cp.sector, cp.industry
```

### Why is swing_score sometimes missing?

**Timing:** Swing scores evaluated at 5:30pm ET daily
- Morning signals don't have scores yet
- But page shows them anyway (correct behavior)
- User sees "no score" badge

**Expected:** This is OK, but should be clearly labeled

---

## V. CALCULATION VERIFICATION NEEDED

### KPI - BUY/SELL Ratio Calculation

```javascript
ratio: sells.length === 0 ? '∞' : (buys.length / sells.length).toFixed(2),
```

**Question:** Is this correctly filtered?
- If user filters to just symbols starting with "A"
- Ratio should be for those filtered symbols only
- **Need to verify** this is using `filtered`, not raw `rows`

Currently uses `filtered` ✅

---

### Fresh Signals (≤3 days old)

```javascript
const fresh = buys.filter(r => {
  const age = Number(r._age);
  return !isNaN(age) && age != null && age >= 0 && age <= 3;
}).length;
```

**Issue:** What's the base date?
- Signal date? ✅ (`_age: daysSince(r.signal_triggered_date || r.date)`)
- When was data loaded? Unclear

**Expected:** Based on signal_triggered_date vs today

---

### High Quality Buys (SQS > 80)

```javascript
const hq = buys.filter(r => {
  const sqs = Number(r._sqs);
  return !isNaN(sqs) && sqs != null && sqs > 80;
}).length;
```

**Issue:** Only counts BUYs with scores > 80

**What if:** A BUY doesn't have a score yet?
- Not counted as HQ ✓
- Not counted as quality-unknown ✗ (silently dropped)

---

## VI. DATA INTEGRITY ISSUES

### Null/NaN Handling

**Status after last commit:**
- ✅ Added isNaN checks in KPI calculations
- ✅ Added isNaN checks in numeric displays
- ✅ Don't drop rows for missing SQS

**Remaining gaps:**
- No validation that API responded with expected schema
- No check that enrichment actually worked (gateMap empty?)
- No check that row.close, row.sma_50, etc. exist before using

---

### Calculation Dependencies

**Example:** If `sma_50` is null:
- Crossing50 count = 0 (correct)
- But table still displays row (correct)
- Row shows "—" in SMA column (correct)
- No warning that this row is missing a key indicator

---

## VII. UI/UX CLARITY ISSUES

1. ❌ "Total Signals" includes filters (confusing - should show available vs displayed)
2. ❌ "Fresh BUYs" - is this BUYs from last 3 days or yesterday?
3. ❌ "Crossing 50-day" - very loose definition, might think actual crosses
4. ❌ Score range slider - default 0-100 doesn't filter, but label says "SQS range"
5. ❌ "Passes algo gates" checkbox - but gate data might be yesterday's
6. ❌ Recent Performance - sample size hidden (shows n=15 small)
7. ❌ SQS histogram - red/amber/green colors but no legend explaining cutoffs

---

## VIII. PERFORMANCE ISSUES

1. Fetches 2000 swing scores but only uses ~100
2. Fetches price history for 25 symbols sequentially (should be parallel, already is ✓)
3. Maps gates data in memory on every render (gateMap correctly memoized ✓)

---

## SUMMARY OF ALL ISSUES

| # | Severity | Issue | Impact | Status |
|---|----------|-------|--------|--------|
| 1 | HIGH | Sector data missing completely | Filters broken, table incomplete | NOT FIXED |
| 2 | HIGH | Industry missing from display | Table detail shows "—" | NOT FIXED |
| 3 | MEDIUM | KPI counts misleading (show filtered, not total) | User confusion | NOT FIXED |
| 4 | MEDIUM | Recent Performance calc limits (sample size) | Stats unreliable | NOT FIXED |
| 5 | MEDIUM | Crossing MA definition too loose | False positives | UNCLEAR |
| 6 | MEDIUM | Gates data refresh interval wrong | Stale data displayed | NOT FIXED |
| 7 | MEDIUM | Base type filter might be empty | Silent failure | NOT VERIFIED |
| 8 | LOW | No filter state preservation in URL | UX - minor | DESIGN CHOICE |
| 9 | LOW | Price history failures silent | Error handling gap | PARTIAL |
| 10 | LOW | SQS threshold for HQ buys unexplained | 80 = quality bar? | DESIGN CHOICE |

---

## ROOT CAUSE SUMMARY

**Primary Issues:**
1. **Sector/Industry not in signals API** → must add JOIN to company_profile
2. **Gate data too fresh** → need to join on same date as signals, not latest date
3. **KPI counting filtered instead of total** → confuses data validation
4. **Performance chart decimates sample** → reduces statistical validity
5. **API response schema not documented** → frontend guessing what fields exist

**Next Steps:**
1. Fix signals API to include sector/industry
2. Fix gate enrichment to use signal_date, not latest eval_date
3. Add total count KPI separate from filtered count
4. Increase performance chart sample size or show full sample
5. Document exact field names and null handling in API

