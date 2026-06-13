# Dashboard Audit: Critical Issues Found

**Status:** Dashboard runs but has 25+ critical issues affecting stability, security, performance, and data integrity.

**Goal:** Identify all issues blocking stable, production-ready operation before market open.

---

## CRITICAL ISSUES (Must Fix Before Production)

### 1. **Duplicate Function Definition - `_error_panel()`** [EASY FIX]
- **File:** `tools/dashboard/panels.py`
- **Lines:** Defined at lines 92-111 AND 130-150
- **Impact:** Code bloat, confusing semantics, second definition shadows first
- **Fix:** Delete lines 130-150 (duplicate)

### 2. **Thread Unsafe Sector Aggregation Cache** [MEDIUM SEVERITY]
- **File:** `tools/dashboard/utilities.py` lines 121-252
- **Issue:** `_sector_agg_cache` is a global OrderedDict accessed without lock during `popitem()` eviction (line 244)
- **Scenario:** Two threads call `compute_sector_agg()` simultaneously, one evicts while other reads cache
- **Fix:** Add `_sector_cache_lock` and acquire it for all cache operations
- **Current:** Has `_data_status_lock` but not `_sector_cache_lock`

### 3. **Unsafe Timeout Exception Handling in `load_all()`** [MEDIUM SEVERITY]
- **File:** `tools/dashboard/fetchers.py` lines 603-608
- **Issue:** Code accesses `futures.items()` while `as_completed()` is still iterating after timeout
- **Problem:** Creates race condition where futures dict is accessed outside context where it's being iterated
- **Fix:** Collect pending futures before timeout, process them separately outside loop

```python
# CURRENT (UNSAFE):
except TimeoutError:
    for f, k in futures.items():  # <-- unsafe, futures still being iterated above
        if not f.done():
            out[k] = {"_error": f"Timeout (exceeded {BATCH_TIMEOUT}s)"}
```

### 4. **API Base URL Defaults to Localhost (Security/Reliability Issue)** [HIGH]
- **File:** `tools/dashboard/utilities.py` line 115
- **Issue:** `API_BASE_URL = os.environ.get("DASHBOARD_API_URL", "http://localhost:3001")`
- **Problem:** If env var not set, silently falls back to localhost instead of failing fast
- **Impact:** In production, would hit local API instead of AWS Lambda
- **Fix:** Require env var, raise error if not set:
```python
API_BASE_URL = os.environ.get("DASHBOARD_API_URL")
if not API_BASE_URL:
    raise RuntimeError("DASHBOARD_API_URL env var required (points to AWS Lambda API)")
```

### 5. **No Connection Pooling for HTTP Requests** [PERFORMANCE]
- **File:** `tools/dashboard/utilities.py` lines 127-177
- **Issue:** Every `api_call()` creates new `requests.Session` implicitly
- **Impact:** 25 parallel fetchers × no pooling = 25 separate TCP connections
- **Fix:** Create session once and reuse:
```python
_session = requests.Session()
_session.close()  # Call at shutdown
# Use _session.get() instead of requests.get()
```

### 6. **Inconsistent Data Structure in Fetchers** [DATA INTEGRITY]
- **Files:** Multiple fetchers in `tools/dashboard/fetchers.py`
- **Issue:** Inconsistent handling of API response structure:
  - Some expect `data.get('data', {})` → dict
  - Some expect `data.get('data', [])` → list
  - Some expect `items` key in dict
- **Examples:**
  - Line 121: `port = data.get('data', {})` (dict)
  - Line 201: `items = result.get('items', [])` (list)
  - Line 252: `rankings = data.get('data', [])` (list)
- **Impact:** Silent failures if API returns unexpected structure
- **Fix:** Document API contract and validate all responses against schema

### 7. **Missing Error Handling in `fetch_notifications()`** [BUG]
- **File:** `tools/dashboard/fetchers.py` lines 346-353
- **Issue:** Returns error dict directly instead of `{"_error": ...}` format:
```python
# CURRENT (INCONSISTENT):
except Exception as e:
    return {"_error": str(e)}  # But also returns list on success (line 351)

# On success: returns `data.get('data', [])` which is a list
# On error: returns dict with "_error"
```
- **Fix:** Return consistent structure: `{"items": [], "_error": "..."}`

### 8. **API Response Validation Missing** [DATA INTEGRITY]
- **File:** All fetchers in `tools/dashboard/fetchers.py`
- **Issue:** Fetchers extract data without validating required fields exist
- **Examples that blindly access dict keys:**
  - Line 124: `"total_portfolio_value": safe_float(port.get("total_portfolio_value"))`
  - Line 169: `"wr": safe_float(perf.get("win_rate_pct"))`
  - Line 389: `"var95": safe_float(d.get("var_pct_95"))`
- **Problem:** If API returns `{"data": {}}` (empty), dashboard displays all `--` with no error indication
- **Fix:** Validate required fields after API call, return `_error` if missing:
```python
required = ["total_portfolio_value", "total_cash", "open_positions"]
if not all(k in port for k in required):
    return {"_error": f"Missing required fields in portfolio response"}
```

### 9. **Log File Written to TEMP Directory** [OPERATIONAL]
- **File:** `tools/dashboard/utilities.py` line 106
- **Issue:** `_log_file = os.path.join(os.environ.get("TEMP", "/tmp"), "dashboard.log")`
- **Problem:** TEMP is not persistent across runs, loses logs
- **Fix:** Use proper log directory:
```python
log_dir = os.path.expanduser("~/.algo/logs")
os.makedirs(log_dir, exist_ok=True)
_log_file = os.path.join(log_dir, "dashboard.log")
```

### 10. **No Data Freshness Tracking** [MONITORING]
- **File:** `tools/dashboard/fetchers.py`
- **Issue:** When data is stale, no indication in logs or display
- **Example:** `fetch_perf()` could return 30-day-old data with no warning
- **Fix:** Add timestamp validation for each fetcher:
```python
def _validate_freshness(data, max_age_hours=24):
    if "timestamp" not in data:
        logger.warning(f"Data missing timestamp - cannot validate freshness")
        return False
    age = (datetime.now() - data["timestamp"]).total_seconds() / 3600
    if age > max_age_hours:
        logger.warning(f"Data stale: {age:.1f}h old (threshold: {max_age_hours}h)")
    return age <= max_age_hours
```

### 11. **No Cache of Successful API Responses** [RESILIENCE]
- **File:** Dashboard architecture
- **Issue:** If API fails, dashboard shows empty state with no fallback
- **Scenario:** API Lambda restarts → all panels show empty for 30 seconds until next refresh
- **Fix:** Implement simple JSON cache of last successful response:
```python
_cache_dir = os.path.expanduser("~/.algo/dashboard-cache")
# On successful API call: write to disk
# On API error: load from cache if available (mark as stale)
```

### 12. **Hardcoded Market Hours Without Holiday Support** [OPERATIONAL]
- **File:** `tools/dashboard/formatters.py` lines 58-105
- **Issue:** `is_open()` and `mkt_hours_str()` use hardcoded 9:30-16:00 hours
- **Problem:** Doesn't account for:
  - Market holidays (Thanksgiving, Christmas)
  - Early closes (3 PM on July 3)
  - Special market closures
- **Fix:** Query market calendar from database:
```python
def is_open() -> bool:
    from algo.algo_market_calendar import MarketCalendar
    return MarketCalendar.is_market_open_now()
```

### 13. **Hardcoded Orchestrator Run Times** [OPERATIONAL]
- **File:** `tools/dashboard/formatters.py` lines 107-132
- **Issue:** `next_run_str()` hardcodes run times: 2 AM, 9:30 AM, 1 PM, 3 PM, 5:30 PM
- **Problem:** If orchestrator schedule changes, dashboard doesn't update
- **Fix:** Fetch schedule from Lambda environment or database:
```python
# Query orchestrator schedule from API or config
ORCHESTRATOR_SCHEDULE = api_call('/api/algo/schedule')  # [{"hour": 9, "min": 30}, ...]
```

### 14. **Sector Cache Doesn't Validate Position Structure** [DATA INTEGRITY]
- **File:** `tools/dashboard/utilities.py` lines 197-252
- **Issue:** `compute_sector_agg()` hashes positions without validating they're well-formed
- **Scenario:** If position dict missing `sector` or `position_value`, cache hash still works but data is garbage
- **Fix:** Validate before hashing:
```python
def _validate_position(pos):
    if not isinstance(pos, dict):
        return False
    required = ["sector", "position_value"]
    return all(k in pos for k in required)

# Then in compute_sector_agg:
invalid_positions = [p for p in pos if not _validate_position(p)]
if invalid_positions:
    logger.error(f"Invalid positions in sector agg: {len(invalid_positions)} malformed")
    return None, None, 0
```

### 15. **Positions Data Structure Inconsistency** [ARCHITECTURE]
- **Files:** `tools/dashboard/utilities.py` and `tools/dashboard/fetchers.py`
- **Issue:** Two different patterns for positions data:
  - `normalize_positions_data()` returns tuple `(list, timestamp, has_error)`
  - `fetch_positions()` returns `{"items": [...], "timestamp": ...}`
  - Some code checks `if pos: ... len(pos)`  (expects list)
  - Some code checks `pos.get('items')`  (expects dict)
- **Impact:** Confusing, error-prone
- **Fix:** Standardize to single structure: always `{"items": [], "timestamp": None, "_error": None}`

---

## HIGH PRIORITY ISSUES (Should Fix)

### 16. **No Circuit Breaker Pattern for API** [RESILIENCE]
- **Issue:** If API Lambda is slow/down, dashboard fetches continue hammering it
- **Fix:** Implement circuit breaker (fail fast after 3 consecutive timeouts):
```python
_circuit_breaker_state = "closed"  # closed, open, half-open
_circuit_breaker_failures = 0

def api_call():
    global _circuit_breaker_state
    if _circuit_breaker_state == "open":
        return {"_error": "Circuit breaker open - API unavailable"}
    # ... normal call ...
    if timeout:
        _circuit_breaker_failures += 1
        if _circuit_breaker_failures >= 3:
            _circuit_breaker_state = "open"
```

### 17. **Thread Pool Size Calculation Wrong** [PERFORMANCE]
- **File:** `tools/dashboard/fetchers.py` line 592
- **Issue:** `max_workers=min(len(FETCHERS), 16)` = 16 workers for 25 fetchers
- **Problem:** Too many threads, could saturate connection pool
- **Fix:** `max_workers=min(len(FETCHERS), 8)` or make configurable

### 18. **No Pagination for Large Result Sets** [PERFORMANCE]
- **File:** `tools/dashboard/fetchers.py`
- **Issue:** Fetchers request all data without limits:
  - `fetch_recent_trades()` requests 100 trades but displays 10
  - `fetch_sector_ranking()` requests all sectors
- **Problem:** API could return millions of rows, consuming memory/bandwidth
- **Fix:** Add pagination params:
```python
# fetch_sector_ranking():
data = api_call('/api/sectors', params={'limit': 50, 'offset': 0})
```

### 19. **Missing Required Fields After Validation** [DATA INTEGRITY]
- **Example:** `fetch_perf()` returns 0 for all metrics if API error (line 152-164)
- **Problem:** Can't distinguish between "0 trades" and "API failed"
- **Fix:** Return `_error` instead of zeros:
```python
if data.get('_error'):
    return {"_error": data.get('_error'), "n": None, "w": None, ...}  # None not 0
```

### 20. **No Input Validation on CLI Arguments** [SECURITY]
- **File:** `tools/dashboard/main.py` lines 14-60+
- **Issue:** Uses `argparse` but doesn't validate watch interval
- **Problem:** User could pass `--watch -999` or non-integer
- **Fix:** Add type and validation:
```python
parser.add_argument('-w', '--watch', type=int, help='Watch interval (seconds)', 
                   default=30, choices=range(5, 601))  # 5-600 sec only
```

### 21. **Panel Title Styles Inconsistent** [PRESENTATION]
- **File:** `tools/dashboard/panels.py`
- **Issue:** Some panels use `[bold cyan]`, others `[bold magenta]`, borders inconsistent
- **Fix:** Define panel style constants:
```python
PANEL_STYLE_PRIMARY = {"border_style": "cyan", "title_style": "bold cyan"}
PANEL_STYLE_SECONDARY = {"border_style": "green", "title_style": "bold green"}
```

### 22. **Error Messages Don't Distinguish Failure Modes** [UX]
- **Issue:** All errors return same message: "API error" or "Timeout"
- **Example:** User can't tell if API is down vs network flaky vs credentials invalid
- **Fix:** Use error codes:
```python
return {
    "_error": "API unavailable",
    "_error_code": "API_TIMEOUT",  # specific, machine-readable
    "_error_details": "Lambda took >20s to respond"
}
```

### 23. **No Concurrent Write Prevention on Cache** [CONCURRENCY]
- **Issue:** If two threads try to write cache simultaneously, data could corrupt
- **Fix:** Use atomic writes with temp file + rename:
```python
def _write_cache_atomic(key, data):
    import tempfile
    with tempfile.NamedTemporaryFile(dir=_cache_dir, delete=False) as f:
        json.dump(data, f)
        temp_path = f.name
    os.rename(temp_path, os.path.join(_cache_dir, key))
```

### 24. **Phase Result Parsing Too Permissive** [DATA INTEGRITY]
- **File:** `tools/dashboard/panels.py` lines 39-69
- **Issue:** `_best_halt_reason()` tries multiple field names without validating data type
- **Problem:** If phase_results contains garbage, code silently uses wrong field
- **Fix:** Validate structure first:
```python
if not isinstance(phase_results, list):
    return [("", "Invalid phase_results structure")]
for p in phase_results:
    if not isinstance(p, dict) or "status" not in p:
        logger.warning(f"Malformed phase result: {p}")
        continue
```

### 25. **Memory Leak: Logger Handlers Not Cleaned Up** [STABILITY]
- **File:** `tools/dashboard/utilities.py` lines 105-112
- **Issue:** Logging configured but handlers never closed
- **Problem:** In watch mode with 30-second refreshes, handler could accumulate
- **Fix:** Use atexit to cleanup:
```python
import atexit
logging.basicConfig(...)
atexit.register(lambda: [h.close() for h in logger.handlers])
```

---

## MODERATE PRIORITY ISSUES

### 26. **Inconsistent Error Field Names Across Fetchers**
- Some return `{"_error": "msg"}` (correct per memory)
- Some return `{"_error": msg}` and also return list on success (fetch_notifications)
- Fix: Standardize all to `{"_error": "msg", ...}`

### 27. **Missing Docstrings on Public Functions**
- `api_call()` has docstring but many fetchers don't
- Hard to understand contract (required response structure)

### 28. **Color Codes Hardcoded**
- `TIER_COLOR`, `MASCOT_COLORS` are tuples
- Hard to change theme; should be in constants file

### 29. **No Timeout on Database Operations**
- `fetch_health()` calls API which queries database
- No statement timeout visible, could hang dashboard

### 30. **Panel Rendering Doesn't Handle Missing Data Gracefully**
- If `data.get("perf")` returns None, panel_performance_spark() could crash
- Need null-checks in all panel renderers

---

## Recommended Fix Priority Order

1. **CRITICAL (Today before market open):**
   - Issue #1: Remove duplicate _error_panel
   - Issue #4: Fix API_BASE_URL fallback
   - Issue #3: Fix TimeoutError race condition
   - Issue #2: Add lock to sector cache

2. **HIGH (This week):**
   - Issue #6: Standardize data structure
   - Issue #8: Add API response validation
   - Issue #5: Add HTTP connection pooling
   - Issue #12: Use real market calendar
   - Issue #13: Fetch orchestrator schedule dynamically

3. **MEDIUM (Before next release):**
   - Issue #9: Fix log file location
   - Issue #10: Add data freshness tracking
   - Issue #11: Implement cache for resilience
   - Issue #16: Add circuit breaker

4. **NICE-TO-HAVE (Backlog):**
   - Issue #17: Tune thread pool size
   - Issue #18: Add pagination
   - Issue #20-30: UX/code quality improvements

---

## Summary

- **Total Issues Found:** 30+
- **Critical (market-open blockers):** 4
- **High (stability/data integrity):** 10
- **Medium (operational):** 8
- **Low (UX/maintainability):** 8+

**Estimated Fix Time:**
- Critical: 30 min (duplicate function, API URL, locks)
- High: 2-3 hours (standardization, validation)
- Medium: 2-4 hours (caching, market calendar)
- **Total: 5-7 hours to production-ready**

Dashboard is **functionally operational** but has **reliability/integrity gaps** that will cause issues under load or API failures.
