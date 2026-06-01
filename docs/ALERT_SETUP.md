# Alert System Setup

Two alert channels: Infrastructure (SNS), Application (SMTP via AlertManager).

## Local Testing

**Run tests:**
```bash
python -m pytest tests/test_alerts_integration.py -v
```

**Test SMTP locally:**
```bash
export ALERT_EMAIL_TO="you@gmail.com"
export ALERT_SMTP_HOST="smtp.gmail.com"
export ALERT_SMTP_PORT="587"
export ALERT_SMTP_USER="you@gmail.com"
export ALERT_SMTP_PASSWORD="your-app-password"  # From myaccount.google.com/apppasswords
export ALERT_SMTP_FROM="you@gmail.com"
```

**Test script:**
```python
from algo.algo_alerts import AlertManager
am = AlertManager()
am.critical('Test alert')
```

## AWS Lambda Deployment

**Set terraform.tfvars:**
```hcl
alert_smtp_host     = "smtp.gmail.com"
alert_smtp_port     = 587
alert_smtp_user     = "you@gmail.com"
alert_smtp_password = ""  # Via GitHub Secret
alert_smtp_from     = "you@gmail.com"
alert_email_to      = "you@gmail.com"
sns_alerts_enabled  = true
sns_alert_email     = "you@gmail.com"
```

**Deploy:**
```bash
cd terraform && terraform apply -var-file=terraform.tfvars
```

**Verify Lambda env vars:**
```bash
aws lambda get-function-configuration --function-name algo-algo-dev | grep ALERT
```

## Testing in AWS

**Manual test:**
```bash
aws lambda invoke \
  --function-name algo-algo-dev \
  --region us-east-1 \
  response.json
aws logs tail /aws/lambda/algo-algo-dev --follow
```

**SNS subscriptions:**
```bash
aws sns list-subscriptions-by-topic \
  --topic-arn arn:aws:sns:us-east-1:ACCOUNT:algo-algo-alerts-dev
```

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| Connection refused | Wrong host/port | Verify ALERT_SMTP_HOST, port 587 open |
| Invalid credentials | Regular password used | Use app-specific password from myaccount.google.com/apppasswords |
| No email received | Alerts not triggering | Check CloudWatch logs with `aws logs tail /aws/lambda/algo-algo-dev --grep "Email"` |
| Special chars in password | ENV var escaping | Use app-specific password (alphanumeric only) or escape in Terraform |

## Configuration Reference

| Variable | Source | Example | Required |
|----------|--------|---------|----------|
| ALERT_EMAIL_TO | terraform.tfvars | user@example.com | Yes (email) |
| ALERT_SMTP_HOST | terraform.tfvars | smtp.gmail.com | Yes (email) |
| ALERT_SMTP_PORT | terraform.tfvars | 587 | Yes (email) |
| ALERT_SMTP_USER | terraform.tfvars | user@example.com | Yes (email) |
| ALERT_SMTP_PASSWORD | GitHub Secret | app-password | Yes (email) |
| ALERT_SMTP_FROM | terraform.tfvars | alerts@example.com | No |
| ALERTS_SNS_TOPIC | Terraform auto | arn:aws:sns:... | Auto-set |
