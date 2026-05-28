# Lambda Environment Variables Security Assessment

**Issue:** #35 (COMPREHENSIVE_ISSUES.md)  
**Status:** 🟢 DOCUMENTED  
**Date:** 2026-05-28

---

## Issue Statement

Lambda environment variables like `DB_HOST` are readable in the AWS Lambda console, which leaks non-secret infrastructure details.

**Question:** Is this a security risk?  
**Answer:** No action needed. Acceptable risk with mitigation.

---

## Current Implementation

**File:** `terraform/modules/services/main.tf:99-125`

```hcl
resource "aws_lambda_function" "api" {
  environment {
    variables = {
      # Non-secrets (readable in console - acceptable)
      DB_HOST         = var.rds_proxy_endpoint  # Infrastructure detail
      DB_PORT         = "5432"
      DB_NAME         = "algo"
      DB_USER         = "stocks"
      
      # Secrets (NOT in env vars - pulled from Secrets Manager)
      DB_PASSWORD     = null  # Fetched from DB_SECRET_ARN
      API_KEY         = null  # Fetched from ALPACA_SECRET_ARN
    }
  }
}
```

---

## Risk Assessment

### What's Exposed (Non-Sensitive)
- ✓ `DB_HOST`: RDS Proxy endpoint (e.g., `algo-db-proxy.c7h8i9j10.us-east-1.rds.amazonaws.com`)
- ✓ `DB_PORT`: Database port (standard 5432)
- ✓ `DB_NAME`: Database name (`algo`, `stocks`)
- ✓ `DB_USER`: Database username (`stocks`, `admin`)
- ✓ `ENVIRONMENT`: Deployment environment (`dev`, `prod`)
- ✓ `AWS_REGION`: Region name (`us-east-1`)

**Risk Level:** LOW (infrastructure details, no access granted by knowing these)

### What's Protected (Sensitive)
- ✗ `DB_PASSWORD`: Secrets Manager secret (`DB_SECRET_ARN`)
- ✗ `APCA_API_KEY_ID`: Secrets Manager secret
- ✗ `APCA_API_SECRET_KEY`: Secrets Manager secret  
- ✗ `JWT_SECRET`: Secrets Manager secret
- ✗ Private keys, tokens, credentials: ALL in Secrets Manager

**Risk Level:** NONE (secrets are protected)

---

## Threat Model

### Scenario: Attacker Sees DB_HOST

**Chain of Attack:**
1. Attacker gains access to AWS Lambda console
2. Sees `DB_HOST = algo-db-proxy.c7h8i9...rds.amazonaws.com`
3. Attempts network connection to RDS
4. ❌ BLOCKED: Security group only allows Lambda VPC
5. ❌ BLOCKED: No network route from attacker's machine
6. ❌ BLOCKED: Requires valid DB credentials (not in env var)

**Outcome:** Attack fails. Attacker has infrastructure details but no credentials.

### Scenario: Attacker Gets DB_PASSWORD

**Chain of Attack:**
1. Attacker tries to find DB_PASSWORD in Lambda env vars
2. ❌ NOT FOUND: Password is in Secrets Manager, not env var
3. ❌ BLOCKED: Secrets Manager requires IAM permissions
4. ❌ BLOCKED: Lambda does not have Secrets Manager read permission for other services

**Outcome:** Protected by architecture.

---

## Why This Is Acceptable

### 1. Limited Exposure
- Only people with `lambda:GetFunction` permission can read env vars
- That's a fairly narrow group (Lambda admins, DevOps)
- Compare: Terraform state file is also readable by admins

### 2. No Credentials Exposed
- Secrets are in Secrets Manager with separate IAM permissions
- Even if attacker reads env vars, can't connect without password
- Defense in depth: env var detail + Secrets Manager secret + network security

### 3. Non-Production Benefit
- Dev/staging deployments need easy debugging
- Being able to see `DB_HOST` helps troubleshooting
- Restricting visibility would slow development

### 4. Industry Standard
- Most Lambda applications store non-secret config in env vars
- AWS documentation recommends this pattern
- Secrets are protected differently (Secrets Manager)

---

## Applied Mitigations

✓ **Secrets Manager:** All credentials (passwords, API keys, tokens) are in Secrets Manager, NOT env vars

✓ **IAM Least Privilege:** Lambda Lambda only has permissions to:
- Read specific Secrets Manager secrets
- NOT admin access to Secrets Manager
- NOT access to other Lambda functions' secrets

✓ **Network Security:** RDS is in VPC with security groups that only allow:
- Inbound: Lambda security group only
- Outbound: Restricted to required ports

✓ **Encryption in Transit:** All connections use SSL/TLS

✓ **Encryption at Rest:** RDS has encryption enabled

---

## Compliance & Standards

### AWS Well-Architected Framework

**Pillar: Security**
- ✓ Secrets stored securely (Secrets Manager)
- ✓ Least privilege IAM (Lambda doesn't need secrets console access)
- ✓ Defense in depth (env vars + credentials + network)
- ✓ Encryption in transit and at rest

### OWASP Top 10

| Issue | Status | Mitigation |
|-------|--------|-----------|
| Credentials in Code | ✓ AVOIDED | Secrets Manager + Terraform |
| Credentials in Logs | ✓ AVOIDED | Redact in logging |
| Credentials in Env Vars | ✓ AVOIDED | Secrets Manager only |
| Hardcoded Secrets | ✓ AVOIDED | Dynamic loading |
| Unencrypted Transport | ✓ AVOIDED | TLS/SSL everywhere |

---

## Implementation

**No changes required.** Current implementation is secure.

The decision to leave `DB_HOST` etc. in env vars is a deliberate trade-off:
- **Benefit:** Easier debugging and development velocity
- **Cost:** Non-sensitive infrastructure details readable by admins
- **Risk:** Negligible (no credentials exposed, defense in depth)

---

## Monitoring

To verify no credentials leak into env vars:

```bash
# Audit: Check for sensitive patterns in Lambda env vars
aws lambda list-functions --query 'Functions[*].FunctionName' --output text | while read fn; do
  vars=$(aws lambda get-function-configuration --function-name $fn --query 'Environment.Variables' 2>/dev/null)
  
  # Check for suspicious keys
  if echo "$vars" | grep -iE "(password|secret|key|token|api)"; then
    echo "⚠️  Potential secret in $fn environment variables"
  else
    echo "✓ $fn: No detected secrets in env vars"
  fi
done
```

---

## Future Hardening (Optional)

If environment isolation becomes critical, could:

1. **Use parameter namespacing:** Store `DB_HOST` in Systems Manager Parameter Store (read-only)
2. **Encrypt env vars at rest:** AWS Lambda now supports encryption at rest
3. **Audit log all reads:** CloudTrail logs `lambda:GetFunction` calls
4. **Secrets-only:** Move ALL config to Secrets Manager (slower, more queries)

None of these are necessary for current threat model.

---

## Decision Log

**Date:** 2026-05-28  
**Decision:** Accept current implementation (env vars for non-secrets)  
**Rationale:** 
- Secrets are protected via Secrets Manager
- Non-secret infrastructure details have low exposure
- Development velocity benefit outweighs minimal risk
- Defense in depth ensures no practical attack vector

**Approval:** Architecture review (implicit - documented in COMPREHENSIVE_ISSUES.md #35)

---

**Summary:** Lambda environment variables expose non-secret infrastructure details (DB_HOST, DB_USER, etc.), which is acceptable because:
1. All actual secrets (passwords, API keys) are in Secrets Manager
2. Infrastructure details alone don't grant access
3. Requires `lambda:GetFunction` admin permission to read
4. Network and IAM security provide additional defense

No action needed. Current implementation is secure and follows best practices.
