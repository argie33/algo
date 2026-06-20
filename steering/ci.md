# CI/CD Pipeline & Quality Gates

## Overview

**Primary CI Workflow:** `ci-fast-gates.yml` (27 min runtime, all gates blocking)

Runs on every commit to `main` and every pull request to `main`. Blocks merges if any gate fails.

## What Gets Checked

### Security Gates (BLOCKING)

1. **Secret Scanning** (~2 min)
   - TruffleHog: Detects known secret patterns (AWS keys, API keys, etc.)
   - Pattern detection: Catches hardcoded APCA/AWS credentials in new commits
   - **Fails:** If any credentials detected
   - **Local:** `trufflehog filesystem . --only-verified`

2. **Dependency Vulnerabilities** (~3 min)
   - pip-audit: Scans Python dependencies for CVEs
   - **Fails:** If any high-risk vulnerabilities found
   - **Local:** `pip-audit --desc`

3. **Static Code Analysis** (~3 min)
   - Bandit: Scans for Python security issues (hardcoded secrets, SQL injection, etc.)
   - **Fails:** Medium+ confidence issues detected
   - **Local:** `bandit -r algo loaders config lambda --severity-level medium --confidence-level high`

4. **Infrastructure Scanning** (~5 min)
   - Terraform: `terraform fmt`, `terraform validate`, `terraform plan`
   - tfsec: Scans Terraform for security misconfigurations (CRITICAL level)
   - **Fails:** If Terraform invalid or critical IaC issues found
   - **Local:** `cd terraform && terraform validate && tfsec . --minimum-severity CRITICAL`

5. **Container Image Scanning** (~5 min)
   - Trivy: Scans Docker image for vulnerabilities
   - **Fails:** If CRITICAL or HIGH vulnerabilities in image
   - **Local:** `docker build -t algo:test . && trivy image algo:test --severity CRITICAL,HIGH`

6. **JavaScript/TypeScript Scanning** (~5 min)
   - Semgrep: OWASP Top 10, security audits, Node.js best practices
   - **Fails:** If security issues detected in JS/TS
   - **Local:** `semgrep --config p/owasp-top-ten --config p/nodejs .`

### Code Quality Gates (BLOCKING)

7. **Linting & Type Checking** (~5 min)
   - **Import validation:** Checks all `.py` files are importable (catches broken imports)
   - **Ruff lint:** `ruff check algo/ tests/ tools/` (linting rules)
   - **Ruff format:** `ruff format --check algo/ tests/ tools/` (formatting)
   - **MyPy:** Type checking for `algo/` and `tools/`
   - **Fails:** If any import broken, linting violation, formatting mismatch, or type error
   - **Local:** `make lint format type-check`

8. **Unit/Integration Tests** (~15 min)
   - **Unit tests:** `pytest tests/ -m unit`
   - **Edge case tests:** `pytest tests/ -m edge`
   - **Integration tests:** `pytest tests/ -m integration`
   - **Fails:** If any test fails
   - **Local:** `make test`

### Compliance & Analysis Gates (BLOCKING or WARNING)

9. **License Scanning** (~5 min, WARNING)
   - Detects GPL/SSPL dependencies
   - **Current status:** WARNING only (not blocking)
   - **Local:** `licensecheck --zero --format json`

10. **Test Coverage** (~10 min, BLOCKING)
    - Runs tests with coverage, uploads to Codecov
    - Minimum threshold: 75% (green), 50% (orange)
    - Generates HTML coverage report
    - **Local:** `make coverage`

11. **SBOM Generation** (~5 min, WARNING)
    - Generates Software Bill of Materials in CycloneDX and SPDX formats
    - Uploaded as artifact for compliance/auditing
    - **Local:** `syft algo:test -o spdx-json > sbom-spdx.json`

12. **Supply Chain Scan** (~5 min, WARNING)
    - Grype: Scans for known vulnerabilities in dependencies
    - **Local:** `grype algo:test -o sarif > grype-results.sarif`

### Runtime Security (NON-BLOCKING)

13. **Dynamic Testing** (~10 min)
    - OWASP ZAP: Baseline scan of running API
    - **Current status:** NON-BLOCKING (findings advisory only)
    - Report uploaded as artifact

## How to Run Checks Locally

### First-time Setup

```bash
make install-hooks
```

This installs pre-commit hooks that run on every commit. Hooks are faster (~10s) and give immediate feedback.

### One-off Checks

```bash
# Code quality (matches CI)
make lint         # Ruff linter
make format       # Format code with ruff
make type-check   # MyPy type checking

# Security
make security     # Bandit + TruffleHog

# Testing
make test         # All tests (unit + edge + integration)
make test-unit    # Unit tests only
make coverage     # Tests with coverage report

# All checks (simulates full CI)
make ci-local
```

## Common CI Failures & How to Fix

### ❌ "Secret scan FAILED — credentials detected"

**Cause:** Hardcoded API key, AWS key, or other credential committed

**Fix:**
1. Remove the credential from code
2. Use AWS Secrets Manager for production, PowerShell profile for local
3. Force-commit without pre-commit hooks (last resort):
   ```bash
   git commit --no-verify  # NOT RECOMMENDED
   ```

**Prevention:** Pre-commit hooks catch this automatically. Install with `make install-hooks`.

### ❌ "Linting and type checks FAILED"

**Cause:** Code doesn't match formatting/linting rules

**Fix:**
```bash
make format       # Auto-fix formatting issues
make lint         # See remaining linting errors
make type-check   # See type errors (manual fix needed)
```

Then commit the changes.

### ❌ "Tests FAILED"

**Cause:** Test assertion failed or test crashed

**Fix:**
```bash
make test              # Run full test suite
make test-unit         # Run specific test category
pytest tests/test_*.py # Run specific file
pytest -k test_name    # Run specific test
```

**Debugging:**
- Check CloudWatch logs for orchestrator/loader failures
- Use `pytest -vv` for verbose output
- Use `pytest --pdb` to drop into debugger on failure
- Check database state for integration tests

### ❌ "Terraform validation FAILED"

**Cause:** Terraform syntax error or validation issue

**Fix:**
```bash
cd terraform
terraform fmt -recursive    # Auto-fix formatting
terraform validate         # Check for errors
terraform plan             # Dry-run (requires AWS credentials)
```

**Common issues:**
- Variable type mismatch (check `.tf` files)
- Missing required variables
- Undefined resource references

### ❌ "Coverage analysis FAILED"

**Cause:** Code coverage dropped below minimum threshold (75%)

**Fix:**
```bash
make coverage              # Generate HTML report
# Open htmlcov/index.html to see coverage
# Write tests for uncovered lines
```

**Note:** New code should maintain or improve coverage. Don't lower thresholds.

### ❌ "Dependency scan FAILED"

**Cause:** Known CVE in a dependency

**Fix:**
1. Check what was flagged: `pip-audit --desc`
2. Update the package: `pip install --upgrade <package>`
3. Update `requirements.txt`
4. Test thoroughly before committing

### ❌ "Container scan FAILED"

**Cause:** Dockerfile based on image with known vulnerabilities

**Fix:**
1. Update base image in `Dockerfile` to latest patch version
2. Run `docker build` locally and scan: `trivy image algo:test`
3. Install security patches if needed

## CI Configuration Files

| File | Purpose | When to Edit |
|------|---------|--------------|
| `.github/workflows/ci-fast-gates.yml` | Main CI pipeline | Adding new gates, changing thresholds |
| `.github/workflows/codeql-analysis.yml` | CodeQL scanning | Enabling new languages/query suites |
| `pyproject.toml` | Ruff, MyPy, Pytest config | Changing formatting/linting rules |
| `.flake8` | Legacy (deprecated) | Don't use - use pyproject.toml instead |
| `.pre-commit-config.yaml` | Local pre-commit hooks | Adding new checks before commit |
| `Makefile` | Local dev commands | Adding new test/quality targets |

## Performance Characteristics

| Gate | Runtime | Cached | Notes |
|------|---------|--------|-------|
| Secret scan | 2 min | No | Scans git history |
| Dependencies | 3 min | Pip cache | Fastest with cached deps |
| SAST (Bandit) | 3 min | No | Fast, pure Python scan |
| IaC (Terraform) | 5 min | No | Requires Terraform init |
| Container scan | 5 min | Docker layer cache | Slow: builds Docker image |
| Semgrep | 5 min | No | Comprehensive JS/TS scan |
| Linting | 5 min | No | Fast, parallelized |
| Tests | 15 min | Pip cache | Longest single job; uses mock DB |
| Coverage | 10 min | Pip cache | Requires Postgres service |
| DAST | 10 min | No | Builds container, runs API server |

**Total:** 27 min average (all jobs parallel where possible)

**Bottlenecks:**
- Container build (Trivy, SBOM, Grype, DAST all rebuild image)
- Test execution (full test suite + coverage)
- Terraform plan (requires AWS credentials, slow without them)

## Branch Protection Rules

The `main` branch requires:
- ✅ `ci-fast-gates` workflow passes (all gates)
- ✅ CodeQL analysis passes
- ✅ At least 1 approval (if PR)
- ✅ No direct pushes to main (PR only)
- ✅ Dismissal of stale reviews on new commits

**Enforce:** GitHub Settings → Branches → Branch protection rules → `main`

## Skipping CI Checks

### Pre-commit Hook Bypass (Local Only)

```bash
git commit --no-verify
```

⚠️ **Use only for emergency fixes.** Bypassed checks may still fail in GitHub CI.

### Skip Specific Pre-commit Hooks

```bash
SKIP=bandit,mypy git commit
```

Available hook IDs: `ruff`, `ruff-format`, `mypy`, `bandit`, `trufflehog`

### Skipping GitHub Actions (Commit Message)

```bash
git commit -m "fix: urgent patch [skip ci]"
```

⚠️ **Use only for documentation-only changes.** Skipping CI can hide real issues.

## Debugging CI Failures

### View Logs

1. **GitHub Actions:** Go to PR → "Checks" tab → Click failing job → See stdout/stderr
2. **CloudWatch:** AWS Console → CloudWatch Logs → Search for orchestrator/loader logs
3. **Artifacts:** PR → "Checks" tab → "Artifacts" → Download reports (SARIF, SBOM, coverage)

### Reproduce Locally

**Best approach:** Run failing check locally first

```bash
# See what the CI sees
make ci-local

# Debug specific check
make lint       # If linting failed
make type-check # If type check failed
make test       # If tests failed
```

### Temporary Fixes

**DO NOT:** Disable gates, lower thresholds, or commit workarounds

**DO:**
1. Understand root cause
2. Fix the code properly
3. Test locally with `make ci-local`
4. Commit the fix
5. Push PR and verify CI passes

## Future Improvements

- [ ] Optimize container scanning (scan only new layers)
- [ ] Add performance regression detection
- [ ] Add mutation testing (verify test quality)
- [ ] Add DAST blocking (currently advisory)
- [ ] Cache Terraform plans between runs
- [ ] Parallel container builds for multiple services

## See Also

- **Code quality standards:** CLAUDE.md → "Code Cleanliness"
- **Security baseline:** CLAUDE.md → "Security Baseline"
- **Orchestrator architecture:** system.md → "Orchestrator Phases"
