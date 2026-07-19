# Fallback Pattern Audit - July 2026

**Goal:** Finance app must fail fast on data loss/errors. No silent fallbacks that mask problems.

**Status:** 15 critical/high/medium severity findings audited. Fixes in progress.

---

## CRITICAL SEVERITY (Must fix - could cause silent trades or data loss)

### 1. ❌ Dashboard Trades Panel - Silent Empty Return on Error
**File:** `dashboard/panels/trades.py:145-146`
```python
if error_boundary.has_error(trades):
    return [], None  # BUG: Swallows error object, frontend gets empty trades
```
**Impact:** Operator sees "no trades" when error occurred. Trading loop may proceed thinking positions are synchronized.
**Fix:** `return error_boundary.get_error_marker(), None` - propagate error to frontend.
**Status:** TODO

---

### 2. ❌ Bootstrap Config - Silent Empty Dict on Incomplete Init
**File:** `dashboard/bootstrap.py:190-191`
```python
if not any(vars_set):
    return {}  # BUG: Incomplete config silently proceeds
```
**Impact:** Dashboard may start with missing credentials/database/API config. Subsequent failures cryptic.
**Fix:** Raise `ValueError("Configuration incomplete: ...")` listing which keys missing.
**Status:** TODO

---

### 3. ❌ Short Interest FINRA - Yfinance Fallback Without Fail-Fast
**File:** `loaders/load_short_interest_finra.py` (throughout)
```python
# Loader depends on yfinance with implicit fallback mechanism
# If yfinance API fails/throttles, entire positioning_metrics chain silently breaks
```
**Impact:** Positioning data missing without explicit marker. Risk calculations proceed with stale data.
**Fix:** Add explicit return pattern: `return {"data_unavailable": True, "reason": "yfinance_api_timeout", "source": "yfinance"}`
**Status:** TODO

---

### 4. ❌ Company Info SEC - Silent Pass on Shares Outstanding Timeout
**File:** `loaders/load_company_info_sec.py:136-143`
```python
except TimeoutError as e:
    marker = handle_exception(...)
    logger.debug(f"[{symbol}] Using NULL for shares_outstanding due to timeout")
    # BUG: Continues with None instead of explicit unavailable marker
```
**Impact:** Market cap calculations proceed with NULL shares, scoring silently breaks downstream.
**Fix:** Return explicit `{"data_unavailable": True, "reason": "shares_outstanding_sec_timeout"}`
**Status:** TODO

---

### 5. ❌ Value/Quality/Growth Metrics - Incomplete Data Silently Skipped
**File:** `loaders/load_value_quality_growth_metrics.py:97-100`
```python
if not metrics:
    symbols_failed += 1
    continue  # BUG: Symbol marked failed but reason unknown
```
**Impact:** Scoring loader silently drops symbols. Operator has no visibility into *why* (missing SEC? NaN? zero division?).
**Fix:** Require `fetch_incremental()` to return dict with `data_unavailable` marker; fail loudly if empty.
**Status:** TODO

---

## HIGH SEVERITY (Masks data problems, hard to debug)

### 6. ❌ Position Enrichment Queries - Silent Timeout Fallback
**File:** `lambda/api/routes/algo_handlers/dashboard.py:203-207`
```python
except (...QueryCanceled...) as enrichment_error:
    logger.warning("[POSITIONS] Enrichment queries timed out or failed (acceptable)")
    # BUG: Strips sector/technical data without flagging incompleteness
```
**Impact:** Frontend gets positions without enrichment; operator doesn't know data is incomplete.
**Fix:** Include `enrichment_incomplete: true` flag in response; client renders warning panel.
**Status:** TODO

---

### 7. ❌ Orchestrator Config - Implicit Default via .get()
**File:** `algo/orchestration/orchestrator.py:148-153`
```python
execution_mode = self.config.get("execution_mode")  # Implicit None default
if not execution_mode:  # BUG: Masks "key missing" vs "key empty"
    raise RuntimeError(...)
```
**Impact:** Error message unclear; operator can't distinguish config issue from runtime state.
**Fix:** Explicit None check: `execution_mode = self.config.get("execution_mode"); if execution_mode is None: raise ValueError("Key missing")`
**Status:** TODO

---

### 8. ❌ YFinance Snapshot - Fallback Cache Miss to On-Demand
**File:** `loaders/load_yfinance_snapshot.py:164-169`
```python
if symbol in self._ticker_batch_cache:
    ticker = self._ticker_batch_cache[symbol]
else:
    ticker = YFinanceWrapper.get_ticker(symbol)  # BUG: Silent fallback path
```
**Impact:** If batch prefetch fails, on-demand fetch silently tries. No logging of which path taken.
**Fix:** Log path: `logger.debug(f"Using {'batch' if symbol in cache else 'on-demand'} fetch")`. Return explicit marker if on-demand fails after batch failure.
**Status:** TODO

---

### 9. ❌ Institutional Holdings - Multiple Fallback Tags Without Clear Cascade
**File:** `loaders/load_institutional_holdings_13f.py:132-156`
```python
possible_tags = ["us-gaap:...", "srt:...", "institutional_ownership_pct"]
for tag in possible_tags:
    if tag in facts:
        # BUG: No logging of which tag succeeded, no fail-fast on malformed
```
**Impact:** If first tag exists but is corrupted, code silently tries next. Operator doesn't know data quality issues.
**Fix:** Log each tag attempt: `logger.debug(f"Trying tag {tag}..."); logger.debug(f"Success: using {tag}")`
**Status:** TODO

---

### 10. ❌ Economic Data - Silent .get() Sentinel Pattern
**File:** `loaders/load_economic_data.py:110`
```python
if obs.get("value", ".") != ".":  # BUG: Uses "." as magic sentinel
```
**Impact:** If API structure changes, code silently treats missing as "." without detecting format change.
**Fix:** Explicit validation: `if "value" not in obs: raise ValueError("Missing value in FRED response")`
**Status:** TODO

---

## MEDIUM SEVERITY (Defensible but questionable, should audit)

### 11. ⚠️ Risk Metrics - VIX Value .get() in Logging
**File:** `algo/risk/market_exposure.py:422`
```python
logger.debug(f"VIX regime: {vix.get('value', 'N/A')} ...")  # BUG: Logging silently hides missing VIX
```
**Impact:** If VIX data missing upstream, logging masks it. Later VIX-dependent calculations fail cryptically.
**Fix:** VIX should return dict with `data_unavailable: true` flag upstream; don't use .get() defaults for metrics.
**Status:** TODO

---

### 12. ⚠️ Position Sync - Reason Tracking with .get() Default
**File:** `algo/infrastructure/alpaca_sync_manager.py:505, 510, 516`
```python
skipped_reasons["zero_qty"] = skipped_reasons.get("zero_qty", 0) + 1  # BUG: Lazy init
```
**Impact:** If key never incremented, operator has no record it was evaluated. Loss of audit trail.
**Fix:** Pre-initialize all skip reasons dict at function start with explicit keys.
**Status:** TODO

---

### 13. ⚠️ Notifications - Missing Field Defaults
**File:** `algo/reporting/notifications.py:72-74`
```python
entry_price = details.get("entry_price")  # BUG: Implicit None default, no validation
shares = details.get("shares")
```
**Impact:** Downstream formatting must handle None. Unclear if None is expected or error.
**Fix:** Use schema validation: `entry_price = strict_get_dict(details, "entry_price", source="trade_notification")`
**Status:** TODO

---

### 14. ⚠️ Alpaca Mock Server - Silent Default on Content-Length
**File:** `algo/infrastructure/alpaca_mock_server.py:75`
```python
content_length = int(self.headers.get("Content-Length", 0))  # BUG: Defaults to 0
```
**Impact:** If client misses Content-Length header, body silently lost. No error surfaced.
**Fix:** Fail-fast: `if "Content-Length" not in self.headers: raise ValueError("Missing Content-Length")`
**Status:** TODO

---

### 15. ⚠️ Trend Analysis - Silent Skip on Data Gaps
**File:** `loaders/load_trend_analysis.py` (inferred from Session 264 memory)
**Impact:** Trend metrics silently become NULL if price_daily has gaps. No explicit marker.
**Fix:** Add data_unavailable marker on gaps, similar to other metric loaders.
**Status:** TODO

---

## SUMMARY TABLE

| # | File | Pattern | Severity | Fix Status |
|---|------|---------|----------|-----------|
| 1 | dashboard/panels/trades.py | Silent empty return on error | CRITICAL | ❌ TODO |
| 2 | dashboard/bootstrap.py | Empty dict on incomplete config | CRITICAL | ❌ TODO |
| 3 | load_short_interest_finra.py | Yfinance fallback implicit | CRITICAL | ❌ TODO |
| 4 | load_company_info_sec.py | Silent pass on timeout | CRITICAL | ❌ TODO |
| 5 | load_value_quality_growth_metrics.py | Incomplete data silent skip | CRITICAL | ❌ TODO |
| 6 | dashboard.py routes | Enrichment timeout fallback | HIGH | ❌ TODO |
| 7 | orchestrator.py | Config .get() implicit default | HIGH | ❌ TODO |
| 8 | load_yfinance_snapshot.py | Cache miss fallback | HIGH | ❌ TODO |
| 9 | load_institutional_holdings_13f.py | Multiple tags no logging | HIGH | ❌ TODO |
| 10 | load_economic_data.py | .get() sentinel pattern | HIGH | ❌ TODO |
| 11 | market_exposure.py | VIX .get() in logging | MEDIUM | ⚠️ TODO |
| 12 | alpaca_sync_manager.py | Reason tracking lazy init | MEDIUM | ⚠️ TODO |
| 13 | notifications.py | Missing field no validation | MEDIUM | ⚠️ TODO |
| 14 | alpaca_mock_server.py | Content-Length default | MEDIUM | ⚠️ TODO |
| 15 | load_trend_analysis.py | Silent skip on gaps | MEDIUM | ⚠️ TODO |

---

## FIX STRATEGY

**Phase 1 - CRITICAL (This session):**
1. Fix trades panel → propagate errors, not swallow
2. Fix bootstrap → fail-fast on incomplete config
3. Fix short_interest_finra → explicit data_unavailable marker
4. Fix company_info_sec → explicit timeout marker
5. Fix value_quality_growth → explicit skip reasons

**Phase 2 - HIGH (Next session if time):**
6. Fix position enrichment → enrichment_incomplete flag
7. Fix orchestrator config → explicit None checks
8. Fix yfinance snapshot → logging + marker on fallback
9. Fix institutional holdings → tag cascade logging
10. Fix economic data → explicit validation

**Phase 3 - MEDIUM (Polish pass):**
11-15. Audit remaining .get() patterns, lazy init patterns, field validation

---

## GOVERNANCE ENFORCED

All fixes must follow pattern in `CLAUDE.md`:
- **CRITICAL data:** Raise exception (raise RuntimeError/ValueError)
- **OPTIONAL data:** Return explicit `{"data_unavailable": True, "reason": "...", "source": "..."}`
- **Never:** `return []`, `return {}`, `return 0` without marker or exception
- **Never:** `.get(key, default)` with defaults on financial data - use explicit key checks

Pre-commit hook `check-silent-fallbacks.py` enforces compliance on commit.
