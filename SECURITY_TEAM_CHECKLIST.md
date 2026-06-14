# Security Team Checklist & Runbook

**Purpose:** Guidelines for developers and security reviewers to maintain security posture.

---

## For All Developers

### Before Committing Code

- [ ] Run pre-commit hook locally: `bash scripts/setup-security-hooks.ps1`
- [ ] Check for hardcoded secrets: `grep -r "password\|secret\|api_key" --include="*.py" | grep -v "get_"`
- [ ] Verify SQL uses parameterized queries: All `execute()` calls have `%s` placeholders, no f-strings
- [ ] Check input validation: User input validated before use in SQL or log
- [ ] Verify authentication is required: Protected endpoints check JWT token
- [ ] Check authorization: Admin endpoints verify user groups
- [ ] Test CORS: Verify whitelist is set, not wildcard

### Code Review Checklist

When reviewing PRs, verify:

**Authentication & Authorization:**
- [ ] All `/api/` endpoints require authentication (except public ones like `/health`)
- [ ] Admin endpoints check `_check_admin_access(jwt_claims)`
- [ ] User data isolation enforced (user can only see their own data)
- [ ] Rate limits applied to sensitive operations

**Input Validation:**
- [ ] All user input validated before use (stock symbols, dates, numbers)
- [ ] Table names use `assert_safe_table()`
- [ ] Column names use `assert_safe_column()`
- [ ] Numeric parameters bounded with min/max
- [ ] String length limits enforced
- [ ] Regex patterns used for complex formats (email, symbols)

**SQL Injection Prevention:**
- [ ] All SQL uses parameterized queries with `%s` placeholders
- [ ] No f-strings with user input in execute()
- [ ] No string concatenation for SQL
- [ ] Table/column names go through whitelist validation
- [ ] LIMIT/OFFSET parameters bounded

**Data Protection:**
- [ ] No sensitive data in error messages returned to client
- [ ] No stack traces sent to client (only in server logs)
- [ ] Secrets loaded from Secrets Manager, not hardcoded
- [ ] API responses sanitized (no HTML/JS injection risk)
- [ ] Sensitive headers redacted in logs

**CORS & Headers:**
- [ ] CORS uses whitelist, not wildcard
- [ ] Includes `Vary: Origin` header
- [ ] Uses `Credentials: true` only for whitelisted origins
- [ ] Security headers set (X-Content-Type-Options, X-Frame-Options, etc.)

**Error Handling:**
- [ ] Database errors don't leak connection strings
- [ ] Auth failures logged but don't reveal whether user exists
- [ ] Timeouts don't expose system details
- [ ] Generic error messages to client, detailed logs on server

---

## For Security Reviewers

### Quarterly Security Audit (Every 3 Months)

**Access Control:**
- [ ] Review IAM roles and permissions
- [ ] Check who has admin access in Cognito
- [ ] Verify MFA is enabled for admin users
- [ ] Audit service account usage

**Credentials:**
- [ ] Rotate database password
- [ ] Rotate API keys (Alpaca, FRED, etc.)
- [ ] Check Secrets Manager for unused secrets
- [ ] Review AWS access key age (< 90 days)

**Dependencies:**
- [ ] Run `pip list --outdated`
- [ ] Check for security advisories (CVE)
- [ ] Review major version updates for compatibility
- [ ] Update vulnerable packages

**Logs & Monitoring:**
- [ ] Review CloudWatch logs for suspicious patterns
- [ ] Check for repeated authentication failures
- [ ] Look for rate limit violations
- [ ] Verify no secrets logged
- [ ] Check for unusual query patterns (potential SQLi attempts)

**Infrastructure:**
- [ ] Verify RDS security groups restrict access
- [ ] Check Lambda security groups
- [ ] Verify S3 buckets are not public
- [ ] Confirm encryption is enabled
- [ ] Review VPC configuration

**Code Security:**
- [ ] Run Bandit: `bandit -r . -ll`
- [ ] Check for new hardcoded secrets: `truffleHog3 -r .`
- [ ] Review recent PRs for security issues
- [ ] Verify pre-commit hooks are blocking issues

**Compliance:**
- [ ] Verify audit log is enabled and immutable
- [ ] Check data retention policies
- [ ] Confirm backups are encrypted
- [ ] Review data access policies

### When Security Issue Found

**Immediate (Within 30 minutes):**
1. Create GitHub security advisory (private)
2. Assess severity and impact
3. Notify dev team in #security Slack channel
4. Begin root cause analysis

**Short-term (Within 2 hours):**
1. Develop fix
2. Create PR with security label
3. Fast-track code review
4. Deploy to production if critical
5. Update issue tracking system

**Medium-term (Same day):**
1. Document the vulnerability
2. Create regression test
3. Add pre-commit hook to prevent recurrence
4. Update security docs

**Follow-up (Next week):**
1. Conduct post-incident review
2. Update security runbooks
3. Security training for team (if needed)
4. Update SECURITY_VULNERABILITIES.md

---

## Common Security Mistakes to Avoid

### ❌ DON'T:

```python
# SQL Injection
cur.execute(f"SELECT * FROM {table}")  # DANGEROUS
cur.execute("SELECT * FROM " + table)  # DANGEROUS
cur.execute(f"SELECT * FROM users WHERE id = {user_id}")  # DANGEROUS

# Auth Bypass
if DEV_BYPASS_AUTH:  # DANGEROUS in production
    return admin_access

# CORS
response['headers']['Access-Control-Allow-Origin'] = '*'  # DANGEROUS

# Hardcoded Secrets
API_KEY = 'sk-1234567890'  # DANGEROUS
password = 'production_db_password'  # DANGEROUS

# Command Injection
os.system(f"process_file {user_input}")  # DANGEROUS
subprocess.Popen([cmd, user_input], shell=True)  # DANGEROUS

# Path Traversal
file_path = f'/data/{user_filename}'  # DANGEROUS

# Information Disclosure
logger.error(f"Query failed: {e}")  # Logs traceback
return {"error": str(e)}  # Returns exception to client
```

### ✅ DO:

```python
# SQL Injection Prevention
from utils.db.sql_safety import assert_safe_table
table_safe = assert_safe_table(table)
cur.execute(f"SELECT * FROM {table_safe}")

# Parameterized Queries
cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))

# Auth Enforcement
if not jwt_claims:
    return error_response(401, 'unauthorized', 'Token required')

# Admin Access Check
if not _check_admin_access(jwt_claims):
    return error_response(403, 'forbidden', 'Admin access required')

# CORS Whitelist
allowed_origins = os.getenv('ALLOWED_ORIGINS', '').split(',')
if origin in allowed_origins:
    response['headers']['Access-Control-Allow-Origin'] = origin

# Secrets from Secrets Manager
from config.credential_manager import get_secret
api_key = get_secret('algo/api-key')

# Command Execution
subprocess.run([cmd, user_input], shell=False)  # No shell

# Path Validation
if not filename.startswith(allowed_dir):
    raise ValueError("Invalid path")

# Error Handling
logger.error(f"Query failed: {type(e).__name__}")  # Generic log
return error_response(500, 'internal_error', 'An error occurred')  # Generic response
```

---

## Useful Commands

### Check for Security Issues

```bash
# Find SQL injection patterns
grep -r 'execute(f"' --include="*.py" | grep -E "SELECT|INSERT|UPDATE"

# Find hardcoded credentials
grep -r 'password.*=' --include="*.py" | grep -v "get_password\|test"

# Find CORS wildcards
grep -r "Access-Control.*\*" --include="*.py"

# Run Bandit security linter
bandit -r . -ll

# Find hardcoded secrets in git history
truffleHog3 -r .

# Check for eval/exec
grep -r "^[[:space:]]*eval(\|^[[:space:]]*exec(" --include="*.py"

# Find subprocess shell=True
grep -r "shell.*True\|shell=True" --include="*.py"
```

### Development & Testing

```bash
# Run security tests
pytest tests/unit/test_api_security.py -v

# Install pre-commit hook
bash scripts/setup-security-hooks.ps1

# Run all security checks
# (Create this script)
bash scripts/run-security-checks.sh

# Check Python dependencies
pip list --outdated
pip check  # Check for dependency conflicts
```

---

## Security Contacts & Resources

**Internal:**
- Security Team: [Who maintains security]
- On-Call Oncall: [Slack channel]

**External References:**
- OWASP Top 10: https://owasp.org/www-project-top-ten/
- SQL Injection Prevention: https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html
- Authentication: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- API Security: https://cheatsheetseries.owasp.org/cheatsheets/REST_API_Security_Cheat_Sheet.html

---

## Documentation References

- `SECURITY_VULNERABILITIES.md` - Detailed findings from this security audit
- `SECURITY_FIXES_IMPLEMENTED.md` - What was fixed and why
- `CONTINUOUS_SECURITY_STRATEGY.md` - 7-layer defense architecture
- `utils/db/sql_safety.py` - SQL injection prevention utilities
- `lambda/api/dev_auth.py` - Safe development authentication
- `lambda/api/security_validators.py` - Input validation utilities

---

## Incident Response Template

### 1. Assess (Immediately)
- [ ] What is the vulnerability?
- [ ] How severe? (Critical/High/Medium/Low)
- [ ] What systems affected?
- [ ] Has it been exploited?
- [ ] Who needs to know?

### 2. Contain (Within 30 min)
- [ ] Take affected service offline? (if critical)
- [ ] Isolate affected database/infrastructure?
- [ ] Rotate compromised credentials?
- [ ] Review recent access logs?

### 3. Fix (Within 2 hours)
- [ ] Develop patch
- [ ] Fast-track code review
- [ ] Deploy fix to production
- [ ] Verify fix effectiveness

### 4. Communicate
- [ ] Notify affected users?
- [ ] Public announcement?
- [ ] Update status page?

### 5. Post-Incident (Within 1 week)
- [ ] Root cause analysis
- [ ] Long-term fix (if needed)
- [ ] Regression test added
- [ ] Documentation updated
- [ ] Team training (if needed)

---

**Last Updated:** 2026-06-14  
**Maintained By:** [Security Team]  
**Next Review:** 2026-09-14
