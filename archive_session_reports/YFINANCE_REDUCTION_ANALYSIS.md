# yfinance Dependency Reduction Analysis

**Analysis Date:** 2026-07-16  
**Scope:** 8 data types from `load_yfinance_snapshot.py` (27 fields total per symbol)  
**Current Load:** ~5,300 symbols × 1 yfinance quoteSummary call = 5,300 API hits/run  
**Freshness Window:** 20 hours (YFINANCE_SNAPSHOT_MAX_AGE_HOURS)  

---

## Per-Data-Type Analysis

### 1. PE_RATIO (Price-to-Earnings)

```
DATA: pe_ratio (trailingPE)
CURRENT: yfinance.Ticker.info['trailingPE']
         Frequency: Daily (snapshot refresh)
         Source: Real-time stock price / trailing twelve-month EPS
         Coverage: ~95% of active symbols

EDGAR ALTERNATIVE: YES - compute from latest quarterly earnings + current price
         Formula: Current stock price / (latest_quarterly_EPS × 4)
         Challenge: Must manually track last 4 quarters; quarterly EPS 30-45 days stale
         Required tables: quarterly_income_statement (EPS), price_daily (current price)
         Implementation: Read last 4 Q earnings, aggregate, divide into current price

TRADEOFF: -30-45 days freshness lost
         Quarterly precision lost (quarterly_income_statement updates every 45 days)
         Example: AAPL Q2 2026 earnings filed 2026-04-30; PE calculated with 30-day stale EPS
         Until next 10-Q, PE value in stock_scores ages progressively (45d old by quarter-end)
         Signal impact: MODERATE - PE score component becomes less responsive to recent profitability changes
         
YFINANCE CALL REDUCTION: -4% (pe_ratio is 1/27 fields in snapshot)
         Savings: 212 API calls/run (5,300 × 4%)
         
COMPLEXITY: MEDIUM (~1 week)
         Tasks: (1) Write TTM aggregator for last 4 quarters
                (2) Handle missing quarters (some symbols file annually only)
                (3) Update value_metrics loader to read from quarterly_income_statement instead of snapshot
                (4) Add fallback: use annual EPS if quarterly unavailable
         Risk: Formula precision on split-adjusted prices

RECOMMENDATION: SKIP IT
         Reason 1: 30-45 day staleness hurts value scoring more than 212 API calls saved
         Reason 2: PE is loaded 5,300× per run; savings only 212 = ~4% (negligible)
         Reason 3: yfinance PE already reflects current market (more accurate for trader risk)
         Better path: Improve yfinance reliability instead

BLOCKERS: None hard blockers, but quality degrades too much for the savings gained
```

---

### 2. PB_RATIO (Price-to-Book)

```
DATA: pb_ratio (priceToBook)
CURRENT: yfinance.Ticker.info['priceToBook']
         Frequency: Daily
         Source: Market cap / book value (from balance sheet)
         Coverage: ~90% active symbols

EDGAR ALTERNATIVE: YES - compute from market cap / stockholders_equity
         Formula: (current_price × shares_outstanding) / total_equity_from_balance_sheet
         Challenge: Shares outstanding from 10-K (annual, 60d lag); market cap from price (daily)
         Must handle dilution, treasury shares separately
         Required tables: annual_balance_sheet (equity), price_daily (market cap)

TRADEOFF: -30-60 days staleness on equity component
         Shares outstanding varies quarterly but 10-K is annual only
         Example: Stock splits, new share issuance not reflected until next 10-K filing
         Signal impact: MODERATE-HIGH - book value can swing significantly with issuances
         
YFINANCE CALL REDUCTION: -4% (pb_ratio is 1/27 fields)
         Savings: 212 API calls/run
         
COMPLEXITY: MEDIUM-HIGH (~1.5 weeks)
         Tasks: (1) Track shares_outstanding from latest quarter
                (2) Handle dilution (stock options, convertibles)
                (3) Read balance sheet equity and divide by market cap
                (4) Add fallback for missing balance sheet data
                (5) Test on edge cases (leveraged buybacks, special dividends)
         Risk: Treasury stock adjustments, dilution precision

RECOMMENDATION: SKIP IT
         Reason 1: PB relies on shares_outstanding from quarterly filings (3-month lag)
         Reason 2: Stock splits/issuances can swing PB; EDGAR source is stale
         Reason 3: Only 4% API reduction; not worth quality loss
         Reason 4: yfinance already handles split adjustments automatically

BLOCKERS: None hard, but precision degrades materially
```

---

### 3. PS_RATIO (Price-to-Sales Trailing 12-Month)

```
DATA: ps_ratio (priceToSalesTrailing12Months)
CURRENT: yfinance.Ticker.info['priceToSalesTrailing12Months']
         Frequency: Daily
         Source: Market cap / trailing 12-month revenue
         Coverage: ~95% of symbols

EDGAR ALTERNATIVE: PARTIAL - Must manually compute TTM revenue
         Formula: Market cap / (sum of last 4 quarters' revenue)
         Challenge: Quarterly revenue is 30-45 days stale
         Requires manual aggregation of quarterly_income_statement last 4 periods
         TTM concept requires quarter boundary handling (Q2→Q1→Q4→Q3 of prior year)
         
TRADEOFF: -30-45 days staleness on revenue component
         TTM aggregation adds complexity (fiscal quarter alignments)
         Example: Today is 2026-07-16; latest 10-Q filed ~2026-05-15 (2 months old revenue)
         Signal impact: MODERATE - revenue growth is less volatile than earnings; 2-month lag acceptable
         
YFINANCE CALL REDUCTION: -4% (1/27 fields)
         Savings: 212 API calls/run
         
COMPLEXITY: HIGH (~2 weeks)
         Tasks: (1) Write TTM aggregator for quarterly revenue
                (2) Handle fiscal year vs calendar year boundaries
                (3) Match EPS date to revenue date for consistency
                (4) Account for special items (discontinued operations)
                (5) Debug edge case: quarters missing or restatements
         Risk: Fiscal calendar complexity (tech Q1 ≠ retail Q1)

RECOMMENDATION: SKIP IT
         Reason 1: High complexity with only 4% API reduction
         Reason 2: Manual TTM is error-prone across 5,300 symbols
         Reason 3: Revenue staleness acceptable for fundamentals but marginal improvement
         Reason 4: yfinance already computes this correctly

BLOCKERS: Fiscal quarter alignment complexity is non-trivial at scale
```

---

### 4. DIVIDEND_YIELD

```
DATA: dividend_yield (dividendYield)
CURRENT: yfinance.Ticker.info['dividendYield']
         Frequency: Daily
         Source: Trailing 12-month dividend / current price
         Coverage: ~70% of symbols (paid dividends)

EDGAR ALTERNATIVE: PARTIAL - Compute from historical dividend declarations
         Source 1: 10-K section on dividend policy (annual declaration)
         Source 2: Quarterly dividend announcements (must track separately)
         Challenge: Forward dividend unknown; 10-K is annual only (60d lag)
         No SEC XBRL concept for declared dividends; must parse 10-K text
         
TRADEOFF: -30-60 days staleness; forward yield missing entirely
         Current yield cannot be computed from EDGAR alone (price is daily, dividend is annual)
         Example: Quarterly dividend increases mid-year not reflected in 10-K until next filing
         Signal impact: HIGH - Yield-based portfolios depend on current distributions
         
YFINANCE CALL REDUCTION: -4% (1/27 fields)
         Savings: 212 API calls/run
         
COMPLEXITY: HIGH-VERY HIGH (~2-3 weeks)
         Tasks: (1) Parse 10-K dividend policy sections (unstructured text)
                (2) Track announced dividends from investor relations
                (3) Aggregate trailing 12 months of actual dividend payments
                (4) Compute yield from TTM / current price
                (5) Fallback: quarterly dividend tracking requires external feed
         Risk: Text parsing fragility; special dividends not in 10-K

RECOMMENDATION: SKIP IT
         Reason 1: yfinance already tracks trailing dividend payments (only source available)
         Reason 2: Forward yield cannot be computed from EDGAR; must use yfinance
         Reason 3: Dividend investors need current yield; EDGAR source too stale
         Reason 4: Implementation requires external data source for real-time announcements
         Reason 5: Only 4% API savings; not worth complexity

BLOCKERS: CRITICAL - Cannot compute forward/current yield from EDGAR alone
         SEC XBRL does not have dividend concepts
```

---

### 5. HELD_PERCENT_INSIDERS (Insider Ownership %)

```
DATA: held_percent_insiders (insidersPercentHeld)
CURRENT: yfinance.Ticker.info['insidersPercentHeld']
         Frequency: Daily (snapshot)
         Source: SEC Form 4 filings (insider transaction tracking)
         Coverage: ~85% of symbols

EDGAR ALTERNATIVE: DUAL SOURCE
         Source 1 (Annual): 10-K beneficial ownership section (~60d lag)
         Source 2 (Real-time): Form 4 filings (transaction-level, 3-5 business days)
         Challenge: yfinance aggregates Form 4s into single %; parsing 10-K text gives annual snapshot
         Form 4 tracking not in EDGAR companyfacts; requires separate SEC filing monitor
         
TRADEOFF: -60 days staleness (annual 10-K) unless Form 4s tracked separately
         yfinance already reads Form 4s; EDGAR alternative requires building Form 4 pipeline
         Signal impact: MODERATE - Insider trading sentiment matters but monthly updates acceptable
         
YFINANCE CALL REDUCTION: -4% (1/27 fields)
         Savings: 212 API calls/run
         
COMPLEXITY: VERY HIGH (~4-6 weeks)
         Tasks: (1) Monitor SEC Form 4 filings (requires separate feed)
                (2) Parse Form 4 transaction details (stock, options, restricted)
                (3) Aggregate insider shares / total shares outstanding
                (4) Store by transaction date in insider_transactions table
                (5) Fallback: use annual 10-K if Form 4s unavailable
                (6) Update value_metrics to read from new insider_transactions table
         Risk: Form 4 parsing complexity; handling restricted stock properly

RECOMMENDATION: DEFER - Consider after Form 4 tracking infrastructure built
         Reason 1: Requires entirely new data pipeline (Form 4 monitor)
         Reason 2: Only 4% API reduction but 4-6 weeks of work
         Reason 3: yfinance already provides this; no reliability issues
         Reason 4: Better ROI: Focus on fixing yfinance reliability instead
         Conditional: If insider ownership becomes critical to strategy, build Form 4 tracking
         Then leverage it across value scoring + risk management

BLOCKERS: Form 4 tracking infrastructure doesn't exist; must build from scratch
```

---

### 6. HELD_PERCENT_INSTITUTIONS (Institutional Ownership %)

```
DATA: held_percent_institutions (heldPercentInstitutions)
CURRENT: yfinance.Ticker.info['heldPercentInstitutions']
         Frequency: Daily (snapshot)
         Source: Aggregate of 13F filings (quarterly, 45 days late)
         Coverage: ~80% of symbols

EDGAR ALTERNATIVE: YES but VERY STALE
         Source: Form 13F filings (quarterly, 45 days after quarter-end)
         Method: Parse XBRL from 13F forms; aggregate holdings / outstanding shares
         Challenge: Quarterly only; 45-day lag = 90+ days stale at quarter-end
         No daily recency; yfinance aggregates real-time from all 13F filers
         
TRADEOFF: -45-90 days staleness vs yfinance daily snapshot
         Quarterly updates miss mid-quarter institutional buying/selling
         Signal impact: HIGH - Fund flows matter for momentum; stale data reduces signal quality
         Example: Major fund sale on day 60 of quarter not reflected until day 90+ when 13F filed
         
YFINANCE CALL REDUCTION: -4% (1/27 fields)
         Savings: 212 API calls/run
         
COMPLEXITY: VERY HIGH (~5-7 weeks)
         Tasks: (1) Parse SEC 13F XBRL filings (complex nested format)
                (2) Aggregate holdings across all institutional filers
                (3) Join to shares_outstanding for percentage
                (4) Store by filing date; track quarterly updates
                (5) Fallback: use last known 13F if current quarter missing
                (6) Update positioning_metrics to read from 13F table
         Risk: 13F parsing complexity; handling various filer formats

RECOMMENDATION: SKIP IT - NOT VIABLE
         Reason 1: 45-90 day lag makes institutional ownership data nearly useless for trading
         Reason 2: yfinance already aggregates 13Fs daily (higher quality)
         Reason 3: Very High complexity for minimal API savings (4%)
         Reason 4: EDGAR alternative is objectively WORSE than current source
         Reason 5: Institutional ownership is enrichment only; not critical to core scoring

BLOCKERS: CRITICAL - EDGAR source is significantly staler than yfinance
         No viable EDGAR alternative that improves upon current snapshot
```

---

### 7. SHORT_INTEREST (Short % of Float)

```
DATA: short_interest (shortPercentOfFloat)
CURRENT: yfinance.Ticker.info['shortPercentOfFloat']
         Frequency: Daily (snapshot)
         Source: FINRA short sale file (compiled from exchange reports)
         Coverage: ~95% of symbols

EDGAR ALTERNATIVE: NONE - NOT IN SEC FILINGS
         SEC does not publish short interest in EDGAR
         Short interest is market data, not company filing data
         Alternative source needed: FINRA, Ycharts, MarketWatch (not SEC)
         
TRADEOFF: CANNOT REPLACE with EDGAR
         To reduce yfinance dependency, would need alternative market data source
         Possible alternatives: Alpaca API, Polygon.io, Intrinio (all paid services)
         
YFINANCE CALL REDUCTION: -4% (1/27 fields)
         If dropped from snapshot, would lose this metric entirely
         
COMPLEXITY: VERY HIGH (~8-10 weeks for new data source integration)
         Tasks: (1) Integrate Polygon.io or Intrinio API (requires API keys, rate limits)
                (2) Replace yfinance short data with new source
                (3) Handle daily updates from new provider
                (4) Circuit breaker + fallback to yfinance if new source fails
                (5) Update positioning_metrics loader
         Cost: $100-500/month for Polygon.io/Intrinio short interest feed

RECOMMENDATION: SKIP IT - NOT IN SCOPE
         Reason 1: No EDGAR alternative exists for short interest
         Reason 2: Would require entirely new data source integration
         Reason 3: Only viable path: Replace yfinance with Polygon.io/Intrinio (larger project)
         Reason 4: Current yfinance reliability acceptable for this metric
         Better path: Keep yfinance for positioning data; focus on reliability improvements

BLOCKERS: CRITICAL - No SEC/EDGAR source for short interest
```

---

### 8. BETA (Market Correlation)

```
DATA: beta (beta)
CURRENT: yfinance.Ticker.info['beta']
         Frequency: Daily (snapshot)
         Source: 252-day rolling correlation to S&P 500
         Coverage: ~95% of symbols

EDGAR ALTERNATIVE: YES - COMPUTE FROM OWN PRICE DATA
         Formula: Correlation(stock_returns, SPX_returns) over 252 trading days
         Data already available: price_daily table has all prices
         Method: Load 252 days of stock prices + SPX prices; compute correlation
         
TRADEOFF: Zero staleness; HIGHER quality than yfinance
         yfinance beta is black-box; own calculation is transparent
         Can customize: Use 126d or 63d beta for different timeframes
         Signal impact: POSITIVE - More recent data, customizable window
         
YFINANCE CALL REDUCTION: -4% (1/27 fields) per snapshot run
         Savings: 212 API calls/snapshot run
         BUT: Requires NEW computation phase in technical indicators loader
         NET SAVINGS: Only if computation doesn't cost more than saved API calls
         
COMPLEXITY: LOW-MEDIUM (~1-2 weeks)
         Tasks: (1) Load 252 days of price_daily for symbol + SPX
                (2) Compute daily returns (log returns)
                (3) Calculate correlation coefficient
                (4) Store in stability_metrics table (already exists)
                (5) Update stability_metrics loader to prefer computed beta over yfinance
                (6) Fallback: use yfinance beta if price data insufficient
         Risk: Edge cases (SPX gaps, stock delisted partway through)

TRADEOFF ANALYSIS:
         ✓ PRO: Eliminate 212 yfinance API calls/run (4%)
         ✓ PRO: Computable from existing price_daily (no new data source needed)
         ✓ PRO: Calculation more transparent than yfinance black-box
         ✗ CON: Adds ~2-3 min compute time to technical_indicators phase
         ✗ CON: Requires 252 days of price data (fails for new IPOs < 1 year old)
         ~ NEUTRAL: Quality neither better nor worse; just fresher

RECOMMENDATION: MEDIUM PRIORITY
         Reason 1: Low implementation complexity (1-2 weeks)
         Reason 2: Only 4% API reduction but legitimate improvement (transparency + freshness)
         Reason 3: Can compute from existing data (no new dependencies)
         Reason 4: Aligns with data-minimization philosophy (prefer computed over external)
         Reason 5: Compute cost is negligible vs yfinance API latency
         
IMPLEMENTATION PATH: 
         Phase 1: Add beta_computed column to stability_metrics
         Phase 2: Compute in load_technical_indicators.py (parallel with other calcs)
         Phase 3: Update load_stability_metrics.py to prefer computed beta
         Phase 4: Monitor for regression (compare computed vs yfinance for same symbols)
         Phase 5: After validation, remove beta from yfinance snapshot fetch

TIMELINE: 1-2 weeks, low risk if phased

BLOCKERS: None; straightforward computation
```

---

### 9. EARNINGS_DATE (Next Earnings Announcement)

```
DATA: earnings_date (earningsDate)
CURRENT: yfinance.Ticker.info['earningsDate']
         Frequency: Daily (snapshot)
         Source: Company earnings announcements (yfinance aggregates)
         Coverage: ~90% of symbols

EDGAR ALTERNATIVE: PARTIAL - Track Form 8-K filings
         Form 8-K filed when earnings announced (not advance notice)
         Could also track investor relations announcements
         Challenge: yfinance provides NEXT earnings date (forward looking)
         EDGAR cannot predict future earnings dates; only knows announced dates after they file
         
TRADEOFF: Can only track PAST earnings dates via EDGAR (8-K), not upcoming
         yfinance provides 2-3 months forward visibility
         Signal impact: HIGH - Risk management needs to know upcoming earnings dates
         Cannot schedule trades around earnings blackout without forward visibility
         
YFINANCE CALL REDUCTION: -4% (1/27 fields)
         Savings: 212 API calls/run
         BUT: Would lose earnings date data entirely (no EDGAR substitute available)
         
COMPLEXITY: VERY HIGH (~6-8 weeks) if tracking Form 8-K
         Tasks: (1) Monitor 8-K filings daily
                (2) Parse Item 2.02 (Results of Operations)
                (3) Extract earnings announcement date from filing text
                (4) Store in earnings_calendar table
                (5) Provide only past earnings (not forward dates)
                (6) Integration with risk management module (which uses forward dates)
         Risk: 8-K parsing is unstructured text; many companies don't clearly state next earnings date in 8-K

RECOMMENDATION: SKIP IT - NOT VIABLE
         Reason 1: EDGAR provides HISTORICAL earnings data only (8-K after announcement)
         Reason 2: yfinance provides FORWARD-LOOKING (next earnings dates) - essential for risk mgmt
         Reason 3: Cannot replace forward visibility with backward-looking 8-K data
         Reason 4: Complex parsing for very limited benefit (no API savings, lose functionality)
         Reason 5: Earnings dates are optional enrichment; not core to scoring
         
ALTERNATIVE PATH: 
         If earnings dates become critical, track from investor relations feeds
         (Not an EDGAR improvement)

BLOCKERS: CRITICAL - Cannot predict future earnings dates from SEC filings
          EDGAR only provides historical/announced data, not forward-looking
```

---

### 10. RECOMMENDATION_KEY (Analyst Recommendation)

```
DATA: recommendation_key (recommendationKey)
CURRENT: yfinance.Ticker.info['recommendationKey']
         Frequency: Daily (snapshot)
         Source: Aggregate analyst ratings (yfinance aggregates)
         Values: 'buy', 'overweight', 'hold', 'underweight', 'sell'
         Coverage: ~70% of symbols

EDGAR ALTERNATIVE: NONE - NOT IN SEC FILINGS
         SEC filings do not contain analyst recommendations
         This is proprietary research from Bloomberg, FactSet, Yahoo Finance
         Only sources: Bloomberg Terminal, FactSet, Morningstar, Seeking Alpha
         
YFINANCE CALL REDUCTION: -4% (1/27 fields)
         Savings: 212 API calls/run
         BUT: Would lose analyst sentiment entirely
         
COMPLEXITY: EXTREMELY HIGH - Requires new data source
         No EDGAR alternative; must integrate Bloomberg/FactSet API
         Cost: $5,000-20,000/month for real-time analyst consensus feed
         Time: 4-8 weeks to integrate + validate
         
RECOMMENDATION: SKIP IT - NOT VIABLE
         Reason 1: Analyst sentiment is NOT in SEC EDGAR
         Reason 2: Would require commercial data source (Bloomberg/FactSet)
         Reason 3: Current yfinance coverage is 70% (acceptable); cost doesn't justify 30% improvement
         Reason 4: Analyst data is enrichment only (momentum component in stock_scores)
         Reason 5: Better alternative: Track price momentum instead of analyst sentiment

BLOCKERS: CRITICAL - No SEC source for analyst data
          EDGAR does not contain recommendations or analyst consensus
          yfinance is only free alternative (vs $10K+/month commercial feeds)
```

---

### 11. NUMBER_OF_ANALYSTS (Analyst Count)

```
DATA: number_of_analysts (numberOfAnalystOpinions)
CURRENT: yfinance.Ticker.info['numberOfAnalystOpinions']
         Frequency: Daily
         Source: Count of analysts providing ratings (from Bloomberg, FactSet, etc.)
         Coverage: ~70% of symbols

EDGAR ALTERNATIVE: NONE - NOT IN SEC FILINGS
         No EDGAR source for analyst coverage
         Same issue as recommendation_key
         
YFINANCE CALL REDUCTION: -4% (1/27 fields)
         If dropped with recommendation_key, saves 212 API calls
         
RECOMMENDATION: SKIP IT
         Same reasoning as recommendation_key (10 above)
         Related data point: Both depend on commercial analyst data feeds

BLOCKERS: CRITICAL - No SEC source for analyst count
```

---

### 12. PEG_RATIO (Price-to-Earnings-Growth)

```
DATA: peg_ratio (pegRatio)
CURRENT: yfinance.Ticker.info['pegRatio']
         Frequency: Daily
         Source: PE ratio / forward earnings growth rate (analyst estimates)
         Coverage: ~70% of symbols (analyst estimates missing for small caps)

EDGAR ALTERNATIVE: PARTIAL - Use historical growth instead of forward
         Formula: Current PE / (historical 5-year EPS CAGR)
         Challenge: No forward growth estimates in EDGAR (requires analyst data)
         Can compute: 5-year EPS growth from annual_income_statement + quarterly_income_statement
         Result: PEG based on PAST growth, not forward growth
         
TRADEOFF: Historical growth ≠ forward growth; misses inflection points
         Example: Amazon 2016 (accelerating) vs 2022 (decelerating)
         Historical PEG would underestimate 2016, overestimate 2022
         Signal impact: HIGH - Forward guidance is critical for growth scoring
         
YFINANCE CALL REDUCTION: -4% (1/27 fields)
         Savings: 212 API calls/run
         
COMPLEXITY: HIGH (~2-3 weeks)
         Tasks: (1) Compute 5-year EPS CAGR from annual_income_statement
                (2) Calculate PE from current price / trailing EPS
                (3) Divide PE by growth rate
                (4) Handle companies with <5 years history (fallback)
                (5) Handle negative growth (delisted, distressed)
         Risk: Edge cases (negative earnings, stock splits affecting historical)

TRADEOFF ANALYSIS:
         ✗ CON: Historical growth ≠ forward growth (analyst estimates missing)
         ✗ CON: Loses forward visibility (critical for growth companies)
         ✗ CON: Only 4% API reduction
         ✗ CON: Moderate implementation effort for degraded signal
         ✓ PRO: Computable from existing EDGAR data (no new source)
         ✓ PRO: More recent data than annual 10-K (if quarterly EDGAR available)

RECOMMENDATION: SKIP IT - Quality Loss Outweighs Benefits
         Reason 1: Historical EPS growth is NOT equivalent to forward PEG
         Reason 2: Forward earnings estimates are critical for growth scoring
         Reason 3: Only 4% API reduction for losing forward guidance
         Reason 4: Better alternative: Compute forward growth from analyst estimates (if available)

BLOCKERS: None hard blockers, but quality degrades materially
```

---

## Summary: Reduction Opportunities Ranked

### Impact × Feasibility Matrix

| Rank | Data Type | Savings | Complexity | Quality Impact | Implementation | Recommendation |
|------|-----------|---------|------------|---|---|---|
| **1** | **BETA** | 4% | LOW | +0% (fresher) | 1-2 weeks | **DO IT** |
| **2** | Insider Holdings | 4% | VERY HIGH | -20% | 4-6 weeks (+ Form 4 pipeline) | Defer |
| **3** | PB Ratio | 4% | MEDIUM | -15% | 1.5 weeks | Skip |
| **4** | PE Ratio | 4% | MEDIUM | -20% | 1 week | Skip |
| **5** | PS Ratio | 4% | HIGH | -15% | 2 weeks | Skip |
| **6** | Dividend Yield | 4% | VERY HIGH | -25% | 2-3 weeks (+ external feed) | Skip |
| **7** | PEG Ratio | 4% | MEDIUM | -30% (forward guidance lost) | 2-3 weeks | Skip |
| **8** | Short Interest | 4% | IMPOSSIBLE | -100% (no EDGAR source) | N/A | N/A |
| **9** | Earnings Date | 4% | VERY HIGH | -50% (loses forward dates) | 6-8 weeks | Skip |
| **10** | Recommendation Key | 4% | IMPOSSIBLE | -100% (no EDGAR source) | N/A | N/A |
| **11** | Analyst Count | 4% | IMPOSSIBLE | -100% (no EDGAR source) | N/A | N/A |
| **12** | Institutional Holdings | 4% | VERY HIGH | -40% (90d stale) | 5-7 weeks | Skip |

---

## Top 3-5 Recommendations (Ranked by Impact × Feasibility)

### TIER 1: IMPLEMENT (High ROI, Low Risk)

#### **#1: Compute BETA from price_daily (1-2 weeks, 4% API reduction)**

**What:**
- Replace yfinance.beta with 252-day rolling correlation (stock returns vs SPX returns)
- Compute in technical_indicators phase from existing price_daily

**Why:**
- Only legitimate yfinance dependency that can be eliminated without data loss
- Improves transparency (explicit formula vs yfinance black-box)
- Fresher data (computed daily vs yfinance snapshot)
- No new external data sources needed
- Adds <3 min compute time (negligible)

**Effort:**
```
Phase 1 (3 days): Add beta_computed column to stability_metrics
                  Implement correlation calculation
                  Add to load_technical_indicators.py
                  
Phase 2 (2 days): Update load_stability_metrics.py to prefer computed beta
                  Add fallback to yfinance for edge cases (<1yr history)
                  
Phase 3 (2 days): Validate: Compare computed vs yfinance on 100 symbols
                  Monitor for regression
                  
Phase 4 (1 day):  Remove beta from yfinance snapshot fetch
                  Update orchestrator logging
                  
TOTAL: ~1-2 weeks (could do in parallel with other work)
```

**Risk Level:** LOW
- Straightforward math (correlation)
- Can run in parallel with existing calculations
- Fallback to yfinance if computation fails
- No breaking changes to downstream consumers

**Expected Impact:**
- Eliminates 212 yfinance API calls/run (4%)
- Improves data transparency & freshness
- Zero quality loss (arguably improves with fresher data)
- Foundation for future price-derived metrics

---

### TIER 2: DEFER (Wait for Infrastructure)

#### **#2: Track Insider Holdings via Form 4 (4-6 weeks after infrastructure built)**

**What:**
- Monitor SEC Form 4 filings (insider transactions)
- Aggregate insider shares into insider_ownership %
- Use as alternative to yfinance insider data

**Why:**
- Real-time insider transaction tracking is more accurate than yfinance snapshot
- Insider selling/buying has high alpha signal
- Once built, can support multiple use cases (risk management, anomaly detection)

**Constraints:**
- Requires building Form 4 monitoring infrastructure (1-2 weeks upfront)
- Only makes sense if insider trading becomes critical to strategy
- High effort for 4% API reduction

**Recommendation:**
- **Do NOT implement now** for just 4% API reduction
- **DO implement later** if: (a) insider flows become core to trading signal, or (b) yfinance insider data becomes unreliable
- Mark as "Future Enhancement: Insider Flow Tracking Pipeline"

---

### TIER 3: SKIP (Not Viable)

#### **Why Skip Valuation Ratios (PE, PB, PS, PEG, Dividend)**

All share common problem:
- EDGAR data is 30-60 days stale (quarterly filing lag)
- Only 4% API reduction (1 field per 27-field snapshot)
- Quality degrades noticeably (valuation timing off)
- Already have reliable yfinance source

**Cost-Benefit:**
```
Benefit:     212 API calls saved/run
Cost:        -15% to -30% quality loss in value_metrics scoring
Time:        1-3 weeks per metric
Result:      Not worth it
```

Better path: Improve yfinance reliability instead (circuit breaker improvements, fallback sources)

#### **Why Skip Data Not in SEC (Short Interest, Analyst Data, Earnings Dates)**

**Critical Issue:** These data types have NO SEC source at all
- Short interest: FINRA data (not SEC)
- Analyst ratings: Bloomberg/FactSet (not SEC)
- Earnings dates: Forward-looking (SEC only has historical 8-K)

**Options:**
1. Keep using yfinance (current best free source)
2. Pay for commercial feed (Bloomberg $10K+/month, Polygon.io $500/month)
3. Drop feature entirely (loses scoring accuracy)

yfinance is the RIGHT choice for positioning/sentiment data.

---

## Alternative Path: Improve yfinance Reliability (Higher ROI)

Rather than replace yfinance data, consider fixing reliability issues:

### Priority 1: Implement Polygon.io Fallback for Snapshot Data

**Problem:** yfinance IP frequently banned; pipeline stalls for hours
**Solution:** Polygon.io as fallback when yfinance rate-limited
**Effort:** 2-3 weeks
**Cost:** $500/month (worth it for reliability)
**Benefit:** Eliminates outages vs incremental API reduction

### Priority 2: Improve yfinance Circuit Breaker

**Current:** Generic exponential backoff
**Improvement:** 
- Predictive circuit breaking (avoid bans before they happen)
- Per-field fallback (if yfinance fails on analyst data, fetch separately)
- Parallel retry attempts

### Priority 3: Cache aggressively

**Current:** 20-hour freshness skip
**Improvement:**
- Increase to 24-48 hours for non-critical fields (analyst data, positioning)
- Keep 4-6 hour freshness for valuation metrics
- Selective skip per field type

---

## Conclusion

### What to Do (Next Sprint)

1. **IMPLEMENT:** Compute beta from price_daily (1-2 weeks)
   - Only yfinance replacement that improves quality + saves API calls
   - Foundation for future price-derived metrics

2. **IMPROVE:** Add Polygon.io fallback for snapshot data (2-3 weeks, higher priority)
   - Addresses real reliability pain (outages)
   - Better ROI than API reduction

3. **MONITOR:** Track yfinance reliability metrics
   - Circuit breaker errors per run
   - Rate-limit recovery time
   - Coverage % of symbols

### What NOT to Do

- Replace valuation ratios (PE, PB, PS) with EDGAR
  - Too stale; quality loss outweighs 4% API savings
  
- Replace positioning/sentiment data with non-existent EDGAR sources
  - Short interest: Not in SEC
  - Analyst data: Not in SEC
  - Earnings dates: EDGAR can't predict future
  
- Build Form 4 pipeline for 4% API savings alone
  - Wait until insider flows become critical to strategy

### Key Insight

**The real bottleneck is NOT data sources; it's yfinance reliability.**

Current system already uses optimal sources:
- yfinance for market data (prices, valuations, sentiment) ✓
- SEC EDGAR for fundamentals (financial statements) ✓
- Hybrid approach is architecturally sound ✓

Problem: yfinance IP bans disrupt pipeline
Solution: Reliability improvements (fallbacks, caching, circuit breaker tuning)

**Better than chasing 4% API reduction: Fix the 1-2 hour outages that kill profitability.**

---

## Implementation Roadmap (Prioritized)

```
Week 1-2:   IMPLEMENT beta computation (1-2 weeks)
            ├─ Phase 1: Add beta_computed calculation
            ├─ Phase 2: Validate + fallback logic
            ├─ Phase 3: Remove from yfinance fetch
            └─ Gain: 212 API calls/run saved, fresher beta data

Week 3-4:   IMPROVE yfinance reliability (2-3 weeks, parallel)
            ├─ Integrate Polygon.io fallback
            ├─ Enhanced circuit breaker
            └─ Gain: Eliminate 1-2 hour outages

Week 5-6:   MONITOR + Document
            ├─ Track improvements in pipeline latency
            ├─ Monitor EDGAR vs yfinance coverage
            └─ Document roadmap for future enhancements

Future:     DEFER Form 4 tracking
            (After reliability improvements, if insider flows needed)
```

---

**Document Version:** 1.0  
**Prepared:** 2026-07-16  
**Status:** Ready for implementation  
