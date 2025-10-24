# Data Pipeline Quick Reference

## At-a-Glance Status

### Data Loader Categories (70+ loaders)

| Category | Count | Status | Key Files | Issue |
|----------|-------|--------|-----------|-------|
| **Price Data** | 9 | ✅ Working | loadpricedaily.py | None |
| **Technical Analysis** | 9 | ✅ Working | loadtechnicalsdaily.py | None |
| **Financials (Statements)** | 6 | ✅ Working | loadannualincomestatement.py | None |
| **Earnings & Estimates** | 5 | ✅ Working | loadearningshistory.py | None |
| **Analyst Sentiment** | 2 | ✅ Working | loadsanalystsentiment.py | None |
| **Social Sentiment** | 3 | ❌ Broken | loadsentiment.py | Generates fake random data |
| **Risk & Positioning** | 3 | ⚠️ Partial | loadpositioning.py | Quality defaults to 0.5 |
| **Sector & Industry** | 3 | ✅ Working | loadsectors.py | None |
| **Economic Data** | 4 | ✅ Working | loadecondata.py | None |
| **Market Sentiment** | 4 | ✅ Working | loadfeargreed.py | None |
| **Key Metrics** | 3 | ✅ Working | loadkeymetrics.py | None |
| **Quality/Growth/Value** | 3 | ✅ Working | loadqualitymetrics.py | None |
| **Momentum** | 2 | ✅ Working | loadmomentum.py | None |
| **Company Profile** | 6 | ✅ Working | loadcompanyprofile.py | None |
| **News** | 3 | ✅ Working | loadnews.py | None |
| **Scoring Engine** | 4 | ⚠️ Incomplete | loadscores.py | Missing sentiment data |

**Total**: ~70 working loaders + 3 with issues

---

## Score System Status

### 6 Score Categories

| Score Type | Status | Components | Issue |
|-----------|--------|------------|-------|
| **Quality** | ✅ Can calculate | Earnings quality, balance strength, profitability, management | All data available |
| **Growth** | ✅ Can calculate | Revenue growth, earnings growth, fundamental growth, market expansion | All data available |
| **Value** | ✅ Can calculate | P/E score, DCF score, relative value | All data available |
| **Momentum** | ✅ Can calculate | Price momentum, fundamental momentum, technical, volume | All data available |
| **Sentiment** | ❌ Incomplete | Analyst ✅, social ❌, market ✅, news ❌ | Missing social (Reddit, Google Trends) and news components |
| **Positioning** | ⚠️ Partial | Institutional, insider, short interest, options flow | Institutional quality defaults to 0.5 |

---

## Critical Issues To Fix

### 1. CRITICAL: Sentiment Data Generation
- **File**: `/home/stocks/algo/loadsentiment.py` (lines 240-331)
- **Issue**: Generates random fake data with `np.random`
- **Impact**: Database filled with fabricated sentiment values
- **Fix**: Remove fake generation or implement real APIs

### 2. CRITICAL: Economic Correlation Matrix
- **File**: `/home/stocks/algo/webapp/lambda/routes/economic.js` (lines 808-820)
- **Issue**: Hardcoded 0.5 for all correlations
- **Impact**: Users see fake correlation relationships
- **Fix**: Calculate Pearson correlation from `economic_data` table

### 3. CRITICAL: Market Correlation Matrix
- **File**: `/home/stocks/algo/webapp/lambda/routes/market.js` (lines 5000-5043)
- **Issue**: Hardcoded correlation values (0.6, 0.7, 0.4, 0.1)
- **Impact**: Portfolio risk analysis shows fake diversification
- **Fix**: Calculate correlation from `price_daily` returns

### 4. HIGH: News Sentiment Fallback
- **File**: `/home/stocks/algo/webapp/lambda/utils/newsAnalyzer.js`, `sentimentEngine.js`
- **Issue**: Returns hardcoded 0.5 instead of NULL
- **Impact**: Missing data masked as neutral
- **Fix**: Return NULL/undefined

### 5. HIGH: Positioning Quality
- **File**: `/home/stocks/algo/loadpositioning.py` (line 210)
- **Issue**: All holders assigned quality = 0.5
- **Impact**: Can't distinguish good from bad institutional investors
- **Fix**: Calculate real quality scores

### 6. MEDIUM: Score Confidence
- **File**: `/home/stocks/algo/loadscores.py` (multiple lines)
- **Issue**: All scores have hardcoded 90% confidence
- **Impact**: Confidence doesn't reflect data completeness
- **Fix**: Calculate from non-null field ratio

---

## Database Tables (7 Score Tables)

```sql
quality_scores       -- earnings_quality, balance_strength, profitability, management
growth_scores        -- revenue_growth, earnings_growth, fundamental_growth, market_expansion
value_scores         -- pe_score, dcf_score, relative_value
momentum_scores      -- price_momentum, fundamental_momentum, technical, volume_analysis
sentiment_scores     -- analyst✅, social❌, market✅, news❌  [INCOMPLETE]
positioning_scores   -- institutional⚠️, insider✅, short_interest✅, options_flow⚠️
master_scores        -- composite of all 6 + recommendation
```

**Plus 40+ supporting data tables**

---

## Real Data Sources Status

| Source | Type | API Key | Status | Used By |
|--------|------|---------|--------|---------|
| yfinance | Prices, Financials, Earnings, Analyst | No | ✅ | Price loaders, Financials |
| FRED | Economic Indicators | Yes (have it) | ✅ | loadecondata.py |
| Fear & Greed | Market Sentiment | Free scrape | ✅ | loadfeargreed.py |
| NAAIM | Advisor Positioning | Yes | ✅ | loadnaaim.py |
| Commodities | Futures | Multiple | ✅ | loadcommodities.py |
| Crypto | Digital Assets | Free | ✅ | loadcrypto.py |
| **Reddit** | **Social Sentiment** | **Yes (needs setup)** | **❌** | **loadsentiment.py** |
| **Google Trends** | **Search Volume** | **No** | **❌** | **loadsentiment.py** |
| **NewsAPI** | **News Sentiment** | **Yes (optional)** | **❌** | **newsAnalyzer.js** |

---

## Data Completeness by Loader

### ✅ COMPLETE & WORKING

```
loadpricedaily.py           → price_daily table ✅
loadtechnicalsdaily.py      → technical_data_daily ✅
loadbuysellly.py            → buy_sell_daily ✅
loadannualincomestatement   → annual income data ✅
loadkeymetrics.py           → key_metrics ✅
loadmomentum.py             → momentum_metrics ✅
loadsanalystsentiment.py    → analyst_sentiment_analysis ✅
loadfeargreed.py            → fear_greed ✅
loadnaaim.py                → naaim ✅
loadfinancials.py           → profitability/valuation metrics ✅
loadsectors.py              → sector_ranking ✅
loadecondata.py             → economic_data ✅
```

### ❌ BROKEN & NEEDS FIXING

```
loadsentiment.py            → sentiment_data ❌ (FAKE RANDOM DATA)
  - Reddit sentiment returns NULL
  - Google Trends returns NULL
  - News sentiment returns NULL/0.0
```

### ⚠️ PARTIAL & INCOMPLETE

```
loadpositioning.py          → positioning_data ⚠️ (quality defaults to 0.5)
loadscores.py               → quality/growth/value/momentum/sentiment/positioning ⚠️
  - Missing sentiment components
  - Confidence hardcoded to 90%
```

---

## Pipeline Flow Summary

```
Raw Data (yfinance, FRED, APIs, web scraping)
    ↓
Load*.py Scripts (70+ loaders)
    ↓
PostgreSQL Database (40+ tables)
    ↓
Scoring Engine (loadscores.py) - INCOMPLETE for sentiment
    ↓
Lambda Routes API
    ↓
React Frontend
```

---

## Quick Fix Checklist

- [ ] **Remove fake sentiment generation** in loadsentiment.py
- [ ] **Fix economic correlation** calculation in routes/economic.js
- [ ] **Fix market correlation** calculation in routes/market.js
- [ ] **Fix sentiment fallbacks** to return NULL
- [ ] **Calculate real confidence scores** based on data completeness
- [ ] **Implement real positioning quality** scoring
- [ ] **Setup Google Trends** (pytrends library)
- [ ] **Setup Reddit API** (PRAW library, credentials)
- [ ] **Implement news sentiment** analysis
- [ ] **Verify database** clean of fake data

---

## Key Files Summary

| File | Purpose | Status | Priority |
|------|---------|--------|----------|
| loadscores.py | Master scoring engine | ⚠️ | CRITICAL |
| loadsentiment.py | Social sentiment loader | ❌ | CRITICAL |
| routes/economic.js | Economic API endpoint | ❌ | CRITICAL |
| routes/market.js | Market API endpoint | ❌ | CRITICAL |
| newsAnalyzer.js | News sentiment utility | ❌ | HIGH |
| sentimentEngine.js | Sentiment aggregation | ⚠️ | HIGH |
| loadpositioning.py | Positioning data loader | ⚠️ | HIGH |
| loadmomentum.py | Momentum calculation | ✅ | REFERENCE |
| loadsanalystsentiment.py | Analyst data loader | ✅ | REFERENCE |

---

## Time Estimates

| Fix | Complexity | Time |
|-----|-----------|------|
| Remove fake sentiment | Easy | 30 min |
| Fix correlations (2 files) | Medium | 2 hours |
| Fix sentiment fallbacks | Easy | 30 min |
| Setup Google Trends | Easy | 1 hour |
| Setup Reddit API | Medium | 2 hours |
| Implement news sentiment | Medium | 2 hours |
| Fix confidence scores | Easy | 1 hour |
| Database cleanup | Easy | 30 min |
| **Total** | — | **~9 hours** |

---

**Report Generated**: 2025-10-23  
**Location**: `/home/stocks/algo/COMPREHENSIVE_DATA_PIPELINE_MAP.md` (detailed)  
**Location**: `/home/stocks/algo/DATA_PIPELINE_QUICK_REFERENCE.md` (this file)
