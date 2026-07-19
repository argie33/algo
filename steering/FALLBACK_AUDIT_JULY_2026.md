# Fallback Pattern Audit - July 2026

**Goal:** Finance app must fail fast on data loss/errors. No silent fallbacks that mask problems.

**Status:** 15 critical/high/medium severity findings audited. **FIXES COMPLETE (Session 265)**
- ✅ 5 Critical issues FIXED and verified in HEAD
- ⚠️ 5 High severity issues identified, staged for Phase 2  
- 🔄 5 Medium severity issues documented for Phase 3

---

## CRITICAL SEVERITY (Must fix - could cause silent trades or data loss)

### 1. ✅ Dashboard Trades Panel - Silent Empty Return on Error
**File:** `dashboard/panels/trades.py:145-151` (FIXED)
```python
if error_boundary.has_error(trades):
    if isinstance(trades, dict) and "_error" in trades:
        raise RuntimeError(f"[TRADES] Data retrieval failed: {trades.get('_error')}")
    else:
        raise RuntimeError("[TRADES] Data unavailable: trades object is None or missing")
```
**Impact:** Error now propagates to caller instead of silent empty return. Panel shows error state.
**Fix:** Raises exception on error boundary detection (fail-fast).
**Status:** ✅ COMPLETED - Verified in HEAD

---

### 2. ✅ Bootstrap Config - Silent Empty Dict on Incomplete Init
**File:** `dashboard/bootstrap.py:190-198` (FIXED)
```python
if not any(vars_set):
    raise RuntimeError(
        "Database configuration not initialized. "
        "Call bootstrap_dashboard_database() before using database. "
        "Required environment variables: DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME"
    )
```
**Impact:** Dashboard fails immediately on startup if config missing (instead of at first query).
**Fix:** Fail-fast with clear error message.
**Status:** ✅ COMPLETED - Verified in HEAD

---

### 3. ✅ Short Interest FINRA - Yfinance Eliminated (FINRA API Direct)
**File:** `loaders/load_short_interest_finra.py` (COMPLETELY REWRITTEN - Session 265)
```python
# Session 265 IMPROVEMENT: Replaced yfinance per-symbol fetch with direct FINRA CSV
# - Eliminated yfinance rate limiting (8+ min -> <30 sec)
# - Single batch CSV fetch replaces 4,711 per-symbol API calls
# - Explicit data_unavailable markers for missing symbols (never silent)
```
**Impact:** No yfinance dependency. Positioning data loads in <30s instead of 8+ minutes. Zero rate-limit issues.
**Fix:** FINRA API (CSV) replaces yfinance entirely. Fail-fast with data_unavailable marker.
**Status:** ✅ COMPLETED - Commit 7826e6dcb (feat: Replace yfinance with FINRA Reg SHO direct API)

---

### 4. ✅ Company Info SEC - Silent Pass on Shares Outstanding Timeout
**File:** `loaders/load_company_info_sec.py:136-145` (FIXED)
```python
except TimeoutError as e:
    marker = handle_exception(symbol, e, "fetching company facts")
    logger.warning(f"[{symbol}] Timeout fetching shares_outstanding: {marker.get('reason')}")
    return [marker]  # Return unavailable marker, don't continue silently
```
**Impact:** Timeouts explicitly marked as unavailable (not hidden in debug logs). Operator sees which symbols failed.
**Fix:** Return unavailable marker on timeout instead of continuing with NULL.
**Status:** ✅ COMPLETED - Verified in HEAD

---

### 5. ✅ Value/Quality/Growth Metrics - Incomplete Data Silently Skipped
**File:** `loaders/load_value_quality_growth_metrics.py:94-141` (FIXED)
```python
# Explicit checks for data_unavailable markers with reason logging
if value_row and value_row.get("data_unavailable"):
    logger.debug(f"[{symbol}] Value metrics unavailable: {value_row.get('reason')}")
    # Still insert unavailable marker, but mark symbol as failed
    
# Check quality/growth availability separately
if quality_row and not quality_row.get("data_unavailable"):
    self._insert_quality_metrics(cur, quality_row)
elif quality_row and quality_row.get("data_unavailable"):
    logger.debug(f"[{symbol}] Quality metrics unavailable: {quality_row.get('reason')}")
```
**Impact:** Operator sees *why* each symbol was skipped (missing SEC data, balance sheet gaps, income history unavailable).
**Fix:** Explicit logging of all data_unavailable markers with detailed reasons.
**Status:** ✅ COMPLETED - Enhanced from minimal logging (a2fd8fae4)

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
| 1 | dashboard/panels/trades.py | Silent empty return on error | CRITICAL | ✅ FIXED (HEAD) |
| 2 | dashboard/bootstrap.py | Empty dict on incomplete config | CRITICAL | ✅ FIXED (HEAD) |
| 3 | load_short_interest_finra.py | Yfinance eliminated (FINRA API) | CRITICAL | ✅ FIXED (7826e6dcb) |
| 4 | load_company_info_sec.py | Silent pass on timeout | CRITICAL | ✅ FIXED (HEAD) |
| 5 | load_value_quality_growth_metrics.py | Incomplete data silent skip | CRITICAL | ✅ FIXED (a2fd8fae4+) |
| 6 | dashboard.py routes | Enrichment timeout fallback | HIGH | 🔄 STAGED |
| 7 | orchestrator.py | Config .get() implicit default | HIGH | 🔄 STAGED |
| 8 | load_yfinance_snapshot.py | Cache miss fallback | HIGH | 🔄 STAGED |
| 9 | load_institutional_holdings_13f.py | Multiple tags no logging | HIGH | 🔄 STAGED |
| 10 | load_economic_data.py | .get() sentinel pattern | HIGH | 🔄 STAGED |
| 11 | market_exposure.py | VIX .get() in logging | MEDIUM | 📋 DOCUMENTED |
| 12 | alpaca_sync_manager.py | Reason tracking lazy init | MEDIUM | 📋 DOCUMENTED |
| 13 | notifications.py | Missing field no validation | MEDIUM | 📋 DOCUMENTED |
| 14 | alpaca_mock_server.py | Content-Length default | MEDIUM | 📋 DOCUMENTED |
| 15 | load_trend_analysis.py | Silent skip on gaps | MEDIUM | 📋 DOCUMENTED |

---

## FIX STRATEGY

**Phase 1 - CRITICAL (Session 265 COMPLETE) ✅**
1. ✅ Fix trades panel → propagate errors, not swallow (HEAD)
2. ✅ Fix bootstrap → fail-fast on incomplete config (HEAD)
3. ✅ Fix short_interest_finra → FINRA API (eliminated yfinance) (7826e6dcb)
4. ✅ Fix company_info_sec → explicit timeout marker (HEAD)
5. ✅ Fix value_quality_growth → explicit skip reasons (a2fd8fae4+)

**Phase 2 - HIGH (Session 266+):**
6. 🔄 Fix position enrichment → enrichment_incomplete flag in response
7. 🔄 Fix orchestrator config → explicit None checks (not implicit .get())
8. 🔄 Fix yfinance snapshot → logging which fetch path used + marker on fallback
9. 🔄 Fix institutional holdings → log each tag attempt + which succeeded
10. 🔄 Fix economic data → explicit validation (not .get() sentinel pattern)

**Phase 3 - MEDIUM (Session 267+ Polish pass):**
11-15. Audit remaining .get() patterns, lazy init patterns, field validation

**GOVERNANCE COMPLIANCE:**
All fixes enforce pattern in `CLAUDE.md`:
- ✅ CRITICAL data: Exception on failure (not silent return)
- ✅ OPTIONAL data: Explicit data_unavailable marker (not empty list)
- ✅ Financial calculations: Fail-fast (not return 0/None ambiguity)
- ✅ Pre-commit hook: `check-silent-fallbacks.py` enforces on all commits

---

## GOVERNANCE ENFORCED

All fixes must follow pattern in `CLAUDE.md`:
- **CRITICAL data:** Raise exception (raise RuntimeError/ValueError)
- **OPTIONAL data:** Return explicit `{"data_unavailable": True, "reason": "...", "source": "..."}`
- **Never:** `return []`, `return {}`, `return 0` without marker or exception
- **Never:** `.get(key, default)` with defaults on financial data - use explicit key checks

Pre-commit hook `check-silent-fallbacks.py` enforces compliance on commit.
