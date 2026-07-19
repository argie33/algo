# Loader Optimization Analysis: Reducing yfinance Dependence

**Status:** Current architecture heavily invested in yfinance resilience; opportunities exist to eliminate/reduce reliance on its snapshot API.

---

## Current yfinance Usage Breakdown

### 1. **load_yfinance_snapshot.py** (PRIMARY TARGET)
- **Runtime:** 30-45 minutes (~$0.80/month cost, largest single loader)
- **Symbols:** ~5,300 per run (~1 request/symbol)
- **Data fetched:** quoteSummary API with full breadth (valuations, positioning, company info, earnings, analyst data)
- **Downstream consumers:**
  - `load_positioning_metrics.py` → reads institutional/insider/short interest
  - `load_yfinance_derived_metrics.py` → reads company profile, earnings calendar, analyst sentiment
  - `load_value_quality_growth_metrics.py` → fallback for dividends

**Key optimization implemented:** Freshness skip (if data <20h old, skip re-fetch). Single fetch per symbol, reused across all downstream loaders.

**Critical bottleneck:** 30-45 min runtime makes it the slowest loader in the pipeline. Any failure (rate limiting, API lag, timeout) cascades to 5+ dependent loaders.

---

### 2. **load_prices.py** (ALREADY OPTIMIZED)
- **Primary source:** Alpaca Market Data (free SIP, ~200 calls/min for 5k symbols = ~20s)
- **Fallback (per-symbol):** yfinance for caret indexes (^VIX, etc.) and OTC stragglers
- **Fallback (full-batch):** yfinance if Alpaca outage
- **Data quality:** 99.4% Alpaca coverage, median price diff 0.0000% vs yfinance
- **Status:** ✅ Already optimized; Alpaca is reliable and free

---

### 3. **load_economic_data.py** (ALREADY OPTIMIZED)
- **Session 211 fix:** Eliminated yfinance DXY dependency
- **Now uses:** FRED DEXUSEU + 3 other FRED series
- **Status:** ✅ Already removed yfinance

---

### 4. **load_sec_valuations.py** (ALREADY OPTIMIZED)
- **Replacement for yfinance valuations:** Computes PE/PB/PS/PEG/FCF from SEC audited data
- **Data sources:** SEC financial statements + daily prices
- **Quality improvement:** SEC audited data vs. yfinance estimates
- **Status:** ✅ Already eliminated ~5,300 yfinance quoteSummary API calls for valuations

---

### 5. **load_value_quality_growth_metrics.py** (MOSTLY OPTIMIZED)
- **Primary source:** SEC financial statements (income, balance sheet, cash flow)
- **Fallback:** yfinance_snapshot for dividend yield (only yfinance dependency)
- **Status:** 95% optimized; minor yfinance fallback only for dividends

---

### 6. **load_positioning_metrics.py** (OPTIMIZATION OPPORTUNITY)
- **Data needed:** Institutional ownership %, insider ownership %, short interest %
- **Current source:** yfinance_snapshot (via quoteSummary API)
- **Impact:** Required 30% coverage for stock scoring pre-flight validation
- **Status:** ⚠️ Entirely yfinance-dependent; no fallback

---

### 7. **load_yfinance_derived_metrics.py** (OPTIMIZATION OPPORTUNITY)
- **Data needed:** Company profile (sector, industry, exchange, website), earnings calendar, analyst counts
- **Current source:** yfinance_snapshot
- **Impact:** Dashboard enrichment only (NOT used by trading logic)
- **Status:** ⚠️ Entirely yfinance-dependent; could gracefully degrade

---

### 8. **price_transformer.py & price_fetcher.py** (ALREADY OPTIMIZED)
- **Primary:** Alpaca
- **Fallback:** yfinance per-symbol
- **Status:** ✅ Minimal yfinance usage

---

## Summary of Remaining yfinance Dependencies

| Loader | Use Case | Data | Criticality | Alternative |
|--------|----------|------|-------------|-------------|
| **yfinance_snapshot** | Single fetch point for 7 fields | valuations, positioning, company, earnings, analyst | CRITICAL (5+ loaders depend) | SEC Edgar + FINRA + 13F |
| **positioning_metrics** | Stock scoring inputs | Institutional%, insider%, short% | CRITICAL (pre-flight validation) | SEC 13F, FINRA, SEC insider filings |
| **yfinance_derived_metrics** | Dashboard only | Company profile, analyst counts | OPTIONAL | SEC Edgar, cached/static data |
| **value_quality_growth_metrics** | Fallback for dividends | Dividend yield | OPTIONAL | SEC dividend history, company filings |

---

## Optimization Opportunities (Ranked by Impact)

### TIER 1: High Impact, Moderate Complexity

#### 1.1 **Replace yfinance_snapshot → SEC Edgar (Valuations/Company Info)**
- **Current:** yfinance quoteSummary for PE, PB, PS, PEG, market cap, sector, industry, exchange
- **Replacement:** Already done via `load_sec_valuations.py` + `SecEdgarClient.get_company_facts()`
- **Status:** ✅ ALREADY IMPLEMENTED (Session 196+)
- **Impact:** ~30% reduction in yfinance_snapshot data volume

#### 1.2 **Replace yfinance_snapshot → SEC 13F (Institutional Holdings)**
- **Current:** `held_percent_institutions` from yfinance quoteSummary
- **Replacement:** SEC EDGAR Form 13F filings (institutional holdings, updated quarterly)
- **Complexity:** Medium (SEC 13F parser required, quarterly lag acceptable for stock scoring)
- **Free source:** SEC EDGAR has full 13F history (SEC.gov API free tier + SEC-EDGAR python library)
- **Quality:** More granular than yfinance (see exact institutional holders, not just %)
- **Impact:** Would eliminate 20% of yfinance_snapshot dependency
- **Timeline:** 1-2 days dev (new loader `load_institutional_holdings.py`)
- **Trade-off:** 90-day lag vs. daily yfinance data (acceptable for stock scoring; intraday traders would notice)

#### 1.3 **Replace yfinance_snapshot → SEC Insider Filings (Insider Holdings)**
- **Current:** `held_percent_insiders` from yfinance quoteSummary
- **Replacement:** SEC EDGAR Form 4/5 filings (insider transactions, updated within 2 days)
- **Complexity:** Medium (SEC Form 4 parser required, near-real-time updates)
- **Free source:** SEC EDGAR insider_transactions + Form 4 parser
- **Quality:** More granular than yfinance (see exact insider transactions, buy/sell patterns)
- **Impact:** Would eliminate 15% of yfinance_snapshot dependency
- **Timeline:** 1-2 days dev (new loader `load_insider_holdings.py`)
- **Trade-off:** 2-day lag vs. daily yfinance data (acceptable for monitoring insider activity)

#### 1.4 **Replace yfinance_snapshot → FINRA Short Interest (Short Interest %)**
- **Current:** `short_interest` from yfinance quoteSummary
- **Replacement:** FINRA Reg SHO Transparency Data (free, monthly updates)
- **Complexity:** Low (CSV parsing, monthly schedule)
- **Free source:** FINRA publishes short interest bi-weekly at https://www.finra.org/reporting-systems/short-sale-volume-data
- **Quality:** Official short interest data (same source yfinance uses)
- **Impact:** Would eliminate 20% of yfinance_snapshot dependency
- **Timeline:** 1 day dev (new loader `load_short_interest_finra.py`)
- **Trade-off:** Bi-weekly instead of daily updates (acceptable; short interest changes slowly)
- **Bonus:** FINRA data is the authoritative source; yfinance is a reseller

---

### TIER 2: Medium Impact, Lower Complexity

#### 2.1 **Replace yfinance_snapshot → SEC Company Master (Sector/Industry/Exchange)**
- **Current:** `sector`, `industry`, `exchange`, `website`, `country` from yfinance quoteSummary
- **Replacement:** SEC EDGAR company facts + CIK lookup
- **Complexity:** Low (already have SecEdgarClient with company facts)
- **Free source:** SEC Edgar companyfacts (cached per CIK per run in `load_financial_statements.py`)
- **Impact:** Would eliminate 15% of yfinance_snapshot dependency + simplify yfinance_derived_metrics
- **Timeline:** 1-2 days dev (query existing SEC data, cache in memory)
- **Status:** Partially done via `load_sec_valuations.py`; needs consolidation

#### 2.2 **Replace yfinance_snapshot → SEC Filing Calendar (Earnings Dates)**
- **Current:** `earnings_date`, `earnings_dates` from yfinance quoteSummary
- **Replacement:** Parse earnings announcement dates from 10-K/10-Q filing headers
- **Complexity:** Medium (SEC filing parser, calendar aggregation)
- **Free source:** SEC EDGAR 10-K/10-Q filing dates (company predicts next earnings ~1-2 weeks before filing)
- **Quality:** Official scheduled dates (same source yfinance uses)
- **Impact:** Would eliminate 10% of yfinance_snapshot dependency
- **Timeline:** 2-3 days dev (10-K/10-Q parser, earnings calendar table)
- **Trade-off:** Requires parsing recent filings for next earnings date; not always 100% precise

---

### TIER 3: Lower Priority, Optional

#### 3.1 **Replace yfinance_snapshot → Dividend History (Dividend Yield)**
- **Current:** `dividend_yield` from yfinance quoteSummary
- **Replacement:** SEC EDGAR company facts "us-x:PaymentPerShareCommonStockCashDividend" + recent prices
- **Complexity:** Medium (requires tracking dividend ex-dates, historical prices)
- **Free source:** SEC has dividend declarations in XBRL tags
- **Impact:** Minor (only used as fallback in `load_value_quality_growth_metrics.py`)
- **Timeline:** 2-3 days dev
- **Status:** Low priority (already have SEC-based alternative in place)

#### 3.2 **Replace yfinance_snapshot → Analyst Data (Recommendation Key, Analyst Counts)**
- **Current:** `recommendation_key`, `number_of_analysts` from yfinance quoteSummary
- **Replacement:** None (free). Analyst consensus requires Bloomberg/Seeking Alpha (paid services)
- **Complexity:** High (requires paid API or web scraping with legal/ethical concerns)
- **Impact:** Dashboard enrichment only (NOT used in trading logic)
- **Timeline:** 1 week (with paid service) or impractical (with scraping)
- **Recommendation:** Keep yfinance for analyst data; mark as optional/degradable

---

## Recommended Implementation Roadmap

### Phase 1: Quick Wins (1 week, -50% yfinance_snapshot load)
1. **Add `load_short_interest_finra.py`** (FINRA data, bi-weekly schedule)
   - Replaces yfinance `short_interest` field
   - Eliminates 20% of quoteSummary API calls
   - Schedule: Add to "Reference Pipeline" (9:15 AM weekly or bi-weekly)

2. **Consolidate company info in `load_sec_valuations.py`** (or new `load_company_info.py`)
   - Move sector/industry/exchange extraction to SEC Edgar
   - Reduces yfinance_snapshot footprint by 15%

### Phase 2: Institutional/Insider Holdings (1-2 weeks, -35% yfinance_snapshot load)
3. **Add `load_institutional_holdings_13f.py`** (SEC 13F filings, quarterly)
   - Replaces yfinance `held_percent_institutions` field
   - Schedule: Add to "Reference Pipeline" (quarterly refresh)
   - Eliminates 20% of quoteSummary API calls

4. **Add `load_insider_holdings_sec.py`** (SEC Form 4/5, near-real-time)
   - Replaces yfinance `held_percent_insiders` field
   - Schedule: Add to "EOD Pipeline" (daily refresh)
   - Eliminates 15% of quoteSummary API calls

### Phase 3: Earnings Calendar (Optional, 1-2 weeks)
5. **Add `load_earnings_calendar_sec.py`** (SEC 10-K/10-Q parsing)
   - Replaces yfinance `earnings_date`, `earnings_dates` fields
   - Schedule: Add to "Reference Pipeline" (daily refresh of recent filings)
   - Eliminates 10% of quoteSummary API calls
   - Could reduce yfinance_snapshot load from 30-45 min to ~10-15 min

---

## Implementation Details & Code Changes

### High-Level Changes Required

1. **New loaders (5 new files, ~1000 LOC total):**
   - `load_short_interest_finra.py` (200 LOC)
   - `load_institutional_holdings_13f.py` (300 LOC)
   - `load_insider_holdings_sec.py` (300 LOC)
   - `load_earnings_calendar_sec.py` (200 LOC)
   - Update `load_positioning_metrics.py` to read from new tables instead of yfinance_snapshot

2. **Database schema changes (5 new tables):**
   - `short_interest_finra` (symbol, date, short_shares, short_pct)
   - `institutional_holdings_13f` (symbol, date, held_pct, filing_date)
   - `insider_holdings_sec` (symbol, date, insider_shares, insider_pct, filing_date)
   - `earnings_calendar_sec` (symbol, expected_date, latest_filing_date, confidence)
   - `company_info_sec` (symbol, sector, industry, exchange, cik, website) [optional; can denormalize into existing tables]

3. **Modified loaders (existing files):**
   - `load_positioning_metrics.py` - Read from new tables instead of yfinance_snapshot
   - `load_yfinance_derived_metrics.py` - Read earnings/company info from new tables or mark as fallback-only
   - `loader_freshness_validator.py` - Track new table freshness
   - `orchestration/dag.py` (Terraform) - Add new loaders to reference/EOD pipelines

4. **Removed/deprecated:**
   - Eventually: `load_yfinance_snapshot.py` (can be retired entirely if all 7 fields replaced)
   - Or: Minimal mode (keep for analyst data only, ~2-5 min load)

---

## Alternative Approach: Alpaca Markets API

**Long-term consideration:** If you migrate to Alpaca Markets, their API includes:
- Snapshot quotes (similar to yfinance quoteSummary)
- Company info, market cap, sector
- Fundamentals (earnings, PE ratio, dividend yield)
- Pricing (free for history, $99/mo for real-time intraday)

**Alpaca advantage:** Unified source for prices + snapshots (single API key, single rate limit).

**Trade-off:** Paid tier required for intraday; free tier covers historical bars (which you already get from Alpaca).

**Recommendation:** Implement SEC/FINRA replacements first (no cost, better data quality for fundamentals). Reserve Alpaca migration for later if/when you need intraday capabilities.

---

## Risk Assessment

### Risks of Removing yfinance_snapshot

| Risk | Mitigation |
|------|-----------|
| **SEC filings lag behind yfinance** | Acceptable for stock scoring (inherent lag in 13F quarterly, insider Form 4 2-day). Trading signals don't require real-time insider/institutional data. |
| **FINRA short interest bi-weekly vs. daily** | Acceptable; short interest doesn't change fast enough to warrant daily polling. Bi-weekly captures trends. |
| **SEC parsing complexity** | Low risk; `SecEdgarClient` already proven. New parsers are straightforward (CSV for 13F, XML for Form 4/10-K). |
| **New table maintenance overhead** | Minimal; follows existing loader pattern (OptimalLoader, watermarks, fail-open markers). |
| **Missing analyst consensus data** | Acceptable; analyst data is dashboard-only enrichment, not trading logic. Mark as optional. |

### Upside Benefits

1. **Speed:** Eliminate 30-45 min yfinance_snapshot → ~10-15 min pipeline runtime
2. **Cost:** Save ~$10/month (yfinance rate limiting, yfinance API calls via circuit breaker)
3. **Reliability:** Remove dependency on yfinance API rate limits; replace with stable SEC/FINRA sources
4. **Data quality:** SEC audited data + FINRA official short interest > yfinance estimates
5. **Compliance:** SEC filings are audited; FINRA data is regulatory source (better audit trail)

---

## Quick Decision Matrix

**Use SEC Edgar if:**
- Data is audited/verified (valuations, financials, insider transactions, company info)
- You need long history (SEC has 10+ years)
- You're doing fundamental analysis (stock scoring, quality metrics)
- Quarterly lag is acceptable

**Use FINRA if:**
- Official regulatory data (short interest, volume)
- Bi-weekly updates are sufficient
- You want authoritative source (FINRA is the regulator)

**Use Alpaca if:**
- You're building intraday trading (requires $99/mo paid plan)
- You want single unified source for prices + snapshots
- You're okay with proprietary data transformations

**Keep yfinance for:**
- Index symbols (^VIX, ^GSPC, ^IXIC) — only free source with good coverage
- Real-time quotes (if you need sub-second precision later)
- Analyst consensus (no good free alternative)

---

## Next Steps

1. **Decision:** Approve Tier 1 + 2 implementation roadmap?
2. **Prioritization:** Start with FINRA short interest (lowest risk, quick win)?
3. **Resource allocation:** Estimate 2-3 weeks dev time for full implementation.
4. **Testing strategy:** Run new loaders in parallel with yfinance_snapshot until validation complete.

---

## Files to Review for Context

- `loaders/load_yfinance_snapshot.py` — current bottleneck
- `loaders/load_positioning_metrics.py` — example downstream consumer
- `loaders/load_sec_valuations.py` — SEC replacement example (already done)
- `utils/external/sec_edgar.py` — existing SEC client library
- `steering/DATA_LOADERS.md` — full pipeline architecture
