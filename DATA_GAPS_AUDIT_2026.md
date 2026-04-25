# Data Gaps Audit - April 25, 2026

## S&P 500 Data Coverage Summary (515 stocks)

| Data Source | Coverage | Status | Impact |
|-------------|----------|--------|--------|
| **Stock Scores** | 515/515 (100%) | ✅ COMPLETE | All scores available |
| **Technical Data** | 515/515 (100%) | ✅ COMPLETE | All indicators calculated |
| **Insider Transactions** | 515/515 (100%) | ✅ COMPLETE | All insider data loaded |
| **Analyst Sentiment** | 359/515 (69.7%) | ⚠️ PARTIAL | 156 stocks missing |
| **Institutional Positioning** | 209/515 (40.6%) | 🔴 CRITICAL | 306 stocks missing |
| **Analyst Upgrades** | 193/515 (37.5%) | 🔴 CRITICAL | 322 stocks missing |
| **Earnings Estimates** | 7/515 (1.4%) | 🔴 CRITICAL | 508 stocks missing |
| **Options Chains** | 1/515 (0.2%) | 🔴 CRITICAL | 514 stocks missing |

## Critical Issues

### 1. Earnings Estimates (1.4% coverage)
- **Expected:** ~515 stocks
- **Actual:** 7 stocks
- **Missing:** 508 stocks (98.6% gap)
- **Impact:** Earnings forecast pages showing blank
- **Root Cause:** Earnings loader likely not running or API failures

### 2. Options Chains (0.2% coverage)
- **Expected:** ~515 stocks (most liquid optionable stocks)
- **Actual:** 1 stock
- **Missing:** 514 stocks (99.8% gap)
- **Impact:** Options data pages completely empty
- **Root Cause:** Options loader not executed or data source unavailable

### 3. Institutional Positioning (40.6% coverage)
- **Expected:** ~515 stocks
- **Actual:** 209 stocks
- **Missing:** 306 stocks (59.4% gap)
- **Impact:** Institutional ownership data shows for 40% of stocks only
- **Root Cause:** Partial loader execution or filtering issues

### 4. Analyst Upgrades/Downgrades (37.5% coverage)
- **Expected:** ~515 stocks
- **Actual:** 193 stocks
- **Missing:** 322 stocks (62.5% gap)
- **Impact:** Analyst action pages incomplete
- **Root Cause:** Analyst loader not fully covering all symbols

### 5. Analyst Sentiment (69.7% coverage)
- **Expected:** ~515 stocks
- **Actual:** 359 stocks
- **Missing:** 156 stocks (30.3% gap)
- **Impact:** Sentiment scores missing for ~30% of portfolio
- **Root Cause:** Sentiment analysis loader partially working

## What's Working

✅ **Stock Scores** (100% - all 515 stocks)
- Quality metrics
- Growth metrics
- Stability metrics
- Momentum metrics
- Value metrics
- Positioning metrics in scores table

✅ **Technical Indicators** (100% - all 515 stocks)
- RSI, SMA, EMA calculated
- Historical price data available

✅ **Insider Data** (100% - all 515 stocks)
- All insider transactions loaded
- Trading activity tracked

## Impact on Frontend

**Blank/Empty Fields Users Are Seeing:**
1. Earnings forecast tables - empty for 99% of stocks
2. Options chains - essentially empty
3. Institutional ownership charts - missing for 60% of stocks
4. Analyst action trackers - incomplete for 63% of stocks
5. Sentiment scores - missing for 30% of stocks

## Loader Status Analysis

Based on data coverage, these loaders are **failing or not running**:

| Loader | Status | Evidence |
|--------|--------|----------|
| `load_earnings_estimates.py` | ❌ FAILING | Only 7/515 stocks |
| `load_options_chains.py` | ❌ FAILING | Only 1/515 stocks |
| `load_institutional_positioning.py` | ⚠️ PARTIAL | 209/515 stocks |
| `load_analyst_upgrades.py` | ⚠️ PARTIAL | 193/515 stocks |
| `load_analyst_sentiment.py` | ⚠️ PARTIAL | 359/515 stocks |
| `load_technical_indicators.py` | ✅ WORKING | 515/515 stocks |
| `load_insider_transactions.py` | ✅ WORKING | 515/515 stocks |
| `load_stock_scores.py` | ✅ WORKING | 515/515 stocks |

## Next Steps (Priority Order)

### CRITICAL (This breaks user experience)
1. Fix `load_earnings_estimates.py` - get from 7 to 515 stocks
2. Fix `load_options_chains.py` - get from 1 to 500+ stocks
3. Fix `load_institutional_positioning.py` - get from 209 to 515 stocks

### HIGH (Improves user experience)
4. Fix `load_analyst_upgrades.py` - get from 193 to 515 stocks
5. Fix `load_analyst_sentiment.py` - get from 359 to 515 stocks

### Action Plan
- [ ] Run each failing loader individually with logging
- [ ] Check data source availability (API keys, rate limits)
- [ ] Verify database column mappings match data loader expectations
- [ ] Re-run successful loaders with S&P 500 filter
- [ ] Verify frontend now shows data for all metrics
