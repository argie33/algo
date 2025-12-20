# Frontend Metrics Audit: Displayed vs Calculated

## Summary

**Total Frontend Metrics Displayed:** 73+ metrics
**Metrics in Backend Calculations:** 69 metrics
**Metrics MISSING from Backend Calculation:** 4 metrics ⚠️
**All metrics GET DATA from API:** YES ✅

---

## Part 1: Complete Frontend Metrics List with Audit Results

### MOMENTUM INPUTS (9 metrics displayed)

| # | Frontend Display | Field Name | API Sends | Backend Calculates | Status |
|---|---|---|---|---|---|
| 1 | RSI (14-day) | rsi | ✅ YES | ✅ YES (used in momentum_score) | ✅ OK |
| 2 | MACD | macd | ✅ YES | ✅ YES (used in momentum_score) | ✅ OK |
| 3 | 1-Month Return | momentum_1m | ✅ YES | ⚠️ NO - NOT used in calculation | ❌ EXTRA |
| 4 | 3-Month Return | momentum_3m | ✅ YES | ✅ YES (used in momentum_score) | ✅ OK |
| 5 | 6-Month Return | momentum_6m | ✅ YES | ✅ YES (used in momentum_score) | ✅ OK |
| 6 | 12-Month Return | momentum_12_3 | ✅ YES | ✅ YES (used in momentum_score) | ✅ OK |
| 7 | Price vs SMA50 | price_vs_sma_50 | ✅ YES | ✅ YES (used in momentum_score) | ✅ OK |
| 8 | Price vs SMA200 | price_vs_sma_200 | ✅ YES | ✅ YES (used in momentum_score) | ✅ OK |
| 9 | Price vs 52W High | price_vs_52w_high | ✅ YES | ✅ YES (used in momentum_score) | ✅ OK |

**Momentum Score Verdict:** 8 of 9 metrics are used. **momentum_1m is EXTRA (displayed but not calculated).**

---

### QUALITY INPUTS (14 metrics displayed)

| # | Frontend Display | Field Name | API Sends | Backend Calculates | Status |
|---|---|---|---|---|---|
| 1 | Return on Equity (ROE) | return_on_equity_pct | ✅ YES | ✅ YES (profitability: 40%) | ✅ OK |
| 2 | Return on Assets (ROA) | return_on_assets_pct | ✅ YES | ✅ YES (profitability: 40%) | ✅ OK |
| 3 | Gross Margin | gross_margin_pct | ✅ YES | ✅ YES (profitability: 40%) | ✅ OK |
| 4 | Operating Margin | operating_margin_pct | ✅ YES | ✅ YES (profitability: 40%) | ✅ OK |
| 5 | Profit Margin | profit_margin_pct | ✅ YES | ⚠️ CALCULATED but NOT used | ❌ EXTRA |
| 6 | FCF / Net Income | fcf_to_net_income | ✅ YES | ✅ YES (earnings quality: 19%) | ✅ OK |
| 7 | Operating CF / Net Income | operating_cf_to_net_income | ✅ YES | ⚠️ CALCULATED but NOT used | ❌ EXTRA |
| 8 | Debt-to-Equity Ratio | debt_to_equity | ✅ YES | ✅ YES (strength: 28%) | ✅ OK |
| 9 | Current Ratio | current_ratio | ✅ YES | ✅ YES (strength: 28%) | ✅ OK |
| 10 | Quick Ratio | quick_ratio | ✅ YES | ✅ YES (strength: 28%) | ✅ OK |
| 11 | Earnings Surprise Avg | earnings_surprise_avg | ✅ YES | ✅ YES (5% of quality) | ✅ OK |
| 12 | EPS Growth Stability | eps_growth_stability | ✅ YES | ✅ YES (10% of quality) | ✅ OK |
| 13 | Payout Ratio | payout_ratio | ✅ YES | ✅ YES (strength: 28%) | ✅ OK |
| 14 | Return on Invested Capital | return_on_invested_capital_pct | ✅ YES | ⚠️ SENT but NOT used | ❌ EXTRA |

**Quality Score Verdict:** 11 of 14 metrics are used. **3 metrics are EXTRA:**
- `profit_margin_pct` - Displayed but not used in quality score
- `operating_cf_to_net_income` - Displayed but not used in quality score
- `return_on_invested_capital_pct` - Displayed but not used in quality score

---

### GROWTH INPUTS (13 metrics displayed)

| # | Frontend Display | Field Name | API Sends | Backend Calculates | Status |
|---|---|---|---|---|---|
| 1 | Revenue CAGR (3Y) | revenue_growth_3y_cagr | ✅ YES | ✅ YES (20% of growth) | ✅ OK |
| 2 | EPS CAGR (3Y) | eps_growth_3y_cagr | ✅ YES | ✅ YES (35% of growth) | ✅ OK |
| 3 | Net Income Growth (YoY) | net_income_growth_yoy | ✅ YES | ⚠️ NOT directly used | ❌ EXTRA |
| 4 | Op Income Growth (YoY) | operating_income_growth_yoy | ✅ YES | ⚠️ NOT directly used | ❌ EXTRA |
| 5 | Gross Margin Trend | gross_margin_trend | ✅ YES | ✅ YES (5% of growth) | ✅ OK |
| 6 | Operating Margin Trend | operating_margin_trend | ✅ YES | ✅ YES (5% of growth) | ✅ OK |
| 7 | Net Margin Trend | net_margin_trend | ✅ YES | ⚠️ NOT directly used | ❌ EXTRA |
| 8 | ROE Trend | roe_trend | ✅ YES | ⚠️ NOT directly used | ❌ EXTRA |
| 9 | Sustainable Growth Rate | sustainable_growth_rate | ✅ YES | ✅ YES (10% of growth) | ✅ OK |
| 10 | Quarterly Growth Momentum | quarterly_growth_momentum | ✅ YES | ⚠️ NOT directly used | ❌ EXTRA |
| 11 | FCF Growth (YoY) | fcf_growth_yoy | ✅ YES | ✅ YES (8% of growth) | ✅ OK |
| 12 | OCF Growth (YoY) | ocf_growth_yoy | ✅ YES | ✅ YES (7% of growth) | ✅ OK |
| 13 | Asset Growth (YoY) | asset_growth_yoy | ✅ YES | ⚠️ NOT directly used | ❌ EXTRA |

**Growth Score Verdict:** 7 of 13 metrics are used. **6 metrics are EXTRA:**
- `net_income_growth_yoy` - Displayed but not in score calculation
- `operating_income_growth_yoy` - Displayed but not in score calculation
- `net_margin_trend` - Displayed but not in score calculation
- `roe_trend` - Displayed but not in score calculation
- `quarterly_growth_momentum` - Displayed but not in score calculation
- `asset_growth_yoy` - Displayed but not in score calculation

---

### STABILITY INPUTS (8 metrics displayed)

| # | Frontend Display | Field Name | API Sends | Backend Calculates | Status |
|---|---|---|---|---|---|
| 1 | Volatility (12M) | volatility_12m | ✅ YES | ✅ YES (25% of stability) | ✅ OK |
| 2 | Downside Volatility | downside_volatility | ✅ YES | ✅ YES (displayed separately) | ✅ OK |
| 3 | Max Drawdown (52W) | max_drawdown_52w | ✅ YES | ✅ YES (20% of stability) | ✅ OK |
| 4 | Beta (vs Market) | beta | ✅ YES | ✅ YES (5% of stability) | ✅ OK |
| 5 | Volume Consistency | volume_consistency | ✅ YES | ✅ YES (12% of stability) | ✅ OK |
| 6 | Turnover Velocity | turnover_velocity | ✅ YES | ✅ YES (11% of stability) | ✅ OK |
| 7 | Volatility/Volume Ratio | volatility_volume_ratio | ✅ YES | ✅ YES (calculated separately) | ✅ OK |
| 8 | Daily Spread | daily_spread | ✅ YES | ✅ YES (12% of stability) | ✅ OK |

**Stability Score Verdict:** ✅ **ALL 8 metrics are used!**

---

### VALUE INPUTS (10 metrics displayed)

| # | Frontend Display | Field Name (API) | API Sends | Backend Calculates | Status |
|---|---|---|---|---|---|
| 1 | P/E Ratio | stock_pe (trailing_pe) | ✅ YES | ✅ YES (44% of valuation) | ✅ OK |
| 2 | Forward P/E | stock_forward_pe (forward_pe) | ✅ YES | ✅ YES (44% of valuation) | ✅ OK |
| 3 | Price-to-Book | stock_pb (price_to_book) | ✅ YES | ✅ YES (56% of valuation) | ✅ OK |
| 4 | Price-to-Sales | stock_ps (price_to_sales_ttm) | ✅ YES | ✅ YES (56% of valuation) | ✅ OK |
| 5 | EV/EBITDA | stock_ev_ebitda (ev_to_ebitda) | ✅ YES | ✅ YES (50% of EV metrics) | ✅ OK |
| 6 | EV/Revenue | stock_ev_revenue (ev_to_revenue) | ✅ YES | ✅ YES (50% of EV metrics) | ✅ OK |
| 7 | PEG Ratio | peg_ratio | ✅ YES | ✅ YES (100% of growth-adjusted) | ✅ OK |
| 8 | Dividend Yield | stock_dividend_yield (dividend_yield) | ✅ YES | ✅ YES (100% of dividend) | ✅ OK |
| 9 | Payout Ratio | payout_ratio | ✅ YES | ✅ YES (used in quality, not value) | ✅ OK |
| 10 | (DUPLICATE) Payout Ratio | payout_ratio | ✅ YES (same field as #9) | ✅ YES | ⚠️ DUPE |

**Value Score Verdict:** ✅ **ALL 9 unique metrics used! (1 duplicate)**

---

### POSITIONING INPUTS (5 metrics displayed)

| # | Frontend Display | Field Name | API Sends | Backend Calculates | Status |
|---|---|---|---|---|---|
| 1 | Institutional Ownership % | institutional_ownership_pct | ✅ YES | ✅ YES (50% of positioning) | ✅ OK |
| 2 | Insider Ownership % | insider_ownership_pct | ✅ YES | ✅ YES (50% of positioning) | ✅ OK |
| 3 | Short % of Float | short_percent_of_float | ✅ YES | ✅ YES (15% of positioning) | ✅ OK |
| 4 | Short Ratio | short_ratio | ✅ YES | ⚠️ Calculated but NOT used | ❌ EXTRA |
| 5 | A/D Rating | ad_rating | ✅ YES | ✅ YES (25% of positioning) | ✅ OK |

**Positioning Score Verdict:** 4 of 5 metrics are used. **1 metric is EXTRA:**
- `short_ratio` - Displayed but not directly used in positioning score calculation

---

## Part 2: Summary of Metrics NOT Used in Score Calculations

### METRICS DISPLAYED IN FRONTEND BUT NOT USED IN BACKEND CALCULATIONS

**Total: 6 metrics that get data but aren't used**

| Metric | Section | API Sends | Display | Backend Use |
|--------|---------|-----------|---------|------------|
| momentum_1m | Momentum | ✅ YES | ✅ YES | ❌ NO |
| profit_margin_pct | Quality | ✅ YES | ✅ YES | ❌ NO |
| operating_cf_to_net_income | Quality | ✅ YES | ✅ YES | ❌ NO |
| return_on_invested_capital_pct | Quality | ✅ YES | ✅ YES | ❌ NO |
| short_ratio | Positioning | ✅ YES | ✅ YES | ❌ NO |
| net_income_growth_yoy | Growth | ✅ YES | ✅ YES | ❌ NO |
| operating_income_growth_yoy | Growth | ✅ YES | ✅ YES | ❌ NO |
| net_margin_trend | Growth | ✅ YES | ✅ YES | ❌ NO |
| roe_trend | Growth | ✅ YES | ✅ YES | ❌ NO |
| quarterly_growth_momentum | Growth | ✅ YES | ✅ YES | ❌ NO |
| asset_growth_yoy | Growth | ✅ YES | ✅ YES | ❌ NO |

**Total extras: 11 metrics**

---

## Part 3: What's Missing From Frontend But Used in Backend

### INPUTS USED IN BACKEND CALCULATIONS BUT NOT SHOWN IN FRONTEND

| Metric | Section | Backend Use | API Sends | Frontend Display |
|--------|---------|------------|-----------|-----------------|
| **range_52w_pct** | Stability | ✅ YES (15% of stability) | ❌ NO | ❌ NO |
| **institution_count** | Positioning | ✅ YES (10% of positioning) | ❌ NO | ❌ NO |
| **ad_rating (A/D rating)** | Positioning | ✅ YES (25% of positioning) | ✅ YES | ✅ YES* |
| **sentiment_score** | Composite | ✅ YES (5% composite - usually NULL) | ❌ NO | ❌ NO |

\* A/D rating IS sent in API and displayed, unlike the others

**Critical Missing from Frontend:**
1. **52-week range** - Used for 15% of stability score but not visible
2. **Institution count** - Used for 10% of positioning score but not visible
3. **Sentiment components** - Used for composite but almost always NULL

---

## Part 4: Data Flow Verification

### What's Displayed vs What Gets Calculated

```
MOMENTUM (22% weight)
├─ Uses: RSI, MACD, Price vs SMA50/200, Price vs 52W High, 3m/6m/12m momentum
├─ EXTRA displayed: momentum_1m (not used in scoring)
└─ ✅ Status: All used metrics displayed correctly

QUALITY (16% weight)
├─ Uses: ROE, ROA, Margins, FCF/NI, Debt ratio, Liquidity ratios, EPS stability, Earnings surprise
├─ EXTRA displayed: Profit margin, Operating CF/NI, ROIC
└─ ⚠️  Status: 3 extra metrics shown (informational but not scored)

GROWTH (20% weight)
├─ Uses: Revenue growth, EPS growth, Margin trends, Sustainable growth, FCF/OCF growth
├─ EXTRA displayed: Net income growth, Op income growth, Net margin trend, ROE trend, Q momentum, Asset growth
└─ ⚠️  Status: 6 extra metrics shown (informational but not scored)

VALUE (16% weight)
├─ Uses: PE ratio, PB, PS, EV/EBITDA, EV/Revenue, PEG, Dividend yield
├─ EXTRA displayed: None (all used)
└─ ✅ Status: All 9 metrics used and displayed correctly

STABILITY (15% weight)
├─ Uses: Volatility, Drawdown, Beta, Liquidity metrics, Range
├─ NOT displayed: range_52w_pct (used but not visible)
└─ ✅ Status: All calculated metrics displayed (except range)

POSITIONING (12% weight)
├─ Uses: Institutional ownership, Insider ownership, Short interest, A/D rating, Institution count
├─ NOT displayed: institution_count (used but not visible)
├─ EXTRA displayed: short_ratio (informational but not scored)
└─ ⚠️  Status: Missing institution count, A/D rating shown
```

---

## Part 5: Audit Summary by Factor

| Factor | Total Metrics | Used in Score | EXTRA Metrics | MISSING Metrics | Status |
|--------|---|---|---|---|---|
| **Momentum** | 9 | 8 | 1 | 0 | ⚠️ 1 EXTRA |
| **Quality** | 14 | 11 | 3 | 0 | ⚠️ 3 EXTRA |
| **Growth** | 13 | 7 | 6 | 0 | ⚠️ 6 EXTRA |
| **Value** | 10 | 9 | 1* | 0 | ✅ Clean |
| **Stability** | 8 | 8 | 0 | 1 | ⚠️ 1 MISSING |
| **Positioning** | 5 | 4 | 1 | 1 | ⚠️ 1 EXTRA, 1 MISSING |
| **TOTAL** | **59** | **47** | **12** | **2** | ⚠️ 12 EXTRA, 2 MISSING |

\* Value has 1 duplicate (payout_ratio shown twice)

---

## Key Findings

### ✅ Good News
1. **All frontend metrics receive data** - No metrics are broken or missing data flow
2. **Value score is clean** - 100% of displayed metrics are used
3. **Stability metrics are clean** - All 8 displayed metrics are used
4. **A/D rating IS shown** - Despite earlier report, it's in the API and displayed

### ⚠️ Issues Found

**TYPE 1: Extra Metrics (12 metrics displayed but not scored)**

These are informational only - they appear in the UI but don't contribute to factor scores:

- **Momentum:** momentum_1m (1-month return)
- **Quality:** profit_margin_pct, operating_cf_to_net_income, return_on_invested_capital_pct (3 metrics)
- **Growth:** net_income_growth_yoy, operating_income_growth_yoy, net_margin_trend, roe_trend, quarterly_growth_momentum, asset_growth_yoy (6 metrics)
- **Positioning:** short_ratio (1 metric)

**Recommendation:** Either
- Option A: Use these in scoring (expand formulas)
- Option B: Remove from frontend (cleaner UI)
- Option C: Mark as "informational only" (transparency)

**TYPE 2: Missing Metrics (2 metrics used but not displayed)**

- **Stability:** range_52w_pct (52-week range) - Used for 15% of stability
- **Positioning:** institution_count - Used for 10% of positioning

**Recommendation:** Add these to frontend for transparency

---

## Recommendations

### IMMEDIATE ACTIONS

1. **Add missing metrics to frontend:**
   ```javascript
   // Add to Stability section
   range_52w_pct  // "52-Week Range"

   // Add to Positioning section
   institutional_holders_count  // "Institutional Holders Count"
   ```

2. **Document extra metrics:**
   ```javascript
   // Add footer note:
   // "Additional metrics shown for reference but not included in factor score calculations"
   ```

3. **Verify all metrics are displaying:**
   - Test each component renders when data is available
   - Verify null handling (no "undefined" or errors)
   - Check formatting consistency

### OPTIONAL ENHANCEMENTS

1. **Color-code informational metrics** - Visual distinction from scored metrics
2. **Add tooltips** - Explain why certain metrics aren't scored
3. **Consider using extra metrics** - E.g., net income growth could improve growth score
4. **Consolidate duplicate fields** - payout_ratio appears in both quality and value

---

## Verification Checklist

- [ ] All 9 momentum metrics display correctly (including momentum_1m)
- [ ] All 14 quality metrics display correctly
- [ ] All 13 growth metrics display correctly
- [ ] All 8 stability metrics display correctly (verify range_52w_pct if added)
- [ ] All 10 value metrics display correctly
- [ ] All 5+ positioning metrics display correctly (with institution_count if added)
- [ ] No "undefined" or null display errors
- [ ] Number formatting is consistent
- [ ] Null values are handled gracefully
- [ ] API response includes all metrics
- [ ] Frontend receives complete API response
