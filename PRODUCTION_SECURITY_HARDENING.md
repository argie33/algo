# Production Security Hardening Checklist

**Status:** 🔴 IN PROGRESS  
**Last Updated:** 2026-05-08  
**Current Environment:** Paper trading (no real money risk)  
**Target:** Production-ready security posture for live trading deployment

---

## Critical Issues (Fix Before Live Trading)

### 1. RDS Database Access ⚠️ HIGH
**Current:** RDS publicly accessible (0.0.0.0/0)  
**Risk:** Anyone with network access can attempt DB credentials  
**Fix:**

```bash
# 1. Create VPC endpoint for private access
# 2. Remove public accessibility from RDS
aws rds modify-db-instance \
  --db-instance-identifier stocks-data-rds \
  --publicly-accessible false \
  --apply-immediately

# 3. Create bastion host for admin access
# Template: template-bastion-security.yml (create separate)

# 4. Update security group to allow access ONLY from within VPC
# FROM: 0.0.0.0/0
# TO: 10.0.0.0/8 (VPC CIDR only)
```

**Effort:** 2 hours  
**Impact:** High - blocks major vulnerability

---

### 2. Encryption in Transit ⚠️ MEDIUM
**Current:** API → RDS over unencrypted connections  
**Risk:** Credentials/data visible on network  
**Fix:**

```bash
# 1. Enable SSL for RDS connections
aws rds modify-db-instance \
  --db-instance-identifier stocks-data-rds \
  --enable-cloudwatch-logs-exports postgresql \
  --apply-immediately

# 2. Force SSL in database connection strings
DB_SSLMODE=require  # Add to .env

# 3. Enable HTTPS on API Gateway (already done via CloudFront)

# 4. Enforce HSTS header on API responses
X-Forwarded-Proto: https
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

**Effort:** 1 hour  
**Impact:** Medium - protects credential transmission

---

### 3. API Gateway Protection ⚠️ MEDIUM
**Current:** No WAF, no rate limiting, no IP filtering  
**Risk:** DDoS attacks, credential brute-forcing, injection attacks  
**Fix:**

```yaml
# Create AWS WAF ACL
AWSWAFv2:
  RulesGroups:
    - RateLimitRule: 2000 requests/5 min per IP
    - AWSManagedSQLiRule: Block SQL injection
    - AWSManagedXSSRule: Block XSS payloads
    - GeoBlockingRule: Allow only US traffic (optional)
    - IPReputationRule: Block known bad IPs

# Attach to API Gateway
aws wafv2 associate-web-acl \
  --web-acl-arn arn:aws:wafv2:... \
  --resource-arn arn:aws:apigateway:...
```

**Effort:** 3 hours  
**Impact:** High - prevents attacks

---

### 4. Secrets Management ⚠️ HIGH
**Current:** Credentials in environment variables  
**Risk:** Accidental exposure in logs, container images, Git  
**Fix:**

```bash
# 1. Rotate all secrets NOW
# Alpaca keys, DB password, JWT secret

# 2. Store ALL secrets in AWS Secrets Manager
aws secretsmanager create-secret \
  --name stocks/prod/db-password \
  --secret-string '{"password":"..."}'

# 3. Enable automatic rotation (every 30 days)
aws secretsmanager rotate-secret \
  --secret-id stocks/prod/db-password \
  --rotation-lambda-arn arn:...

# 4. Remove from .env - use Lambda environment variables
# Lambda pulls from Secrets Manager at runtime

# 5. Audit secret access
aws cloudtrail start-logging --trail-name ...
```

**Effort:** 4 hours  
**Impact:** Critical - prevents credential leakage

---

## Important Issues (Fix Before 1st Real Trade)

### 5. Audit Logging ⚠️ MEDIUM
**Current:** No comprehensive audit trail  
**Risk:** Can't track who did what when something goes wrong  
**Fix:**

```bash
# Enable CloudTrail for all AWS API calls
aws cloudtrail create-trail \
  --name stocks-audit-trail \
  --s3-bucket-name stocks-audit-logs

# Enable VPC Flow Logs for network monitoring
aws ec2 create-flow-logs \
  --resource-type VPC \
  --resource-ids vpc-... \
  --traffic-type ALL \
  --log-destination-type cloud-watch-logs

# Enable RDS Enhanced Monitoring
aws rds modify-db-instance \
  --db-instance-identifier stocks-data-rds \
  --enable-cloudwatch-logs-exports postgresql \
  --monitoring-interval 60

# Enable API Gateway logging
aws logs create-log-group \
  --log-group-name /aws/apigateway/stocks-api
```

**Effort:** 2 hours  
**Impact:** Medium - required for compliance/debugging

---

### 6. Backup & Disaster Recovery ⚠️ MEDIUM
**Current:** 7-day RDS backups (good)  
**Risk:** Data loss if primary region fails  
**Fix:**

```bash
# 1. Enable cross-region replication
aws rds create-db-instance-read-replica \
  --db-instance-identifier stocks-data-rds-replica \
  --source-db-instance-identifier stocks-data-rds \
  --availability-zone us-west-2a

# 2. Test backup restoration monthly
# Script: backup-restore-test.sh

# 3. Extend retention to 30 days (costs ~$2/day)
aws rds modify-db-instance \
  --db-instance-identifier stocks-data-rds \
  --backup-retention-period 30

# 4. Store RDS snapshots in different account (AWS DataProtection best practice)
aws rds copy-db-snapshot \
  --source-db-snapshot-identifier arn:... \
  --target-db-snapshot-identifier backup-20260508 \
  --source-region us-east-1
```

**Effort:** 3 hours  
**Impact:** Medium - protects against data loss

---

### 7. Network Segmentation ⚠️ LOW-MEDIUM
**Current:** All resources in one VPC, security groups allow broad access  
**Risk:** Lateral movement if one service is compromised  
**Fix:**

```bash
# Create separate security groups for each service tier
# Web/API tier:
aws ec2 create-security-group \
  --group-name stocks-api-sg \
  --ingress: Allow 443 from CloudFront only
  --engress: Allow 5432 to DB-SG only

# Database tier:
aws ec2 create-security-group \
  --group-name stocks-db-sg \
  --ingress: Allow 5432 from API-SG only
  --engress: None (DB doesn't initiate outbound)

# Lambda tier:
aws ec2 create-security-group \
  --group-name stocks-lambda-sg \
  --ingress: None
  --engress: Allow 443 to Alpaca API, 5432 to DB
```

**Effort:** 2 hours  
**Impact:** Low - defense in depth

---

## Compliance & Monitoring

### 8. Compliance Audit
- [ ] GDPR: No PII collection (except email)
- [ ] SOC 2: Audit logging enabled
- [ ] Access Control: RBAC working (JWT + role-based endpoints)
- [ ] Data Retention: Clear policies on old data
- [ ] Incident Response: Plan documented

### 9. Monitoring & Alerting
- [ ] CloudWatch alarms for failed logins
- [ ] CloudWatch alarms for DB connection errors
- [ ] CloudWatch alarms for Lambda errors >1%
- [ ] SNS topic for security alerts
- [ ] Weekly security report to email

---

## Implementation Roadmap

### Phase 1: Pre-Live Trading (Week 1)
1. **Day 1:** Fix RDS public access + rotate secrets
2. **Day 2:** Enable WAF on API Gateway
3. **Day 3:** Set up audit logging & CloudTrail
4. **Day 4:** Test backup restoration

### Phase 2: During Paper Trading (Ongoing)
1. Enable cross-region RDS replica
2. Implement automated secrets rotation
3. Set up comprehensive monitoring
4. Monthly security audit

### Phase 3: Before Live Trading (Week 3)
1. Penetration testing (internal)
2. Security code review
3. Deployment checklist signoff
4. Incident response plan validation

---

## Estimated Costs

| Item | Monthly Cost | Notes |
|------|-------------|-------|
| RDS backup retention (30 days) | $2 | From $0 |
| RDS read replica (us-west-2) | $35 | DR/failover |
| WAF (Basic) | $5 | DDoS protection |
| CloudTrail logs (S3) | $2 | Audit trail |
| VPC Flow Logs (CloudWatch) | $3 | Network monitoring |
| Secrets Manager (manual rotation) | $1 | Secret storage |
| **Total additional** | **$48** | **~5% cost increase** |

---

## Success Criteria

✅ All critical issues fixed  
✅ All security tests passing  
✅ Audit log trail continuous (no gaps)  
✅ Incident response plan tested  
✅ Backup restoration tested monthly  
✅ Zero successful intrusion attempts in monitoring

---

## Next Steps

1. **Priority 1 (This week):** RDS access + secrets management
2. **Priority 2 (This week):** WAF + audit logging
3. **Priority 3 (Next week):** DR + monitoring
4. **Priority 4 (Ongoing):** Compliance audit + penetration testing

---

**Owner:** Security Lead  
**Review Date:** 2026-05-15  
**Sign-off:** [Pending]
