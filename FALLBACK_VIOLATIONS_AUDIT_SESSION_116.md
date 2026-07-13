# Session 116 - Comprehensive Fallback Violations Audit

**Goal:** Find and eliminate ALL silent fallbacks in finance app (fail-fast principle)

**Status:** Audit in progress - violations being systematically cataloged and fixed

---

## CRITICAL VIOLATIONS FOUND

### Category 1: .get() with Fallback Chains (15 files)

**Files with `.get(...) or` patterns:**
1. `dashboard/fetchers_portfolio.py` - Lines 91, 98, 104, 135-140, 156-160
2. `dashboard/local_api_server.py` 
3. `dashboard/fetchers_config.py`
4. `dashboard/api_data_layer.py`
5. `lambda/api/routes/algo_handlers/metrics.py`
6. `lambda/api/routes/algo_handlers/signals.py` - Lines 437-444 (CRITICAL: financial counts with silent 0 default)
7. `scripts/rotate_secrets_automated.py`
8. `utils/ops/orchestrator_query.py`
9. `utils/decorators.py`
10. `config/credential_validator.py`
11. + 5 others with various fallback patterns

**Pattern 1a: Redundant Cascading Fallbacks**
```python
# lambda/api/routes/algo_handlers/signals.py:437-442
total = int(result_dict.get("total", 0) or 0)  # VIOLATES: .get() already provides 0, "or 0" is redundant
t1 = int(result_dict.get("t1", 0) or 0)
t2 = int(result_dict.get("t2", 0) or 0)
# ... more of same pattern
```
**Impact:** CRITICAL - Signal counts silently default to 0 instead of raising. Operator can't distinguish "no signals" from "API/query failure"

**Pattern 1b: Financial Field Fallback Chains**
```python
# dashboard/fetchers_portfolio.py:91
snapshot_date = port.get("snapshot_date") or port.get("last_run")  # Multi-level fallback
# If both are None, code doesn't know which one is missing
```
**Impact:** HIGH - Can't diagnose which API field is broken; cascading failures

**Pattern 1c: Silent Dict Defaults**
```python
# dashboard/fetchers_portfolio.py:98-99
data_freshness = port.get("data_freshness", {})  # Silent empty dict
is_stale_from_api = data_freshness.get("is_stale", False)  # Silent False when stale check unavailable
```
**Impact:** HIGH - Operator doesn't know if freshness check ran or failed

**Pattern 1d: Multi-Level Credential/Config Fallbacks**
```python
# dashboard/fetchers_portfolio.py:104
data_age = data_freshness.get("age_seconds", port.get("data_age_seconds", "unknown"))
```
**Impact:** MEDIUM - Operator sees "unknown" but can't tell which layer failed

### Category 2: Implicit None Returns on Financial Data (50+ files)

**Pattern 2a: .get() without explicit nil marker**
```python
# lambda/api/routes/algo_handlers/signals.py:443-444
avg_score = result_dict.get("avg_score")  # Returns None if missing
signal_date = result_dict.get("signal_date")  # Returns None if missing
# Returned in API response with no indication field was unavailable
```
**Impact:** HIGH - API response can't distinguish "score=None (calculated as None)" from "score unavailable (query failed)"

**Pattern 2b: Derived metric .get() without checks**
```python
# dashboard/fetchers_portfolio.py:156-160
daily_return = port.get("daily_return_pct")  # Implicit None
cumulative_return = port.get("cumulative_return_pct")  # Implicit None
max_dd = port.get("max_drawdown_pct")  # Implicit None
largest_pos = port.get("largest_position_pct")  # Implicit None
```
**Impact:** MEDIUM - Valid for derived metrics (legitimately None on first day), but needs explicit marker

### Category 3: Exception Swallowing (250+ files have try/except)

**High-risk exception handlers:**
1. `loaders/load_economic_data.py` - Returns [] on API failure
2. `loaders/price_*.py` - Multiple try/except blocks with silent empty returns
3. `lambda/api/routes/` - Several routes catching exceptions without re-raising
4. `dashboard/` - Exception swallowing in data fetchers

**Pattern 3a: Silent Empty Returns**
```python
try:
    data = fetch_from_api()
except Exception:
    return []  # VIOLATES: Should raise, not silent empty
```

**Pattern 3b: Exception Logging Without Propagation**
```python
except Exception as e:
    logger.error(f"Failed to load {symbol}: {e}")
    return None  # VIOLATES: Caller can't distinguish from valid None
```

### Category 4: Implicit Boolean Returns (Validation Functions)

Functions returning bool instead of raising:
- `utils/validation/financial.py` - Likely has validation returning False instead of raising
- `utils/validation/framework.py` - Type conversion returning bool
- `utils/validation/data_quality_scorer.py` - Scoring with implicit 0 defaults

**Impact:** Code can't distinguish "validation passed (False)" from "validation failed silently"

### Category 5: Credential Fallback Chains (5+ locations)

**Pattern 5a: Multi-Source Credential Loading**
```python
# config/credential_manager.py (Session 115 notes)
# Falls back: User-specific → Shared → Env vars → Hardcoded
# Operator doesn't know which source provided credentials
```

**Impact:** CRITICAL in production - Can't diagnose credential mismatches without logging source

---

## VIOLATIONS BY SEVERITY & IMPACT

| Severity | Category | Count | Examples |
|----------|----------|-------|----------|
| **CRITICAL** | Signal count defaults (0 instead of raise) | 6 | signals.py:437-442 |
| **CRITICAL** | Credential fallback chains | 5+ | credential_manager.py |
| **HIGH** | Fallback chains on financial data | 15 files | fetchers_portfolio.py, data_layer |
| **HIGH** | Implicit None on API responses | 50+ files | signals.py avg_score, signal_date |
| **HIGH** | Exception swallowing | 250+ files | loaders/*, lambda/api |
| **MEDIUM** | Dict default fallbacks | 10+ files | data_freshness={}, is_stale=False |
| **MEDIUM** | Derived metric .get() | 20+ files | daily_return, max_dd, etc |

---

## VIOLATIONS STILL TO FIX

### Immediate (Hook-blocking)
- [ ] signals.py:437-442 - Redundant `.get(..., 0) or 0` pattern (6 lines)
- [ ] fetchers_portfolio.py:91 - Fallback chain `port.get("snapshot_date") or port.get("last_run")`
- [ ] fetchers_portfolio.py:98-99 - Silent dict/bool defaults

### High Priority (Data Integrity)
- [ ] fetchers_portfolio.py:104 - Multi-level data_age fallback
- [ ] signals.py:443-444 - Implicit None on avg_score, signal_date
- [ ] ALL loaders with exception swallowing patterns
- [ ] credential_manager.py - Multi-source fallback chains with no explicit source logging

### Medium Priority (Robustness)
- [ ] All `.get()` with None implicit returns (50+ files)
- [ ] Validation functions returning bool (should raise)
- [ ] Exception handlers in dashboard fetchers

---

## FIX STRATEGY

### Phase 1: Critical Signals Handler (signals.py)
**Fix:** Replace redundant `.get(..., 0) or 0` with explicit validation:
```python
# BEFORE
total = int(result_dict.get("total", 0) or 0)

# AFTER
if "total" not in result_dict or result_dict["total"] is None:
    raise ValueError(f"Signal query result missing 'total' field")
total = int(result_dict["total"])
```

### Phase 2: Portfolio Fetcher Fallback Chains
**Fix:** Make all fallbacks explicit with markers:
```python
# BEFORE
snapshot_date = port.get("snapshot_date") or port.get("last_run")

# AFTER
snapshot_date = port.get("snapshot_date")
if not snapshot_date:
    # Try fallback and log explicitly
    snapshot_date = port.get("last_run")
    if not snapshot_date:
        raise ValueError("Portfolio missing both snapshot_date and last_run fields")
```

### Phase 3: Silent Dict Defaults (Cascade to Optional Fields)
```python
# BEFORE
data_freshness = port.get("data_freshness", {})  # Silent empty dict
is_stale_from_api = data_freshness.get("is_stale", False)  # Silent False

# AFTER
data_freshness = port.get("data_freshness")  # None if missing
if data_freshness is None:
    logger.warning("Portal missing data_freshness field; cannot validate freshness")
    is_stale_from_api = None  # Explicit marker
else:
    is_stale_from_api = data_freshness.get("is_stale")
```

### Phase 4: Implicit None Returns (Add Explicit Markers)
```python
# For optional fields that legitimately can be None:
# BEFORE
avg_score = result_dict.get("avg_score")  # Implicit None

# AFTER - Make it explicit in response:
avg_score = result_dict.get("avg_score")  # Documented as "None if not computed"
# OR if missing is an error:
if "avg_score" not in result_dict:
    raise ValueError("avg_score missing from signal result")
```

---

## Files to Fix (Prioritized)

### Tier 1: Critical (Must fix before merge)
1. `lambda/api/routes/algo_handlers/signals.py` - Lines 437-444 (6 violations)
2. `dashboard/fetchers_portfolio.py` - Lines 91, 98-99, 104 (3 violations)
3. `lambda/api/routes/algo_handlers/monitoring.py` - Lines 104-109 (multiple .get() without markers)

### Tier 2: High Priority (This week)
1. `dashboard/fetchers_config.py` - Fallback patterns
2. `dashboard/local_api_server.py` - Fallback patterns
3. `lambda/api/routes/algo_handlers/metrics.py` - Fallback patterns
4. All loaders with exception swallowing

### Tier 3: Medium Priority (Next sprint)
1. `config/credential_validator.py`
2. `utils/ops/orchestrator_query.py`
3. Dashboard fetchers with .get() and implicit None
4. Validation functions returning bool

---

## Prevention: Updated Governance

**Rule:** In a finance app, ALL data access must be one of:
1. ✅ Explicit key check: `if "key" in dict: value = dict["key"]; else: raise ValueError(...)`
2. ✅ Explicit marker: `{"data_unavailable": True, "reason": "..."}`
3. ✅ Try/except with re-raise: `except Exception as e: logger.error(...); raise`
4. ❌ BANNED: `.get()` with defaults on critical data
5. ❌ BANNED: `except: return []` or `except: return None`
6. ❌ BANNED: `value or fallback` on financial data
7. ❌ BANNED: Validation functions returning bool (must raise or return marker)

---

**Next Step:** Systematically fix Tier 1, verify pre-commit hook passes, then continue to Tier 2.
