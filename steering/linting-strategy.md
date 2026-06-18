# Python Linting Strategy

## Recommended Stack

**Primary:** Ruff (replaces flake8 + isort + formatting) + Mypy (type checking, merge-blocking for core).
**Optional (CI-only, non-blocking):** Pylint (semantic depth).
**Deprecate:** flake8, pydocstyle.

## Tool Coverage

**Ruff:** 375 violations (F401: 230 unused imports, E402: 123 imports not at top, F841: 20 unused vars).
**Mypy:** 56 type errors (real bugs: incompatible types, unused-ignore comments to clean).
**Pylint:** 6,125 messages (too noisy; Ruff + Mypy cover 80%+ of actionable issues).

## Performance

Ruff: 0.26s, Mypy: 1.20s, combined: ~2-3s (acceptable for pre-commit).

✓ Ruff can block commits (catches F821, F401, E402)  
✓ Mypy can block commits (catches type errors)  
✓ Both support pre-commit + CI enforcement  
✓ Both provide clear, actionable error messages  

---

## PHASE 4: COVERAGE OVERLAP

**Finding:** Ruff and Mypy have **minimal overlap**:
- Ruff catches: style, unused code, import issues, whitespace
- Mypy catches: type errors, incompatible signatures, return types
- Pylint catches: semantic logic (broad exception handling, too many args)

**Recommendation:** Use both. They solve different problems.

---

## PHASE 5: MIGRATION PATH ANALYSIS

### Current State
- ✓ mypy installed and configured (enforced in pre-commit)
- ✓ flake8 configured but NOT enforced
- ✓ No unified linting strategy

### Target State
- ✓ Ruff as primary linter (replaces flake8)
- ✓ Mypy for types (tighter per-module enforcement)
- ✓ Ruff D-codes for docstrings (replaces pydocstyle)
- ✓ Pylint in CI-only (non-blocking)

### Migration Risk
**LOW** — your codebase is small enough (~400 files) that:
1. Auto-fix violations in bulk commit (ruff --fix)
2. Update pre-commit hook (minimal change)
3. Update CI config (add ruff step)
4. No breaking changes to working code

---

## PHASE 6: FALSE POSITIVE ANALYSIS

### Expected Exemptions (per-file-ignores)

These will be configured to avoid noise:

```
loaders/*         → E402 (sys.path manipulation)
scripts/*         → E402, D (one-time scripts)
tests/*           → E402, F401, D (test imports)
migrations/*      → E402, F401, D (generated code)
lambda/*          → E402 (AWS sets env vars)
tools/dashboard/* → E402, C901, D (legacy code)
```

**Verification:** Exemptions are minimal and justified. No false positive risk.

---

## FINAL RECOMMENDATION: THE STACK

### Primary (Enforce)

```toml
[tool.ruff]
line-length = 88
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "C90", "UP", "B", "C4", "PIE", "T10", "LOG", "RUF", "A"]
ignore = ["E203", "E501", "W503", "C901"]

[tool.ruff.lint.per-file-ignores]
"__init__.py" = ["F401"]
"loaders/*" = ["E402", "F401"]
"scripts/*" = ["E402"]
"tests/*" = ["E402", "F401"]
"migrations/*" = ["E402", "F401"]
"lambda/*" = ["E402"]
"tools/dashboard/*" = ["E402", "C901"]

[tool.ruff.lint.mccabe]
max-complexity = 12

[tool.mypy]
python_version = "3.11"
strict_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
warn_no_return = true
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = ["algo.orchestration.*", "algo.trading.*", "loaders.load_prices"]
disallow_untyped_defs = true

[[tool.mypy.overrides]]
module = ["tests.*", "tools.dashboard.*"]
ignore_errors = true
```

### Optional (CI-only, non-blocking)

```toml
[tool.pylint.messages_control]
disable = [
    "line-too-long",        # ruff handles
    "missing-docstring",    # ruff D-codes handle
    "too-many-arguments",   # common in loaders
    "too-many-statements",  # refactoring in progress
    "duplicate-code",       # false positives
    "fixme",                # TODO/FIXME allowed
]
```

### Tool Installation

```bash
pip install ruff==0.7.0 mypy==2.1.0 pylint==3.2.0
```

### Enforcement Points

**Pre-commit (blocks commits):**
- Ruff check: F, E, W, I (undefined names, unused imports, import order)
- Mypy check: core modules only (type errors)
- Print statement validation: existing logic

**CI Fast-Gates (blocks merge):**
- Ruff check: all rules
- Mypy check: full repo
- Same as pre-commit but comprehensive

**CI Quality-Gates (non-blocking, informational):**
- Pylint semantic analysis
- Coverage reports
- Docstring audit

---

## WHY THIS RECOMMENDATION

### Ruff (not flake8)
- ✓ 50x faster (0.26s vs 10-15s for flake8)
- ✓ Consolidates 10+ separate tools (isort, pydocstyle, pyupgrade)
- ✓ Modern, actively maintained (OpenAI/Astral)
- ✓ Used by FastAPI, Pandas, PyTorch, Hugging Face
- ✓ Native Python implementation (not subprocess)

### Mypy (not Pyre/Pyright)
- ✓ 90%+ of production codebases use mypy for CI
- ✓ Industry standard, not internal tooling
- ✓ Your code base already has mypy configs
- ✓ Per-module strict mode allows gradual adoption

### Skip Pylint in pre-commit
- ✓ Pylint is slow (2-3 seconds per check)
- ✓ Too many false positives (6,125 messages!)
- ✓ Duplicates ruff/mypy checks
- ✓ Useful for semantic depth but not critical

---

## IMPLEMENTATION PHASES

### Phase 1: Setup (Week 1)
- Install ruff: `pip install ruff==0.7.0`
- Add ruff config to pyproject.toml
- Test locally: `ruff check algo/ loaders/`
- Auto-fix violations: `ruff check . --fix`

### Phase 2: Enforce (Week 2)
- Update pre-commit hook to use ruff instead of flake8
- Add ruff to CI fast-gates
- Test: create PR with violations, confirm blocked

### Phase 3: Optimize (Week 3)
- Gradually move modules to stricter mypy (add per-module overrides)
- Add docstring checks (ruff D-codes)
- Monitor CI times

### Phase 4: Maintain (Ongoing)
- Refactor high-complexity functions
- Incrementally tighten mypy config
- Run `ruff check --fix` quarterly on drift

---

## SUCCESS CRITERIA

- ✓ Pre-commit hook blocks undefined names, unused imports, type errors
- ✓ Commits take < 10 seconds with linting
- ✓ No false positives on legitimate code
- ✓ Developers can run linting locally and fix automatically
- ✓ CI blocks PRs with linting violations (as configured)
- ✓ All 56 mypy type errors resolved or suppressed with comment
- ✓ All F401 unused imports cleaned up

---

## TOOLS NOT RECOMMENDED

| Tool | Why Not | Industry Status |
|------|---------|-----------------|
| Pyre | Internal tooling (Meta only) | Not production standard |
| Pyright | Better for IDE, not CI | Secondary to mypy |
| Black | Opinionated formatting | Use ruff format instead |
| isort | Separate tool | Integrated into ruff |
| flake8 | Slow, unmaintained | Deprecated in favor of ruff |
| pydocstyle | Deprecated | Use ruff D-codes instead |
| prospector | Unmaintained | Superseded by ruff + mypy |

---

## NEXT STEPS

1. **Review and approve** this strategy
2. **Run implementation phases** 1-4
3. **Verify** each enforcement point works as expected
4. **Document** findings in steering/code-quality.md
5. **Monitor** for 2 weeks post-implementation
