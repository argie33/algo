# Stock Scores Completeness Crisis - Audit & Fix Plan

**Date:** 2026-07-19  
**Status:** 🔴 CRITICAL - Only 52.1% of stocks scoring with ≥70% completeness  
**Goal:** Improve coverage to 80%+ via real data sources only

## Executive Summary

Stock score completeness is critically low (52.1% at ≥70%) because **three of six metric loaders have failed or are using deprecated data sources**:

| Metric | Coverage | Status | Root Cause |
|--------|----------|--------|-----------|
| **stability_metrics** | 93.9% ✅ | WORKING | Price data (Alpaca) - excellent |
| **momentum_metrics** | 80.2% ✅ | WORKING | Price data (Alpaca) - good |
| **growth_metrics** | 85.1% ✅ | WORKING | SEC filings - some IPO gaps expected |
| **value_metrics** | 81.2% ✅ | WORKING | SEC valuations - minor gaps |
| **quality_metrics** | 54.7% 🔴 | DEGRADED | SEC balance sheet data unavailable for 45% of stocks |
| **positioning_metrics** | 41.6% 🔴 | CRITICAL | Three sub-loaders completely broken |

## Root Causes (in priority order)

### 1. CRITICAL: Positioning Metrics (41.6% coverage)

**Broken Components:**
- **short_interest_finra**: 0 symbols with real data (100% unavailable)
  - Root cause: FINRA URLs hardcoded in code return 404
  - Loader: `load_short_interest_finra.py` lines 30-31
  - URL pattern: `https://www.finra.org/sites/default/files/shortinterest/short_volume_week_{date}.csv`
  - Status: URLs DO NOT EXIST (404 on all dates)

- **institutional_holdings_13f**: Only 1 symbol with real data (AAPL)
  - Root cause: SEC companyfacts API query for institutional ownership metrics failing
  - 4669 symbols marked "no_institutional_ownership_metric" 
  - 4568 symbols marked "no_schedule13g_filings_found"
  - Loader assumes institutional_ownership_pct is available in companyfacts - it isn't for most companies

- **insider_holdings_sec**: 0 symbols with real data
  - Root cause: Form 4/5 parsing failing for all 1117+ symbols
  - Loader: `load_insider_holdings_sec.py`
  - Issue: Form 4 XML parsing errors on all filings

**Impact:**
- Positioning metrics required for 30% coverage minimum pre-flight check
- Currently 58.4% unavailable = fails all positioning-dependent stocks

### 2. HIGH: Quality Metrics (54.7% coverage)

**Broken Component:**
- **quality_metrics** depends on: annual_balance_sheet + annual_income_statement
- Coverage gap: 45.3% (2134 stocks unavailable)
- Root causes:
  - IPOs < 1 year old: No annual filings yet
  - Micro-caps: Don't file annual reports
  - REITs/Special structures: Different financial reporting standards
  - Recently public: Minimal historical data

**Analysis:**
- 5658 stocks total have NO SEC balance sheet data
- These are legitimate exclusions but could be handled better

### 3. MODERATE: Growth Metrics (85.1% coverage)

**Status:** Mostly working, expected gaps
- 704 symbols unavailable due to "Insufficient historical data"
- These are likely IPOs with < 2 years of annual reports
- Expected and acceptable

---

## Data Sources & Alternatives

### Short Interest
Current source: FINRA (broken URLs)
Alternatives:
1. **FINRA API** - Direct API instead of CSV files (investigate)
2. **SEC Schedule 13H filings** - Large security-based swaps (partial data)
3. **Yahoo Finance** - DEPRECATED per Session 275 (but reliable)
4. **Alpaca** - Has short interest data in market data feeds
5. **Polygon.io** - Short interest aggregator (paid API)

### Institutional Holdings
Current source: SEC companyfacts API (failing)
Alternatives:
1. **SEC XBRL institutionalOwnersPercent tag** - Different tag names to try
2. **SEC Form 13F filings** - Direct parsing instead of companyfacts
3. **Alpaca institutional holdings** - If available in market data
4. **Manual fallback: Use 0 (or mark unavailable)** - No fudging numbers

### Insider Holdings
Current source: SEC Form 4/5 (parsing errors)
Alternatives:
1. **Fix Form 4 XML parser** - Current one has bugs
2. **Use raw filing text** - Parse HTML instead of XML if XML broken
3. **SEC XBRL insider ownership metrics** - If companyfacts has these
4. **Mark unavailable if unfixable** - Don't fake data

---

## Fix Strategy (Priority Order)

### Phase 1: Emergency Data Source Fixes (TODAY)

**1. FINRA Short Interest (CRITICAL)**
- [ ] Investigate FINRA API direct access (no CSV files)
- [ ] Find working URL pattern or alternative FINRA endpoint
- [ ] If FINRA API unavailable: Implement Alpaca short interest integration
- [ ] Last resort: Temporarily use Yahoo Finance with explicit deprecation warning in logs

**2. SEC Institutional Holdings (HIGH)**
- [ ] Debug companyfacts API queries - try all XBRL tag variations
- [ ] If companyfacts fails: Direct Form 13F filing parsing
- [ ] Test with symbols we know have data (AAPL, MSFT, large-caps)

**3. SEC Insider Holdings (HIGH)**
- [ ] Fix Form 4/5 XML parser or switch to HTML parsing
- [ ] Test with 10 random symbols to verify output

### Phase 2: Quality Metrics Improvement (SECONDARY)

**Accept Expected Gaps:**
- Don't try to cover IPOs < 1 year (legitimate exclusion)
- Document minimum requirements (2 years of filings for quality score)
- This is working as designed

### Phase 3: Completeness Thresholds (FEEDBACK)

**After fixing data loaders:**
- Re-run all 4711+ symbols through metrics pipeline
- Expected new coverage:
  - positioning_metrics: 80-90% (up from 41.6%)
  - quality_metrics: stay at 54.7% (expected for IPOs)
  - Stock scores ≥70% completeness: 75-80% (up from 52.1%)

---

## Implementation Priorities

1. **Fix FINRA short interest** (Highest ROI - 58% of missing positioning data)
2. **Fix SEC institutional holdings** (Next highest)
3. **Fix SEC insider holdings** (Important for complete positioning picture)
4. **Re-run metrics pipeline** (full orchestrator cycle)
5. **Verify stock scores completeness** (should jump to 75%+)

---

## Testing & Validation

For each fix:
1. Test loader on 10 representative symbols (small-caps, large-caps, ETFs)
2. Verify data_unavailable=false for real data
3. Check pre-flight validation passes stock_scores.py minimum coverage thresholds
4. Commit fix with link to this audit

---

## Notes

- No yfinance fallbacks (deprecated)
- No fake data or defaults
- Explicit data_unavailable markers with reasons
- Real sources only (SEC, FINRA, Alpaca, FRED)
