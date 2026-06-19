# Security Policy & Scanning

This document describes the multi-layered security scanning strategy for the algo trading system.

## Overview

Security scanning is implemented at three layers:

1. **Pre-commit (local developer machine)** — Fast checks to catch obvious issues before pushing
2. **CI/CD (GitHub Actions) — Comprehensive automated scanning on every commit/PR
3. **Operational (AWS)** — Runtime security via IAM, WAF, monitoring

## Layer 1: Pre-commit Scanning (Local)

Runs on developer machines before commits are pushed.

| Check | Tool | Purpose | Blocking |
|-------|------|---------|----------|
| Code formatting | ruff | Enforce consistent style | ❌ Warning only |
| Linting | ruff | Catch common errors (unused vars, shadowing, etc.) | ✅ Blocks commit |
| Type checking | mypy | Detect type mismatches | ✅ Blocks commit |
| Import validation | Python | Detect syntax/NameErrors | ✅ Blocks commit |
| Session docs | Git hook | Prevent committing temporary status files | ✅ Blocks commit |
| .env files | Git hook | Prevent committing credentials | ✅ Blocks commit |
| Large files | Git hook | Prevent committing binaries/dumps | ✅ Blocks commit |
| Debug code | Git hook | Prevent committing pdb/breakpoint() | ✅ Blocks commit |

**Configuration:** `.git/hooks/pre-commit` (bash script)

## Layer 2: CI/CD Automated Scanning (GitHub Actions)

Runs on every commit to main / every PR. See `.github/workflows/ci-fast-gates.yml`.

### 2a. Secrets Detection

**Tools:** TruffleHog + pattern matching  
**Purpose:** Catch hardcoded API keys, tokens, credentials  
**Blocking:** ✅ Required — fails the entire CI pipeline  

Detects:
- Known secret patterns (AWS keys, API tokens, JWTs, etc.)
- Generic API key assignments: `APCA_API_KEY_ID=`, `AKIA...`, etc.

### 2b. Dependency Scanning

**Tool:** pip-audit  
**Purpose:** Detect vulnerable dependencies (CVEs in installed packages)  
**Blocking:** ✅ Required — fails pipeline  

Scans `requirements.txt` for:
- Known CVEs in direct dependencies
- Transitive dependency vulnerabilities
- Updates available for critical packages

**Known Issues:** See `SECURITY-VULNERABILITIES.md`

### 2c. Static Code Analysis (SAST)

**Tool:** Bandit  
**Purpose:** Detect security anti-patterns (hardcoded secrets, SQL injection, etc.)  
**Blocking:** ✅ Required — fails pipeline on HIGH-confidence findings  

Configuration: `.bandit` file

**Important:** Bandit reports medium-confidence SQL injection warnings (B608) in this codebase, but these are false positives:
- All user-facing values use parameterized queries (`%s` placeholders)
- Table names come from system config, never user input
- Safe pattern: `cur.execute("SELECT * FROM {} WHERE col = %s".format(table_name), (param,))`

### 2d. Terraform IaC Scanning

**Tools:** tfsec (security), terraform validate (syntax)  
**Purpose:** Detect overpermissive IAM, exposed secrets, misconfiguration  
**Blocking:** ✅ Required for CRITICAL severity issues  

### 2e. Code Quality & Type Checking

**Tools:** mypy, Black, isort, flake8  
**Purpose:** Type safety, consistent formatting, import ordering  
**Blocking:** ✅ Required — type errors and import failures fail pipeline  

### 2f. Unit & Integration Tests

**Purpose:** Functional correctness  
**Blocking:** ✅ Required for critical tests, warnings-only for integration tests  

## Layer 3: Operational Security (AWS)

- **WAF:** API Gateway has 10,000 RPS global rate limit
- **Network:** VPC with private database, no direct internet access
- **IAM:** Principle of least privilege, no hard-coded credentials (use Secrets Manager + OIDC)
- **Monitoring:** CloudWatch logs, EventBridge auditing, alerts on errors
- **Secrets rotation:** Quarterly credential rotation (first Monday of quarter)

---

## Known Vulnerabilities & Exceptions

See `SECURITY-VULNERABILITIES.md` for tracked, analyzed vulnerabilities.

Summary:
- **aiohttp 3.13.5** (11 CVEs) — Transitive via Twilio
- **pyjwt 2.12.1** (8 CVEs) — Transitive via Twilio
- **pip 24.0** (5 vulnerabilities) — Transitive
- **setuptools 65.5.0** (4 vulnerabilities) — Transitive

**Action:** SMS alerts (Twilio-based) are optional. Prioritize webhooks for alerts. Plan future refactor to remove Twilio or update when vulnerabilities are patched upstream.

---

## Adding New Security Checks

When adding a new security tool (e.g., new linter, DAST tool, code scanner):

1. **Verify it's needed** — Does it add value over existing tools?
2. **Add to CI/CD first** — Run in `.github/workflows/ci-fast-gates.yml`
3. **Add to pre-commit if fast** — Only if scan time < 2 seconds
4. **Document here** — Explain purpose and blocking behavior
5. **Configure to reduce false positives** — Tune thresholds, add skips/ignores as needed

---

## Reporting Security Issues

**DO NOT** open public GitHub issues for security vulnerabilities.

Instead: Email security@example.com with:
- Description of the issue
- Affected component
- Suggested fix (if known)
- Your contact information

---

## Quarterly Compliance Checklist

First Monday of each quarter:
- [ ] Run `pip-audit --desc` locally and review any new CVEs
- [ ] Check if vulnerability fixes are available for transitive deps
- [ ] Rotate AWS credentials (see `steering/algo.md`)
- [ ] Review and update `.secrets.baseline` if patterns change
- [ ] Scan Terraform for new tfsec violations
- [ ] Update this document if tools/thresholds change
