# Alert System Setup & Testing Guide

This guide explains how to configure and test the complete alert system for the Algo trading platform.

## Architecture

**Two independent alert channels:**

1. **Infrastructure Alerts (SNS)**
   - Source: CloudWatch alarms (Lambda errors, RDS metrics, API Gateway errors)
   - Delivery: SNS → Email subscriptions
   - Status: ✅ Terraform-configured, ready to deploy

2. **Application Alerts (SMTP Email)**
   - Source: Orchestrator phases, position monitor, data patrol, loaders
   - Class: `AlertManager` in `algo/algo_alerts.py`
   - Delivery: Direct SMTP (Gmail, Outlook, custom)
   - Status: ✅ Code complete, needs credentials

---

## Local Testing (Development)

### 1. Run Unit Tests

```bash
cd /path/to/algo
python -m pytest tests/test_alerts_integration.py -v
```

Expected output:
```
8 passed in 1.42s
```

### 2. Test SMTP Email Locally

**Setup:**
```bash
# For Gmail (recommended)
export ALERT_EMAIL_TO="your-email@gmail.com"
export ALERT_SMTP_HOST="smtp.gmail.com"
export ALERT_SMTP_PORT="587"
export ALERT_SMTP_USER="your-email@gmail.com"
export ALERT_SMTP_PASSWORD="your-app-password"  # Not your regular password!
export ALERT_SMTP_FROM="your-email@gmail.com"
```

**Gmail App-Specific Password Setup:**
1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. Select "Mail" and "Windows Computer" (or your device)
3. Copy the generated 16-character password
4. Set as `ALERT_SMTP_PASSWORD` above

**Run Local Test:**
```python
#!/usr/bin/env python3
import sys, os
sys.path.insert(0, '/path/to/algo')
from algo.algo_alerts import AlertManager

am = AlertManager()

# Test 1: Patrol alert
am.send_patrol_alert(
    'PATROL-LOCAL-TEST-001',
    {'critical': 1, 'error': 0, 'warn': 0, 'info': 0},
    [{
        'check': 'test_check',
        'severity': 'critical',
        'target': 'test_table',
        'message': 'Test alert from local development'
    }]
)

# Test 2: Generic critical alert
am.critical('Test critical alert message')

print("✅ Both alerts sent successfully!")
```

Run it:
```bash
python test_alert_local.py
```

Check your email for the alerts!

---

## AWS Lambda Deployment

### 1. Set Terraform Variables

Edit `terraform/terraform.tfvars`:
```hcl
# For Gmail
alert_smtp_host     = "smtp.gmail.com"
alert_smtp_port     = 587
alert_smtp_user     = "your-email@gmail.com"
alert_smtp_password = ""  # Set via GitHub Secret in CI/CD
alert_smtp_from     = "your-email@gmail.com"
alert_email_to      = "your-email@gmail.com"
```

### 2. Set GitHub Secret (for CI/CD)

1. Go to repository Settings → Secrets and variables → Actions
2. Create new secret: `ALERT_SMTP_PASSWORD`
3. Paste your app-specific password

### 3. Deploy to AWS

```bash
# From local machine with AWS credentials
cd terraform
terraform apply -var-file=terraform.tfvars

# OR via GitHub Actions (automatic on merge to main)
git push origin feature/alert-setup
```

Terraform will:
- Create SNS topic for infrastructure alerts
- Set Lambda environment variables (ALERT_SMTP_HOST, ALERT_SMTP_PASSWORD, etc.)
- Configure CloudWatch alarms → SNS → Email

### 4. Verify Lambda Environment Variables

In AWS Console:
1. Go to Lambda → Functions → algo-algo-dev
2. Configuration → Environment Variables
3. Verify these are set:
   - `ALERT_EMAIL_TO`
   - `ALERT_SMTP_HOST`
   - `ALERT_SMTP_PORT`
   - `ALERT_SMTP_USER`
   - `ALERT_SMTP_PASSWORD`
   - `ALERT_SMTP_FROM`

---

## Testing Alerts in AWS Lambda

### 1. Manual Orchestrator Test

SSH into Lambda (via AWS Console or invoke locally):

```python
from algo.algo_orchestrator import Orchestrator

orch = Orchestrator(dry_run=True)
# This will initialize AlertManager with Lambda env vars
assert orch.alerts is not None
assert orch.alerts.email_to == ['your-email@gmail.com']
assert orch.alerts.smtp_host == 'smtp.gmail.com'
```

### 2. Trigger Data Patrol Alert

Data patrol runs automatically as Phase 1 of orchestration. To force a test:

```bash
aws lambda invoke \
  --function-name algo-algo-dev \
  --region us-east-1 \
  response.json

# Check CloudWatch logs
aws logs tail /aws/lambda/algo-algo-dev --follow
```

Watch for:
```
[ALERT CONFIG] Email alerts configured to: your-email@gmail.com
Email sent: [ALGO ALERT] ERROR: Data Patrol ...
```

### 3. CloudWatch Alarms (SNS)

Check SNS:
```bash
aws sns list-subscriptions-by-topic \
  --topic-arn arn:aws:sns:us-east-1:ACCOUNT:algo-algo-alerts-dev

# Should show email subscription
```

Subscribe to alerts:
```bash
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:ACCOUNT:algo-algo-alerts-dev \
  --protocol email \
  --notification-endpoint your-email@gmail.com
```

---

## Email Alert Examples

### Patrol Alert (Critical Data Issue)
```
Subject: [ALGO ALERT] CRITICAL: Data Patrol RUN-2026-05-30-093000

Data Patrol Alert — 2026-05-30T09:30:00+00:00
Run: RUN-2026-05-30-093000

Counts:
  CRITICAL: 1
  ERROR:    0
  WARN:     0

Findings:
  [CRITICAL] staleness: price_daily - Data is 9d old (threshold: 7d)

ACTION REQUIRED: Review patrol results and halt trading if necessary.
```

### Position Alert (Stuck Order)
```
Subject: [ALGO ALERT] STUCK_ORDER: AAPL

Position Alert — 2026-05-30T14:22:15+00:00
Type: STUCK_ORDER
Symbol: AAPL

Message: Order has been pending for 5 minutes. Manual intervention required.
```

### Generic Critical Alert
```
Subject: [ALGO ALERT] CRITICAL

Critical Alert — 2026-05-30T16:45:30+00:00

Circuit breaker triggered: Daily loss limit exceeded. Trading halted.
```

---

## Troubleshooting

### SMTP Connection Failed
```
Error: [Errno 111] Connection refused
```
**Cause:** Wrong hostname or firewall blocking port 587
**Fix:**
- Verify ALERT_SMTP_HOST: `nslookup smtp.gmail.com`
- Confirm port 587 is open: `telnet smtp.gmail.com 587`

### Gmail "Invalid Credentials"
```
Error: Authentication failed; please check your email and password
```
**Cause:** Using regular password instead of app-specific password
**Fix:**
1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. Generate new app-specific password
3. Copy full 16-character password (no spaces)
4. Update ALERT_SMTP_PASSWORD

### No Email Received
**Check CloudWatch Logs:**
```bash
aws logs tail /aws/lambda/algo-algo-dev --grep "Email sent\|Email failed"
```

**Verify configuration:**
```bash
# Check Lambda env vars
aws lambda get-function-configuration --function-name algo-algo-dev | grep ALERT

# Check if alerts are being triggered
aws logs tail /aws/lambda/algo-algo-dev --grep "AlertManager\|send_patrol"
```

### SMTP Password Contains Special Characters
**Issue:** Credentials with `$`, `'`, `"` may break environment variables
**Solution:**
- Use app-specific password (16 characters, no special chars)
- In Terraform, escape special characters: `alert_smtp_password = "pass\\$word"`
- In GitHub Secrets, paste raw password (auto-escaped)

---

## Configuration Reference

### Environment Variables (Lambda)

| Variable | Source | Example | Required |
|----------|--------|---------|----------|
| ALERT_EMAIL_TO | terraform.tfvars | user@example.com | Yes (for email) |
| ALERT_SMTP_HOST | terraform.tfvars | smtp.gmail.com | Yes (for email) |
| ALERT_SMTP_PORT | terraform.tfvars | 587 | Yes (default: 587) |
| ALERT_SMTP_USER | terraform.tfvars | user@example.com | Yes (for email) |
| ALERT_SMTP_PASSWORD | GitHub Secret | app-password | Yes (for email) |
| ALERT_SMTP_FROM | terraform.tfvars | alerts@example.com | No (default: noreply@algo.local) |
| ALERT_WEBHOOK_URL | terraform.tfvars | https://hooks.slack.com/... | No (for Slack) |
| ALERTS_SNS_TOPIC | Terraform (auto) | arn:aws:sns:... | Auto-set |

### Terraform Variables (terraform.tfvars)

```hcl
# Email alerts (required for SMTP)
alert_email_to     = "your-email@example.com"

# SMTP configuration (all required for email alerts)
alert_smtp_host     = "smtp.gmail.com"
alert_smtp_port     = 587
alert_smtp_user     = "your-email@gmail.com"
alert_smtp_password = ""  # Set via GitHub Secrets in CI/CD
alert_smtp_from     = "your-email@gmail.com"

# Infrastructure alerts (SNS)
sns_alerts_enabled = true
sns_alert_email    = "your-email@example.com"
```

---

## Next Steps

1. ✅ **Local Testing:** Run `pytest tests/test_alerts_integration.py`
2. ✅ **Credentials Setup:** Gmail app-specific password
3. **Deploy:** `terraform apply` with credentials
4. **Verify:** Check email for test alerts
5. **Monitor:** Watch CloudWatch logs for alert triggers

---

## Support

For issues:
1. Check CloudWatch Logs: `/aws/lambda/algo-algo-dev`
2. Review this troubleshooting guide
3. Verify environment variables: `aws lambda get-function-configuration --function-name algo-algo-dev`
4. Test locally first before debugging in AWS
