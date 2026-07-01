# Lint Coverage Policy

**Goal:** Catch real errors while minimizing false positives. Enforce discipline on what can be ignored.

---

## Core Principle

**NEVER suppress critical errors with blanket patterns.** Ignores must be:
1. **Specific:** Named file, not wildcard pattern
2. **Justified:** Inline comment explaining why
3. **Auditable:** Running `grep -r "# noqa\|# type: ignore\|# pylint:"` shows all suppressed errors
4. **Minimal:** Only the specific error code, not the whole file

---

## Type Safety (Critical: Prevents Runtime Type Errors)

**Two-layer approach catches type errors:**

### Layer 1: mypy (Static Type Checking)
- **Config:** `strict = true` (enforced in pyproject.toml)
  - Requires type annotations on all functions
  - Catches missing types, incorrect assignments, untyped calls
  - `ignore_missing_imports = true` (pragmatic for untyped deps)
- **What it catches:** Missing types, incorrect type usage, None errors
- **When to ignore:** NEVER — all mypy errors block commits. No exceptions.

### Layer 2: Pylint + Data Validation (Runtime Type Safety)
- **Pylint rules enabled (pre-commit):**
  - `comparison-with-callable` — Catches `dict >= int`, `list == str`, etc.
  - `unsupported-binary-operation` — Catches `dict + int`, invalid operations
- **Data validation pattern (always use):**
  ```python
  # ❌ Unsafe — mypy passes but fails at runtime
  if data.get("price") >= 0:  # price could be dict

  # ✅ Safe — Pylint catches, runtime safe
  price = safe_float(data.get("price"))  # Returns float | None
  if price is not None and price >= 0:  # Type-safe now
  ```
- **Helpers:** `safe_float()`, `safe_int()`, `safe_get_field()`, `safe_extract()`
- **No exceptions:** Cannot disable `comparison-with-callable` or `unsupported-binary-operation` (pre-commit hook blocks it)

---

## Enforcement (Non-Negotiable)

### Pre-Commit Checks (Automated & Blocking)
```bash
mypy dashboard/ --show-error-codes        # Type checking (strict mode)
pylint dashboard/ --disable=all --enable=comparison-with-callable,unsupported-binary-operation
ruff check dashboard/                     # Code style
```

### Audit (Weekly)
**Run before Friday to catch drift:**
```bash
# Check for attempts to disable critical pylint rules (pre-commit blocks these)
grep -rn "# pylint: disable=comparison-with-callable\|# pylint: disable=unsupported-binary-operation" --include="*.py"

# Check for mypy type ignores (document if found, don't suppress wholesale)
grep -rn "# type: ignore" --include="*.py" | wc -l

# Verify strict mode still enabled in pyproject.toml
grep "strict = true" pyproject.toml
```

**If critical rules are disabled:** Pre-commit hook blocks the commit. PR rejected.

---

## Cannot Be Bypassed (Pre-Commit Protected)

These rules are **blocked by automated pre-commit hook** — cannot be disabled even with `# pylint:` comments:

1. Pylint `comparison-with-callable` — Catches dict >= int
2. Pylint `unsupported-binary-operation` — Catches dict + int
3. mypy `strict = true` — Blocks all type errors

**Rationale:** Past production incidents from bypassing these checks. Team grows, people push boundaries, safety checks drift. These are load-bearing rules.

### What These Catch Together

| Error | Tool | Example | Fix |
|-------|------|---------|-----|
| dict >= int | mypy + pylint | `if data.get("price") >= 0` | Use `safe_float()` |
| Missing type | mypy | `def func(x):` | Add annotation: `x: int` |
| Unsafe Any | mypy | `value: Any` in comparison | Use `cast()` or `safe_*()` helpers |
| Dead code | ruff | `unused_var = 5` | Remove or use `_unused` |

---

## What CANNOT Be Ignored (Even with Justification)

These errors indicate real bugs or dangerous code:
- **F401** (unused imports) — Dead code is debt. Use explicit `from typing import TYPE_CHECKING` blocks if needed
- **F405** (undefined name) — Name was never bound; indicates import/typo error
- **F841** (unused variables) — Same as unused imports; indicates dead code
- **E999** (syntax error) — Broken code

---

## Strict Validation Testing (Prevents Runtime Validation Errors)

**Goal:** Catch `StrictValidationError` during pre-commit and CI/CD testing, BEFORE production.

### The Problem
Validation errors occur when parsers return `None`, which is then passed to strict converters (`safe_float(..., strict=True)`). Without testing, these slip into production.

### Testing Layers

**Layer 1: Unit Tests**
- File: `tests/test_strict_validation_error_detection.py`
- Tests `safe_float()`, `safe_int()` with strict mode
- 30+ test cases covering None detection, invalid data, passthrough

**Layer 2: Integration Tests**
- File: `tests/test_dashboard_panel_strict_validation.py`
- Validates data flows through pipeline (fetchers → panels)
- Common patterns: dict.get, list indexing, attribute access

**Layer 3: Pre-Commit Validation**
- File: `.pre-commit-scripts/check-strict-validation-tests.py`
- Ensures test files exist and contain required patterns
- Blocks commits if validation tests missing

### Developer Patterns

**✅ DO: Use strict mode in finance paths**
```python
from utils.safe_data_conversion import safe_float
vix = safe_float(market_data.get("vix"), strict=True, field_name="vix")
```

**✅ DO: Validate at data source**
```python
def fetch_market_data():
    data = fetch_from_api()
    if data.get("vix") is None:
        logger.error("VIX data missing from API response")
        return None  # Explicit, not silent
    return data
```

**✅ DO: Handle None explicitly in panels**
```python
vix_raw = market_data.get("vix")
if vix_raw is None:
    vix = None  # or "N/A" for display
else:
    vix = safe_float(vix_raw, strict=True, field_name="vix")
```

**❌ DON'T: Pass dict.get() directly to strict converter**
```python
# WRONG: dict.get() can return None, strict converter will raise
vix = safe_float(data.get("vix"), strict=True)  # Raises if vix is missing!
```

**❌ DON'T: Use strict mode with fallback defaults**
```python
# WRONG: defeats the purpose
price = safe_float(data.get("price"), default=0.0, strict=True)  # Inconsistent!
```

### Running Tests
```bash
# All strict validation tests
pytest tests/test_strict_validation_error_detection.py -v
pytest tests/test_dashboard_panel_strict_validation.py -v

# Pre-commit check
python .pre-commit-scripts/check-strict-validation-tests.py

# Full CI simulation
make ci-local
```

### Checklist Before Committing Strict Validation Code

- [ ] Tests exist for the strict conversion
- [ ] Tests cover None case
- [ ] Tests cover invalid type/string case  
- [ ] Tests cover valid data passthrough
- [ ] Error messages include `field_name`
- [ ] Data source validates BEFORE strict conversion (no silent None)
- [ ] Pre-commit hooks pass
- [ ] `make test` passes locally

---

## What CAN Be Ignored (With Inline Justification)

These are legitimate cases for specific file ignores:

### Per-File Ignores (Still Specific!)
- **E402** (module-level import not at top) — Only in `scripts/`, `loaders/`, `tools/` where setup code runs before imports
- **C901** (function too complex) — Per-function inline ignore only, not file-wide
- **N812** (lowercase import alias) — Third-party library import (`from psycopg2.extensions import cursor as PsycopgCursor`)

### Inline Ignores (Per-Line)
- **type: ignore** with error code — Only for libraries with incomplete stubs (e.g., `termios`, `signal`)
- **noqa** with error code — Only for third-party naming issues outside our control

---

## Audit & Enforcement

### Weekly Audit
Run and review:
```bash
grep -rn "# noqa\|# type: ignore" --include="*.py" | grep -v "test_" | grep -v ".pytest"
```

Count by file:
```bash
grep -r "# noqa\|# type: ignore" --include="*.py" | wc -l
```

Goal: Keep under 100 total; every entry must have a comment.

### Pre-Commit Enforcement
- MyPy `warn_unused_ignores = true` catches `# type: ignore` that aren't needed
- Ruff must run `--show-error-codes` to show what's being suppressed
- No new per-file-ignore patterns allowed (only explicit file lists)

---

## Configuration Structure

Use specific file paths only (not wildcards like `load*.py`). Keep all ignores per-file or inline:

```toml
[tool.ruff.lint.per-file-ignores]
"scripts/setup.py" = ["E402"]
"loaders/load_prices.py" = ["E402"]
```

```python
def complex_function():  # pylint: disable=too-many-arguments
    ...
```

---

## Related Rules
- See `GOVERNANCE.md` for type-safety requirements
- See `OPERATIONS.md` for CI enforcement
