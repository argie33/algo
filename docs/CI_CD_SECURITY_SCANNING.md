# CI/CD Security Scanning & Quality Gates

## Overview

The CI/CD pipeline implements comprehensive security scanning, code quality checks, and vulnerability detection across all commits to the `main` branch and pull requests.

## Pipeline Architecture

### Jobs & Duration

| Job | Duration | Purpose | Status |
|-----|----------|---------|--------|
| Secret scanning | 2 min | Detect hardcoded credentials | **BLOCKING** |
| Dependency audit | 3 min | Scan for vulnerable packages | Warning |
| SAST analysis | 3 min | Python code security issues | Warning |
| IaC scanning | 3 min | Terraform configuration review | Warning |
| Linting & types | 5 min | Code style and type safety | **BLOCKING** |
| Unit tests | 5 min | Core logic validation | **BLOCKING** |
| Edge case tests | 5 min | Boundary condition handling | **BLOCKING** |
| Integration tests | 10 min | End-to-end workflows | Optional |

**Total Pipeline Time**: ~20-25 minutes

### Gate Strategy

- **Blocking gates** (fail PR merge):
  - Secret detection (hardcoded credentials)
  - Linting & type checking
  - Unit and edge case tests
  
- **Warning gates** (alert but allow merge):
  - Dependency vulnerabilities
  - SAST findings
  - IaC configuration issues
  - Integration test failures

## Detailed Security Scans

### 1. Secret Scanning

**Tool**: TruffleHog + Custom Patterns  
**Scope**: All git commits  
**Coverage**:
- Verified secrets (API keys, tokens, credentials)
- Hardcoded Alpaca API keys (`APCA_API_KEY_ID`)
- AWS access key IDs (`AKIA*`)
- Custom PostgreSQL credential patterns

**Running Locally**:
```bash
# Install TruffleHog
pip install trufflehog

# Scan recent commits
trufflehog git https://github.com/yourusername/yourrepo.git --only-verified

# Scan filesystem
trufflehog filesystem . --only-verified
```

**Common Findings & Fixes**:
```
❌ Found: APCA_API_KEY_ID = PK...
✅ Fix: Use environment variable or AWS Secrets Manager

❌ Found: .env file with credentials
✅ Fix: Add to .gitignore, use dotenv library
```

### 2. Dependency Vulnerability Scanning

**Tool**: pip-audit  
**Purpose**: Detect known vulnerabilities in Python packages  
**Scope**: All Python dependencies

**Sample Output**:
```
Found 3 known vulnerabilities in 2 packages

┌─────────────────┬──────────┬──────────┬───────────────────┐
│ Package         │ Version  │ Severity │ ID                │
├─────────────────┼──────────┼──────────┼───────────────────┤
│ requests        │ 2.28.0   │ HIGH     │ PYSEC-2023-42     │
│ paramiko        │ 2.11.0   │ MEDIUM   │ PYSEC-2022-1819   │
└─────────────────┴──────────┴──────────┴───────────────────┘
```

**Running Locally**:
```bash
# Install and run pip-audit
pip install pip-audit

# Audit current environment
pip-audit

# Audit specific directory
pip-audit --desc
```

**Remediation**:
```bash
# Update vulnerable package
pip install --upgrade paramiko>=3.0.0

# Pin safe version in requirements.txt
paramiko>=3.0.0,<4.0.0
```

### 3. Static Application Security Testing (SAST)

**Tool**: Bandit  
**Purpose**: Identify Python code security issues  
**Severity Levels**: LOW, MEDIUM, HIGH  
**Confidence**: LOW, MEDIUM, HIGH

**Scanned Directories**:
- `algo/` - Algorithm implementations
- `loaders/` - Data loading scripts
- `config/` - Configuration modules

**Sample Findings**:
```
>> Issue: [B108:hardcoded_temp_file] Probable insecure usage of temp file
   Location: loaders/load_data.py:42
   Code: tmpfile = "/tmp/data.csv"
   
✅ Fix: Use tempfile.NamedTemporaryFile() instead
```

**Running Locally**:
```bash
# Install Bandit
pip install bandit[toml]

# Scan specific directory
bandit -r algo/ --severity-level MEDIUM

# Generate detailed report
bandit -r algo/ -f json > bandit-report.json
```

**Common Issues & Fixes**:

| Issue | Fix |
|-------|-----|
| Hardcoded paths | Use environment variables |
| Exec/eval | Replace with safer alternatives |
| SQL injection | Use parameterized queries (psycopg2 does this) |
| Insecure deserialization | Validate input before pickle |
| Plaintext secrets | Use AWS Secrets Manager |

### 4. Infrastructure as Code (IaC) Scanning

**Tool**: tfsec  
**Purpose**: Identify Terraform security misconfigurations  
**Scope**: `terraform/` directory

**Sample Findings**:
```
Rule: aws-rds-encryption-enabled
Description: Ensure RDS instances are encrypted
Location: terraform/modules/database/main.tf:42
Severity: HIGH
```

**Running Locally**:
```bash
# Install tfsec (binary)
curl -L https://github.com/aquasecurity/tfsec/releases/download/v1.28.4/tfsec-linux-amd64 -o tfsec
chmod +x tfsec

# Scan Terraform
./tfsec terraform/

# Show detailed results
./tfsec terraform/ --format json > tfsec-report.json
```

**Common Issues**:
- Unencrypted RDS databases
- Open security groups (0.0.0.0/0)
- Missing backup configuration
- Unencrypted S3 buckets
- CloudTrail not enabled

## Code Quality Gates

### Linting & Type Checking

**Tools**:
- Black: Code formatting
- isort: Import sorting
- Flake8: Style compliance
- MyPy: Type checking

**Running Locally**:
```bash
# Format code
black algo/ tests/

# Sort imports
isort algo/ tests/

# Check linting
flake8 algo/ tests/ --max-line-length=120

# Type check
mypy algo/ --ignore-missing-imports
```

### Testing

**Unit Tests**: Core logic validation (required)
```bash
pytest tests/unit/ -v
```

**Edge Case Tests**: Boundary conditions (required)
```bash
pytest tests/edge_cases/ -v
```

**Integration Tests**: End-to-end workflows (optional)
```bash
pytest tests/integration/ -v -m "not db"
```

## Interpreting CI Results

### ✅ All Checks Passed
```
✅ Secret scan passed
✅ Dependency scan passed
✅ SAST analysis passed
✅ IaC scan passed
✅ Linting and type checks passed
✅ Unit tests passed
✅ Edge case tests passed
✅ All required gates passed — ready to merge
```

### ⚠️ Warnings (Non-Blocking)
```
❌ Secret scan FAILED — credentials detected
```
**Action**: Fix hardcoded credentials before merge

```
⚠️ Dependency scan had warnings (review recommended)
```
**Action**: Update vulnerable packages, re-run tests

```
⚠️ SAST analysis had findings (review recommended)
```
**Action**: Review flagged code, apply fixes

## Running Checks Locally

### Pre-Commit Validation

Run these before pushing:
```bash
#!/bin/bash
set -e

echo "🔍 Running pre-commit checks..."

# Formatting
echo "📝 Formatting code..."
black algo/ tests/ --quiet
isort algo/ tests/ --quiet

# Linting
echo "🔎 Linting..."
flake8 algo/ tests/ --max-line-length=120 --quiet

# Type checking
echo "✓ Type checking..."
mypy algo/ --ignore-missing-imports --quiet

# Security
echo "🔐 Scanning for secrets..."
trufflehog filesystem . --only-verified

# Tests
echo "🧪 Running unit tests..."
pytest tests/unit/ -q

echo "✅ All pre-commit checks passed!"
```

### Full Pipeline Locally

```bash
# Install all tools
pip install black isort flake8 mypy pytest bandit pip-audit

# Run all checks
bash ./scripts/pre-commit-checks.sh
```

## Debugging CI Failures

### Secret Detection Failed
```
❌ Hardcoded credentials detected in new commit

Check git diff for:
  - APCA_API_KEY_ID = PK...
  - AKIA[0-9A-Z]{16} patterns
  - .env files with secrets

Fix:
  git reset --soft HEAD~1
  # Remove secrets from files
  git add .
  git commit
```

### Dependency Vulnerabilities
```
⚠️ pip-audit found vulnerabilities

Run locally:
  pip-audit --desc

Update:
  pip install --upgrade <package_name>
  
Update requirements.txt:
  <package_name>==<new_version>
```

### Test Failures
```
❌ Unit tests FAILED

Run locally:
  pytest tests/unit/ -v --tb=short

Fix and re-run:
  # Make code changes
  pytest tests/unit/<specific_test.py> -v
```

## Best Practices

1. **Run checks locally before pushing**
   - Use pre-commit hooks to automate
   - Test against Python 3.11 (CI version)

2. **Keep dependencies up-to-date**
   - Run `pip-audit` regularly
   - Update vulnerable packages quickly
   - Use dependency pinning for stability

3. **Address SAST findings**
   - Review Bandit output
   - Understand the risk
   - Apply proper fixes (not just ignoring)

4. **Use environment variables for secrets**
   - Never commit credentials
   - Use AWS Secrets Manager for production
   - Use .env (git-ignored) for local dev

5. **Write tests first**
   - Test edge cases
   - Test error conditions
   - Aim for >80% coverage

## Integration with IDEs

### VS Code
```json
{
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": true,
  "python.formatting.provider": "black",
  "python.linting.banditEnabled": true,
  "[python]": {
    "editor.defaultFormatter": "ms-python.python",
    "editor.formatOnSave": true
  }
}
```

### PyCharm
- **Inspections** → Enable Bandit, mypy
- **Code Style** → Use Black formatter
- **Run Tests** → Configure pytest

## Performance & Costs

### GitHub Actions Free Tier
- **Free minutes**: 2,000/month
- **Pipeline cost**: ~25 min per run
- **Monthly budget**: ~80 runs before charges

### Optimization Tips
1. Use `continue-on-error: true` for non-blocking scans
2. Cache pip dependencies
3. Skip integration tests for documentation-only PRs
4. Use matrix strategy for parallel test execution

## Troubleshooting

### Why is my PR blocked?
Check the job that failed:
1. Click on the failed job in GitHub
2. Scroll to see error details
3. Run the same check locally
4. Fix the issue
5. Push to update PR

### Why are warnings ignored?
Non-blocking warnings (SAST, dependencies) allow merge for urgency:
- Review the findings
- Address in follow-up PRs if minor
- Fix immediately if critical

### How to skip a scan?
Don't. But for exceptional cases:
```yaml
# In workflow file (not recommended)
continue-on-error: true  # Allows failure
```

## Related Docs

- [Database Backup Strategy](./DATABASE_BACKUP_STRATEGY.md)
- [Architecture Design](../ARCHITECTURE.md)
- [Contributing Guidelines](../CONTRIBUTING.md)

## Support & Escalation

**For CI/CD issues**:
1. Check GitHub Actions tab for full logs
2. Run checks locally to reproduce
3. Review this documentation
4. Open an issue with:
   - Workflow name and run ID
   - Exact error message
   - Steps to reproduce locally
