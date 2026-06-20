# Security Scanning & Code Quality Audit

**Date:** 2026-06-19  
**Scope:** CI/CD pipeline, static analysis, dependency scanning, infrastructure validation  
**Status:** Comprehensive baseline with best-practice gaps identified

---

## Executive Summary

Your CI pipeline (`ci-fast-gates.yml`) has **solid foundational security scanning** with secrets detection, SAST, dependency auditing, and infrastructure validation. However, you're missing several **industry best practices** that would significantly improve security posture:

| Category | Status | Priority |
|----------|--------|----------|
| **Secrets Scanning** | ✅ Implemented | — |
| **Dependency Scanning (SCA)** | ✅ Implemented | — |
| **Static Code Analysis (SAST)** | ⚠️ Partial | Add DAST + JavaScript SAST |
| **Infrastructure as Code (IaC)** | ✅ Implemented | — |
| **Dynamic Testing (DAST)** | ❌ Missing | **HIGH** |
| **Container Scanning** | ❌ Missing | **HIGH** |
| **Automated Dependency Updates** | ❌ Missing | **MEDIUM** |
| **License Compliance** | ❌ Missing | **MEDIUM** |
| **JavaScript/TypeScript SAST** | ❌ Missing | **MEDIUM** |
| **API Security Testing** | ❌ Missing | **MEDIUM** |
| **Software Bill of Materials (SBOM)** | ❌ Missing | **LOW** |

---

## Current Implementation Details

### ✅ What You Have

#### 1. **Secrets Detection (TruffleHog)**
- **Tool:** TruffleHog v1.28.4+ (latest)
- **Config:** `.secrets.baseline` (detect-secrets framework)
- **Coverage:** 
  - Verified secrets: AWS keys, GitHub tokens, GitLab tokens, Discord tokens, Azure storage keys, Artifactory credentials
  - Custom patterns: Alpaca API keys, AWS access key IDs
- **Strength:** Full commit history scanning, verified patterns only (low false positive rate)
- **Weakness:** Only catches known patterns; doesn't catch obfuscated or novel secret formats

```yaml
# CI job: scan-secrets (2 min timeout)
- TruffleHog with --only-verified flag (low false positives)
- Custom regex for Alpaca API keys (APCA_API_KEY_ID, PK prefix)
- Custom regex for AWS access keys (AKIA pattern)
```

#### 2. **Dependency Vulnerability Scanning (SCA)**
- **Python:** `pip-audit` with `--desc` flag (shows vulnerability descriptions)
- **Node/JavaScript:** `npm audit --audit-level=high` (in pre-commit scripts)
- **Coverage:** 
  - Python: psycopg2, yfinance, requests, pandas, boto3, Flask, urllib3, openpyxl, etc.
  - Node: axios, express, helmet, bcrypt, AWS SDK v3, jsonwebtoken, etc.
- **Strength:** Blocks on high CVEs (SCA-2024 standards)
- **Weakness:** No automated patching; requires manual dependency updates

```yaml
# CI job: scan-dependencies (3 min timeout)
- pip-audit for Python dependencies
- npm audit in Lambda function pre-commit
```

#### 3. **Static Application Security Testing (SAST) — Python**
- **Tool:** Bandit v1.7.5
- **Config:** `.bandit` (skips B608 SQL injection false positives)
- **Coverage:**
  - Hardcoded credentials
  - Insecure random generators
  - Command injection risks
  - Use of unsafe modules (pickle, pickle.loads, eval)
  - Hardcoded SQL (with safe parameterized exceptions)
- **Severity Filter:** Medium+ confidence (ignores low-confidence false positives)
- **Exclusions:** tests/, migrations/, node_modules/, .venv/
- **Strength:** Fast, integrated in CI, catches common Python security bugs
- **Weakness:** No cross-file data flow analysis; false positives on legitimate parameterized queries

```yaml
# CI job: scan-sast (3 min timeout)
- bandit -r algo loaders config lambda
- --severity-level medium
- --confidence-level high
```

#### 4. **Code Quality & Linting**
- **Formatting:** `black --check` (Python code formatter)
- **Import Sorting:** `isort --check-only` (import standardization)
- **Linting:** `flake8` (advisory only, non-blocking, max-line-length=120)
- **Type Checking:** `mypy` (BLOCKING, shows error codes)
- **JavaScript/Node:** ESLint + Prettier (in Lambda package.json)

```yaml
# CI job: lint-and-type (5 min timeout)
- Importability check (catches NameError, ImportError, SyntaxError)
- Black format enforcement
- isort import ordering
- flake8 (E501, W503, E203 ignored)
- mypy type checking (BLOCKING)
```

#### 5. **Testing & Coverage**
- **Framework:** pytest (unit, edge case, integration markers)
- **Coverage:** pytest-cov with Codecov integration
- **Minimum:** 75% green, 50% orange thresholds (enforced in PRs)
- **Scope:** algo/, loaders/, lambda/
- **Database:** Real PostgreSQL in coverage job (not mocked)
- **CI coverage:** 15 min timeout with mocked DB (unit/edge/integration)

```yaml
# 3 separate test jobs:
1. tests job (unit + edge + integration with mocked DB) — 15 min
2. coverage job (with real PostgreSQL) — 10 min
3. Codecov upload + PR comment
```

#### 6. **Infrastructure as Code (IaC) Scanning**
- **Validation:** Terraform fmt, init, validate, plan (dry-run)
- **Security Scanning:** tfsec v1.28.4 (Terraform security scanner)
- **Scope:** terraform/ directory
- **Filter:** CRITICAL issues only (medium/low warnings ignored)
- **Dry-run:** terraform plan with dummy AWS credentials (catches config errors)

```yaml
# 2 IaC jobs:
1. validate-terraform (5 min) — fmt, init, validate, plan
2. scan-iac (3 min) — tfsec --minimum-severity CRITICAL
```

#### 7. **Pre-Commit Hooks (Local)**
- **No .pre-commit-config.yaml found** — relies on npm/pip scripts
- **Python Pre-Commit:** implicit in CI gates (mypy, black, isort)
- **Node Pre-Commit:** npm scripts in package.json (lint, format:check, test:dep)

---

## ❌ What's Missing (Best Practices)

### 1. **DAST (Dynamic Application Security Testing)** — HIGH PRIORITY

**What it is:** Runtime testing of your application to find vulnerabilities through interaction.

**Why you need it:**
- Bandit (SAST) catches static code issues but misses:
  - Injection attacks in running code paths
  - Authentication/authorization bypasses
  - Session management flaws
  - Broken access control
  - Insecure deserialization at runtime
  - XXE (XML External Entity) in request handlers

**Recommendation:**
- **OWASP ZAP (free):** Container-based scanner, can run in CI
- **Burp Suite Community (free):** Manual interactive testing for complex flows
- **API-specific:** Postman/REST client with security test collections

**Implementation approach:**
```yaml
# Add to ci-fast-gates.yml:
scan-dast:
  runs-on: ubuntu-latest
  needs: [coverage]  # Wait for tests to pass first
  services:
    app:
      image: your-docker-image:latest
      ports:
        - 5000:5000
  steps:
    - uses: actions/checkout@v4
    - uses: zaproxy/action-baseline@v0.11.0
      with:
        target: 'http://localhost:5000'
        rules_file_name: '.zap/rules.tsv'
        cmd_options: '-a'
```

---

### 2. **GitHub CodeQL** — HIGH PRIORITY (Free)

**What it is:** GitHub's native vulnerability scanner; detects memory safety, injection, authentication flaws.

**Why you need it:**
- Semantic analysis (understands code flow, not just patterns)
- Language-specific (Python, JavaScript/TypeScript, Java, C/C++, Go, Ruby)
- Catches subtle vulnerabilities Bandit misses (taint analysis, data flow)
- Free for public repos, low cost for private repos
- Integrated into GitHub (shows findings on security tab)

**Implementation:**
```yaml
# Add to .github/workflows/codeql-analysis.yml:
name: CodeQL Analysis

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 2 * * 1'  # Weekly Monday 2 AM UTC

jobs:
  analyze:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        language: ['python', 'javascript']
    steps:
      - uses: actions/checkout@v4
      - uses: github/codeql-action/init@v2
        with:
          languages: ${{ matrix.language }}
      - uses: github/codeql-action/autobuild@v2
      - uses: github/codeql-action/analyze@v2
        with:
          category: /language:${{ matrix.language }}
```

**Cost:** Free for GitHub-hosted runners, saves 15 min per job = $0 (within GitHub Actions free tier).

---

### 3. **GitHub Dependabot** — MEDIUM PRIORITY (Free)

**What it is:** Automated dependency update PRs with security vulnerability checks.

**Why you need it:**
- pip-audit only finds vulnerabilities; doesn't fix them
- npm audit doesn't auto-patch
- Dependabot creates PRs for patch/minor/major bumps
- Includes security advisory checks
- Auto-merge option for patch updates

**Implementation:**
```yaml
# Create .github/dependabot.yml:
version: 2
updates:
  # Python dependencies
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    reviewers:
      - "your-github-username"
    allow:
      - dependency-type: "production"
      - dependency-type: "development"
    commit-message:
      prefix: "chore(deps):"

  # Node dependencies (root)
  - package-ecosystem: "npm"
    directory: "/"
    schedule:
      interval: "weekly"
    reviewers:
      - "your-github-username"

  # Node dependencies (Lambda)
  - package-ecosystem: "npm"
    directory: "/webapp/lambda"
    schedule:
      interval: "weekly"
    reviewers:
      - "your-github-username"

  # Terraform
  - package-ecosystem: "terraform"
    directory: "/terraform"
    schedule:
      interval: "weekly"
    reviewers:
      - "your-github-username"
```

**Cost:** Free.

---

### 4. **Container Image Scanning** — HIGH PRIORITY

**What it is:** Scan your Docker images for vulnerabilities before deployment.

**Why you need it:**
- Your Dockerfile uses base images (probably ubuntu/python) with unpatched CVEs
- Base image vulnerabilities can be exploited even if your code is secure
- Needed for Lambda layers, ECR images, ECS tasks

**Recommendation:**
- **Trivy (free, fast, accurate):** Scans Dockerfile layers, container images, artifact dependencies
- **Snyk Container (free tier):** Alternative with better developer experience

**Implementation:**
```yaml
# Add to ci-fast-gates.yml or separate workflow:
scan-container:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: aquasecurity/trivy-action@master
      with:
        scan-type: 'config'
        scan-ref: 'Dockerfile'
        format: 'sarif'
        output: 'trivy-results.sarif'
    - uses: github/codeql-action/upload-sarif@v2
      with:
        sarif_file: 'trivy-results.sarif'
```

---

### 5. **JavaScript/TypeScript SAST** — MEDIUM PRIORITY

**What it is:** Security scanning for JavaScript/TypeScript code (you only have ESLint linting, not security analysis).

**Why you need it:**
- ESLint catches style/syntax, not security
- NodeJS has unique vulnerabilities:
  - Command injection in child_process.exec()
  - Prototype pollution
  - NoSQL injection in MongoDB queries
  - Unsafe eval/Function() constructors
  - Hardcoded AWS keys in Lambda code

**Recommendation:**
- **Semgrep (free tier):** Fast, rule-based SAST for JS/TS/Python
- **Snyk SAST (free tier):** Semantic analysis for JS/TS
- **ESLint security plugins:** eslint-plugin-security

**Implementation (Semgrep):**
```yaml
# Add to ci-fast-gates.yml:
scan-js-sast:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: returntocorp/semgrep-action@v1
      with:
        config: >-
          p/security-audit
          p/owasp-top-ten
          p/nodejs
          p/typescript
```

---

### 6. **License Compliance Scanning** — MEDIUM PRIORITY

**What it is:** Ensure dependencies use compatible open-source licenses.

**Why you need it:**
- GPL dependencies might require you to open-source your code
- Copyleft licenses have downstream obligations
- SSPL, Elastic License, Commons Clause can be commercially restrictive

**Recommendation:**
- **FOSSA (free tier):** Lightweight license scanner
- **Black Duck (free tier):** Comprehensive license + vulnerability DB
- **Licensefinder (open-source):** Lightweight Ruby tool

**Implementation (via npm/pip):**
```bash
# Python:
pip install licensecheck
licensecheck --zero

# Node:
npm install -g license-checker
license-checker --onlyunknown --excludePrivatePackages
```

---

### 7. **Software Bill of Materials (SBOM)** — LOW PRIORITY

**What it is:** Formal, machine-readable manifest of all dependencies.

**Why you need it:**
- Required by government contracts (SLSA L3+, EO 14028)
- Enables faster CVE response (know which products affected)
- Better supply chain visibility
- Needed for compliance frameworks (SOC 2, ISO 27001)

**Recommendation:**
- **Syft (free, by Anchore):** Fast, accurate SBOM generation
- **CycloneDX:** Standard format (better than SPDX for some tools)

**Implementation:**
```yaml
# Add to ci-fast-gates.yml:
sbom:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: anchore/sbom-action@v0
      with:
        path: .
        format: spdx-json
        output-file: sbom-spdx.json
    - uses: actions/upload-artifact@v4
      with:
        name: sbom
        path: sbom-spdx.json
```

---

### 8. **API Security Testing** — MEDIUM PRIORITY

**What it is:** Schema validation, authentication, rate limit enforcement testing.

**Why you need it:**
- Your API has routes in lambda/api/routes/
- Need to verify:
  - Authentication/JWT validation works
  - Rate limiting is enforced
  - Input validation rejects malicious payloads
  - Response headers are secure (CORS, CSP, etc.)

**Recommendation:**
- **Postman Collections + Newman (free):** Define API contract, run in CI
- **Dredd (free):** API Blueprint/OpenAPI validator
- **API Contracts in Jest:** Integration tests with security assertions

**Implementation (integration tests in Jest):**
```javascript
// tests/integration/api/security.test.js
describe('API Security', () => {
  test('POST /api/trade rejects request without JWT', async () => {
    const res = await request(app).post('/api/trade');
    expect(res.status).toBe(401);
  });

  test('POST /api/trade includes secure headers', async () => {
    const res = await request(app).post('/api/trade')
      .set('Authorization', `Bearer ${validToken}`);
    expect(res.headers['x-content-type-options']).toBe('nosniff');
    expect(res.headers['strict-transport-security']).toBeDefined();
  });

  test('Rate limit enforcement: 10 requests/min to /api/accounts', async () => {
    for (let i = 0; i < 11; i++) {
      const res = await request(app).get('/api/accounts')
        .set('Authorization', `Bearer ${validToken}`);
      if (i < 10) expect(res.status).not.toBe(429);
      if (i === 10) expect(res.status).toBe(429);
    }
  });
});
```

---

### 9. **Automated Secrets Rotation Enforcement** — LOW PRIORITY

**What it is:** Detect if AWS/API credentials are stale and enforce rotation.

**Why you need it:**
- Your .secrets.baseline detects secrets that are checked in
- Doesn't detect if AWS keys are stale (should rotate quarterly)
- CLAUDE.md mentions quarterly credential rotation, but no CI enforcement

**Recommendation:**
```yaml
# Add to ci-fast-gates.yml:
check-secrets-age:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
      with:
        fetch-depth: 0
    - name: Check AWS key age in git history
      run: |
        # Extract AWS key from git history (if present)
        KEY=$(git log --all --grep="AKIA" --oneline | head -1)
        if [ -n "$KEY" ]; then
          COMMIT_DATE=$(git log -1 --format=%ad --date=short $KEY)
          DAYS_OLD=$(( ($(date +%s) - $(date -d "$COMMIT_DATE" +%s)) / 86400 ))
          if [ $DAYS_OLD -gt 90 ]; then
            echo "WARNING: AWS key in commit history is $DAYS_OLD days old"
          fi
        fi
```

---

### 10. **Performance Regression Testing** — OPTIONAL

**What it is:** Detect performance degradation in PRs.

**Why you need it:**
- Your data loaders have timeouts (SLA enforcement)
- Need to catch performance regressions before deployment
- Your benchmark suite doesn't run in CI

**Recommendation:**
- **pytest-benchmark:** Capture baseline, alert on regression
- **Custom timing checks:** Loaders must complete within SLA

---

## Recommended Implementation Roadmap

### Phase 1: Quick Wins (1-2 days, High Impact)
1. ✅ **CodeQL** (GitHub-native, free)
   - Time: 30 min to implement
   - Benefit: Semantic vulnerability analysis
   
2. ✅ **Dependabot** (GitHub-native, free)
   - Time: 15 min to implement
   - Benefit: Auto-patch vulnerable dependencies

3. ✅ **Semgrep** (free tier, fast)
   - Time: 1 hour to implement
   - Benefit: JavaScript SAST coverage

### Phase 2: Runtime Security (2-3 days)
4. ✅ **Trivy Container Scanning**
   - Time: 1-2 hours
   - Benefit: Dockerfile/image vulnerability detection

5. ✅ **OWASP ZAP DAST**
   - Time: 2-3 hours
   - Benefit: Runtime security testing

### Phase 3: Compliance & Visibility (1-2 days)
6. ✅ **License Scanning**
   - Time: 1 hour
   - Benefit: License compliance, supply chain risk

7. ✅ **SBOM Generation**
   - Time: 1 hour
   - Benefit: Government contract readiness

8. ✅ **API Security Tests**
   - Time: 2-3 hours
   - Benefit: Authentication/authorization validation

---

## Implementation Commands

### CodeQL
```bash
# Create .github/workflows/codeql-analysis.yml (see above)
```

### Dependabot
```bash
# Create .github/dependabot.yml (see above)
```

### Semgrep
```bash
# Add to ci-fast-gates.yml in the ci-fast-gates job section
```

### Trivy
```bash
# Add new scan-container job to ci-fast-gates.yml
```

### License Check (Python)
```bash
pip install licensecheck
licensecheck --zero
```

### License Check (Node)
```bash
npm install -g license-checker
license-checker --onlyunknown
```

---

## Estimated CI Pipeline Impact

| Tool | Scanning Time | Cost | Blocking |
|------|---------------|------|----------|
| CodeQL | +3-4 min | Free | Yes (NEW) |
| Dependabot | N/A (async) | Free | Only PR creation |
| Semgrep | +2-3 min | Free | Yes (NEW) |
| Trivy | +1-2 min | Free | Yes (NEW) |
| ZAP DAST | +5-10 min | Free | Yes (NEW) |
| License Check | +1 min | Free | Yes (NEW) |
| SBOM | +1 min | Free | No (artifact only) |
| **TOTAL** | **+13-21 min** | **Free** | — |

**Current pipeline:** ~12 min  
**With all additions:** ~25-33 min (still within GitHub free tier)

---

## Security Posture Summary

### Strengths ✅
- Secrets detection with low false-positive rate
- Comprehensive Python SAST (Bandit)
- Type checking enforcement (MyPy)
- Infrastructure validation (Terraform)
- Dependency vulnerability scanning
- Real PostgreSQL in coverage tests (catches DB issues)
- All security gates are BLOCKING (no advisor-only mode)

### Gaps ⚠️
- No DAST (runtime testing)
- No JavaScript SAST
- No CodeQL (semantic analysis)
- No container image scanning
- No automated dependency patching
- No license compliance
- No SBOM for supply chain

### Compliance Readiness
- **SOC 2 (Type II):** Needs DAST + API security tests
- **ISO 27001:** Needs automated secret rotation, license tracking
- **FedRAMP:** Needs SBOM, SLSA, container scanning
- **HIPAA:** Needs encryption validation, audit logging
- **PCI-DSS:** Needs container scanning, secrets rotation

---

## Next Steps

1. **Prioritize:** Start with CodeQL + Dependabot (free, 45 min setup)
2. **Add Semgrep:** Covers JavaScript security gaps
3. **Implement DAST:** Runtime validation (ZAP)
4. **Container Scanning:** Trivy for Dockerfile/ECR images
5. **Monitor:** Set baseline, tune false-positive suppression rules

---

## References

- [OWASP Top 10 2024](https://owasp.org/www-project-top-ten/)
- [GitHub CodeQL Docs](https://codeql.github.com/)
- [Trivy Security Scanner](https://github.com/aquasecurity/trivy)
- [Semgrep Documentation](https://semgrep.dev/docs/)
- [SLSA Framework](https://slsa.dev/)
- [CycloneDX Specification](https://cyclonedx.org/)
