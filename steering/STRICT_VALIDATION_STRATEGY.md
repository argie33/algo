# Strict Validation Error Detection Strategy

## Goal
Catch `StrictValidationError: Cannot convert None to float` (and similar validation errors) during pre-commit and CI/CD testing, BEFORE they reach production.

## Problem Statement
Validation errors occur when data parsers or fetchers return `None` values, which are then passed to strict converters (`safe_float(..., strict=True)`) that raise `StrictValidationError`. These errors were not being caught in testing, allowing them to slip into production.

## Solution: Multi-Layer Testing Strategy

### Layer 1: Unit Tests for Strict Converters
**File:** `tests/test_strict_validation_error_detection.py`

Tests that verify `StrictValidationError` is raised correctly:
- When `None` is passed to `safe_float(..., strict=True)`
- When `None` is passed to `safe_int(..., strict=True)`
- When invalid data is passed with strict mode enabled
- When valid data passes through strict mode

**Coverage:** 30 test cases covering:
- Basic None detection
- Invalid string/bool handling
- Valid data passthrough
- Dashboard panel scenarios
- Fetcher data validation patterns
- Error message clarity

### Layer 2: Integration Tests for Data Flows
**File:** `tests/test_dashboard_panel_strict_validation.py`

Tests that verify strict validation works across the data pipeline:
- Dashboard panels handle missing data gracefully
- Fetchers validate data before strict conversion
- Data validation chain from source to display
- Common data access patterns (dict.get, list indexing, attribute access)

**Coverage:** Validation pattern documentation and best practices:
- ✅ Good: Validate at data source, handle None explicitly
- ❌ Bad: Pass None directly to strict converters

### Layer 3: Pre-Commit Checks
**File:** `.pre-commit-scripts/check-strict-validation-tests.py`

Ensures test files exist and contain required validation patterns:
- Verifies `test_strict_validation_error_detection.py` exists
- Verifies `test_dashboard_panel_strict_validation.py` exists
- Checks for required test patterns (StrictValidationError, strict=True, pytest.raises)

**When it runs:** On every commit (`stages: [commit]`)

### Layer 4: Existing Pre-Commit Checks
Complements new tests:
- `.pre-commit-scripts/check-strict-safe-conversion.py` — Ensures `strict=True` is used in finance paths
- MyPy with strict mode — Catches type errors that could lead to None values
- Pylint rules — Catches unsafe type comparisons

## CI/CD Integration

### Pre-Commit Hooks
```yaml
- id: check-strict-validation-tests
  name: Ensure StrictValidationError tests exist (CI/CD detection)
  entry: python .pre-commit-scripts/check-strict-validation-tests.py
  language: system
  pass_filenames: false
  types: [python]
  stages: [commit]
```

### Test Execution in CI
Tests are run as part of the standard CI pipeline:
```bash
make test  # Runs pytest on all tests including strict validation tests
```

## Best Practices for Developers

### When using safe_float/safe_int:

#### ✅ DO: Use strict mode in finance paths
```python
# Dashboard panel receiving data from fetcher
from utils.safe_data_conversion import safe_float

vix = safe_float(market_data.get("vix"), strict=True, field_name="vix")
```

#### ✅ DO: Validate at data source (fetchers)
```python
def fetch_market_data():
    data = fetch_from_api()
    if data.get("vix") is None:
        logger.error("VIX data missing from API response")
        # Handle gracefully: return None marker, raise error, or use fallback
        return None
    return data
```

#### ✅ DO: Handle None explicitly in panels
```python
def format_market_data(market_data):
    vix_raw = market_data.get("vix")
    
    if vix_raw is None:
        vix = None  # or "N/A" for display
    else:
        vix = safe_float(vix_raw, strict=True, field_name="vix")
    
    return {"vix": vix}
```

#### ❌ DON'T: Pass dict.get() directly to strict converter
```python
# WRONG: dict.get() can return None, strict converter will raise
vix = safe_float(data.get("vix"), strict=True)  # Raises if vix is missing!
```

#### ❌ DON'T: Use strict mode with fallback defaults
```python
# WRONG: strict mode + default defeats the purpose
price = safe_float(data.get("price"), default=0.0, strict=True)  # Inconsistent!
```

## Error Messages

When `StrictValidationError` is raised, it includes:
- The field name (from `field_name` parameter)
- The problematic value
- The context (from `context` parameter if provided)

Example:
```
StrictValidationError: Cannot convert None to float for spy_close
StrictValidationError: Cannot convert "not_a_number" to float for portfolio_value
```

## Testing Checklist

Before committing code that uses `safe_float(..., strict=True)`:

- [ ] Data validation tests exist (or updated)
- [ ] Tests cover None case
- [ ] Tests cover invalid string/type case
- [ ] Tests cover valid data passthrough
- [ ] Error messages are clear (include field_name)
- [ ] Data source validates before strict conversion
- [ ] Pre-commit hooks pass (including check-strict-validation-tests.py)
- [ ] All tests pass locally: `make test`

## Running the Tests

### All strict validation tests:
```bash
pytest tests/test_strict_validation_error_detection.py -v
pytest tests/test_dashboard_panel_strict_validation.py -v
```

### Specific test class:
```bash
pytest tests/test_strict_validation_error_detection.py::TestStrictFloatNoneDetection -v
```

### Pre-commit check:
```bash
python .pre-commit-scripts/check-strict-validation-tests.py
```

### Full CI simulation:
```bash
make ci-local  # Runs all checks including tests
```

## Governance Rules (From CLAUDE.md & LINT_POLICY.md)

1. **Finance paths MUST use strict=True** — Prevents silent data loss
2. **Type safety is critical** — MyPy strict mode enforces type correctness
3. **Fail-fast design** — Errors surface immediately, no silent defaults
4. **No .get() with empty defaults** — Would mask missing credentials/data
5. **All errors must be loggable** — Missing data returns None or raises (never silent)

## Related Files

- `utils/safe_data_conversion.py` — Safe conversion functions with strict mode
- `steering/GOVERNANCE.md` — Overall fail-fast architecture
- `steering/LINT_POLICY.md` — Type safety enforcement
- `.pre-commit-scripts/check-strict-safe-conversion.py` — Enforce strict=True usage
- `pyproject.toml` — MyPy strict mode config

## Future Enhancements

1. **Enhanced diagnostics** — Collect and report all validation errors at once (not just first failure)
2. **Performance testing** — Ensure strict validation has minimal performance impact
3. **Fetcher-level validation** — Ensure all data sources validate output before returning
4. **Dashboard-wide audit** — Verify all strict calls have meaningful field names

---

**Last Updated:** 2026-06-30  
**Status:** Active (all tests passing, pre-commit hook enabled)
