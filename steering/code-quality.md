# Code Quality Standards & CI/CD Pipeline

## Overview

This document defines the code quality standards and automated checks that ensure consistent, reliable, and maintainable code across the project.

**Three-layer approach:**
1. **Local development**: Pre-commit hooks catch issues before they're pushed
2. **Pull request**: Automated CI gates verify quality before merge
3. **Production**: Continuous monitoring detects regressions

## Type Checking (mypy)

### Local Development

```bash
# Check your changes before committing
python -m mypy algo/ loaders/ lambda/ --ignore-missing-imports

# Fix type errors
python -m mypy <file>.py --show-error-codes --pretty
```

### CI/CD (Strict Mode)

Core modules run in **strict mode** (blocking):
- `algo/` — Core orchestration and trading logic
- `loaders/` — Data loading pipelines
- `lambda/` — AWS Lambda handlers

Supporting modules run in **non-strict mode** (non-blocking):
- `utils/` — Utility functions
- `tests/` — Test suites
- `tools/` — Admin tools

**Configuration:** `pyproject.toml` → `[tool.mypy]`

**Requirements:**
- All type errors in core modules BLOCK CI
- Type errors in utils/tests are reported but don't block
- NO `# type: ignore` except for explicitly documented reasons

## Test Coverage

### Local Development

```bash
# Run tests with coverage report
pytest tests/ --cov=algo --cov=loaders --cov-report=html

# View coverage (opens htmlcov/index.html)
open htmlcov/index.html
```

### CI/CD Coverage Targets

| Module | Target | Status |
|--------|--------|--------|
| algo/ | 80%+ | 🟡 (currently 45-60%) |
| loaders/ | 70%+ | 🟡 (currently 30-50%) |
| lambda/ | 60%+ | 🟡 (currently 20-40%) |
| tests/ | N/A | (not counted) |

**Actions:**
- PR coverage report is automatically commented on every PR
- Coverage regressions > 5% are highlighted
- Coverage improvements are tracked

**Configuration:** `pyproject.toml` → `[tool.coverage.run]` and `[tool.coverage.report]`

## Test Execution

### Local Development

```bash
# Quick test run
pytest tests/ -x --tb=short

# Full run with timing
pytest tests/ -v --tb=short

# Test a specific file
pytest tests/unit/test_position_sizer.py -v
```

### CI/CD Test Strategy

**Fast gates (on every commit):**
- Security scans (TruffleHog, pip-audit, bandit)
- Type checking (mypy)
- Critical unit tests (position_sizer, circuit_breaker)
- Duration: ~90 seconds

**Quality gates (on every PR):**
- Full test suite (all tests)
- Coverage analysis
- Code formatting checks (Black, isort, flake8)
- Duration: ~10 minutes

**Requirements:**
- All tests MUST pass before merge
- Test failures block CI
- Skipped tests (`@pytest.mark.skip`) are visible but non-blocking

## Code Formatting & Linting

### Tools

| Tool | Purpose | Fixable | Blocking |
|------|---------|---------|----------|
| Black | Code formatting | ✅ Yes | Non-blocking |
| isort | Import ordering | ✅ Yes | Non-blocking |
| flake8 | Linting | ✅ Partial | Non-blocking |
| mypy | Type checking | ✅ Partial | ✅ Yes (strict) |

### Local Development

```bash
# Format code with Black
black algo/ loaders/ lambda/ tests/

# Sort imports with isort
isort algo/ loaders/ lambda/ tests/

# Check linting
flake8 algo/ loaders/ --max-line-length=120 --ignore=E501,W503

# Fix imports in-place
isort --force-single-line-imports algo/
```

### CI/CD Behavior

- **Black/isort/flake8**: Reported in CI but non-blocking (informational)
- **mypy strict**: Blocking for core modules
- PR comments show style violations for reference

## Pre-Commit Hook

Local validation **before** you can commit:

```bash
# Located in: .git/hooks/pre-commit
```

**Checks:**
1. ❌ Blocks `.env` files (use AWS Secrets Manager)
2. ❌ Blocks session status docs at root
3. ❌ Blocks debug code (`pdb`, `ipdb`, `breakpoint()`)
4. ✅ Type checks modified Python files (only YOUR code, not deps)
5. ✅ Validates imports (no NameError)

**To bypass** (only for documented emergencies):
```bash
git commit --no-verify  # NOT RECOMMENDED
```

## Security Scanning

### Automated Checks

**TruffleHog** (secrets detection):
- Scans all commits for leaked credentials
- Runs on every push and PR
- Blocks if secrets found

**pip-audit** (dependency vulnerabilities):
- Scans `requirements.txt` for known vulnerabilities
- Runs on every push and PR
- Non-blocking (informational)

**Bandit** (Python security issues):
- Scans for hardcoded secrets, SQL injection risks
- Runs on every push and PR
- Non-blocking (informational)

**Manual scanning:**
```bash
pip install pip-audit bandit

# Check dependencies
pip-audit --desc

# Check code security issues
bandit -r algo loaders lambda --severity-level medium --confidence-level high
```

## Continuous Improvement

### Coverage Improvement Plan

**Target:** 80% overall coverage by end of Q4

**Current gaps:**
- Loader error handling (30%)
- API route validation (40%)
- Circuit breaker edge cases (50%)

**Actions:**
1. Add tests for high-risk error paths
2. Mock external API calls properly
3. Test timeout and retry logic

### Type Coverage Improvement

**Target:** Eliminate all `# type: ignore` comments except 3 allowed exceptions

**Current situation:**
- ~15 `# type: ignore` comments
- Most are in tools/dashboard/ (legacy code)
- Plan: Migrate to `mypy overrides` in pyproject.toml

## Running the Full Quality Check Locally

```bash
# Quick check (60s)
./scripts/check-quality.sh

# Full check with coverage (3-5m)
./scripts/check-quality.sh --coverage

# Strict type checking
./scripts/check-quality.sh --strict

# All three
./scripts/check-quality.sh --strict --coverage
```

## Troubleshooting

### Type errors blocking commit

```bash
# See what's wrong
python -m mypy <file>.py --show-error-codes --pretty

# If it's a transitive dependency error, update pre-commit hook
# Edit .git/hooks/pre-commit to filter by filename
```

### Test failures

```bash
# Run specific test with verbose output
pytest tests/test_name.py -vv

# Run with detailed traceback
pytest tests/test_name.py --tb=long

# Run with print statements visible
pytest tests/test_name.py -s
```

### Coverage not improving

```bash
# Find uncovered lines
coverage report --include=algo/ --skip-covered

# Generate HTML report with line details
coverage html
open htmlcov/index.html
```

## References

- **mypy docs**: https://mypy.readthedocs.io/
- **pytest docs**: https://docs.pytest.org/
- **coverage.py docs**: https://coverage.readthedocs.io/
- **Black formatting**: https://black.readthedocs.io/
- **isort documentation**: https://pycqa.github.io/isort/
