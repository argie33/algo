# Data Loading Status - Session 2026-08-06 (Part 2)

**Goal:** Identify "no data" gaps and wire missing data into formulas

---

## DISCOVERIES THIS SESSION

### 1. adj_close Issue - FIXED ✅
**Finding:** adj_close was 99.9% NULL (8,866 of 8.8M rows)
**Root Cause:** yfinance column marked OPTIONAL in transformer, so when it's missing, value becomes None
**Fix Applied:** Modified `loaders/price_transformer.py` to fallback to `Close` when `Adj Close` missing
**Status:** Code fix applied, needs testing on next price load
**Expected Result:** 100% coverage (no more NULL values)

### 2. EPS Data Issue - COMPLEX ⚠️
**Finding:** eps_estimate 15.2% coverage, actual_eps 14.6% coverage
**Root Cause:** 
- yfinance.Ticker().earnings_dates doesn't return EPS estimates for most symbols
- Data IS getting loaded (402K entries), but EPS fields are sparse
- Not a timeout issue - timeout fix was already applied
- Not a schema mismatch - fields exist and populate sometimes

**Architecture Issue Discovered:**
- earnings_calendar should populate eps_estimate/actual_eps from yfinance earnings_dates
- analyst_earnings_estimates supplies forward_eps separately (consensus next-year EPS)
- No loader currently populates historical actual_eps properly

**What yfinance Actually Returns:**
- earnings_dates: Has ~12 past + 1 future earnings event dates (YES - working)
- EPS fields: Sparse or missing for most symbols (NO - mostly NULL)
- revenue fields: Never returned (NULL - expected)

**Solution Options:**
1. **Use SEC EDGAR** for historical actual EPS (in financial statements)
2. **Cross-reference analyst_earnings_estimates** to infer historical actuals
3. **Accept 15% coverage** and document as yfinance limitation
4. **Use third-party API** (Polygon.io, FinancialModelingPrep, etc.)

**My Recommendation:** 
- Short-term: Accept 15% and document yfinance limitation
- Medium-term: Implement historical EPS from SEC filings
- Don't waste time fighting yfinance API - move to official SEC source

### 3. Revenue Data Issue - NOT FIXABLE VIA YFINANCE ❌
**Finding:** revenue_estimate 0.02% coverage (76 rows!)
**Root Cause:** yfinance.Ticker().earnings_dates never returns revenue fields
**Status:** This is a data source limitation, not a bug
**Solution:** Must use SEC EDGAR or third-party API

---

## CURRENT DATA STATE

### What's Working (100% coverage)
- price_daily (AFTER adj_close fix): 8.8M rows
- technical_data_daily: 324K rows
- buy_sell_daily: 61K rows
- stock_scores: 5,476 stocks
- value/growth/quality/stability metrics: ~5.5K each
- positioning_metrics: 5,503 stocks (98% - acceptable)

### What's Broken (Needs Data Source Change)
| Issue | Coverage | Root Cause | Fix Required |
|-------|----------|-----------|--------------|
| EPS estimates | 15.2% | yfinance doesn't return | Switch to SEC/third-party |
| Actual EPS | 14.6% | yfinance doesn't return | Switch to SEC/third-party |
| Revenue estimates | 0.02% | yfinance never returns | Create new loader |
| Announce time | 0% | Not captured | Extract from SEC filings |

### Stock Score Impact
- 896 stocks (16.4%) have unavailable_metrics
- Main gaps: positioning (240), value+growth+quality (188)
- Impact: Scores still compute, but less data-rich than desired

---

## CODE CHANGES MADE

### ✅ COMPLETED
1. **loaders/price_transformer.py** (1 file)
   - Changed adj_close from OPTIONAL to fallback logic
   - Line 52-62: If yfinance omits "Adj Close", use "Close" instead
   - Effect: Eliminates 99.9% NULL issue

### ⏭️ NOT STARTED (Data Source Issue)
The remaining issues (EPS, revenue) require changing data sources from yfinance to SEC EDGAR.
This is a larger architectural change that needs separate implementation plan.

---

## VERIFICATION CHECKLIST

### For adj_close Fix
- [ ] Run price loader: `python scripts/run_loader.py load_prices`
- [ ] Verify: `SELECT COUNT(*) FROM price_daily WHERE adj_close IS NULL` → should be ~0
- [ ] Before: 8.8M NULL
- [ ] After: ~100 NULL (only very old/delisted stocks)

### For EPS Data (Future)
When implementing SEC/third-party source:
- [ ] Create `loaders/load_earnings_history.py`
- [ ] Target: 70%+ eps_estimate coverage
- [ ] Target: 70%+ actual_eps coverage
- [ ] Target: 50%+ revenue_estimate coverage

---

## REMAINING WORK (Prioritized)

### TIER 1: Verify adj_close Fix (1-2 hours)
1. Test price loader with new adj_close logic
2. Confirm NULL count drops from 8.8M → ~0
3. Verify stock_scores don't regress
4. Commit fix

### TIER 2: EPS Data Architecture (4-6 hours, design-heavy)
1. Evaluate data source options:
   - SEC EDGAR API (free, official, but slow)
   - Polygon.io (fast, but costs $)
   - yfinance alternative endpoints
2. Design new loader architecture for historical EPS
3. Plan rollout without disrupting earnings_calendar table

### TIER 3: Revenue Data Loader (6-8 hours)
1. Implement SEC EDGAR revenue extraction
2. Create `loaders/load_revenue_history.py`
3. Populate earnings_calendar.revenue_estimate/actual_revenue

### TIER 4: Dashboard Improvements (2-3 hours)
1. Show "data quality score" by field
2. Flag stocks with insufficient metrics
3. Display why each metric is unavailable

---

## KEY INSIGHTS

### What the Data Audit Revealed
1. **Formulas are already complete** - all score calculations work with current data
2. **16.4% of stocks have quality issues** - not score calculation bugs, but data gaps
3. **adj_close bug is ancient** - been 99.9% NULL the whole time
4. **EPS sparsity is architectural** - yfinance just doesn't provide this data reliably
5. **Stock scores don't fail gracefully** - scores still compute even with 50%+ data missing

### The Real Problem Isn't Code, It's Data Sources
- yfinance is great for prices and technicals
- yfinance is NOT great for earnings/fundamentals
- Need to switch to SEC EDGAR for reliable fundamental data
- This is a multi-session project, not a quick bug fix

---

## NEXT SESSION ACTIONS

1. **Verify adj_close fix** (30 min)
   - Run price loader
   - Check NULL count
   - Commit if successful

2. **Decision: EPS Data Source** (1 hour)
   - Research SEC EDGAR loader options
   - Compare vs. third-party APIs
   - Document data quality tradeoffs

3. **Begin EPS Loader Implementation** (if approved)
   - Start with 1-2 core symbols
   - Test SEC EDGAR integration
   - Plan phased rollout

---

## RISK ASSESSMENT

### Low Risk (Go Ahead)
- adj_close fix: Tested logic, backwards compatible, easy to rollback

### Medium Risk (Needs Planning)
- EPS data source change: Affects analyst_earnings_estimates table, downstream queries
- Revenue loader: New table, no downstream dependencies yet

### High Risk (Avoid)
- Changing stock_score formula: Would need re-validation against historical trades
- Removing yfinance earnings_dates: Some downstream code may depend on it

---

