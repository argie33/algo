# Fail-Fast Violations & Fallback Patterns

**Goal:** Identify all cases where we silently fall back to defaults instead of failing fast in critical finance paths.

**Finance Best Practice:** When dealing with trading positions, prices, and portfolio calculations, missing or invalid data should ALWAYS fail loudly (raise exception), never silently default.

---

## CRITICAL ISSUES (Finance-Facing Data)

### 1. **Reconciliation.py — PnL Fallback to 0** ⚠️ CRITICAL
**File:** `algo/infrastructure/reconciliation.py`
**Line:** 1142, 1144
**Pattern:**
```python
pnl = float(pnl_raw) if pnl_raw else 0.0  # FALLBACK: masks missing PnL
pnl_pct = (float(pnl_pct_raw) * 100) if pnl_pct_raw else 0.0  # FALLBACK
```
**Problem:** Missing realized P&L should be an error, not silently 0. This breaks reconciliation accuracy.
**Impact:** Positions imported with missing P&L data get registered as break-even (0%) instead of raising an error.
**Fix Needed:** Require both pnl_raw and pnl_pct_raw to be present; raise ValueError if missing.

---

### 2. **Reconciliation.py — Market Value Fallback to Computed Value** ⚠️ CRITICAL
**File:** `algo/infrastructure/reconciliation.py`
**Line:** 1140
**Pattern:**
```python
pos_value = float(pos_value_raw) if pos_value_raw else qty * cur_price  # FALLBACK: computes value
```
**Problem:** Using quantity × current_price as fallback for market_value masks Alpaca data issues.
**Impact:** If Alpaca returns stale or missing market_value, we silently compute it, hiding data freshness problems.
**Fix Needed:** Fail if market_value is missing; don't compute fallback.

---

### 3. **Executor.py — Order Send Time Fallback** ⚠️ CRITICAL
**File:** `algo/trading/executor.py`
**Line:** 832
**Pattern:**
```python
execution_latency_ms = int((time.time() - getattr(self, "_order_send_time", time.time())) * 1000)
```
**Problem:** If `_order_send_time` not set, latency = 0ms (fake data). TCA records incorrect slippage.
**Impact:** Every order without send time recorded has 0 latency, corrupting TCA metrics.
**Fix Needed:** Require `_order_send_time` to be set before this code path executes; fail if missing.

---

### 4. **Circuit-Breaker Lambda — Database Credential Default Port** ⚠️ MEDIUM
**File:** `lambda/circuit-breaker/index.py`
**Line:** 57
**Pattern:**
```python
"port": int(creds.get("port", 5432))  # FALLBACK: hardcoded default port
```
**Problem:** If port config is missing, silently defaults to 5432. May connect to wrong database.
**Impact:** Credential misconfiguration could go unnoticed; circuit breaker might check wrong DB.
**Fix Needed:** Require port in credentials; raise ValueError if missing.

---

## HIGH PRIORITY ISSUES (Dashboard Data Layer)

### 5. **Fetchers.py — Phases Array Fallback to Empty** ⚠️ HIGH
**File:** `tools/dashboard/fetchers.py`
**Line:** 144
**Pattern:**
```python
phases = inner.get("phases") or []  # FALLBACK: empty array hides missing phase data
```
**Problem:** If phases is missing from API response, returns empty array instead of error.
**Impact:** Dashboard shows "no phases" instead of "data error", hiding API/loader issues.
**Fix Needed:** Explicit validation; raise error if phases key is missing.

---

### 6. **Fetchers.py — Run Timestamp Chained Fallback** ⚠️ HIGH
**File:** `tools/dashboard/fetchers.py`
**Line:** 156
**Pattern:**
```python
"run_at": inner.get("run_at") or inner.get("completed_at") or inner.get("started_at")
```
**Problem:** Multiple fallback levels hide which timestamp is actually missing.
**Impact:** Can't tell if run_at, completed_at, or started_at is the missing field.
**Fix Needed:** Explicit check; fail if primary field (run_at) is missing.

---

### 7. **Fetchers.py — Success & Halted Flags Default to False** ⚠️ HIGH
**File:** `tools/dashboard/fetchers.py`
**Line:** 157-158
**Pattern:**
```python
"success": inner.get("success", False),  # FALLBACK
"halted": inner.get("halted", False),   # FALLBACK
```
**Problem:** Missing status flags default to "not successful / not halted", hiding API data issues.
**Impact:** Dashboard assumes runs succeeded when data is actually missing.
**Fix Needed:** Explicit validation; require these fields in API response.

---

### 8. **Fetchers.py — Algo Config Enable Fallback to True** ⚠️ HIGH
**File:** `tools/dashboard/fetchers.py`
**Line:** 186-187
**Pattern:**
```python
en_raw = cfg.get("enable_algo", "true")
enabled = str(en_raw).lower() in ("true", "1", "yes") if en_raw is not None else True  # FALLBACK
```
**Problem:** If enable_algo config is missing, defaults to True (enable algo).
**Impact:** Missing config doesn't halt algo; it starts trading by default.
**Fix Needed:** Require enable_algo in config; fail if missing.

---

### 9. **Fetchers.py — Market Regime Fallback Chain** ⚠️ HIGH
**File:** `tools/dashboard/fetchers.py`
**Line:** 258-269
**Pattern:**
```python
tier = current.get("regime")
if not tier:
    active_tier = mkt.get("active_tier")
    if isinstance(active_tier, dict):
        tier = active_tier.get("name")
if not tier:
    logger.warning("...")
    tier = "unknown"  # FALLBACK: silent default
```
**Problem:** Market regime falls through multiple levels, finally defaults to "unknown".
**Impact:** Position sizing uses "unknown" regime instead of failing; position sizing behavior is undefined.
**Fix Needed:** Explicit validation; fail if regime cannot be determined from primary source.

---

### 10. **Fetchers.py — Config Value Parsing with Defaults** ⚠️ MEDIUM
**File:** `tools/dashboard/fetchers.py`
**Line:** 190-196
**Pattern:**
```python
"mode": cfg.get("execution_mode"),  # Can be None
"max_pos_pct": safe_float(cfg.get("max_position_size_pct")),  # Can be None
```
**Problem:** Config values are silently None when missing; safe_float() returns None.
**Impact:** Dashboard doesn't show error; position sizer receives None for critical config.
**Fix Needed:** Validate all required config fields exist before returning.

---

## MEDIUM PRIORITY ISSUES (Data Processing)

### 11. **Reconciliation.py — Early Skip on Missing Qty** ⚠️ MEDIUM
**File:** `algo/infrastructure/reconciliation.py`
**Line:** 1128-1129, 1140-1144
**Pattern:**
```python
if qty_raw is None or qty_raw == 0:
    continue  # SILENT SKIP: doesn't log or track
```
**Problem:** Silently skips positions with missing quantity. No audit trail.
**Impact:** Positions with data issues go unnoticed; reconciliation counts appear correct but data is incomplete.
**Fix Needed:** Log and count each skip; raise error if count exceeds threshold.

---

### 12. **Exit-Engine.py — Config Values with .get() Fallback** ⚠️ MEDIUM
**File:** `algo/trading/exit_engine.py`
**Line:** 320, 387, 421, 434, 491
**Pattern:**
```python
if self.config.get("exit_on_rs_line_break_50dma", True):  # FALLBACK to True
require_pb = bool(self.config.get("require_target_pullback", False))  # FALLBACK to False
chandelier_enabled = self.config.get("use_chandelier_trail")  # Can be None
```
**Problem:** Config flags have implicit defaults (True/False) instead of requiring explicit values.
**Impact:** Missing exit rules use default behavior; behavior is undefined when config is incomplete.
**Fix Needed:** All config flags should be required; no implicit defaults.

---

### 13. **Order-Manager.py — Filled Price with .get() Fallback** ⚠️ MEDIUM
**File:** `algo/trading/order_manager.py`
**Line:** 386
**Pattern:**
```python
filled_price = float(data.get("filled_avg_price")) if data.get("filled_avg_price") else None
```
**Problem:** Missing filled_avg_price silently becomes None.
**Impact:** Exit orders created with None filled price; position pricing is wrong.
**Fix Needed:** Require filled_avg_price in order response; fail if missing.

---

### 14. **Trigger-Loaders Lambda — Task Count Fallback to 1** ⚠️ LOW
**File:** `lambda/trigger-loaders/lambda_function.py`
**Line:** 42
**Pattern:**
```python
task_count = int(event.get("task_count", 1))  # FALLBACK to 1 task
```
**Problem:** Missing task_count defaults to 1 instead of requiring explicit specification.
**Impact:** Concurrent loader runs may be triggered with wrong parallelism.
**Fix Needed:** Require task_count; use AWS context to infer if not specified.

---

### 15. **Algo-Orchestrator Lambda — Dry-Run Mode Fallback** ⚠️ LOW
**File:** `lambda/algo_orchestrator/lambda_function.py`
**Line:** 141, 144
**Pattern:**
```python
dry_run = event.get("dry_run", True)   # FALLBACK to dry_run=True for evening
dry_run = event.get("dry_run", False)  # FALLBACK to dry_run=False for preclose
```
**Problem:** Missing dry_run flag uses implicit defaults that differ by run type.
**Impact:** Ambiguous whether a run is live or dry if dry_run is not specified.
**Fix Needed:** Require dry_run explicitly; don't infer from run_identifier.

---

## PATTERNS THAT ARE OK (Intentional Fallbacks)

### ✅ API Caching During Circuit Breaker
**File:** `tools/dashboard/api_data_layer.py`
**Line:** 270-283
**Status:** CORRECT - Intentional fallback to stale cache when circuit breaker is open
**Reason:** Documented as explicit fallback for degraded mode; not a silent default

### ✅ Empty Collection Defaults for Optional Fields
**File:** `various`
**Pattern:** `.get("items", [])` for truly optional arrays
**Status:** CORRECT WHEN - Used only for optional fields (activity logs, auxiliary data)
**Watch For:** Don't use for required fields (positions, trades, signals)

---

## Summary by Severity

| Severity | Count | Impact |
|----------|-------|--------|
| 🔴 CRITICAL | 4 | Finance calculations corrupted (PnL, values, latency) |
| 🟠 HIGH | 6 | Dashboard doesn't error; hides data issues |
| 🟡 MEDIUM | 4 | Exit logic & order tracking affected |
| 🔵 LOW | 1 | Config/parallelism ambiguity |

**Total Violations:** 15

---

## Recommended Fix Priority

1. **Immediate (this sprint):** Fix #1, #2, #3 (reconciliation & executor latency)
2. **Next sprint:** Fix #5, #6, #7, #8, #9 (dashboard fail-fast)
3. **Backlog:** Fix #11-15 (lower impact config/skip issues)
