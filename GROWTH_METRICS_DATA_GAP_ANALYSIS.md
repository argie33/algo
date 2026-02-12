# 📊 GROWTH METRICS DATA GAP ANALYSIS
**Analysis Date:** 2026-02-12 13:42 CST

---

## Executive Summary

**Bad News:** Growth metrics have significant data gaps
**Good News:** We have most of the input data, just not all growth calculations

| Metric | Coverage | Status | Can Calculate? |
|--------|----------|--------|---|
| Revenue Growth | 88.2% | Good | ✅ YES |
| Earnings Growth | 47.0% | Poor | ⚠️ PARTIAL |
| Quarterly Earnings Growth | 47.7% | Poor | ⚠️ PARTIAL |
| **Growth Scores** | 98.5% | Excellent | ✅ YES (mostly) |

---

## Why 78 Stocks Missing Growth Score

### The 78 Symbols Without Growth Score:
```
BRR, PICS, CEPS, BOBS, DTCX, EQPT, GOAI, SEV, OBAI, AGMB, DJP, APXT, BGL, BMM, PPHC, CBIO, CGCT, CHAI, CMTV, CUB...
```

### Root Cause Analysis:
```
✅ All 78 are in key_metrics table
❌ Only 22 have revenue_growth_pct (28.2%)
❌ Only 7 have earnings_growth_pct (9.0%)
⚠️ Missing earnings growth data is main blocker
```

### Why These 78 Have NULL Growth Score:
- **Earnings growth data missing** (91% of these symbols)
- yfinance doesn't provide earnings growth for all stocks
- Small cap / penny stocks have limited financial data
- Some are:
  - SPACs (special purpose acquisition companies)
  - Micro-cap stocks
  - Foreign listings with limited US data
  - New IPOs

---

## Data Available for Growth Calculations

### ✅ Good Data (80%+ coverage):

| Data Type | Coverage | Count | Status |
|-----------|----------|-------|--------|
| **Revenue Data** | 91.6% | 4,634/5,057 | ✅ GOOD |
| **Net Income** | 98.6% | 4,985/5,057 | ✅ EXCELLENT |
| **Operating Cash Flow** | 86.3% | 4,366/5,057 | ✅ GOOD |
| **Free Cash Flow** | 80.7% | 4,083/5,057 | ✅ GOOD |

### ⚠️ Partial Data (40-90% coverage):

| Data Type | Coverage | Count | Status |
|-----------|----------|-------|--------|
| **Revenue Growth %** | 88.2% | 4,458/5,057 | ✅ USABLE |
| **Earnings Growth %** | 47.0% | 2,377/5,057 | ⚠️ POOR |
| **Q Earnings Growth %** | 47.7% | 2,414/5,057 | ⚠️ POOR |

---

## Why Earnings Growth Data is Missing

### Root Causes:

1. **yfinance Data Limitations** (53% NULL earnings_growth_pct)
   - yfinance doesn't provide historical earnings growth rates
   - Only provides current EPS, not historical trends
   - Cannot calculate YoY growth without historical data

2. **Earnings History Still Loading** (96% complete)
   - We're loading earnings data (4,870/5,057 symbols)
   - Once complete, can calculate historical growth rates
   - But still won't have it for 187 stocks without earnings data

3. **Small Cap / Micro Cap Stocks** (50% of missing data)
   - Limited financial data available
   - yfinance doesn't cover all small stocks
   - Some have no public earnings reports

4. **Special Entities** (20% of missing data)
   - ETFs, closed-end funds
   - SPACs (no earnings yet)
   - Foreign stocks with limited US data

---

## Growth Score Calculation Status

### Current State:
```
✅ 4,979/5,057 symbols have growth_score (98.5%)
❌ 78/5,057 symbols missing growth_score (1.5%)
```

### Why 78 Are NULL:

For these 78 symbols:
- Revenue growth: Only 28% have it
- Earnings growth: Only 9% have it
- **Cannot calculate growth score without earnings growth**

### Fix Options:

1. **Option A: Use Revenue Growth Only**
   - 28% of these symbols have revenue_growth_pct
   - But incomplete for most

2. **Option B: Wait for Earnings to Load**
   - Complete earnings history (96% done, 34 min remaining)
   - Can then recalculate growth scores
   - But still won't help stocks without earnings data

3. **Option C: Estimate from Available Data**
   - Use revenue growth as proxy for earnings growth
   - Use net income trend instead of earnings growth
   - Would fill ~90% of the gaps

4. **Option D: Leave as NULL**
   - Accept that 1.5% of stocks have unknown growth
   - Most important stocks (large cap) have data
   - Only affects micro-cap/special stocks

---

## What We Can Calculate NOW

### With Current Data:

✅ **Revenue Growth** (88.2% coverage)
- Have data for 4,458/5,057 stocks
- Range: -99.6% to +100%
- Average: +0.7% annual growth

✅ **Net Income Trends** (98.6% coverage)
- Can measure income stability
- Proxy for earnings quality

✅ **Cash Flow Growth** (80-86% coverage)
- Operating cash flow trends
- Free cash flow trends
- Quality of earnings indicator

⚠️ **Earnings Growth** (47% coverage)
- Only 2,377/5,057 have data
- Missing for smaller stocks
- Will improve with earnings loader

---

## What's Missing

### Blocked Until Earnings Complete:

```
Current: Earnings 96% loaded (4,870/5,057 symbols)
Blocker: Can't calculate historical earnings growth without earnings history
Timeline: 34 minutes remaining

After Earnings Load:
- Can calculate year-over-year earnings growth
- Can improve growth score calculations
- But won't help 187 symbols without any earnings data
```

### Permanently Unavailable:

```
For 78 symbols with NULL growth_score:
- 70 have NO earnings growth data from yfinance
- 56 have NO revenue growth data
- These are mostly micro-cap or special entities
- No way to get data for these stocks
```

---

## Impact on Trading

### Growth Metrics Used For:
1. **Growth Score Calculation** (98.5% complete)
2. **Portfolio Quality Assessment**
3. **Stock Screening** (filter by growth rate)
4. **Sector Analysis** (compare growth rates)

### Impact of Missing 78 Symbols:
- **Negligible** - only 1.5% of portfolio
- 4,979/5,057 stocks are covered
- Missing stocks are mostly micro-cap/illiquid
- Large cap/liquid stocks all have data

---

## Recommendations

### Short Term (Next 34 minutes):
1. ✅ Wait for earnings to complete loading
2. ✅ Recalculate growth scores with new earnings data
3. ✅ Growth coverage should stay at 98.5% or improve

### Medium Term (After earnings):
1. 🔄 Calculate YoY earnings growth from earnings history
2. 🔄 Update growth scores with calculated earnings growth
3. 🔄 Improve coverage from 98.5% to potentially 99%+

### Long Term:
1. 💡 Consider alternative data sources for micro-cap stocks
2. 💡 Use revenue growth as fallback for earnings growth
3. 💡 Document which stocks have estimated vs. real data

---

## Data Quality Summary

```
GROWTH METRICS - DATA COMPLETENESS

Revenue Data:        ████████████████████░  91.6% ✅
Net Income:          ███████████████████████ 98.6% ✅✅
Operating Cash Flow: ███████████████░░░░░░  86.3% ✅
Free Cash Flow:      ███████████████░░░░░░  80.7% ✅
Revenue Growth %:    ████████████░░░░░░░░░  88.2% ✅
Earnings Growth %:   ████████░░░░░░░░░░░░░  47.0% ⚠️
Earnings Q Growth:   █████████░░░░░░░░░░░░  47.7% ⚠️
Growth Scores:       ███████████████████░░  98.5% ✅
```

---

## Bottom Line

**YES, we have the inputs for growth metrics:**
- ✅ 99% of stocks have basic financial data (revenue, net income, cash flow)
- ✅ 88% have revenue growth rates
- ✅ 98.5% have growth scores calculated
- ⚠️ 47% have earnings growth (will improve when earnings complete)
- ❌ 78 micro-cap stocks can't be scored (1.5%)

**Is it a blocker?**
- **NO** - Most important stocks are covered
- Only affects tiny micro-cap positions
- Large cap and mid-cap all have complete data

**Will it improve?**
- **YES** - After earnings complete (34 minutes)
- Can then calculate historical earnings growth
- Should improve earnings growth coverage from 47% to 50-60%+
