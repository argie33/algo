# Loader Strategy Update: Comprehensive Optimization Roadmap
**Session 234 | Status: Strategic Analysis Complete**

---

## Executive Summary

Your loader architecture is **already well-optimized** for reliability. Phase 1 (FINRA short interest) has been built but not yet deployed. The remaining opportunities are:

1. **Deploy Phase 1** (FINRA short interest) - Ready to go, eliminates ~20% yfinance dependency
2. **Execute Phase 2-3** (SEC 13F/Form 4/Earnings) - 1-2 weeks dev, eliminates 50% more
3. **Compute 52-week extremes** - Shift from yfinance to price_daily (quick win)
4. **Evaluate alternative data sources** - IEX Cloud, Polygon, others for incremental improvements
5. **Plan Alpaca expansion** - Beyond prices to fundamentals/earnings (future)

---

## Current State (Session 234)

### ✅ Already Deployed
- **Alpaca prices** (primary) + yfinance fallback → ~99.4% coverage
- **SEC financials** (income/balance/cash flow, annual/quarterly)
- **SEC valuations** (PE/PB/PS/PEG/FCF computed from SEC data)
- **FRED economic data** (no yfinance DXY dependency)
- **Technical indicators** (computed from price_daily)
- **Market health** (VIX from prices, breadth, yield curve)

**yfinance_snapshot runtime:** 30-45 minutes (single largest bottleneck)

---

## Phase 1: Ready for Deployment (Session 225 Implementation)

### Status: ✅ Code Complete, Awaiting Deployment

**What was built:**
1. `loaders/load_short_interest_finra.py` - 150 LOC
2. `migrations/1012_create_short_interest_finra_table.sql`
3. `loaders/load_positioning_metrics.py` - Refactored to read from multiple sources
4. `terraform/modules/loaders/main.tf` - Updated with new loader config

**What it does:**
- Fetches official FINRA Reg SHO short interest (bi-weekly, authoritative source)
- Replaces yfinance `short_interest` field (~20% of yfinance_snapshot calls)
- Graceful degradation: marks data_unavailable only if ALL sources unavailable

**Deployment checklist:**
- [ ] Run `migrations/1012_create_short_interest_finra_table.sql`
- [ ] Deploy loaders + Terraform
- [ ] Test: Run `python scripts/run_loader.py load_short_interest_finra` locally
- [ ] Verify dashboard shows positioning metrics with FINRA data

**Expected impact:** Eliminates ~5,300 quoteSummary API calls per run

---

## Phase 2-3 Opportunities (1-2 weeks dev)

### Phase 2: SEC Institutional & Insider Holdings

#### 2.1 Institutional Holdings (SEC Form 13F)
- **Data source:** SEC EDGAR Form 13F filings (quarterly, audited institutional holdings)
- **Replaces:** yfinance `held_percent_institutions`
- **Quality:** More granular than yfinance; see exact institutional holders, not just %
- **Lag:** 90 days (acceptable for stock scoring)
- **Implementation:** New loader `load_institutional_holdings_13f.py`
- **Impact:** Eliminates ~20% of yfinance_snapshot dependency
- **Timeline:** 1 week dev
- **Complexity:** Medium (SEC 13F parser, quarterly schedule)

#### 2.2 Insider Holdings (SEC Form 4/5)
- **Data source:** SEC EDGAR insider transaction filings (updated within 2 days)
- **Replaces:** yfinance `held_percent_insiders`
- **Quality:** More granular; see exact insider transactions, buy/sell patterns
- **Lag:** 2 days (near real-time)
- **Implementation:** New loader `load_insider_holdings_sec.py`
- **Impact:** Eliminates ~15% of yfinance_snapshot dependency
- **Timeline:** 1 week dev
- **Complexity:** Medium (Form 4 parser, daily refresh)

**Phase 2 combined impact:** -35% yfinance_snapshot load

---

### Phase 3: Company Info & Earnings Calendar

#### 3.1 Consolidated Company Info (SEC Master)
- **Current fields:** sector, industry, exchange, website, country, long_name
- **Data source:** SEC company facts + ticker mapping
- **Quality:** SEC-audited company records
- **Implementation:** Consolidate into new `load_company_info_sec.py` or denormalize into existing tables
- **Impact:** Eliminates ~15% of yfinance_snapshot dependency
- **Timeline:** 3-5 days (mostly reorg of existing SEC reads)
- **Complexity:** Low (data already fetched by `load_financial_statements.py`)

#### 3.2 Earnings Calendar (SEC Filing Dates)
- **Data source:** SEC 10-K/10-Q filing headers (companies announce in advance)
- **Replaces:** yfinance `earnings_date`, `earnings_dates`
- **Quality:** Official scheduled dates; same source yfinance uses
- **Implementation:** New loader `load_earnings_calendar_sec.py`
- **Impact:** Eliminates ~10% of yfinance_snapshot dependency
- **Timeline:** 1 week dev (10-K/10-Q parser, calendar aggregation)
- **Complexity:** Medium (parsing + calendar logic)

**Phase 3 combined impact:** -25% yfinance_snapshot load

---

## Quick Wins: Derived Data (No API Calls)

### 4.1 52-Week Extremes (from price_daily)
- **Current source:** yfinance `fifty_two_week_high`, `fifty_two_week_low`
- **Alternative:** Compute in SQL from `price_daily` (high/low over last 252 trading days)
- **Implementation:** Add to `load_technical_indicators.py` or new `load_price_extremes.py`
- **Impact:** Eliminates ~5% of yfinance_snapshot dependency
- **Timeline:** 1-2 days dev
- **Complexity:** Very Low (SQL aggregate)
- **Quality trade-off:** Daily update vs. real-time (acceptable for scoring)

### 4.2 Market Cap (Compute from Shares Outstanding + Price)
- **Current source:** yfinance `market_cap` (sometimes stale)
- **Alternative:** Compute from SEC shares_outstanding + latest price
- **Implementation:** Add to `load_sec_valuations.py` or `load_technical_indicators.py`
- **Impact:** Eliminates ~3% of yfinance_snapshot dependency
- **Timeline:** 1 day dev (already have shares_outstanding from SEC)
- **Complexity:** Very Low (arithmetic)
- **Quality improvement:** Always current (derived from latest price + recent SEC data)

**Quick wins combined impact:** -8% yfinance_snapshot load

---

## Summary: Impact by Phase

| Phase | Focus | Impact | Timeline | Effort | Status |
|-------|-------|--------|----------|--------|--------|
| **Phase 1** | FINRA short interest | -20% | Ready now | Low | ✅ Code complete |
| **Phase 2** | SEC 13F + Form 4 | -35% | 1-2 weeks | Medium | Planned |
| **Phase 3** | Company info + earnings | -25% | 1-2 weeks | Medium | Planned |
| **Quick Wins** | Computed fields | -8% | 1 week | Very Low | Quick |
| **Total** | All of above | **-88%** | **3-4 weeks** | **Moderate** | On roadmap |

**Result:** yfinance_snapshot from 30-45 minutes down to **~5-10 minutes** (analyst data only)

---

## Alternative Data Sources to Evaluate

### IEX Cloud (Paid, $9/mo student tier, $99+/mo pro)
**Pros:**
- Company info, earnings calendar, dividends
- Fundamental data (PE, PB, PS, market cap)
- Insider transactions
- Unified source (prices + fundamentals)
- Better rate limits than yfinance

**Cons:**
- Paid service (though affordable)
- Another API dependency
- Not as comprehensive as SEC + FINRA combo

**Recommendation:** Consider as Phase 4 once SEC foundation is solid. Good for earnings alerts.

### Polygon.io (Paid, $200+/mo for fundamentals)
**Pros:**
- Unified market data + fundamentals
- Strong technical support
- Intraday support

**Cons:**
- Expensive for your use case
- Overkill for EOD scoring

**Recommendation:** Skip unless you move to intraday trading.

### CBOE (Paid, for options data)
**Pros:**
- Official option expiration calendar
- Put/call volume

**Cons:**
- Not needed for current stock scoring
- Paid API

**Recommendation:** Skip for now.

### Yahoo Finance (Paid API, $10-20/mo)
**Pros:**
- Official tier; bypasses rate limits
- Same data as free version
- Faster support

**Cons:**
- Just adds reliability to current setup; doesn't reduce yfinance dependency
- Same data quality issues (analyst data is proprietary estimates)

**Recommendation:** Not worth it if you replace snapshot with SEC/FINRA.

---

## Alpaca Expansion Opportunities (Future)

### Current: Prices only
Alpaca free plan serves:
- Daily OHLCV bars (SIP consolidated tape, $0/mo)
- ~200 API calls/min (covers ~8,500 symbols in 43 requests ≈ 20 seconds)

### Future: Snapshots & Fundamentals (Paid, $99/mo)
Alpaca $99/mo "Algo Trader Plus" adds:
- Real-time quotes (intraday, not needed for EOD)
- Unlimited websocket connections

**NOT included in Alpaca (even paid):**
- Fundamental data (PE, earnings, insider, institutional)
- Earnings calendar
- Sector/industry classification
- Analyst consensus

**Recommendation:** Alpaca is excellent for prices; stick with SEC + FINRA for fundamentals. Alpaca doesn't provide the fields you need to replace yfinance entirely.

---

## Implementation Order (Recommended Sequence)

### Week 1: Deploy Phase 1 + Quick Wins
1. **Deploy FINRA short interest** (Phase 1, ready to go)
   - [ ] Run migration
   - [ ] Deploy loaders + Terraform
   - [ ] Test end-to-end
   - **Savings: -20% yfinance load, eliminates 5,300 API calls**

2. **Add 52-week extremes computation** (Quick win)
   - [ ] Add SQL to derive from price_daily
   - [ ] Test
   - **Savings: -5% yfinance load**

3. **Monitor yfinance_snapshot runtime**
   - Should drop from 30-45 min → ~25-35 min

### Week 2-3: Phase 2 (SEC Holdings)
4. **Build `load_institutional_holdings_13f.py`**
   - Parallel dev with existing SEC client
   - Test against sample 13F filings
   - **Savings: -20% of remaining yfinance load**

5. **Build `load_insider_holdings_sec.py`**
   - Parallel dev
   - Test against Form 4 samples
   - **Savings: -15% of remaining yfinance load**

### Week 4: Phase 3 (Company Info & Earnings)
6. **Consolidate company info** (if not done in 13F/Form 4 dev)
   - Reuse existing SEC reads
   - Denormalize or cache in new table

7. **Build `load_earnings_calendar_sec.py`** (optional, lower priority)
   - Parse 10-K/10-Q filing dates
   - Aggregate expected earnings

### Week 5+: Polish & Monitoring
8. **Run all new loaders in parallel with yfinance_snapshot**
   - Verify data alignment
   - Monitor for gaps

9. **Retire yfinance_snapshot** (once validated)
   - Keep as fallback-only for analyst data? Or
   - Replace with lightweight analyst-data-only fetch (~5 min instead of 30-45 min)

---

## Data Quality & Risk Notes

### What You Gain (vs. yfinance)
- **Audited data:** SEC filings are audited by companies + SEC oversight
- **Authoritative sources:** FINRA short interest is the official regulatory source
- **Transparency:** See exact holdings, not yfinance's proprietary "estimates"
- **Cost savings:** No more yfinance rate-limiting risk or API overhead
- **Speed:** Reduce yfinance_snapshot from 30-45 min to ~5-10 min (analyst data only)

### What You Sacrifice
- **Real-time analyst counts:** No good free alternative (analyst consensus is proprietary Bloomberg/Seeking Alpha data)
- **Quarterly lag on 13F:** OK for stock scoring; intraday traders would notice
- **2-day lag on insider:** OK for monitoring; real-time insiders need paid service
- **Bi-weekly lag on short interest:** OK; short interest doesn't change daily enough to warrant daily polling

### Mitigation Strategies
1. **Mark optional data explicitly:** Analyst data is dashboard-only enrichment, not trading logic
2. **Graceful degradation:** If SEC source unavailable, mark data_unavailable (no silent fallbacks)
3. **Parallel validation:** Run new loaders alongside yfinance_snapshot until confidence high
4. **Monitor data freshness:** Use existing `data_freshness_monitor` Lambda to alert on missing data

---

## Questions to Decide

1. **Phase 1 (FINRA) deployment:** Ready to deploy now, or wait for Phase 2-3?
   - *Recommendation: Deploy now. Eliminates 20% yfinance load with zero risk.*

2. **Analyst data fallback:** Keep yfinance_snapshot for analyst counts only (5 min instead of 30-45 min)?
   - *Recommendation: Yes. Analyst data has no good free alternative.*

3. **Company info consolidation:** New table vs. denormalize into existing tables?
   - *Recommendation: New table initially (easier to maintain). Denormalize later if performance needed.*

4. **52-week extremes:** Compute in SQL or fetch from Alpaca/yfinance?
   - *Recommendation: Compute in SQL (free, always current, no API dependency).*

5. **Earnings calendar priority:** Nice-to-have or should it wait?
   - *Recommendation: Wait. It's enrichment-only. Focus on Phase 1-2 first.*

---

## Files to Update/Create

### Create (New Loaders)
- `loaders/load_short_interest_finra.py` ✅ **Already done (Session 225)**
- `loaders/load_institutional_holdings_13f.py` ← Phase 2
- `loaders/load_insider_holdings_sec.py` ← Phase 2
- `loaders/load_company_info_sec.py` ← Phase 3 (optional)
- `loaders/load_earnings_calendar_sec.py` ← Phase 3 (optional)

### Update (Existing Loaders)
- `loaders/load_positioning_metrics.py` ← Already refactored to read from FINRA
- `loaders/load_technical_indicators.py` ← Add 52-week extremes computation
- `loaders/load_sec_valuations.py` ← Add market cap computation (or keep separate)
- `terraform/modules/loaders/main.tf` ← Add new loader configs
- `steering/DATA_LOADERS.md` ← Update architecture docs

### Create (Migrations)
- `migrations/1012_create_short_interest_finra_table.sql` ✅ **Already done**
- `migrations/1013_create_institutional_holdings_table.sql` ← Phase 2
- `migrations/1014_create_insider_holdings_table.sql` ← Phase 2
- `migrations/1015_create_company_info_table.sql` ← Phase 3

---

## Next Steps

**This week:**
1. **Decide:** Deploy Phase 1 (FINRA) now?
2. **Review:** Any feedback on Phase 2-3 priorities?
3. **Identify:** Are there other data sources you're already using that could replace yfinance fields?

**Next week (if approved):**
1. Deploy Phase 1
2. Start Phase 2 dev (13F + Form 4 loaders in parallel)
3. Monitor yfinance_snapshot runtime to confirm improvement

---

## Reference: All yfinance_snapshot Fields Mapped

| Field | Current Size (% of Load) | Replacement | Status | Phase |
|-------|--------------------------|-------------|--------|-------|
| `short_interest` | 20% | FINRA Reg SHO | ✅ Ready | 1 |
| `held_percent_institutions` | 20% | SEC 13F | Planned | 2 |
| `held_percent_insiders` | 15% | SEC Form 4/5 | Planned | 2 |
| `sector`, `industry`, `exchange`, `website`, `country`, `long_name` | 15% | SEC company facts | Planned | 3 |
| `earnings_date`, `earnings_dates` | 10% | SEC filing calendar | Planned | 3 |
| `fifty_two_week_high`, `fifty_two_week_low` | 5% | Computed from price_daily | Quick win | - |
| `market_cap` | 3% | Computed from shares + price | Quick win | - |
| `pe_ratio`, `pb_ratio`, `ps_ratio`, `peg_ratio`, `dividend_yield`, `fcf_yield` | 5% | ✅ Already replaced (load_sec_valuations.py) | Deployed | - |
| **`recommendation_key`, `number_of_analysts`, `analysts_*`** | **7%** | **None (keep yfinance)** | Keep | - |
| **Total** | **100%** | **Minimal yfinance** | **-88%** | **1-3** |

---

## Session 234 Summary

✅ **What we found:**
- Phase 1 (FINRA short interest) is **ready to deploy** from Session 225
- Phases 2-3 are well-documented in `LOADER_OPTIMIZATION_ANALYSIS.md`
- Additional quick wins available (52-week extremes, market cap)
- No major blocker; just execution

✅ **What we recommend:**
1. Deploy Phase 1 immediately (ready to go, eliminates 20% yfinance load)
2. Execute Phase 2 next (1-2 weeks dev, eliminates 35% more)
3. Consider Phase 3 after 2 (nice polish, eliminates 25% more)
4. Stick with yfinance for analyst data (no good alternative)
5. Evaluate IEX Cloud later if you want unified fundamentals source

**Expected outcome:** yfinance_snapshot from 30-45 minutes down to ~5-10 minutes (analyst-data-only fetches).

