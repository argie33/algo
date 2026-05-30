# Production Deployment Checklist

Complete this checklist before deploying to production on Monday (2026-05-31).

## Alert System Configuration ✅ (NEW)

- [ ] **SMTP Credentials Ready**
  - [ ] Gmail account with 2FA enabled
  - [ ] App-specific password generated at myaccount.google.com/apppasswords
  - [ ] Password verified locally: can send test email

- [ ] **GitHub Secrets Configured**
  - [ ] `ALERT_SMTP_PASSWORD` secret created with app-specific password
  - [ ] Repository: Settings → Secrets and variables → Actions

- [ ] **Terraform Variables Updated** (terraform/terraform.tfvars)
  - [ ] `alert_email_to = "argeropolos@gmail.com"` (or your email)
  - [ ] `alert_smtp_host = "smtp.gmail.com"`
  - [ ] `alert_smtp_user = "your-email@gmail.com"`
  - [ ] `alert_smtp_from = "your-email@gmail.com"`
  - [ ] `sns_alert_email = "argeropolos@gmail.com"`
  - [ ] `sns_alerts_enabled = true`

- [ ] **Local Testing Completed**
  - [ ] Run: `python -m pytest tests/test_alerts_integration.py -v`
  - [ ] All 8 tests pass
  - [ ] Manual SMTP test successful (received email)

- [ ] **SNS Infrastructure Verified**
  - [ ] SNS topic created: `algo-algo-alerts-dev`
  - [ ] Email subscription active
  - [ ] CloudWatch alarms → SNS properly linked

---

## Terraform & Infrastructure ✅ (EXISTING)

- [ ] **No Terraform Errors**
  - [ ] Run: `terraform validate` in `terraform/` directory
  - [ ] No cycle errors (FIXED: CloudFront ↔ API Gateway)
  - [ ] No missing variable errors

- [ ] **Critical Resources Ready**
  - [ ] RDS database: db.t3.medium (not micro)
  - [ ] RDS Proxy enabled for connection pooling
  - [ ] API Lambda: 50 concurrent executions (not 10)
  - [ ] VPC, subnets, security groups configured

---

## Application Code ✅ (VERIFIED)

- [ ] **Orchestrator**
  - [ ] AlertManager initialized (line 113 in algo_orchestrator.py)
  - [ ] All 7 phases implemented and tested
  - [ ] Phase 1: Data freshness → sends patrol alert on failure

- [ ] **API Lambda**
  - [ ] REST endpoints working
  - [ ] CORS configured for localhost (not CloudFront in API Gateway)
  - [ ] Health check endpoint at `/health` (public, no auth)

- [ ] **Data Loaders**
  - [ ] 40+ loaders scheduled via EventBridge
  - [ ] Failure handler Lambda deployed
  - [ ] LoaderMonitor integrated with AlertManager

- [ ] **Tests**
  - [ ] All 42 existing tests passing
  - [ ] 8 new alert tests passing
  - [ ] No syntax errors in Python code

---

## AWS Deployment Steps

### Step 1: Prepare Credentials
```bash
# Set GitHub secret (one-time)
# Go to: https://github.com/YOUR_ORG/algo/settings/secrets/actions
# Create ALERT_SMTP_PASSWORD with Gmail app-specific password

# Update local terraform.tfvars with your email
export ALERT_EMAIL_TO="argeropolos@gmail.com"
```

### Step 2: Deploy Infrastructure
```bash
cd terraform

# Validate
terraform validate

# Plan
terraform plan -out=tfplan

# Apply (or merge to main for GitHub Actions to deploy)
terraform apply tfplan
```

### Step 3: Verify Deployment
```bash
# Check Lambda environment variables
aws lambda get-function-configuration \
  --function-name algo-algo-dev \
  --region us-east-1 | grep ALERT

# Check SNS topic
aws sns list-topics | grep algo-alerts

# Check CloudWatch alarms
aws cloudwatch describe-alarms \
  --alarm-name-prefix algo-algo-dev
```

### Step 4: Test Alerts End-to-End
```bash
# Invoke orchestrator (dry-run)
aws lambda invoke \
  --function-name algo-algo-dev \
  --region us-east-1 \
  --payload '{"dry_run": true}' \
  response.json

# Check logs
aws logs tail /aws/lambda/algo-algo-dev --follow

# Expected: "Email sent: [ALGO ALERT]..." in logs
```

---

## Verification Checklist

Run these tests locally before deploying:

```bash
# 1. Unit tests
python -m pytest tests/ -v --tb=short

# 2. Alert configuration test
export ALERT_EMAIL_TO="test@example.com"
export ALERT_SMTP_HOST="smtp.gmail.com"
export ALERT_SMTP_USER="test@example.com"
export ALERT_SMTP_PASSWORD="app-specific-password"
python tests/test_alerts_integration.py

# 3. Code quality
python -m flake8 algo/ --max-line-length=120 --exclude __pycache__

# 4. Orchestrator import
python -c "from algo.algo_orchestrator import Orchestrator; print('✅ Orchestrator imports OK')"
```

---

## Rollback Plan

If alerts fail in production:

1. **Stop Alerts Immediately** (no downtime to trading)
   ```bash
   # Set empty values in terraform.tfvars
   alert_email_to = ""
   alert_webhook_url = ""
   
   # Run: terraform apply
   ```

2. **Lambda Continues Working**
   - Trading logic unaffected
   - Orchestrator runs normally
   - Just no email/webhook notifications

3. **Debug**
   - Check CloudWatch logs: `/aws/lambda/algo-algo-dev`
   - Verify SMTP credentials: `aws lambda get-function-configuration --function-name algo-algo-dev`
   - Test locally with same credentials

4. **Redeploy**
   - Fix issue
   - Reapply Terraform

---

## Post-Deployment Monitoring

After successful deployment:

- [ ] **Monitor First 24 Hours**
  - [ ] Check for alert emails (data patrol, position alerts)
  - [ ] Verify SNS emails arriving from infrastructure alarms
  - [ ] No false positives in log spam

- [ ] **Weekly Check**
  - [ ] Confirm patrol alerts being sent weekly
  - [ ] Verify SNS email subscription still active
  - [ ] Check CloudWatch alarms are all in ALARM/OK states

- [ ] **Quarterly Credential Rotation**
  - [ ] Rotate Gmail app-specific password
  - [ ] Update GitHub Secret: `ALERT_SMTP_PASSWORD`
  - [ ] Redeploy via Terraform

---

## Go/No-Go Decision

**GO to Production if:**
- ✅ All checkboxes above are completed
- ✅ All tests pass locally and in AWS
- ✅ Alert emails successfully received
- ✅ No Terraform errors or warnings
- ✅ Trading logic unaffected by alert changes

**NO-GO if:**
- ❌ Alert tests failing
- ❌ SMTP authentication issues
- ❌ Terraform validation errors
- ❌ Trading logic not working

---

## Quick Reference

**Terraform Commands:**
```bash
# Validate
terraform validate

# Plan
terraform plan

# Apply
terraform apply

# Check specific resource
terraform state show module.services.aws_sns_topic.algo_alerts
```

**AWS CLI Commands:**
```bash
# Check Lambda env vars
aws lambda get-function-configuration --function-name algo-algo-dev | jq '.Environment'

# Check SNS subscriptions
aws sns list-subscriptions-by-topic --topic-arn arn:aws:sns:us-east-1:ACCOUNT_ID:algo-algo-alerts-dev

# Monitor logs
aws logs tail /aws/lambda/algo-algo-dev --follow

# Test alert email from Lambda
aws sns publish \
  --topic-arn arn:aws:sns:us-east-1:ACCOUNT_ID:algo-algo-alerts-dev \
  --subject "Test Alert" \
  --message "This is a test alert"
```

---

**Last Updated:** 2026-05-30  
**Prepared by:** Claude Code  
**Deployment Target:** Monday 2026-05-31
