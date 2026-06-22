# Reference: Detailed Operations

This file contains detailed operations information not needed in every conversation. Linked from `OPERATIONS.md`.

---

## Detailed CI/CD Gates

### Security Gates (BLOCKING)

1. **Secret Scanning** (~2 min)
   - TruffleHog: Detects known secret patterns (AWS keys, API keys, etc.)
   - Pattern detection: Catches hardcoded APCA/AWS credentials in new commits
   - Fails: If any credentials detected
   - Local: `trufflehog filesystem . --only-verified`

2. **Dependency Vulnerabilities** (~3 min)
   - pip-audit: Scans Python dependencies for CVEs
   - Fails: If any high-risk vulnerabilities found
   - Local: `pip-audit --desc`

3. **Static Code Analysis** (~3 min)
   - Bandit: Scans for Python security issues (hardcoded secrets, SQL injection, etc.)
   - Fails: Medium+ confidence issues detected
   - Local: `bandit -r algo loaders config lambda --severity-level medium --confidence-level high`

4. **Infrastructure Scanning** (~5 min)
   - Terraform: `terraform fmt`, `terraform validate`, `terraform plan`
   - tfsec: Scans Terraform for security misconfigurations (CRITICAL level)
   - Fails: If Terraform invalid or critical IaC issues found
   - Local: `cd terraform && terraform validate && tfsec . --minimum-severity CRITICAL`

5. **Container Image Scanning** (~5 min)
   - Trivy: Scans Docker image for vulnerabilities
   - Fails: If CRITICAL or HIGH vulnerabilities in image
   - Local: `docker build -t algo:test . && trivy image algo:test --severity CRITICAL,HIGH`

6. **JavaScript/TypeScript Scanning** (~5 min)
   - Semgrep: OWASP Top 10, security audits, Node.js best practices
   - Fails: If security issues detected in JS/TS
   - Local: `semgrep --config p/owasp-top-ten --config p/nodejs .`

### Code Quality Gates (BLOCKING)

7. **Linting & Type Checking** (~5 min)
   - Import validation: Runs `scripts/ci_validation.py` to ensure all `.py` files are importable
   - Ruff lint: `ruff check algo/ tests/ tools/` (linting rules E, F for errors and undefined names)
   - Ruff format: `ruff format --check algo/ tests/ tools/` (code formatting)
   - MyPy: Type checking for `algo/` and `tools/`
   - Fails: If any import broken, linting violation, formatting mismatch, or type error
   - Local: `make lint format type-check` or `python scripts/ci_validation.py`

8. **Unit/Integration Tests** (~15 min)
   - Unit tests: `pytest tests/ -m unit`
   - Edge case tests: `pytest tests/ -m edge`
   - Integration tests: `pytest tests/ -m integration`
   - Fails: If any test fails
   - Local: `make test`

### Compliance & Analysis Gates (BLOCKING or WARNING)

9. **License Scanning** (~5 min, WARNING)
   - Detects GPL/SSPL dependencies
   - Current status: WARNING only (not blocking)
   - Local: `licensecheck --zero --format json`

10. **Test Coverage** (~10 min, BLOCKING)
    - Runs tests with coverage, uploads to Codecov
    - Minimum threshold: 75% (green), 50% (orange)
    - Generates HTML coverage report
    - Local: `make coverage`

11. **SBOM Generation** (~5 min, WARNING)
    - Generates Software Bill of Materials in CycloneDX and SPDX formats
    - Uploaded as artifact for compliance/auditing
    - Local: `syft algo:test -o spdx-json > sbom-spdx.json`

12. **Supply Chain Scan** (~5 min, WARNING)
    - Grype: Scans for known vulnerabilities in dependencies
    - Local: `grype algo:test -o sarif > grype-results.sarif`

### Runtime Security (NON-BLOCKING)

13. **Dynamic Testing** (~10 min)
    - OWASP ZAP: Baseline scan of running API
    - Current status: NON-BLOCKING (findings advisory only)
    - Report uploaded as artifact

---

## CI Configuration Files

| File | Purpose | When to Edit |
|------|---------|--------------|
| `.github/workflows/ci-fast-gates.yml` | Main CI pipeline | Adding new gates, changing thresholds |
| `.github/workflows/codeql-analysis.yml` | CodeQL scanning | Enabling new languages/query suites |
| `pyproject.toml` | Ruff, MyPy, Pytest config | Changing formatting/linting rules |
| `.flake8` | Legacy (deprecated) | Don't use - use pyproject.toml instead |
| `.pre-commit-config.yaml` | Local pre-commit hooks | Adding new checks before commit |
| `Makefile` | Local dev commands | Adding new test/quality targets |

---

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

**Bottlenecks:** Container build (Trivy, SBOM, Grype, DAST all rebuild image), test execution (full test suite + coverage), Terraform plan (requires AWS credentials)

---

## Branch Protection Rules

The `main` branch requires:
- `ci-fast-gates` workflow passes (all gates)
- CodeQL analysis passes
- At least 1 approval (if PR)
- No direct pushes to main (PR only)
- Dismissal of stale reviews on new commits

Enforce: GitHub Settings → Branches → Branch protection rules → `main`

---

## Skipping CI Checks

### Pre-commit Hook Bypass (Local Only)

`git commit --no-verify` — Use only for emergency fixes. Bypassed checks may still fail in GitHub CI.

### Skip Specific Pre-commit Hooks

`SKIP=bandit,mypy git commit` — Available hook IDs: `ruff`, `ruff-format`, `mypy`, `bandit`, `trufflehog`

### Skipping GitHub Actions (Commit Message)

`git commit -m "fix: urgent patch [skip ci]"` — Use only for documentation-only changes. Skipping CI can hide real issues.

---

## Debugging CI Failures

### View Logs

1. GitHub Actions: Go to PR → "Checks" tab → Click failing job → See stdout/stderr
2. CloudWatch: AWS Console → CloudWatch Logs → Search for orchestrator/loader logs
3. Artifacts: PR → "Checks" tab → "Artifacts" → Download reports (SARIF, SBOM, coverage)

### Reproduce Locally

Best approach: Run failing check locally first with `make ci-local` or specific checks (`make lint`, `make type-check`, `make test`).

### Temporary Fixes

**DO NOT:** Disable gates, lower thresholds, or commit workarounds

**DO:**
1. Understand root cause
2. Fix the code properly
3. Test locally with `make ci-local`
4. Commit the fix
5. Push PR and verify CI passes

---

## Future Improvements

- [ ] Optimize container scanning (scan only new layers)
- [ ] Add performance regression detection
- [ ] Add mutation testing (verify test quality)
- [ ] Add DAST blocking (currently advisory)
- [ ] Cache Terraform plans between runs
- [ ] Parallel container builds for multiple services

---

## Dashboard Diagnostics (Detailed)

### Quick Start: Diagnose Data Issues

Tool: `python -m dashboard.diagnose_dashboard`

Options:
- `--verbose` — Full responses
- `--local` — Local development mode

Output shows:
- ✓ **SUCCESS**: Data successfully loaded (shows field count)
- ⚠ **STALE**: Data is too old (loader hasn't run recently)
- ✗ **ERRORS**: API call failed or validation failed
- ⚡ **MISSING FIELDS**: Data returned but some fields are None

### Interpret the Report

Example:
```
SUMMARY
  ✓ Success:        15
  ⚠ Stale:          2
  ✗ Errors:         3
  ⚡ Missing fields: 1
```

Meaning:
- 15 endpoints working fine
- 2 endpoints have stale data (e.g., portfolio hasn't been refreshed in >5 days)
- 3 endpoints throwing errors (network, validation, auth failures)
- 1 endpoint returning partial data (some expected fields are None)

### Troubleshooting by Issue Type

#### ✗ ERRORS (API Failures)

**Common causes:**
1. Network/connectivity issues
2. API endpoint not responding
3. Validation failure (missing required fields in API response)
4. Authentication failure (Cognito token expired)

**Resolution steps:**

1. Check if API is responding: `curl https://api-url/api/health -H "Authorization: Bearer $TOKEN"`
2. Check specific endpoint: `curl https://api-url/api/algo/portfolio -H "Authorization: Bearer $TOKEN" -s | jq '.'`
3. Check API logs in CloudWatch: AWS Console → CloudWatch → Logs → /aws/lambda/api-handler. Look for 5xx errors or timeout patterns.
4. Check database connectivity: RDS console → Database → Connectivity & security. Ensure security groups allow Lambda VPC access.

**If API validation fails:**
- Check API response has all required fields (see `VALIDATORS` mapping in `response_validators.py`)
- Check field types match expected (e.g., number not string)
- See GOVERNANCE.md for critical fields documentation

#### ⚠ STALE (Data Too Old)

**Common causes:**
1. Scheduled loaders haven't run (e.g., daily batch jobs)
2. Loader failed silently
3. Data freshness threshold is very strict

**Resolution steps:**

Check when data was last updated: Portfolio (should be <5 days old), Market data (should be <24 hours old), Performance (should be <1 hour old).

Manually trigger missing loaders:

Via GitHub Actions: `gh workflow run manual-invoke-loaders.yml -f loaders="portfolio,performance"`

Or locally: `python -m loaders.load_portfolio_snapshot && python -m loaders.load_performance_metrics`

#### ⚡ MISSING FIELDS (Partial Responses)

**Meaning:** API returned successfully but some expected fields are None

**Example:** Portfolio returns `{total_portfolio_value: 50000, total_cash: None, position_count: 5}`

**Causes:**
1. Data hasn't been computed yet (e.g., daily returns before market close)
2. Loader query returned empty result
3. API doesn't populate field (check API documentation)

**Resolution:**

1. Query database directly: `SELECT total_portfolio_value, total_cash, position_count FROM portfolio ORDER BY last_updated DESC LIMIT 1;`
2. Check if NULL is expected (some fields legitimately can be NULL)
3. If field should never be NULL, check loader logs: AWS Console → CloudWatch. Search for portfolio loader errors.

### Error Handling per Panel

Each panel:
1. Checks for errors first (before trying to display data)
2. Shows error message if data unavailable
3. Never shows placeholder values (no fake dashes/zeros)

Example: If portfolio fails, panel shows:
```
[PORTFOLIO] fetch failed:
  Portfolio data conversion failed: VIX = -1 (must be > 0)
```

Not:
```
Portfolio: $0.00
```

---

## FAQ

**Q: Why am I seeing data errors instead of the dashboard?**
A: That's working correctly! The dashboard now surfaces data issues instead of masking them. Fix the root cause (stale loader, failed API call) and errors will disappear.

**Q: How do I know if an error is critical vs. informational?**
A: Red borders = critical data (blocks core functionality). Yellow borders = stale data (old but usable). Check the error message for specific field name.

**Q: Can I ignore some data errors?**
A: Check the field name. If marked as "optional" in the API contract, it's ok to skip. If marked "critical", you must fix it.

**Q: How do I reload all data?**
A: Run the diagnostic tool, note which loaders are failing, and trigger them:
```
python -m loaders.load_portfolio_snapshot
python -m loaders.load_performance_metrics
python -m loaders.load_market_health_daily
python -m loaders.load_stock_signals
```

---

## Verification Checklist

After fixing issues, verify:

1. Run diagnostic: `python -m dashboard.diagnose_dashboard`
   - All critical fetchers show "Success" ✓
   - No red "ERRORS" section
   - No yellow "STALE" section (or acceptable age)

2. Run dashboard: `python -m dashboard.dashboard`
   - No error panel at top
   - All data visible (no placeholder dashes)
   - Portfolio values, positions count, performance metrics all show

3. Run full test suite: `pytest tests/ -k dashboard`
   - All panel tests pass
   - Error boundary tests pass

---

## Debug Mode: Run Dashboard with Verbose Logging

`LOGLEVEL=DEBUG python -m dashboard.dashboard -w 30`

Look for lines like:
```
[DEBUG] API /api/algo/portfolio: fields with None value: [...]
[WARNING] API /api/algo/performance stale (X min old, threshold: Y min)
```
