# Session 442: Data Loading System - Aggressive Official Sources Strategy

**Goal:** Fix broken data sources, remove dead code, and systematically pursue official data sources (SEC EDGAR, FINRA, SEC.GOV) instead of free APIs.

**Current State (2026-07-26):**
- 25 loaders wired, all executing
- 3 major data gaps identified:
  1. Analyst sentiment/ratings: BROKEN (frozen 2026-05-22)
  2. Analyst sentiment coverage: INCOMPLETE (only 500/5500 symbols)
  3. Segment metrics: UNIMPLEMENTED (needs XBRL parsing)

---

## Priority 1: FIX BROKEN ANALYST DATA (HIGH IMPACT - 2-4 hours)

### Issue: analyst_upgrade_downgrade Table (BROKEN)
- **Current state:** 50 stale rows from 2026-05-22 (64 days old)
- **Root cause:** yfinance_snapshot loader removed (Session 275+), no replacement wired
- **Impact:** Analyst catalyst scoring silently computes 0 for all symbols

### Issue: analyst_sentiment_analysis Table (INCOMPLETE)
- **Current state:** 1503 rows but only 500 symbols (9% coverage)
- **Root cause:** Loader exists (load_analyst_estimates.py) but not wired to terraform
- **Impact:** Missing analyst sentiment for 5000 symbols = incomplete catalyst scoring

### Solutions (Pick ONE, execute in order of preference):

#### Option A: Wire Existing Polygon.io Integration (RECOMMENDED FIRST)
**File:** `loaders/load_analyst_estimates.py` (already exists, just needs wiring)
**Steps:**
1. Check if `POLYGON_API_KEY` configured in AWS Secrets Manager
2. Add `analyst_estimates` to terraform `all_loaders` config
3. Add to metrics pipeline (3:30 PM ET, depends on prices/fundamentals)
4. Verify coverage: target 4500+ symbols (85%+)

**Effort:** 1 hour (config only, no code changes)

#### Option B: Build SEC Alternative (If Polygon Not Available)
**Official Source:** SEC EDGAR Form 424B5 (preliminary prospectus) contains equity analyst coverage disclosures
**Alternative:** Parse Seeking Alpha HTML (unofficial but comprehensive)

**Effort:** 4-6 hours (architecture work)

#### Option C: Accept Graceful Degradation (MINIMUM)
**Action:** Document analyst sentiment as "optional enhancement"
**Reasoning:** Current trading logic doesn't hard-require analyst scores; they're part of 6-factor composite
**Result:** System continues, no analyst catalyst factor

**Effort:** 30 minutes (documentation only)

---

## Priority 2: REMOVE DEAD CODE (1 hour)

### Task 1: Delete Orphaned Analyst File
- `loaders/load_analyst_estimates.py` — if NOT wiring to terraform in Priority 1
- Reason: Either wire it (Priority 1) OR delete it (this task), not both

### Task 2: Remove economic_metrics_daily Dead References
- Migration exists (079) but no active loader
- Remove from:
  - `terraform/modules/loaders/main.tf` (allowlists)
  - `utils/loaders/config.py` (config)
  - Any monitoring/alerting references
  - Database allowlist

### Task 3: Verify load_company_profile.py Deletion
- Session 441 deleted it; confirm it's gone from:
  - `loaders/` directory
  - All imports/references
  - Terraform config

**Effort:** 30 minutes (find & delete)

---

## Priority 3: IMPLEMENT SEGMENT METRICS (HIGH EFFORT - 16+ hours)

**Issue:** sec_segment_metrics table exists but loader unimplemented
- Uses XBRL structured data from SEC EDGAR filings
- Needed for: Business diversification scoring (Phase 4)
- Official source: SEC XBRL system (xbrl.sec.gov)

**Implementation Path:**
1. Parse SEC XBRL instance documents (ASC 280 segment reporting)
2. Extract segment revenue/income by business unit
3. Compute Herfindahl concentration index (0-10000 scale)
4. Write to sec_segment_metrics table

**Decision Gate:** Is business segment concentration part of Phase 7 signal generation?
- If YES → Implement now (16+ hours)
- If NO → Document as intentionally unimplemented, mark table as soft-deprecated

**Effort:** 16-24 hours (full XBRL parser + SQL aggregations)

---

## Priority 4: VERIFY ALL 25 LOADERS ARE ACTUALLY WORKING (2-3 hours)

### Verification Checklist:

**Critical Path (MUST WORK):**
- [ ] stock_prices_daily — Alpaca SIP data, 99.4% coverage
- [ ] technical_data_daily — Computed from prices
- [ ] market_status_daily — VIX, market breadth, yields
- [ ] market_constituents — SP500 + Nasdaq-100 + micro-caps

**Metrics & Scoring (MUST WORK for Phase 5):**
- [ ] stock_scores — 6-factor composite (depends on value/quality/growth + stability + positioning)
- [ ] buy_sell_daily — buy signals (depends on trend + technicals + scores)
- [ ] positioning_metrics — short interest + institutional holdings
- [ ] value_quality_growth_metrics — SEC fundamentals
- [ ] stability_metrics — volatility + momentum

**Supporting Data (SHOULD WORK):**
- [ ] company_info_sec — Company names, sectors, industries
- [ ] earnings_calendar_sec — Earnings dates
- [ ] institutional_holdings_13f — Form 13F holdings (currently 91% working)
- [ ] insider_holdings_sec — Form 4/5 insider holdings
- [ ] short_interest_finra — FINRA bi-weekly short interest
- [ ] sec_cash_flow_metrics — Working capital, capex, FCF
- [ ] sec_valuations — SEC-derived P/E, P/B, P/S

**Optional/Dashboard-Only:**
- [ ] signal_quality_scores — Dashboard display (non-critical)
- [ ] algo_metrics_daily — Portfolio stats
- [ ] aaii_sentiment — Investor sentiment (Playwright-based)
- [ ] naaim — Advisor allocation (HTML parsing)
- [ ] sector_industry_daily — Sector rankings
- [ ] trend_template_data — Trend template snapshots
- [ ] economic_data — FRED economic indicators

**Verification Method:**
```bash
# For each loader:
# 1. Check if table has recent data
SELECT COUNT(*), MAX(created_at) FROM [table_name] WHERE created_at > NOW() - INTERVAL '2 days';

# 2. Check error logs
grep "[loader_name]" logs/loaders.log | tail -50

# 3. Spot-check data quality
SELECT * FROM [table_name] WHERE data_unavailable = true LIMIT 10;
```

**Effort:** 2-3 hours (spot checks for each loader)

---

## Priority 5: AGGRESSIVE OFFICIAL SOURCES STRATEGY (Ongoing)

### SEC EDGAR Integrations Already Live:
- ✅ Company Info (CIK lookup, sectors, tickers)
- ✅ Financial Statements (10-K/10-Q, 8 statement types)
- ✅ Form 4/5 (Insider holdings)
- ✅ Form 13G (Institutional holdings - 91% working)
- ✅ Earnings Calendar (Submission metadata)
- ✅ Cash Flow Metrics (Operating/investing/financing cash flow)
- ✅ Valuations (P/E, P/B, P/S from SEC data + prices)

### FINRA Integrations Already Live:
- ✅ Short Interest (Bi-weekly short % outstanding)

### Gaps Requiring Work:
- ❌ XBRL Segment Metrics (ASC 280 segment reporting) — Priority 3
- ❌ Form 8-K Current Events (material announcements)
- ❌ Form DEFM14A (proxy statements - M&A activity)
- ❌ Insider Transaction Details (Form 4/5 detailed trades)

### Free API Integrations:
- ✅ Polygon.io (if configured) — Analyst estimates
- ✅ FRED (Federal Reserve) — Economic indicators
- ⚠️ Yahoo Finance / Alpha Vantage (deprecated for prices, kept for fallback)
- ⚠️ AAII (Investor sentiment, requires Playwright for web scraping)
- ⚠️ NAAIM (Advisor allocation, HTML parsing)

### Recommendations:
1. **Maximize SEC coverage** → Implement missing Form 8-K, DEFM14A parsing
2. **Eliminate reliance on yfinance** → Already done for prices, verify for other metrics
3. **Evaluate Polygon.io** → If configured and reliable, make it primary analyst source
4. **Accept unofficial sources strategically** → AAII/NAAIM for sentiment (non-critical) is acceptable

---

## Execution Order

### Today (Session 442):
1. **Priority 1A** — Wire Polygon.io if configured (1 hour)
   - OR implement Priority 1C (accept degradation) if not
2. **Priority 2** — Clean up dead code (30 minutes)
3. **Priority 4** — Spot-check 10 critical loaders (45 minutes)

### Next Session:
1. **Priority 3** — XBRL segment metrics (if required by Phase 7)
2. **Priority 5** — Form 8-K, DEFM14A parsing (if prioritized)

### Estimated Total Time:
- Immediate fixes: 2-3 hours
- Optional enhancements: 16-24 hours
- **System will be production-ready after Priority 1-2-4 complete**

---

## Key Metrics to Track

After fixes, verify:
```sql
-- Coverage by table (target: 85%+ non-data_unavailable)
SELECT table_name, 
       COUNT(*) as total,
       COUNT(*) FILTER (WHERE data_unavailable = false) as available,
       ROUND(100.0 * COUNT(*) FILTER (WHERE data_unavailable = false) / COUNT(*), 1) as pct_available
FROM (
  SELECT 'stock_scores' as table_name, data_unavailable FROM stock_scores WHERE created_at > NOW() - INTERVAL '1 day'
  UNION ALL
  SELECT 'analyst_sentiment_analysis', data_unavailable FROM analyst_sentiment_analysis WHERE created_at > NOW() - INTERVAL '1 day'
  UNION ALL
  SELECT 'positioning_metrics', data_unavailable FROM positioning_metrics WHERE created_at > NOW() - INTERVAL '1 day'
) t
GROUP BY table_name
ORDER BY pct_available ASC;
```

---

## Decision Points

**Do we wire Polygon.io for analyst data?**
- Yes: Proceed with Priority 1A (1 hour)
- No: Proceed with Priority 1C (30 min, document graceful degradation)

**Do we implement XBRL segment metrics?**
- Yes: Schedule Priority 3 (16+ hours, separate session)
- No: Document intentionally unimplemented, mark as soft-deprecated

**Do we pursue Form 8-K/DEFM14A parsing?**
- Yes: Add to Priority 5 roadmap
- No: Accept current SEC coverage as baseline
