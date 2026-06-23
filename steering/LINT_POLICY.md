# Lint Coverage Policy

**Goal:** Catch real errors while minimizing false positives. Enforce discipline on what can be ignored.

---

## Core Principle

**NEVER suppress critical errors with blanket patterns.** Ignores must be:
1. **Specific:** Named file, not wildcard pattern
2. **Justified:** Inline comment explaining why
3. **Auditable:** Running `grep -r "# noqa\|# type: ignore"` shows all suppressed errors
4. **Minimal:** Only the specific error code, not the whole file

---

## What CANNOT Be Ignored (Even with Justification)

These errors indicate real bugs or dangerous code:
- **F401** (unused imports) — Dead code is debt. Use explicit `from typing import TYPE_CHECKING` blocks if needed
- **F405** (undefined name) — Name was never bound; indicates import/typo error
- **F841** (unused variables) — Same as unused imports; indicates dead code
- **E999** (syntax error) — Broken code
- **E302/E303** (blank lines) — Formatting, not a real error but enforce consistency
- **Type errors** (mypy strict mode) — We run mypy strict; all types must be sound

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

### Ruff: Specific Files Only
✅ **GOOD:**
```toml
[tool.ruff.lint.per-file-ignores]
"scripts/setup.py" = ["E402"]
"loaders/load_prices.py" = ["E402"]
```

❌ **BAD:**
```toml
[tool.ruff.lint.per-file-ignores]
"load*.py" = ["E402"]
"*config*.py" = ["E402"]
```

### Pylint: Move to Inline or Specific Files
✅ **GOOD:**
```python
def complex_function():  # pylint: disable=too-many-arguments
    ...
```

❌ **BAD:**
```toml
[tool.pylint.messages_control]
disable = ["too-many-arguments", "too-many-locals"]
```

---

## Enforcement (Non-Negotiable)

### What We Will NOT Accept
❌ **DO NOT add patterns like:**
```toml
"load*.py" = ["E402", "F401"]
"*config*.py" = ["E402"]
"dashboard/*.py" = ["E402", "C901"]
```

These hide violations and make linting unauditable. If a whole file category needs ignores, it indicates a design problem.

❌ **DO NOT disable critical rules globally:**
- `F401` (unused imports) — indicates dead code
- `too-many-arguments` / `too-many-locals` (unless inline per-function)
- Type errors from mypy strict mode

### Code Review Enforcement
Every PR will:
1. Check for new wildcard patterns (will be requested to change)
2. Verify inline ignores have comments explaining why
3. Run the audit command: `grep -rn "# noqa\|# type: ignore" --include="*.py" | grep -v "test_"`
4. Ensure count doesn't increase without strong justification

### Pre-Commit Hook Addition
Consider adding this to `.pre-commit-config.yaml`:
```yaml
- repo: local
  hooks:
    - id: forbid-lint-patterns
      name: Forbid wildcard lint ignores
      entry: bash -c 'grep -q "load\*\.py\|\\*config.*\.py\|dashboard/\\*" pyproject.toml && exit 1 || exit 0'
      language: system
      files: pyproject.toml
      stages: [commit]
```

---

## Migration from Current State

1. **Delete wildcard per-file-ignores** from `pyproject.toml` ✅
2. **List specific files** that genuinely need E402 (scripts, loaders, tools) ✅
3. **Audit existing ignores** — run the grep command above, document each one (ongoing)
4. **Re-enable Pylint rules** and use inline ignores for edge cases ✅

---

## Related Rules
- See `GOVERNANCE.md` for type-safety requirements
- See `OPERATIONS.md` for CI enforcement
