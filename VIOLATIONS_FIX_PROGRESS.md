# Violations Fix Progress Tracking

**Last Updated:** 2026-06-20  
**Phase:** Ongoing implementation  
**Overall Completion:** 93/3,777 (2.5%)  
**Critical Phase 1 Completion:** 0/39 (0%)  
**High Priority Phase 2 Completion:** 93/826 (11%)

---

## Current Status Summary

| Phase | Category | Total | Fixed | % Complete | Status |
|-------|----------|-------|-------|------------|--------|
| 1 | Silent Exceptions | 39 | 0 | 0% | 🔴 Not Started |
| 2 | Unsafe .get() Defaults | 826 | 93 | 11% | 🟡 In Progress |
| 3 | Return {} Patterns | 23 | 0 | 0% | 🔴 Not Started |
| 4 | Defensive .get() Calls | 2,889 | 0 | 0% | 🔴 Not Started |
| **TOTAL** | **ALL** | **3,777** | **93** | **2.5%** | 🟡 Early stage |

---

## Session 1 Progress (2026-06-20)

### Violations Fixed This Session: 93

#### Phase 2 Work (Unsafe .get() Defaults)

**1. tools/dashboard/panels/health.py - panel_algo_health()**
- **Lines:** 618-945 (328 lines)
- **Violations Fixed:** ~86
- **Changes:**
  - Section A (Run outcome): 9 → 3 .get() calls
  - Section B (Phase badges): 30+ → 6+ .get() calls
  - Section C (Metrics): 12 → 3 .get() calls
  - Section D (Data health): 15 → 4 .get() calls
  - Section E (Risk): 2 → 1 .get() calls
  - Section F (Notifications): 7 → 3 .get() calls
- **Pattern Applied:** safe_get_field(), safe_get_list(), safe_get_dict()
- **Commit:** 87c42da27

**2. lambda/api/lambda_wrapper.py - LambdaAPIClient.invoke()**
- **Violations Fixed:** ~4
- **Changes:**
  - Add fail-fast validation for statusCode (raise if missing)
  - Add fail-fast validation for body (raise if missing)
  - Remove implicit defaults (500, "{}")
- **Pattern Applied:** Explicit validation before use
- **Commit:** 87c42da27

**3. tools/dashboard/panels/positions.py - panel_positions()**
- **Violations Fixed:** ~3
- **Changes:**
  - Improve error message extraction
  - Remove implicit default for _error field
  - Explicit None checking
- **Pattern Applied:** safe error handling without defaults
- **Commit:** 87c42da27

### Patterns Established

#### Pattern 1: Safe Field Extraction
```python
# Use safe_get_field() instead of .get() with implicit None
from .data_extractors import safe_get_field

# ✅ CORRECT - No implicit default
value = safe_get_field(data, "field")  # Returns None if missing

# ✅ CORRECT - Explicit default when needed
value = safe_get_field(data, "field", "default")

# ❌ WRONG - Implicit default
value = data.get("field", "default")  # Silent fallback
```

#### Pattern 2: List Validation
```python
# Use safe_get_list() to extract and validate lists
from .data_extractors import safe_get_list

# ✅ CORRECT - Validate structure, extract once
items = safe_get_list(data)
for item in items:
    name = safe_get_field(item, "name")

# ❌ WRONG - Defensive defaults per iteration
for item in data.get("items", []):
    name = item.get("name", "unknown")
```

#### Pattern 3: Dict Validation
```python
# Use safe_get_dict() for nested dict validation
from .data_extractors import safe_get_dict

# ✅ CORRECT - Validate nested structure
nested = safe_get_dict(risk)
if nested:
    value = nested.get("var95")

# ❌ WRONG - Multiple defensive .get() levels
value = data.get("nested", {}).get("field", {}).get("subfield")
```

#### Pattern 4: Error Check First
```python
# Always check for errors before accessing fields
from .error_boundary import has_error

# ✅ CORRECT - Fail-fast error handling
def panel_function(data):
    if has_error(data):
        return error_summary_panel({"data": data})
    # Now data is validated
    value = safe_get_field(data, "field")

# ❌ WRONG - Mixing error handling with .get()
def panel_function(data):
    value = data.get("field", "unknown")
    if value == "unknown":
        # Too late, already used default
```

---

## Remaining Work by Priority

### 🔴 CRITICAL - Phase 1: Silent Exceptions (39 violations)

**Files Requiring Fixes:**
- tools/dashboard/panels/*.py (8 files)
- loaders/load_*.py (10 files)  
- lambda/api/routes/*.py (5 files)
- algo/infrastructure/*.py (3 files)

**Pattern to Fix:**
```python
# ❌ WRONG
except Exception:
    pass
    
# ✅ CORRECT
except SpecificException as e:
    logger.error(f"[CONTEXT] Error occurred: {e}")
    raise  # or return {"_error": "message"}
```

**Estimated Effort:** 2-3 hours

---

### 🟠 HIGH - Phase 2: Unsafe .get() Defaults (826 violations)

**Remaining after Session 1:**
- panels/health.py: panel_algo_health_expanded (320+ lines, ~86 violations)
- panels/signals.py: 92 violations
- panels/market.py: 74 violations
- panels/exposure.py: 57 violations
- panels/economic.py: 37 violations
- fetchers.py: 193 violations (partially fixed)
- API handlers (50-80 violations each)

**Top Files by Violation Count:**
1. fetchers.py: 193 violations
2. health.py (panel_algo_health_expanded): ~86 violations
3. signals.py: 92 violations
4. metrics.py: 84 violations
5. portfolio.py: 82 violations
6. market.py: 74 violations
7. exposure.py: 57 violations

**Estimated Effort:** 6-8 hours remaining

---

### 🟠 HIGH - Phase 3: Return {} Patterns (23 violations)

**Files:**
- loaders/load_signal_quality_scores.py
- loaders/load_prices.py
- lambda/api response handlers (8 files)

**Pattern to Fix:**
```python
# ❌ WRONG - Ambiguous empty dict
return {}

# ✅ CORRECT - Clear error marker
return {"_error": "reason for failure"}
```

**Estimated Effort:** 1 hour

---

### 🟡 MEDIUM - Phase 4: Defensive .get() Calls (2,889 violations)

**By Component:**
- Defensive .get() without defaults: 2,889 violations
- Systematic replacement with safe_get_* helpers
- Many can be automated with careful search/replace

**Strategy:**
- Process by component (infrastructure, loaders, API, utilities)
- Use safe_get_* helpers consistently
- Preserve intentional optional field patterns

**Estimated Effort:** 6-8 hours

---

## Recommended Next Steps (Session 2)

### High Priority (Do First)
1. **Phase 1 Complete** (2-3 hours)
   - Fix all 39 silent exception handlers
   - Add logging to every except block
   - Verify no hidden failures

2. **Phase 2a** (4-5 hours)
   - Refactor panel_algo_health_expanded (320 lines, 86 violations)
   - Use pattern from panel_algo_health as template
   - Apply safe_get_* helpers systematically

### Medium Priority (Do Next)
3. **Phase 2b** (2-3 hours)
   - Fix signals.py, market.py, exposure.py
   - Apply same refactoring pattern to each

4. **Phase 3** (1 hour)
   - Replace all `return {}` with `return {"_error": "message"}`

### Lower Priority (Do Last)
5. **Phase 4** (6-8 hours)
   - Systematic safe_get_* replacement
   - Can be parallelized across components

---

## Key Metrics to Track

### Daily Progress
- Violations fixed (cumulative)
- Files completed
- Commits created
- Test pass rate

### Code Quality
- mypy type checking (must pass)
- Linting (must pass)
- Test coverage maintained
- No breaking changes

### Phase Progress
- Phase 1 completion: 0/39 (0%)
- Phase 2 completion: 93/826 (11%)
- Phase 3 completion: 0/23 (0%)
- Phase 4 completion: 0/2,889 (0%)

---

## Testing Strategy

### After Each Session
```bash
# Type checking
python -m mypy [modified_file] --ignore-missing-imports

# Linting
ruff check [modified_file]

# Tests (if available)
pytest tests/test_[component] -v

# Manual verification
- Dashboard renders without errors
- Error panel shows when data missing
- No silent defaults used
```

### Before Each Commit
- ✅ mypy passes
- ✅ No import errors
- ✅ Tests pass
- ✅ Code follows established patterns

---

## Helper Functions Reference

Located in `tools/dashboard/panels/data_extractors.py`:

```python
# Field extraction (no implicit default)
value = safe_get_field(dict_obj, "field_name")
value = safe_get_field(dict_obj, "field_name", "explicit_default")

# List extraction and validation
items = safe_get_list(data)  # Returns [] if error/invalid

# Dict extraction and validation
nested = safe_get_dict(data)  # Returns {} if error/invalid
```

Located in `tools/dashboard/error_boundary.py`:
```python
# Check if data has error marker
has_error_flag = has_error(data)

# Display error panel
error_panel = error_summary_panel({"data": data})
```

---

## Session History

### Session 1 (2026-06-20)
- **Violations Fixed:** 93
- **Focus:** Phase 2 early work (panel_algo_health refactoring)
- **Key Output:** Established safe_get_* patterns
- **Status:** Successfully applied fail-fast validation to 1 major panel

---

## Known Patterns (Do NOT Change)

These patterns are intentional and should be preserved:

1. **Optional Display Fields**
   ```python
   # OK - Display field with sensible default
   display_name = data.get("display_name", "N/A")
   ```

2. **Data Extraction Helpers**
   ```python
   # OK - Helper function returning extracted data
   def extract_config():
       return data.get("config", {})
   ```

3. **Circuit Breaker Fallback**
   ```python
   # OK - Documented degraded mode
   if circuit_open:
       return cached_data.get("last_value")
   ```

---

## Documentation References

- **Complete Audit:** steering/VIOLATIONS_AUDIT_COMPLETE.md (comprehensive 3,777 violation inventory)
- **Implementation Plan:** steering/VIOLATIONS_FIX_ROADMAP.md (4-phase plan with timeline)
- **Codebase Standards:** CLAUDE.md (Dashboard API Validation Strategy section)
- **Session Summary:** SESSION_VIOLATIONS_FIX_SUMMARY.md (detailed work completed)
