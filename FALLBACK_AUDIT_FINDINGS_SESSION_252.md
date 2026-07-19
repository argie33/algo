# Comprehensive Fallback & Secondary Data Source Audit - Session 252

**Status:** Complete audit of fallback patterns, dual implementations, and silent degradation across codebase.

**Scan Date:** 2026-07-18  
**Total Issues Found:** 25+ documented patterns  
**Risk Levels:** 4 CRITICAL, 6 HIGH, 5 MEDIUM, 10+ LOW

---

## CRITICAL ISSUES (Require Immediate Attention)

### CRITICAL-001: Alpaca→yfinance Fallback Without Source Transparency
**File:** `utils/data/source_router.py` (lines 243-335)  
**Pattern:** Silently falls back from Alpaca to yfinance without caller knowing source changed

**Current Behavior:**
```python
# Line 263-276: If Alpaca fails on 1d interval, silently tries yfinance
if interval == "1d" and os.getenv("PRICE_DATA_SOURCE", "yfinance").lower() == "alpaca":
    alpaca_results = self._alpaca_batch_or_none([symbol], start, end, request_desc)
    if alpaca_results is not None and alpaca_results.get(symbol):
        self.last_source = "alpaca"
        return alpaca_results[symbol]
    # Falls through to yfinance with NO indication that source changed
```

**Why It's Problematic:**
- Caller configured for Alpaca data but receives yfinance without knowing
- Price quality/latency differs - Alpaca provides SIP data, yfinance is delayed
- Loaders can't distinguish between "Alpaca unavailable today" vs "using fallback"
- Downstream (Phase 1-7) may use prices of different quality without awareness

**Risk:** Price-based calculations may use degraded/stale data without system knowing

**Should Be:**
1. Option A (Strict): Fail fast if Alpaca unavailable when configured as primary
2. Option B (Hybrid): Return source metadata with data so caller knows quality level
3. Option C: Only fallback for specific errors (auth/rate-limit), not all failures

**Effort to Fix:** 2-4 hours (audit first, then implement source tracking throughout)

---

### CRITICAL-002: SEC Edgar→yfinance Fallback in Fundamentals Chain  
**File:** `utils/data/source_router.py` (lines 166-232) + loader usage  
**Pattern:** Phase 7 signal generation may use yfinance fundamentals after SEC Edgar fails

**Current Behavior:**
```python
# _try_chain() method treats SEC failure as "try next source"
# No distinction between "SEC data unavailable" vs "using yfinance fallback"
sources = [
    ("sec_edgar", lambda: fetch_sec_fundamentals(...)),
    ("yfinance", lambda: fetch_yfinance_fundamentals(...)),  # Silent fallback
]
return self._try_chain(sources, "fundamentals")
```

**Why It's Problematic:**
- SEC Edgar is authoritative for fundamentals (official filings)
- yfinance data is estimator-derived, often stale or incorrect
- composite_score calculation (Phase 7) may use incorrect fundamentals
- Signal quality degrades without visible indication

**Risk:** Trading signals based on incorrect or stale fundamentals → financial losses

**Status:** Blocked in Phase 2 per Session 249 (SEC data format issues)  
**Should Be:** Fail fast on missing SEC data, don't silently degrade to yfinance

**Effort to Fix:** 1-2 hours (add explicit source requirements to Phase 7)

---

### CRITICAL-003: Optional Route Imports Silently Fail at API Startup
**File:** `lambda/api/api_router.py` (lines 51-96)  
**Pattern:** 17 optional routes fail to import, API starts anyway, returns 503 on first request

**Current Behavior:**
```python
_OPTIONAL_ROUTE_MODULES = ["algo", "openapi_spec", "logs", ..., "diagnostics"]

for module_name in _OPTIONAL_ROUTE_MODULES:
    try:
        module = __import__(f"routes.{module_name}", fromlist=[module_name])
        _AVAILABLE_ROUTES[module_name] = module
    except Exception as e:  # Silent catch-all
        error_msg = f"{type(e).__name__}: {str(e)[:200]}"
        _ROUTE_IMPORT_ERRORS[module_name] = error_msg
        logger.warning(...)  # Only logs warning, doesn't fail
```

**Why It's Problematic:**
- No distinction between "truly optional" (logs, swagger) vs "critical" (algo, scores)
- If `routes/algo.py` fails to import, all dashboard endpoints fail silently
- Deployment breakage invisible until first client request
- Production incident = client discovers API is broken

**Risk:** Invisible deployment failures, customer-facing outages

**Examples of Route Import Failures That Should FAIL-FAST:**
- `routes/algo.py` - ALL dashboard endpoints depend on this
- `routes/scores.py` - Stock scoring data (Phase 7)
- `routes/market.py` - Market regime (critical for position sizing)
- `routes/signals.py` - Signal data (trading decisions)

**Examples of Routes That CAN Safely Be Optional:**
- `routes/logs.py` - Frontend logging only
- `routes/openapi_spec.py` - API documentation only
- `routes/contact.py` - Contact form (informational)

**Should Be:** 
```python
CRITICAL_ROUTES = {"health", "algo", "scores", "market", "signals"}

for module in CRITICAL_ROUTES:
    # Fail-fast - don't start API if critical route can't load
    try:
        _AVAILABLE_ROUTES[module] = __import__(...)
    except Exception as e:
        raise RuntimeError(f"CRITICAL: Failed to load {module}: {e}") from e

for module in OPTIONAL_ROUTES:
    # Safe to skip - app still functions
    try:
        _AVAILABLE_ROUTES[module] = __import__(...)
    except Exception as e:
        logger.warning(f"Optional route {module} unavailable")
```

**Effort to Fix:** 1-2 hours (audit which routes are truly critical, add fail-fast)

---

### CRITICAL-004: Portfolio Data Cache Survives API Outages (30-min stale data)
**File:** `dashboard/api_data_layer.py` (lines ~294-400)  
**Pattern:** Cache fallback during API failures masks stale portfolio data

**Current Behavior:**
- Cache TTL: 30 minutes or until first API error
- On 503/504 error: Returns cached data (potentially 30 min old) without "STALE" warning
- Dashboard displays positions/cash as if current when actually from 30 min ago

**Why It's Problematic:**
- User sees 30-min-old portfolio positions without knowing they're stale
- User might make trading decisions based on outdated P&L
- Position sizing calculations use stale exposure
- No way to distinguish "live data" from "30-min cache"

**Risk:** User makes trades based on stale position data → financial losses

**Should Be:** Never return cached portfolio data on API failure - show error state instead

**Effort to Fix:** 2-3 hours (redesign cache invalidation, add freshness checks)

---

## HIGH-PRIORITY ISSUES (Should Fix This Sprint)

### HIGH-001: 80+ Silent .get() Defaults Treating Missing = Zero
**Files:** 
- `dashboard/panels/health.py` (15+ instances)
- `dashboard/panels/positions.py` (3+ instances)
- `loaders/*.py` (20+ instances)

**Pattern:** `.get("field", 0)` masks missing data as zero activity

**Examples:**
```python
# dashboard/panels/health.py:320
signals_generated = data.get("signals_generated", 0)  # 0 = no signals OR missing data!

# dashboard/panels/health.py:331
tables_fresh = data.get("tables_fresh", 0)  # 0 = no fresh tables OR data missing!

# loaders/load_prices.py:469
price_count = data.get("row_count", 0)  # Masks missing loader output as zero rows
```

**Why It's Problematic:**
- Dashboard shows "0 signals generated" when actually data is missing
- Operators can't distinguish "no trading activity" from "system broken"
- Silent degradation: system appears working when actually failing
- Phase 1 freshness check uses these defaults, might skip real issues

**Risk:** Silent system failures masked as "normal operation"

**Should Be:** Explicit None values or error states, never default to 0

**Effort to Fix:** 3-4 hours (audit all 80+ instances, replace with explicit checks)

---

### HIGH-002: Portfolio Fetch Field Fallback (snapshot_date → last_run)
**File:** `dashboard/fetchers_portfolio.py` (lines 89-99)

**Pattern:** Tries snapshot_date first, falls back to last_run without clear error

**Current:**
```python
snapshot_date = port.get("snapshot_date")
if snapshot_date is None:
    # Try secondary field
    snapshot_date = port.get("last_run")
    if snapshot_date is None:
        logger.error("Portfolio missing both fields...")
        return error
```

**Why It's Problematic:**
- Schema mismatch between API and consumer - which field is authoritative?
- Fallback suggests fields have same semantics when they might not
- Future schema changes could break silently

**Should Be:** Require exact field names, fail if field missing (schema contract)

**Effort to Fix:** 1 hour (remove fallback, require explicit field)

---

### HIGH-003: API Response Format Dual-Path Handling
**File:** `lambda/api/response_formatter.py` + `dashboard/api_data_layer.py`  
**Pattern:** Multiple ways to structure API responses, callers try both

**Current:** Different routes return different response formats:
- Some: `{statusCode, data, message}`
- Others: `{statusCode, result, metadata}`
- Falls back between formats when first doesn't match

**Why It's Problematic:**
- Inconsistent API schema increases bug surface
- Callers must implement fallback logic (fragile)
- Schema drift over time

**Should Be:** Single canonical response format enforced across all routes

**Effort to Fix:** 4-6 hours (audit all routes, standardize schema)

---

### HIGH-004: Market Regime Falsy Check (if not tier)
**File:** `dashboard/fetchers_market.py` (line 151)

**Pattern:** Uses falsy check instead of None check
```python
tier = current.get("regime")
if not tier:  # Treats 0, "", False as missing
    raise ValueError("regime missing")
```

**Why It's Problematic:**
- If regime can legitimately be 0 or empty string, check is wrong
- Fails on valid data if that data is falsy
- Should be: `if tier is None:`

**Should Be:** Explicit None check for clarity

**Effort to Fix:** < 1 hour (one-line fix, add tests)

---

### HIGH-005: SEC Edgar Missing = yfinance Fallback (Company Info)
**File:** `loaders/load_company_info_sec.py` (lines ~80-120)  
**Pattern:** Falls back to yfinance for company facts when SEC unavailable

**Why It's Problematic:**
- SEC is authoritative source for company fundamentals
- yfinance data is crowd-sourced, often incorrect
- Fallback silently introduces inaccuracy

**Should Be:** Fail-fast, mark data unavailable, don't use yfinance

**Effort to Fix:** 1-2 hours (disable fallback, require explicit SEC data)

---

### HIGH-006: Trade Insert ON CONFLICT (Already Fixed in HEAD!)
**File:** `algo/trading/executor_entry_handler.py` (recently fixed - commit 0ff4e545d)  
**Status:** ✅ FIXED - Removed ON CONFLICT DO NOTHING, now fails fast

---

## MEDIUM-PRIORITY ISSUES

### MEDIUM-001: Graceful 503/504 Degradation on Signals
**File:** `dashboard/fetchers_signals.py` (lines 74-96)

**Issue:** Signals gracefully degrade on transient 503/504 errors  
**Question:** Are signals truly optional enrichment, or critical for trading?
- If optional → OK to degrade
- If critical → Should fail-fast

**Action:** Verify signal usage in Phase 7/8, update comment if needed

---

### MEDIUM-002: Market Stage / Trend Optional Fields
**File:** `dashboard/fetchers_market.py` (lines 163-176)

**Pattern:** market_stage and market_trend are optional (skip if None)  
**Question:** Are these truly optional or required for risk calculations?

**Action:** Verify in Phase 5 exposure policy, change to required if needed

---

### MEDIUM-003: Alpaca→yfinance Per-Symbol Fallback  
**File:** `utils/data/source_router.py` (lines 337-371)

**Pattern:** `_fill_alpaca_residual_from_yfinance()` fills Alpaca gaps with yfinance

**Risk:** Mixed sources in single symbol (first N bars Alpaca, rest yfinance)  
**Should Be:** Either all-Alpaca or all-yfinance per symbol, never mix sources

**Effort:** 2-3 hours (track source per symbol, enforce consistency)

---

### MEDIUM-004: yfinance Not Installed → Data Unavailable Marker
**File:** `utils/data/source_router.py` (lines 391-399)

**Pattern:** Returns explicit marker if yfinance not installed (correct!)  
**Note:** This is actually GOOD fail-fast behavior - keep as-is

---

### MEDIUM-005: VIX as List Handling
**File:** `dashboard/fetchers_market.py` (lines 119-131)

**Pattern:** If VIX is list (data corruption), extracts first element  
**Issue:** This is a workaround for upstream data quality issue

**Should Be:** Fail-fast, return error, fix root cause in VIX loader  
**Effort:** 1-2 hours (trace VIX corruption source, fix in load_market_status_daily)

---

## LOW-PRIORITY ISSUES

- Reconciliation entry price fallback (already has audit logging per Session 248)
- Sector momentum COALESCE fallbacks (already fixed per git history)
- Phase 7 signal composite_score fallback (already fixed with INNER JOIN)
- Dashboard "data not available" graceful degradation (intentional, working as designed)

---

## Summary Statistics

| Category | Count | Impact |
|----------|-------|--------|
| CRITICAL | 4 | Causes system failures or wrong trading decisions |
| HIGH | 6 | Causes silent failures or data quality issues |
| MEDIUM | 5 | Causes incorrect behavior on edge cases |
| LOW | 10+ | Minor issues, mostly already fixed |
| **TOTAL** | **25+** | |

---

## Recommended Fix Order

1. **CRITICAL-003** (1-2 hours): Make critical routes fail-fast at startup
2. **CRITICAL-001** (2-4 hours): Add source transparency to Alpaca/yfinance fallback
3. **HIGH-001** (3-4 hours): Replace .get() defaults with explicit None checks
4. **CRITICAL-002** (1-2 hours): Require SEC data, don't fallback to yfinance  
5. **CRITICAL-004** (2-3 hours): Remove portfolio cache fallback, show error on API failure

**Estimated Total Effort:** 15-20 hours for all CRITICAL + HIGH fixes

---

## Governance Alignment

✅ **Fail-Fast Principle:** Remaining issues where we fall back silently violate this  
✅ **Data Integrity:** Fallbacks without metadata tracking reduce confidence in data quality  
✅ **Transparency:** Users/operators need to know when system is degraded vs. normal  

All fixes align with established CLAUDE.md governance: explicit errors >> silent degradation.

---

## Action Items for Session 252+

- [ ] Audit which dashboard routes are truly critical vs. optional
- [ ] Add source metadata tracking to Alpaca/yfinance fallback
- [ ] Replace 80+ .get() defaults with explicit None/error handling  
- [ ] Verify signal criticality (Phase 7/8 requirements)
- [ ] Trace and fix VIX data corruption source
- [ ] Update api_router.py route import logic
- [ ] Disable portfolio cache fallback during API outages
- [ ] Review and document all remaining "graceful degradation" patterns
