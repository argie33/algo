# NEXT 10 DATA ISSUES - After Initial Top 10 Fixes

**Updated:** January 22, 2026
**Status:** Comprehensive audit complete - found 30,507+ additional fixable data points

---

## 📊 CRITICAL GAPS FOUND (< 80% coverage)

### Priority A: HIGHLY FIXABLE (Can improve 10%+ with calculations)

**#1. PAYOUT RATIO (34.6% → Can reach 65%+)**
- Current: 1,874/5409 (34.6%)
- Missing: 3,535 stocks
- **Can Fix:** Calculate from dividend_rate ÷ net_income × 100
- **Benefit:** Critical quality metric for value/dividend stocks
- **Effort:** LOW - Simple SQL calculation

**#2. EBITDA MARGIN (72.8% → Can reach 85%+)**
- Current: 3,939/5409 (72.8%)
- Missing: 1,470 stocks
- **Can Fix:** Calculate from ebitda ÷ total_revenue × 100
- **Benefit:** Key profitability metric
- **Effort:** LOW - Simple SQL calculation

**#3. GROSS MARGIN (82.3% → Can reach 90%+)**
- Current: 4,453/5409 (82.3%)
- Missing: 956 stocks
- **Can Fix:** Calculate from (revenue - cost_of_goods) ÷ revenue × 100
  - Alternative: Derive from net_income + taxes + depreciation logic
- **Benefit:** Important for margin analysis
- **Effort:** MEDIUM - May need multiple fallback sources

**#4. NET PROFIT MARGIN (82.5% → Can reach 90%+)**
- Current: 4,460/5409 (82.5%)
- Missing: 949 stocks
- **Can Fix:** Calculate from net_income ÷ total_revenue × 100
- **Benefit:** Core quality metric
- **Effort:** LOW - Simple SQL calculation

**#5. FREE CASH FLOW (83.5% → Can reach 90%+)**
- Current: 4,516/5409 (83.5%)
- Missing: 893 stocks
- **Can Fix:** Calculate from operating_cashflow - capital_expenditures
  - Data exists in tables but not merged
- **Benefit:** Critical for cash health assessment
- **Effort:** MEDIUM - Need to join multiple tables

---

### Priority B: MODERATELY FIXABLE (Can improve 5-10%)

**#6. EV/EBITDA (85.2% → Can reach 92%+)**
- Current: 4,611/5409 (85.2%)
- Missing: 798 stocks
- **Can Fix:** Calculate from enterprise_value ÷ ebitda
- **Benefit:** Alternative valuation metric
- **Effort:** LOW - Simple SQL calculation

**#7. EBITDA (85.9% → Can stay high)**
- Current: 4,645/5409 (85.9%)
- Missing: 764 stocks
- **Status:** Already good - mostly unprofitable/startup companies
- **Effort:** SKIP - Not worth the effort

**#8. EPS FORWARD (77.4% → Can reach 82%+)**
- Current: 4,184/5409 (77.4%)
- Missing: 1,225 stocks
- **Can Fix:** Use analyst_target_price ÷ forward earnings estimates
  - OR use consensus from analyst ratings
- **Benefit:** Growth metric for forward-looking valuation
- **Effort:** HIGH - Need external analyst data

**#9. PRICE/EPS CURRENT YEAR (70.0% → Can reach 80%+)**
- Current: 3,789/5409 (70.0%)
- Missing: 1,620 stocks
- **Can Fix:** Calculate from price ÷ eps_current_year (once EPS improved)
- **Benefit:** Alternative P/E metric
- **Effort:** LOW - Depends on fixing #10

**#10. EPS CURRENT YEAR (69.8% → Can reach 75%+)**
- Current: 3,777/5409 (69.8%)
- Missing: 1,632 stocks
- **Can Fix:** Pull from analyst estimates or quarterly data
- **Benefit:** Needed for P/E calculations and forward valuations
- **Effort:** HIGH - Need analyst data or quarterly compilation

---

## ❌ NOT FIXABLE (Legitimate gaps)

- **Dividend Yield (35.5%):** 70% are correct NULLs (growth stocks)
- **Earnings Growth (44.1%):** Unprofitable/IPO companies (correct NULL)
- **Quarterly Earnings Growth (45.1%):** Same as earnings growth
- **Trailing P/E (53.8%):** 1,800+ unprofitable companies (correct NULL)
- **PEG Ratio (65.6%):** Already improved from 17% - further improvement needs external data

---

## 🎯 RECOMMENDED ACTION PLAN

### IMMEDIATE (Do Now - 30 minutes)
1. **Fix Payout Ratio** (34.6% → 65%+): dividend_rate / net_income × 100
2. **Fix EBITDA Margin** (72.8% → 85%+): ebitda / total_revenue × 100
3. **Fix Net Profit Margin** (82.5% → 90%+): net_income / total_revenue × 100
4. **Fix EV/EBITDA** (85.2% → 92%+): enterprise_value / ebitda

**Expected Result:** +3,210 new data points

### SECONDARY (Do Next - if time permits)
5. **Fix Gross Margin** (82.3% → 90%+): Calculate from available data
6. **Fix Free Cash Flow** (83.5% → 90%+): operating_cashflow - capex

**Expected Result:** +1,850 new data points

### EXTERNAL (Requires API/Subscription)
7. EPS Current Year (69.8%) - Needs analyst data
8. EPS Forward (77.4%) - Needs analyst estimates
9. Advanced dividend data (32.9% - 35.5%) - Needs external service

---

## 📈 IMPACT ANALYSIS

**If we fix Priority A immediately:**
- +3,210 new data points
- Better quality scores (more complete financial ratios)
- Better value scores (payout ratio critical for dividend investors)
- Better profitability analysis

**System will have:**
- Payout Ratio: 65%+ (was 34.6%)
- EBITDA Margin: 85%+ (was 72.8%)
- Net Profit Margin: 90%+ (was 82.5%)
- EV/EBITDA: 92%+ (was 85.2%)

**Total improvements across all issues:** 2,941 (done) + 3,210 (new) = **6,151 total data points added!**

---

## SUMMARY: Top 10 → Extended Top 20

### COMPLETED (Top 10):
1. ✅ PEG Ratio: 65.6% (+1,663)
2. ⚠️ Dividend Yield: 35.5% (correct NULLs)
3. ✅ Earnings Growth: 44.5% (verified)
4. ⚠️ Trailing P/E: 53.8% (correct NULLs)
5. ✅ Debt/Equity: 95.7% (+867)
6. ❌ Earnings Estimates: 85.0% (needs external)
7. ✅ Forward P/E: 88.9% (+335)
8. ✅ Revenue Growth: 87.5% (excellent)
9. ✅ ROE: 90.9% (+141)
10. ✅ Current Ratio: 91.4% (excellent)

### NEXT 10 (Available to fix now):
11. 🔴 Payout Ratio: 34.6% → Can reach 65% (+2,200 potential)
12. 🟡 EBITDA Margin: 72.8% → Can reach 85% (+400)
13. 🟡 Gross Margin: 82.3% → Can reach 90% (+300)
14. 🟡 Net Profit Margin: 82.5% → Can reach 90% (+310)
15. 🟡 Free Cash Flow: 83.5% → Can reach 90% (+300)
16. 🟡 EV/EBITDA: 85.2% → Can reach 92% (+200)
17. 🟡 EBITDA: 85.9% (SKIP - already good)
18. 🟡 EPS Forward: 77.4% (HIGH EFFORT)
19. 🟡 Price/EPS Current: 70% (depends on #20)
20. 🔴 EPS Current Year: 69.8% (HIGH EFFORT)

---

## ACTION: Ready to Implement?

Should we fix the **Priority A gaps now** (+3,210 data points)?
- Payout Ratio calculation
- EBITDA Margin calculation
- Net Profit Margin calculation
- EV/EBITDA calculation

**Estimated time:** 20-30 minutes
**Impact:** +3,210 additional data points
**Loader time:** 5-10 minutes for recalculation

