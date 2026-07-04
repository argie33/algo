# Fallback Violations — Remediation Plan

**Date**: 2026-07-04  
**Violations Found**: 15  
**Status**: READY FOR IMPLEMENTATION  
**Total Effort**: 5-8 hours  

---

## CRITICAL VIOLATIONS (Trading-Blocking) 🔴

Must fix before next trading session.

### VIOLATION 1: Data Completeness Threshold Too Low
- **File**: `algo/orchestrator/phase7_signal_generation.py`
- **Line**: 332
- **Current Code**: 
  ```sql
  WHERE ... AND ss.data_completeness >= 50 ...
  ```
- **Fix Code**:
  ```sql
  WHERE ... AND ss.data_completeness >= 70 ...
  ```
- **Why**: GOVERNANCE.md Rule: "Entry quality: ... completeness ≥70%"
- **Risk Without Fix**: Enters positions with only HALF required factors
- **Effort**: 1 minute

---

### VIOLATION 2: Missing Data_Unavailable Check in Signal Consumption
- **File**: `algo/signals/advanced_filters.py`
- **Lines**: 573-574
- **Current Code**:
  ```python
  cur.execute(
      "SELECT composite_score FROM stock_scores WHERE symbol = %s"
  )
  ```
- **Fix Code**:
  ```python
  cur.execute(
      "SELECT composite_score FROM stock_scores "
      "WHERE symbol = %s "
      "  AND (data_unavailable = FALSE OR data_unavailable IS NULL)"
  )
  ```
- **Why**: Must validate data quality before using in trading logic
- **Risk Without Fix**: Signals use invalid/incomplete metrics
- **Effort**: 3 minutes

---

### VIOLATION 3: Insufficient Metric Threshold in Dashboard
- **File**: `dashboard/panels/health.py`
- **Lines**: 1374, 2502
- **Current Code**:
  ```python
  if len(valid_metrics) >= 2:
  ```
- **Fix Code**:
  ```python
  if len(valid_metrics) >= 3:
  ```
- **Why**: Min 50% completeness (3/6 metrics) required
- **Risk Without Fix**: Dashboard shows incomplete data summaries
- **Effort**: 1 minute

---

### VIOLATION 4: Design Flaw — Single-Metric Scoring Allowed
- **File**: `algo/orchestrator/phase1_failsafe_retry.py`
- **Line**: 61
- **Current Code**:
  ```python
  # stock_scores is designed to work with partial metrics (min_required_metrics=1)
  ```
- **Fix Code**:
  ```python
  # stock_scores enforces min_required_metrics=3 (per GOVERNANCE.md)
  # Min 50% completeness prevents 100% single-factor bias
  ```
- **Why**: Single metric = 100% bias, violates GOVERNANCE Rule 4
- **Risk Without Fix**: Extreme bias in position sizing
- **Effort**: Code review + architecture validation (1-2 hours)

---

## HIGH-SEVERITY VIOLATIONS (Data Quality) 🟠

### VIOLATIONS 5-7: Silent None Returns (3 Files)

#### 5A. `utils/data/source_router.py:223`
- **Current**: `return None`
- **Fix**:
  ```python
  logger.warning(f"[SOURCE_ROUTER] {reason} — marking unavailable")
  return {"data_unavailable": True, "reason": "source_routing_failed"}
  ```
- **Effort**: 2 minutes

#### 5B. `utils/loaders/helpers.py:79`
- **Current**: `return None`
- **Fix**:
  ```python
  logger.warning(f"[HELPERS] Active symbols list missing")
  return {"data_unavailable": True, "reason": "active_symbols_unavailable"}
  ```
- **Effort**: 2 minutes

#### 5C. `loaders/market_health_fetchers.py:222, 244`
- **Current**: `return None` (2 locations)
- **Fix**:
  ```python
  logger.warning(f"[MARKET_HEALTH] Fetch failed for {field}")
  return {"data_unavailable": True, "reason": f"fetch_failed_{field}"}
  ```
- **Effort**: 3 minutes

---

### VIOLATION 8: Inconsistent data_unavailable NULL Handling
- **File**: `loaders/load_stock_scores.py`
- **Lines**: 97-100, 150, 157
- **Current**: Mix of `FALSE OR NULL`, just `FALSE`, just `FALSE`
- **Fix**: Standardize ALL to:
  ```python
  WHERE data_unavailable = FALSE OR data_unavailable IS NULL
  ```
- **Why**: Some loaders don't set the flag (NULL), some do (FALSE)
- **Effort**: 5 minutes (3 locations)

---

### VIOLATIONS 9-10: Wrong Logging Levels
- **File**: `loaders/load_stock_scores.py`
- **Lines**: 104, 153
- **Current**: `logger.warning()`
- **Fix**: `logger.critical()`
- **Why**: Schema mismatches are BLOCKING errors, not warnings
- **Effort**: 1 minute

---

## MEDIUM-SEVERITY VIOLATIONS (Observability) 🟡

### VIOLATION 11: Improper Logging in Data Quality Paths
- **File**: `dashboard/error_boundary.py`
- **Issue**: Multiple `logger.debug()` for data_unavailable conditions
- **Fix**: Change to `logger.warning()` (per GOVERNANCE Rule 5)
- **Effort**: 5-10 minutes

---

### VIOLATIONS 12-13: Silent Exception Swallowing

#### 12. `utils/db/connection.py:202`
- **Current**: `except Exception: pass`
- **Fix**:
  ```python
  except Exception as e:
      logger.error(f"[DB_CONNECTION] Connection failed: {e}")
      raise RuntimeError(f"Database connection critical failure: {e}") from e
  ```
- **Effort**: 3 minutes

#### 13. `utils/db/structured_logging.py:42`
- **Current**: `except Exception: return fallback`
- **Fix**:
  ```python
  except Exception as e:
      logger.error(f"[STRUCTURED_LOGGING] Logging failed: {e}")
      return {"error": str(e), "logged_successfully": False}
  ```
- **Effort**: 3 minutes

---

## REMEDIATION SCHEDULE

### PHASE 1 (Immediate - 30 minutes)
Priority: CRITICAL trading-blocking issues
1. ✏️ phase7_signal_generation.py:332 — change >= 50 to >= 70 (1 min)
2. ✏️ advanced_filters.py:573-574 — add data_unavailable check (3 min)
3. ✏️ health.py:1374, 2502 — change >= 2 to >= 3 (1 min)
4. 🏗️ phase1_failsafe_retry.py — review/fix min_required_metrics design (1-2 hours)

### PHASE 2 (High Priority - 15 minutes)
Data quality violations
5. ✏️ source_router.py:223 — return marker (2 min)
6. ✏️ helpers.py:79 — return marker (2 min)
7. ✏️ market_health_fetchers.py:222, 244 — return markers (3 min)
8. ✏️ load_stock_scores.py — standardize NULL checks (5 min)
9. ✏️ load_stock_scores.py:104, 153 — fix logging (1 min)

### PHASE 3 (Medium Priority - 15 minutes)
Observability improvements
10. ✏️ error_boundary.py — upgrade logging (5-10 min)
11. ✏️ connection.py:202 — add error context (3 min)
12. ✏️ structured_logging.py:42 — return error marker (3 min)

---

## VERIFICATION CHECKLIST

After fixes, verify:
- [ ] Phase 1 fixes deployed and trading with >= 70% completeness data
- [ ] All advanced_filters queries include data_unavailable check
- [ ] All metrics gates require >= 3 factors minimum
- [ ] No silent None returns without explicit markers
- [ ] All logging uses WARNING for data quality issues
- [ ] Pre-commit hook passes (check-silent-fallbacks.py)
- [ ] Tests pass (57 CI tests should pass)
- [ ] Manual test: swing trader scoring computes (if fixed)

---

## Expected Impact After Fixes

✅ **Trading System**:
- All position sizing uses >= 70% complete data
- All metrics require >= 3 factors (prevents 100% single-factor bias)
- No degraded/incomplete datasets silently accepted

✅ **Data Quality**:
- All missing data marked explicitly with reasons
- Inconsistent NULL handling standardized
- No silent error swallowing

✅ **Observability**:
- Operators see all data quality issues (WARNING level)
- Error paths include full context
- Dashboard accuracy verified for trading decisions

---

**Ready to implement** — all 15 violations mapped with specific code fixes.
