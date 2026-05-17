# Data Population Strategy

**Status:** In Progress - Company profiles and earnings calendar loading  
**Priority:** CRITICAL - These gaps block production readiness

---

## Critical Data Gaps Identified

| Data Type | Table | Status | Coverage | Priority |
|-----------|-------|--------|----------|----------|
| Stock Profiles | company_profile | LOADING | 10.9% → targeting 95% | CRITICAL |
| Earnings Dates | earnings_calendar | NEEDS LOAD | 0.7% → need 95%+ | CRITICAL |
| Earnings History | earnings_history | PARTIAL | 1.1% | HIGH |
| Analyst Sentiment | analyst_sentiment_analysis | EMPTY | 0% | HIGH |
| Technical Data | technical_data_daily | SPARSE | 19% | MEDIUM |
| Price Data | price_daily | SPARSE | 19.2% | MEDIUM |

---

## Why These Matter

### 1. Company Profiles (Loading Now)
- **What:** Sector, industry, employee count, market cap, website, etc.
- **Used By:** Stock detail pages, filtering, research
- **Current:** 1,110/10,167 symbols (10.9%)
- **Target:** 9,500+ symbols (95%+)
- **Impact if Missing:** Stock detail pages show incomplete info
- **Loader:** `loadcompanyprofile.py` (from yfinance)
- **Runtime:** ~5-10 minutes for full 10K symbols

### 2. Earnings Calendar (Needs Load)
- **What:** Upcoming earnings announcement dates
- **Used By:** Earnings blackout enforcement in algo
- **Current:** 69 rows (0.7% coverage)
- **Target:** 5,000+ rows (50%+ of symbols)
- **Impact if Missing:** Algo might trade through earnings announcements (HIGH RISK)
- **Loader:** `load_earnings_calendar.py` (from yfinance)
- **Runtime:** ~3-5 minutes

### 3. Analyst Sentiment (Missing Table Check)
- **What:** Analyst buy/hold/sell ratings
- **Used By:** Sentiment signals, research pages
- **Current:** Table `analyst_sentiment_analysis` exists but EMPTY
- **Loader:** `loadanalystsentiment.py` (needs to be added to Terraform)
- **Status:** Loader exists but not scheduled in production

### 4. Technical Data (Sparse)
- **What:** RSI, MACD, SMA, EMA, ATR per symbol
- **Used By:** Technical analysis, signal generation
- **Current:** 19% coverage (1,953/10,167 symbols)
- **Reason:** Only symbols with price data get technical indicators
- **Fix:** Needs price data first (see below)

### 5. Price Data (Sparse - Expected)
- **What:** Daily OHLCV data
- **Used By:** Technical indicators, charting, backtesting
- **Current:** 19.2% coverage (1,953/10,167 symbols)
- **Reason:** EXPECTED - only major stocks have good price histories
- **Status:** OK - this is normal (small-cap stocks have sparse data)

---

## Execution Plan

### Phase 1: Critical Data (This Session)
```
RUNNING NOW:
1. loadcompanyprofile.py --parallelism 16
   - Target: 95%+ of 10K symbols
   - Runtime: ~10 minutes
   - Status: IN PROGRESS

TODO:
2. load_earnings_calendar.py
   - Target: Populate all upcoming earnings
   - Runtime: ~5 minutes
   
3. Verify analyst_sentiment_analysis table
   - If exists but empty: schedule analyst sentiment loader
   - If doesn't exist: create table
```

### Phase 2: Secondary Data (Next Session)
```
TODO:
4. loadanalystsentiment.py
   - Load analyst ratings and upgrades
   - Runtime: ~10 minutes
   - Impact: Medium (nice to have for research)

5. loadearningshistory.py (refresh)
   - Already has some data (1.1%)
   - Could expand coverage
```

### Phase 3: Derived Data (Auto-Generates)
```
AUTO-GENERATED (depends on above):
- technical_data_daily (regenerates when prices available)
- weekly_prices, monthly_prices (aggregates from daily)
- stock_scores (generated from fundamentals + technicals)
```

---

## Execution Commands

### Load Company Profiles (RUNNING)
```bash
python3 loaders/loadcompanyprofile.py --parallelism 16
# Expected output: inserted=~9000, processing ~15 minutes
```

### Load Earnings Calendar (NEXT)
```bash
python3 loaders/load_earnings_calendar.py
# Expected output: inserted=~3000+, processing ~5 minutes
```

### Verify Analyst Sentiment Table
```bash
python3 -c "
import psycopg2
conn = psycopg2.connect('host=localhost user=postgres dbname=stocks password=YOUR_PW')
cur = conn.cursor()
cur.execute(\"\"\"
    SELECT EXISTS (
        SELECT FROM information_schema.tables
        WHERE table_name = 'analyst_sentiment_analysis'
    )
\"\"\")
print('Table exists:', cur.fetchone()[0])
"
```

---

## Expected Outcomes

After executing Phase 1:
- ✅ Company profiles: 95%+ coverage
- ✅ Earnings calendar: 50%+ coverage
- ✅ Analyst sentiment: Either populated or flagged for Phase 2
- ✅ Technical data: Will auto-regenerate for all price-available symbols

After executing Phase 2:
- ✅ Analyst sentiment: 50%+ coverage
- ✅ Earnings history: Expanded coverage
- ✅ Full data completeness for production readiness

---

## Blockers & Risks

### No Blockers for Phase 1
- All required loaders exist
- All tables exist in schema
- All data sources (yfinance) available

### Risks
1. **Earnings Calendar Accuracy** - yfinance earnings dates sometimes delayed
   - Mitigation: Fallback to SEC EDGAR if yfinance incomplete
   
2. **API Rate Limiting** - Large parallel loads might hit rate limits
   - Mitigation: Using --parallelism 16 which is conservative
   
3. **Data Staleness** - Company profiles don't update frequently
   - Mitigation: OK - Company info doesn't change daily

---

## Success Metrics

✅ **Phase 1 Success:**
- [ ] Company profiles: 9,000+/10,167 symbols (88%+)
- [ ] Earnings calendar: 3,000+ rows (30%+ of symbols)
- [ ] Zero data loading errors
- [ ] Data inserted confirmed via audit_data_gaps.py

✅ **Production Ready When:**
- Company profiles: 90%+
- Earnings calendar: 80%+
- Analyst sentiment: 50%+ (if using)
- All critical loaders automated in Terraform

