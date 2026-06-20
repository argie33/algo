# Security Scanning Implementation Checklist

## Quick Reference Table

| Category | Tool | Status | Effort | Impact | Priority |
|----------|------|--------|--------|--------|----------|
| **Secrets** | TruffleHog | ✅ DONE | — | High | — |
| **Dependency (Python)** | pip-audit | ✅ DONE | — | High | — |
| **Dependency (Node)** | npm audit | ✅ DONE | — | High | — |
| **SAST (Python)** | Bandit | ✅ DONE | — | High | — |
| **Lint** | Black + isort + MyPy | ✅ DONE | — | High | — |
| **Tests** | pytest + coverage | ✅ DONE | — | High | — |
| **IaC** | Terraform + tfsec | ✅ DONE | — | High | — |
| **DAST** | OWASP ZAP | ❌ TODO | 3h | High | **P0** |
| **Semantic Analysis** | GitHub CodeQL | ❌ TODO | 0.5h | High | **P0** |
| **JS/TS SAST** | Semgrep | ❌ TODO | 1h | Medium | **P1** |
| **Container Scan** | Trivy | ❌ TODO | 1.5h | High | **P0** |
| **Dependency Updates** | Dependabot | ❌ TODO | 0.25h | Medium | **P1** |
| **License Scan** | licensecheck | ❌ TODO | 1h | Medium | **P1** |
| **API Security** | Jest tests | ❌ TODO | 2h | Medium | **P2** |
| **SBOM** | Syft | ❌ TODO | 0.5h | Low | **P2** |

---

## Implementation Queue

### Priority 0 (Do First - 5 hours total)

#### [ ] 1. GitHub CodeQL
**File to create:** `.github/workflows/codeql-analysis.yml`
```yaml
name: 'CodeQL Analysis'

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]
  schedule:
    - cron: '0 2 * * 1'

jobs:
  analyze:
    name: Analyze (${{ matrix.language }})
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        language: [ 'python', 'javascript-typescript' ]
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Initialize CodeQL
        uses: github/codeql-action/init@v3
        with:
          languages: ${{ matrix.language }}

      - name: Autobuild
        uses: github/codeql-action/autobuild@v3

      - name: Perform CodeQL Analysis
        uses: github/codeql-action/analyze@v3
        with:
          category: /language:${{ matrix.language }}
```
**Time:** 30 min  
**Cost:** Free (GitHub Actions)  
**Verify:** Check "Security" tab in GitHub repo, should show CodeQL results

---

#### [ ] 2. OWASP ZAP DAST
**File to modify:** `.github/workflows/ci-fast-gates.yml`
**Add new job after `tests` job:**
```yaml
  scan-dast:
    name: Security — Dynamic Testing (DAST)
    runs-on: ubuntu-latest
    timeout-minutes: 10
    needs: [tests]
    steps:
      - uses: actions/checkout@v4.1.7

      - name: Build Docker image for testing
        run: |
          docker build -t algo-api:test .

      - name: Start API server
        run: |
          docker run -d \
            -p 5000:5000 \
            -e DATABASE_URL=postgresql://mock:mock@localhost/algo_test \
            -e EXECUTION_MODE=dry_run \
            algo-api:test

      - name: Wait for API to be ready
        run: |
          timeout 30 bash -c 'until curl -f http://localhost:5000/health; do sleep 1; done'

      - name: Run OWASP ZAP baseline scan
        uses: zaproxy/action-baseline@v0.11.0
        with:
          target: 'http://localhost:5000'
          rules_file_name: '.zap/rules.tsv'
          cmd_options: '-a'

      - name: Upload ZAP results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: zap-report
          path: report_html.html
```
**Also create:** `.zap/rules.tsv` (ZAP rules configuration)
```
10001,PASS  # Buffer overflow
10002,PASS  # Directory traversal
10003,PASS  # Insufficient authentication
10004,PASS  # SQL injection
10005,PASS  # Command injection
```
**Time:** 1.5 hours (includes Docker image testing setup)  
**Cost:** +8 min per CI run  
**Verify:** Look for ZAP report in artifacts, check for HIGH findings

---

#### [ ] 3. Trivy Container Scanning
**File to modify:** `.github/workflows/ci-fast-gates.yml`
**Add new job:**
```yaml
  scan-container:
    name: Security — Container Image Scanning
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4.1.7

      - name: Build container image
        run: docker build -t algo:${{ github.sha }} .

      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: algo:${{ github.sha }}
          format: 'sarif'
          output: 'trivy-results.sarif'

      - name: Upload Trivy results to GitHub Security tab
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: 'trivy-results.sarif'
```
**Time:** 1 hour  
**Cost:** +2 min per CI run  
**Verify:** Check "Security" tab, "Code scanning" section for Trivy results

---

#### [ ] 4. Semgrep JavaScript/TypeScript SAST
**File to modify:** `.github/workflows/ci-fast-gates.yml`
**Add new job:**
```yaml
  scan-semgrep:
    name: Security — JavaScript/TypeScript Analysis (Semgrep)
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4.1.7

      - name: Run Semgrep
        uses: returntocorp/semgrep-action@v1
        with:
          config: >-
            p/security-audit
            p/owasp-top-ten
            p/nodejs
            p/typescript
            p/aws-best-practices
          generateSarif: true

      - name: Upload Semgrep results
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: 'semgrep.sarif'
```
**Time:** 1 hour  
**Cost:** +2 min per CI run  
**Verify:** Check "Security" tab for Semgrep findings

---

### Priority 1 (Add Next - 2.5 hours total)

#### [ ] 5. Dependabot Auto-Update
**File to create:** `.github/dependabot.yml`
```yaml
version: 2
updates:
  # Python dependencies
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "03:00"
    reviewers:
      - "your-github-username"
    assignees:
      - "your-github-username"
    commit-message:
      prefix: "chore(deps):"
      prefix-development: "chore(deps-dev):"
      include: "scope"

  # Root Node dependencies
  - package-ecosystem: "npm"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "04:00"
    reviewers:
      - "your-github-username"
    allow:
      - dependency-type: "all"

  # Lambda Node dependencies
  - package-ecosystem: "npm"
    directory: "/webapp/lambda"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "04:30"
    reviewers:
      - "your-github-username"

  # Terraform
  - package-ecosystem: "terraform"
    directory: "/terraform"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "05:00"
    reviewers:
      - "your-github-username"
```
**Time:** 15 min  
**Cost:** Free (async PRs, no CI impact)  
**Verify:** PRs start appearing on Mondays; merge them to stay updated

---

#### [ ] 6. License Compliance Scanning
**File to modify:** `.github/workflows/ci-fast-gates.yml`
**Add new job:**
```yaml
  scan-licenses:
    name: Compliance — License Checking
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4.1.7

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install licensecheck
        run: pip install -q licensecheck

      - name: Check Python licenses
        run: |
          echo "Checking Python dependencies for GPL/proprietary licenses..."
          licensecheck --zero --format json > license-report.json || true
          cat license-report.json

      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: '18'

      - name: Check Node licenses
        run: |
          npm install -g license-checker
          echo "Checking Node dependencies..."
          license-checker --onlyunknown --excludePrivatePackages || true

      - name: Fail if GPL/SSPL found
        run: |
          if grep -q '"license": "GPL\|"license": "SSPL\|"license": "AGPL' license-report.json; then
            echo "ERROR: GPL/SSPL dependencies detected — review with team"
            exit 1
          fi
```
**Time:** 1.5 hours  
**Cost:** +1 min per CI run  
**Verify:** Run locally first: `licensecheck --zero`

---

#### [ ] 7. Dependabot Configuration (Alternative: CLI-based)
**Run locally before committing:**
```bash
# Python
pip install licensecheck
licensecheck --zero --format json

# Node
npm install -g license-checker
license-checker --onlyunknown
```

---

### Priority 2 (Nice-to-Have - 3 hours total)

#### [ ] 8. API Security Integration Tests
**File to create:** `tests/integration/api/security.test.js`
```javascript
const request = require('supertest');
const app = require('../../webapp/lambda/index.js');

describe('API Security Tests', () => {
  describe('Authentication', () => {
    test('POST /api/trade without JWT returns 401', async () => {
      const res = await request(app)
        .post('/api/trade')
        .send({ symbol: 'AAPL' });
      expect(res.status).toBe(401);
    });

    test('POST /api/trade with invalid JWT returns 401', async () => {
      const res = await request(app)
        .post('/api/trade')
        .set('Authorization', 'Bearer invalid.token.here')
        .send({ symbol: 'AAPL' });
      expect(res.status).toBe(401);
    });
  });

  describe('Security Headers', () => {
    test('Responses include HSTS header', async () => {
      const res = await request(app)
        .get('/health')
        .set('Authorization', `Bearer ${process.env.TEST_JWT}`);
      expect(res.headers['strict-transport-security']).toBeDefined();
      expect(res.headers['strict-transport-security']).toMatch(/max-age=/);
    });

    test('Responses include X-Content-Type-Options', async () => {
      const res = await request(app)
        .get('/health');
      expect(res.headers['x-content-type-options']).toBe('nosniff');
    });

    test('Responses include CSP header', async () => {
      const res = await request(app)
        .get('/health');
      expect(res.headers['content-security-policy']).toBeDefined();
    });
  });

  describe('Rate Limiting', () => {
    test('Enforces rate limit on /api/accounts', async () => {
      const token = process.env.TEST_JWT;
      let statusCodes = [];
      
      for (let i = 0; i < 15; i++) {
        const res = await request(app)
          .get('/api/accounts')
          .set('Authorization', `Bearer ${token}`);
        statusCodes.push(res.status);
        if (res.status === 429) break;
      }
      
      expect(statusCodes.slice(0, 10)).toEqual(Array(10).fill(200));
      expect(statusCodes[10]).toBe(429);
    });
  });

  describe('Input Validation', () => {
    test('Rejects SQL injection in symbol parameter', async () => {
      const res = await request(app)
        .post('/api/signal/buy')
        .set('Authorization', `Bearer ${process.env.TEST_JWT}`)
        .send({ symbol: "'; DROP TABLE signals; --" });
      expect(res.status).toBe(400);
      expect(res.body.error).toMatch(/invalid.*symbol/i);
    });

    test('Rejects oversized payloads', async () => {
      const hugePayload = { data: 'x'.repeat(10 * 1024 * 1024) };
      const res = await request(app)
        .post('/api/batch')
        .set('Authorization', `Bearer ${process.env.TEST_JWT}`)
        .send(hugePayload);
      expect([400, 413]).toContain(res.status);
    });
  });
});
```
**Time:** 2-3 hours (depends on API surface)  
**Cost:** No CI impact (runs in existing test job)  
**Verify:** `npm run test:security`

---

#### [ ] 9. SBOM Generation (Syft)
**File to modify:** `.github/workflows/ci-fast-gates.yml`
**Add new job:**
```yaml
  sbom-generation:
    name: Compliance — Software Bill of Materials
    runs-on: ubuntu-latest
    timeout-minutes: 5
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4.1.7

      - name: Generate SBOM (CycloneDX)
        uses: anchore/sbom-action@v0
        with:
          path: .
          format: cyclonedx-json
          output-file: sbom-cyclonedx.json

      - name: Generate SBOM (SPDX)
        uses: anchore/sbom-action@v0
        with:
          path: .
          format: spdx-json
          output-file: sbom-spdx.json

      - name: Upload SBOMs
        uses: actions/upload-artifact@v4
        with:
          name: sbom
          path: |
            sbom-cyclonedx.json
            sbom-spdx.json
```
**Time:** 30 min  
**Cost:** +1 min per CI run (main branch only)  
**Verify:** Check artifacts in GitHub Actions, should have JSON files

---

#### [ ] 10. Performance Regression Testing (Optional)
**File to create:** `tests/performance/loader-benchmarks.py`
```python
import pytest
import time
from algo.loaders.price_loader import load_prices_for_symbols

@pytest.mark.performance
class TestLoaderPerformance:
    def test_price_loader_sla(self):
        """Prices must load within SLA timeout."""
        symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA']
        start = time.time()
        
        result = load_prices_for_symbols(symbols)
        
        elapsed = time.time() - start
        assert elapsed < 30, f"Price loader took {elapsed}s, SLA is 30s"
        assert len(result) == len(symbols)
```
**Time:** 1-2 hours (depends on benchmarks)  
**Cost:** No CI impact (runs in existing coverage job)  
**Verify:** `pytest tests/ -m performance`

---

## Update Summary Job

Modify the `summary` job in `.github/workflows/ci-fast-gates.yml`:

```yaml
  summary:
    runs-on: ubuntu-latest
    needs: [
      scan-secrets, 
      scan-dependencies, 
      scan-sast, 
      validate-terraform, 
      scan-iac, 
      lint-and-type, 
      tests, 
      coverage,
      scan-codeql,           # NEW
      scan-dast,             # NEW
      scan-container,        # NEW
      scan-semgrep,          # NEW
      scan-licenses          # NEW
    ]
    if: always()
    steps:
      - name: Check all gates passed
        run: |
          echo "CI Security Gates Summary"
          echo "=========================="
          
          # Existing checks
          [[ "${{ needs.scan-secrets.result }}" == "success" ]] && \
            echo "✅ Secrets scan passed" || \
            (echo "❌ Secrets scan FAILED"; exit 1)
          
          # New checks
          [[ "${{ needs.scan-codeql.result }}" == "success" ]] && \
            echo "✅ CodeQL analysis passed" || \
            (echo "❌ CodeQL analysis FAILED"; exit 1)
          
          [[ "${{ needs.scan-dast.result }}" == "success" ]] && \
            echo "✅ Dynamic security testing passed" || \
            (echo "⚠️  DAST check incomplete"; true)  # Optional for now
          
          [[ "${{ needs.scan-container.result }}" == "success" ]] && \
            echo "✅ Container scanning passed" || \
            (echo "❌ Container scanning FAILED"; exit 1)
          
          [[ "${{ needs.scan-semgrep.result }}" == "success" ]] && \
            echo "✅ JavaScript/TypeScript SAST passed" || \
            (echo "❌ JS/TS SAST FAILED"; exit 1)
          
          [[ "${{ needs.scan-licenses.result }}" == "success" ]] && \
            echo "✅ License compliance check passed" || \
            (echo "⚠️  License scan check"; true)  # Advisory only
          
          echo ""
          echo "All required security gates passed ✅"
```

---

## Rollout Timeline

### Week 1 (Priority 0)
- [ ] Day 1: CodeQL + Trivy (1 hour)
- [ ] Day 2: Semgrep (1 hour)
- [ ] Day 3: DAST ZAP (2 hours + testing)
- [ ] Day 4-5: Test, tune, verify

### Week 2 (Priority 1)
- [ ] Day 1: Dependabot (15 min)
- [ ] Day 2: License checking (1.5 hours)
- [ ] Day 3-5: Monitor, merge dependency updates

### Week 3 (Priority 2, Optional)
- [ ] Day 1-3: API security tests (2-3 hours)
- [ ] Day 4: SBOM generation (30 min)
- [ ] Day 5: Performance benchmarks (1-2 hours)

---

## Estimated Cost Impact

| Tool | Setup Time | CI Impact | Annual Cost |
|------|------------|-----------|------------|
| CodeQL | 30 min | +3 min/run | Free |
| Dependabot | 15 min | 0 | Free |
| Trivy | 1 hour | +2 min/run | Free |
| Semgrep | 1 hour | +2 min/run | Free |
| DAST (ZAP) | 1.5 hours | +8 min/run | Free |
| License Check | 1.5 hours | +1 min/run | Free |
| API Security Tests | 2-3 hours | 0 | Free |
| SBOM | 30 min | +1 min/run | Free |
| **TOTAL** | **9 hours** | **+17 min/run** | **$0** |

**Current CI time:** 12 min  
**New total:** 29 min (still within GitHub free tier of 2,000 min/month)

---

## Verification Commands

```bash
# Test locally before pushing:

# Python SAST
pip install bandit
bandit -r algo loaders config lambda

# Python dependencies
pip install pip-audit
pip-audit --desc

# Node dependencies
npm audit --audit-level=high

# License check
pip install licensecheck
licensecheck --zero

# Linting
black --check algo/
isort --check-only algo/
flake8 algo/
mypy algo/

# Tests
pytest tests/ -v

# Terraform
cd terraform
terraform validate
terraform fmt -check -recursive

# Semgrep (local)
pip install semgrep
semgrep --config=p/security-audit algo/ loaders/ lambda/

# Bandit with more rules
bandit -r . -ll
```

---

## Success Criteria

✅ All Priority 0 tools running in CI  
✅ All findings (HIGH/CRITICAL) blocking merge  
✅ No false positives (rules tuned)  
✅ Developers can suppress legitimate findings with comments  
✅ CI pipeline completes in < 35 min  
✅ Security dashboard accessible in GitHub "Security" tab  

---

## Support & References

- [GitHub Security Best Practices](https://docs.github.com/en/code-security)
- [OWASP Top 10 2024](https://owasp.org/www-project-top-ten/)
- [NIST SSDF Practice List](https://csrc.nist.gov/publications/detail/sp/800-218/final)
- [CIS Benchmarks for Docker](https://www.cisecurity.org/cis-benchmarks/)
