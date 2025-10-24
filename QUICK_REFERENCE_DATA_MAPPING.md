# Quick Reference: Stock Score Components Data Mapping

## Component Status Summary

```
┌─────────────────┬─────────┬──────────────────────────────────┬──────────────┐
│ Component       │ Status  │ Data Table                       │ Coverage     │
├─────────────────┼─────────┼──────────────────────────────────┼──────────────┤
│ QUALITY SCORE   │ ⚠️ PART │ quality_metrics (13 metrics)     │ 60-70%       │
│ GROWTH SCORE    │ ⚠️ PART │ growth_metrics (13 metrics)      │ 50-60%       │
│ VALUE SCORE     │ ⚠️ PART │ value_metrics (4 metrics)        │ 30-40%       │
│ MOMENTUM SCORE  │ ⚠️ PART │ momentum_metrics (31 metrics)    │ 40-50%       │
│ POSITIONING     │ ✅ GOOD │ positioning_metrics (36 metrics) │ 80-90%       │
└─────────────────┴─────────┴──────────────────────────────────┴──────────────┘
```

---

## Data Source Dependency Map

```
PRIMARY DATA SOURCES:
├─ key_metrics (yfinance)
│  ├→ QUALITY: profitability, balance sheet, payout ratio
│  ├→ GROWTH: revenue growth, earnings growth, ROE
│  ├→ VALUE: P/E, P/B, EV/EBITDA, PEG ratios
│  └─ STATUS: ⚠️ ~60-70% populated
│
├─ Quarterly Financial Tables (yfinance)
│  ├─ quarterly_income_statement
│  │  └─ GROWTH: operating income, net income, margin trends
│  ├─ quarterly_cash_flow  
│  │  └─ GROWTH: FCF growth YoY
│  ├─ quarterly_balance_sheet
│  │  └─ GROWTH: asset growth
│  └─ STATUS: ❌ ~15-25% populated (15-30% stocks have 5+ quarters)
│
├─ earnings_metrics (SEC filings)
│  └─ QUALITY: earnings surprise, EPS growth stability
│  └─ STATUS: ⚠️ ~40-50% populated
│
├─ earnings_history (YCharts/SEC)
│  └─ GROWTH: EPS growth, MOMENTUM: earnings acceleration
│  └─ STATUS: ⚠️ ~40-50% populated
│
├─ revenue_estimates (analyst consensus)
│  └─ GROWTH: revenue growth estimate
│  └─ STATUS: ⚠️ ~35-45% populated
│
└─ yfinance API (live)
   ├─ MOMENTUM: 31 metrics (price history, volume, analyst data)
   │  └─ STATUS: ✅ ~95%+ populated (price momentum)
   └─ POSITIONING: 36 metrics (ownership, insider, options, short)
      └─ STATUS: ✅ ~70-90% populated

```

---

## Metric Coverage by Component

### 1. QUALITY SCORE (13 Metrics)

```
✅ Available (60-70% of stocks):
  • ROE, ROA, Gross/Operating/Net Margins
  • Debt/Equity, Current Ratio, Quick Ratio
  • Payout Ratio

⚠️ Partial (40-50% coverage):
  • Earnings Surprise (requires earnings_metrics)
  • EPS Growth Stability (requires earnings_metrics)

❌ Missing:
  • Historical ROE/ROA trends (not available)
  • Earnings quality from earnings_metrics (table often empty)
```

**Primary Issue:** earnings_metrics table rarely populated

---

### 2. GROWTH SCORE (13 Metrics)

```
✅ Available (50-60% of stocks):
  • Revenue Growth YoY
  • EPS Growth YoY
  • Sustainable Growth Rate

⚠️ Partial (40-50% coverage):
  • Operating Income Growth YoY (requires quarterly data)
  • Net Income Growth YoY (requires quarterly data)
  • FCF Growth YoY (requires quarterly data)
  • Margin Trends (requires quarterly data)
  • Quarterly Growth Momentum (requires quarterly data)
  • Asset Growth YoY (requires quarterly data)

❌ Missing (15-25% stocks have data):
  • quarterly_income_statement - only 15-25% populated
  • quarterly_cash_flow - only 15-25% populated
  • quarterly_balance_sheet - only 15-25% populated

Note: "3Y CAGR" metrics actually use 1Y growth rates (mislabeled)
```

**Primary Issue:** Quarterly financial tables severely underpopulated

---

### 3. VALUE SCORE (4 Metrics + 0 Advanced)

```
✅ Available (40-50% of stocks):
  • P/E Ratio
  • P/B Ratio
  • EV/EBITDA Ratio
  • PEG Ratio (15-25% coverage)

❌ Missing (0% coverage):
  • DCF Intrinsic Value (requires 5Y projections, WACC)
  • Relative Valuation vs Sector (requires sector medians)
  • Dividend Yield
  • Fair Value Estimate
  • Historical Price Targets

Additional data needed for DCF:
  • 5-year historical FCF (not stored)
  • Terminal growth rate assumption
  • Risk-free rate
  • WACC calculation components
```

**Primary Issue:** No forward-looking valuation, only static multiples

---

### 4. MOMENTUM SCORE (31 Metrics)

```
✅ Price Momentum (95%+ coverage):
  • Jegadeesh-Titman 12-1 Month (academic standard)
  • Risk-Adjusted Momentum (Sharpe, Sortino)
  • Multi-horizon momentum (1W, 1M, 3M, 6M, 12M variants)
  • Volume-based momentum (4 metrics)
  • Momentum quality metrics (6 metrics)
  • Momentum acceleration

⚠️ Fundamental Momentum (40-60% coverage):
  • Analyst recommendations
  • Price targets
  • Expected EPS growth
  • Earnings momentum (requires earnings_history)

❌ Missing:
  • Option Greeks (gamma_exposure, vega)
  • Implied volatility trend
```

**Primary Issue:** Great price momentum, sparse fundamental momentum

---

### 5. POSITIONING SCORE (36 Metrics)

```
✅ Strong Coverage (65-90% of stocks):
  • Institutional Ownership % & Holders Count (70%)
  • Insider Ownership % & Trading Activity (55-60%)
  • Put/Call Ratio & Options Sentiment (80%)
  • Short Interest % & Squeeze Score (75%)
  • Smart Money Score (calculated from institutions)
  • Insider Sentiment Score (calculated)
  • Options Sentiment (calculated)

⚠️ Simulated (100% coverage but estimated):
  • Institutional flows (calculated from price)
  • Institutional quality score (classified by fund name)
  • Borrow rates (estimated from short %)
  • Unusual options activity (estimated)

❌ Advanced Metrics Not Calculated:
  • Historical 13F flow changes
  • Gamma exposure
  • Options skew

**Primary Advantage:** Complete coverage (no missing sources), mostly direct from yfinance
```

---

## Critical Data Gaps

### 🔴 BLOCKING ISSUES (Prevent Score Calculation)

#### 1. Missing Quarterly Financial Data
- **Impact:** Can't calculate 50% of GROWTH metrics
- **Affected:** operating_income_growth_yoy, net_income_growth_yoy, fcf_growth_yoy, margin trends
- **Loader:** loadquarterlyincomestatement.py, loadquarterlycashflow.py exist but data sparse
- **Solution:** Run loaders on full schedule, verify yfinance data availability

#### 2. Missing Earnings Metrics
- **Impact:** Can't calculate QUALITY earnings quality metrics
- **Affected:** earnings_surprise_avg, eps_growth_stability
- **Loader:** loadearningsmetrics.py exists but earnings_metrics table empty
- **Solution:** Populate earnings_metrics from SEC filings or earnings API

#### 3. No DCF Valuation
- **Impact:** VALUE score lacks forward-looking component
- **Affected:** dcf_fair_value, intrinsic_value
- **Requires:** 5-year FCF projections, WACC, terminal growth
- **Solution:** Implement simplified DCF or use external valuation data

---

### ⚠️ COVERAGE ISSUES (Partial Coverage)

#### 1. key_metrics Gaps
- **Coverage:** ~60-70% of stocks have complete data
- **Problem:** yfinance doesn't provide all fields for all stocks
- **Workaround:** Accept NULL values, weight available metrics

#### 2. Quarterly Data Incomplete
- **Coverage:** ~15-25% of stocks have 5+ quarters
- **Problem:** Not all stocks file quarterly reports (many are private or delisted)
- **Workaround:** Skip quarterly-dependent metrics if not available

#### 3. Analyst Data Biased
- **Coverage:** ~60% of large caps, <20% of small caps
- **Problem:** Analysts don't cover unpopular/small stocks
- **Workaround:** Use analyst data only for large cap weighting

---

## Data Population Status Checks

### Query: Quality Score Data Availability
```sql
SELECT 
    COUNT(*) as total_rows,
    COUNT(return_on_equity_pct) as has_roe,
    COUNT(debt_to_equity) as has_de,
    COUNT(earnings_surprise_avg) as has_earnings_surprise
FROM quality_metrics
WHERE date = CURRENT_DATE;
```

### Query: Growth Score Data Availability
```sql
SELECT 
    COUNT(*) as total_rows,
    COUNT(revenue_growth_3y_cagr) as has_revenue_growth,
    COUNT(operating_income_growth_yoy) as has_op_income_yoy,
    COUNT(fcf_growth_yoy) as has_fcf_yoy,
    COUNT(gross_margin_trend) as has_margin_trend
FROM growth_metrics
WHERE date = CURRENT_DATE;
```

### Query: Quarterly Data Availability
```sql
SELECT 
    symbol,
    COUNT(*) as quarter_count,
    COUNT(DISTINCT item_name) as metrics_count
FROM quarterly_income_statement
GROUP BY symbol
HAVING COUNT(*) >= 5
ORDER BY quarter_count DESC;
```

---

## Loader Scripts & Execution

| Component | Loader Script | Table | Exec Frequency | Status |
|-----------|---------------|-------|-----------------|--------|
| QUALITY | loadqualitymetrics.py | quality_metrics | Daily | ⚠️ Check if running |
| GROWTH | loadgrowthmetrics.py | growth_metrics | Daily | ⚠️ Check if running |
| VALUE | loadvaluemetrics.py | value_metrics | Daily | ⚠️ Check if running |
| MOMENTUM | loadmomentum.py | momentum_metrics | Daily | ⚠️ Check if running |
| POSITIONING | loadpositioning.py | positioning_metrics | Daily | ⚠️ Check if running |
| — | loadkeymetrics.py | key_metrics | Daily | ⚠️ Critical: Check |
| — | loadquarterlyincomestatement.py | quarterly_income_statement | Weekly | ❌ Likely not running |
| — | loadquarterlycashflow.py | quarterly_cash_flow | Weekly | ❌ Likely not running |
| — | loadquarterlybalancesheet.py | quarterly_balance_sheet | Weekly | ❌ Likely not running |
| — | loadearningshistory.py | earnings_history | Daily | ⚠️ Check if running |
| — | loadearningsmetrics.py | earnings_metrics | Daily | ❌ Likely not running |
| — | loadrevenueestimate.py | revenue_estimates | Daily | ⚠️ Check if running |

---

## Action Priority Matrix

```
┌──────────────────────────┬──────────┬─────────────────────────────────────┐
│ Issue                    │ Impact   │ Fix Effort                          │
├──────────────────────────┼──────────┼─────────────────────────────────────┤
│ Quarterly data missing   │ CRITICAL │ Medium (ensure loaders run)         │
│ key_metrics incomplete   │ CRITICAL │ Low (verify yfinance availability)  │
│ earnings_metrics empty   │ HIGH     │ Medium (SEC filing integration)     │
│ DCF not implemented      │ MEDIUM   │ High (complex calculation)          │
│ Analyst data sparse      │ MEDIUM   │ Low (accept limitation for small)   │
│ No sector benchmarks     │ MEDIUM   │ Medium (calculate from available)   │
│ Options Greeks missing   │ LOW      │ High (requires pricing model)       │
│ 13F flows simulated      │ LOW      │ High (SEC filing API)               │
└──────────────────────────┴──────────┴─────────────────────────────────────┘
```

---

## Files in This Documentation

- `/home/stocks/algo/DATA_REQUIREMENTS_MAPPING.md` - Complete detailed mapping (855 lines)
- `/home/stocks/algo/QUICK_REFERENCE_DATA_MAPPING.md` - This file (quick lookup)

---

**Generated:** 2025-10-23  
**Codebase Version:** Latest from git status  
**Data as of:** 2025-10-23

