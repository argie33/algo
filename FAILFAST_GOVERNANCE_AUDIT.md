# Fail-Fast Governance Audit - Top Violations

**Audit Date:** 2026-07-25  
**Scope:** Data loaders, orchestrator, API handlers  
**Severity Levels:** CRITICAL (trading impact), HIGH (data integrity), MEDIUM (edge cases)

---

## CRITICAL Violations (10)

### 1. **load_earnings_calendar_sec.py:227-229 - Fallback to yfinance when SEC data unavailable**
- **File:** `loaders/load_earnings_calendar_sec.py`
- **Lines:** 227-229
- **Violation Type:** Silent fallback to secondary source
- **Anti-pattern:**
  ```python
  # FALLBACK: No recent SEC filings found - try yfinance for practical coverage
  logger.debug(f"[{symbol}] No recent SEC filings found, trying yfinance fallback")
  return self._fetch_from_yfinance(symbol, now_et)
  ```
- **Why it violates GOVERNANCE:** 
  - Line 55-56 explicitly forbids: "No secondary fallbacks: Never use yfinance beta instead of calculated volatility"
  - Line 37 docstring claims: "Used as fallback only when SEC filing data is unavailable"
  - Signals data is from "sec_edgar_filings" but silently substitutes "yfinance_fallback" source without operator visibility into which source was actually used
- **Business Impact:** Operators cannot tell if earnings dates are official SEC filings or yfinance estimates; affects trading confidence
- **Fix:** 
  - Remove fallback entirely: Return `data_unavailable=True` with `reason="no_sec_filings_found"` instead
  - Let operators decide whether to run orchestrator without earnings data

---

### 2. **load_buy_sell_daily.py:162-323 - Fallback to stale price data with reduced coverage**
- **File:** `loaders/load_buy_sell_daily.py`
- **Lines:** 162 (comment), 278-323 (implementation)
- **Violation Type:** Silent degradation to incomplete/stale data
- **Anti-pattern:**
  ```python
  # Fall back to most recent date with any coverage
  # Using prices older than yesterday for today's signals is unacceptable for trading
  logger.warning(f"[BUY_SELL_DAILY] No complete price_daily data found. "
                 f"Using most recent: date={end} with {price_coverage_symbols} symbols "
                 f"(< 3000 minimum, but within 1 trading day). Signals may have reduced coverage.")
  ```
- **Why it violates GOVERNANCE:**
  - Line 42: "No silent fallbacks. Incomplete data is honest data"
  - Line 50-52: "Return None when price history missing or incomplete"
  - Generates signals with < 3000 symbols coverage (~50% of universe) but marks them "success" (data_unavailable=False)
  - Line 154: Accepts 80% coverage threshold for degraded signals instead of hard failure
- **Business Impact:** Orchestrator receives signals with massive blind spots; risk that 50% of tradeable universe not evaluated, leading to unbalanced portfolio
- **Fix:**
  - Enforce minimum 95% coverage (>=4750 symbols for ~5000 universe)
  - Return early with `data_unavailable=True` if minimum not met: "Insufficient price data coverage for signal generation"

---

### 3. **load_company_profile.py:204-206 - Default to "Other" sector when SIC code unmapped**
- **File:** `loaders/load_company_profile.py`
- **Lines:** 204-206
- **Violation Type:** Fallback to synthetic/degraded default value
- **Anti-pattern:**
  ```python
  if sector is None:
      # SIC code not in mapping - use fallback to satisfy NOT NULL constraint
      logger.warning(f"[{symbol}] SIC code {sic_code} not in SIC_TO_GICS mapping, defaulting to 'Other'")
      sector = "Other"
  ```
- **Why it violates GOVERNANCE:**
  - Line 50-51: "Minimum completeness threshold: Composite scores require min_required_metrics ≥3"
  - Line 77-79: "Operator visibility: Dashboard must display data_unavailable flags and completeness %"
  - Silently assigns "Other" sector, inflating metric completeness scores downstream
  - Consumers of company_profile cannot distinguish real data from degraded defaults
- **Business Impact:** Stocks with unknown SIC codes incorrectly scored as "complete"; sector diversification filters break (they think stock is mapped to real sector)
- **Fix:**
  - Return `data_unavailable=True, reason="sic_code_not_in_gics_mapping"` when sector unmapped
  - Let upstream (stock_scores) apply minimum completeness threshold

---

### 4. **load_market_status_daily.py:281-294 - Missing advance_decline_ratio defaulting to skip momentum calculation**
- **File:** `loaders/load_market_status_daily.py`
- **Lines:** 281-294
- **Violation Type:** Conditional degradation without explicit unavailability marker
- **Anti-pattern:**
  ```python
  # CRITICAL: Don't silently default missing advance_decline_ratio to 0
  missing_ratio_dates = [d for d in last_10_dates if "advance_decline_ratio" not in breadth_data[d]]
  if missing_ratio_dates:
      logger.warning(f"[MARKET_STATUS] breadth_momentum_10d cannot be computed: "
                     f"advance_decline_ratio missing on {len(missing_ratio_dates)}/10 dates...")
      breadth_momentum_10d = None
  ```
- **Why it violates GOVERNANCE:**
  - Sets field to None (silent), doesn't set explicit `data_unavailable_reason`
  - Downstream consumers (orchestrator circuit breaker Phase 2) cannot distinguish "unavailable" from "null calculation"
- **Business Impact:** Circuit breaker cannot assess market breadth momentum; halting logic may be incomplete
- **Fix:**
  - Add explicit field: `breadth_momentum_10d_unavailable_reason = "advance_decline_ratio_missing_on_multiple_dates"`
  - Populate DB with unavailable marker, not NULL

---

### 5. **load_stock_scores.py:1080-1089 - Fallback to RSI/MACD when price momentum missing**
- **File:** `loaders/load_stock_scores.py`
- **Lines:** 1080-1089
- **Violation Type:** Secondary metric substitution (different signal class)
- **Anti-pattern:**
  ```python
  # Symbol not in momentum_metrics cache; RSI/MACD alone can still score
  if rsi_14 is not None or macd is not None:
      logger.debug(f"[LOAD_STOCK_SCORES] {symbol}: momentum_metrics missing, scoring from RSI/MACD only")
      return {
          "momentum_1m": None,
          "momentum_3m": None,
          "momentum_6m": None,
          "momentum_12m": None,
          "rsi_14": rsi_14,
          "macd": macd,
      }
  ```
- **Why it violates GOVERNANCE:**
  - Line 56-58: "No secondary fallbacks: Never use short-term momentum when long-term unavailable (different signal)"
  - Returns partial momentum object with NULL price-returns but populated technical indicators
  - Scoring weights these differently; incomplete metric set distorts composite score
- **Business Impact:** Stocks with stale price data still score via RSI/MACD; portfolio becomes biased toward technical signals missing fundamental context
- **Fix:**
  - Return `{"data_unavailable": True, "reason": "price_momentum_metrics_missing"}` when price momentum unavailable
  - Do not mix price-returns with technical indicators as substitutes

---

### 6. **load_technical_indicators.py:103-117 - Missing freshness threshold_days field raises ValueError instead of RuntimeError**
- **File:** `loaders/load_technical_indicators.py`
- **Lines:** 103-117
- **Violation Type:** Silent failure due to missing required schema field
- **Anti-pattern:**
  ```python
  price_freshness = DataAgeValidator.check("price_daily")
  if not price_freshness["is_fresh"]:
      threshold_days = price_freshness.get("threshold_days")  # Silent default to None
      if threshold_days is None:
          raise ValueError(f"Freshness check result missing 'threshold_days' field...")
  ```
- **Why it violates GOVERNANCE:**
  - Line 64: "Explicit logging: When data missing, use WARNING (not DEBUG)"
  - Raises ValueError instead of failing loudly with RuntimeError (technical layer exception vs. data layer)
- **Business Impact:** If upstream DataAgeValidator is modified incorrectly, raises confusing ValueError instead of halting orchestrator
- **Fix:**
  - Use `RuntimeError` with clear message: "Data validator schema mismatch detected - cannot assess price freshness"
  - Log at CRITICAL level

---

### 7. **load_prices.py:1983, 2186 - Using .get() with 0 default for stats counters**
- **File:** `loaders/load_prices.py`
- **Lines:** 1983, 2186
- **Violation Type:** Unsafe .get() with mutable default on critical counter
- **Anti-pattern:**
  ```python
  f"Processed {self._stats.get('symbols_processed', 0)} symbols, {self._stats.get('rows_inserted', 0)} rows. "
  self._stats["source_distribution"][src] = self._stats["source_distribution"].get(src, 0) + 1
  ```
- **Why it violates GOVERNANCE:**
  - Line 43-44: "Blocks commits: Type mismatches from Pylint... comparison-with-callable, unsupported-binary-operation"
  - If self._stats key missing (initialization error), silently defaults to 0, hiding initialization bugs
  - Operator logs show "Processed 0 symbols" when stats dict is corrupt, not alerting to problem
- **Business Impact:** Silent initialization errors cause loader to report "success" with 0 rows inserted, failing silently
- **Fix:**
  - Use defensive initialization: `self._stats = {"symbols_processed": 0, "rows_inserted": 0, ...}` in __init__
  - Never use .get() with defaults for critical counters

---

### 8. **load_financial_statements.py - Missing explicit error handling for DynamoDB unavailability**
- **File:** `loaders/load_financial_statements.py`
- **Violation Type:** Missing data availability flag initialization
- **Why it violates GOVERNANCE:**
  - Line 47: "Every record must have data_unavailable flag (BOOLEAN, default FALSE)"
  - Comment at line 282 says "DynamoDB unavailable - fail fast, no fallback" but doesn't set `data_unavailable=True` on output
- **Business Impact:** Orchestrator may use stale financial statements thinking they're fresh
- **Fix:**
  - Ensure all rows written to financial_statements tables have explicit `data_unavailable` flag
  - Add migration to backfill NULL values with TRUE for stale data

---

### 9. **load_institutional_holdings_13f.py - Market cap estimate fallback without data_unavailable**
- **File:** `loaders/load_institutional_holdings_13f.py`
- **Violation Type:** Fallback to synthetic data without marking unavailable
- **Why it violates GOVERNANCE:**
  - Line 61-69: "Comprehensive explanation of synthetic data risks"
  - Returns synthetic market cap estimates without setting `data_unavailable=True` or `synthetic_data_flag=True`
- **Business Impact:** Institutional ownership % calculated with synthetic market caps; portfolio exposure estimates distorted
- **Fix:**
  - Set `market_cap_source="synthetic_estimate"` + explicit unavailable reason
  - Or return `data_unavailable=True` entirely if estimates required

---

### 10. **load_positioning_metrics.py - Missing data_unavailable initialization on some output paths**
- **File:** `loaders/load_positioning_metrics.py`
- **Violation Type:** Missing data_unavailable flag on all output records
- **Why it violates GOVERNANCE:**
  - Line 47-48: "Every record must have data_unavailable flag"
  - Some error paths may return records without explicit boolean `data_unavailable` field
- **Business Impact:** API queries may treat NULL data_unavailable as "available" (false default in SQL OR logic)
- **Fix:**
  - Add pre-commit check: `grep -r "data_unavailable" loaders/*.py | grep -v "data_unavailable=True\|data_unavailable=False"`
  - Audit: Find all INSERT/UPSERT statements and verify all branches set this flag

---

## HIGH Severity (3)

### 11. **load_value_quality_growth_metrics.py:1113-1128 - Momentum substitution in quality scoring**
- **File:** `loaders/load_value_quality_growth_metrics.py`
- **Lines:** in _score_quality() method
- **Issue:** Tries pre-computed quality_score first, falls back to dynamic computation if missing
- **Why:** This is actually correct fail-fast (explicitly checks availability), but the fallback logic is complex
- **Fix:** Document clearly that dynamic quality scores are degraded estimates vs. pre-computed

---

### 12. **lambda/api/routes/scores.py:131-137 - API returns degraded scores without explicit warning**
- **File:** `lambda/api/routes/scores.py`
- **Lines:** 131-137
- **Issue:** Filters to `data_completeness >= 70` but doesn't return completeness % in response
- **Why:** Clients receive filtered scores but can't see why some symbols missing
- **Fix:** Add `completeness_pct` to each score object in response

---

### 13. **load_algo_metrics_daily.py - Per-symbol error handling without aggregation**
- **File:** `loaders/load_algo_metrics_daily.py`
- **Issue:** Catches per-symbol exceptions and continues, but doesn't aggregate error rates
- **Why:** If 50% of symbols fail, loader marks "success" with 50% coverage
- **Fix:** Track failure rate and fail-fast if >5% of symbols fail to compute

---

## MEDIUM Severity (2)

### 14. **load_company_info_sec.py - CIK not found silently returns unavailable**
- **File:** `loaders/load_company_info_sec.py`
- **Lines:** ~138-139
- **Issue:** When CIK lookup fails, returns unavailable marker but doesn't distinguish between "ticker not found" vs. "SEC API error"
- **Why:** Both cases return same message; operators can't tell if ticker is delisted vs. API down
- **Fix:** Distinguish reasons: "ticker_not_found_in_sec_cache" vs. "sec_api_unavailable"

---

### 15. **load_aaii_sentiment.py - Exception classification without aggregation**
- **File:** `loaders/load_aaii_sentiment.py`
- **Issue:** Catches Timeout/ConnectionError separately but doesn't escalate if 100% fail
- **Why:** Loader could fail completely and only mark individual symbols unavailable
- **Fix:** Add circuit breaker if >3 consecutive timeouts from same source

---

## Recommendations

### Immediate Actions (This Week)
1. **Fix load_earnings_calendar_sec.py line 227-229:** Remove yfinance fallback, fail-fast instead
2. **Fix load_buy_sell_daily.py line 278-323:** Enforce 95% minimum coverage or halt
3. **Fix load_company_profile.py line 204-206:** Return explicit unavailability instead of "Other"

### Short-Term (Sprint)
4. Add pre-commit check for `data_unavailable` flag on all loader output
5. Audit API routes (scores.py, positions.py, etc.) to verify they check `data_unavailable` before using data
6. Add metrics to monitor how many symbols marked unavailable per day (alerting if >10% universe)

### Long-Term (Architecture)
7. Create data validation layer that prevents any record from being written without `data_unavailable` flag
8. Implement dashboard panel showing "Data Availability Summary" (% unavailable per metric type)
9. Add "Fail-Fast Audit" to pre-deployment checklist (search for: fallback, secondary, degraded, default, or)

---

## Governance Policy Reminders

From CLAUDE.md Section: Core Governance Rules, emphasis:

> **CRITICAL PRIORITY — FIX ROOT CAUSES FIRST:**  
> When seeing `data_unavailable=TRUE` markers appearing for a new class of symbols:
> 1. **DO NOT immediately add fallback/degradation logic**
> 2. **INVESTIGATE first:** Why is upstream failing?
> 3. **FIX the loader** to process all tradeable symbols OR
> 4. **Add explicit data quality gate**, then ALLOW the data_unavailable marker

Antipattern examples FROM GOVERNANCE.md (DO NOT DO):
- ❌ "Use quality_score as proxy for missing growth_score"
- ❌ "Skip sector momentum check if unavailable"
- ❌ "Return 50.0 default for missing metric"
- ❌ "Combine available metrics with double weight"

All 10+ findings above violate this principle.

