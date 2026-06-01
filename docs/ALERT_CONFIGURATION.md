# Alert Configuration

## Local Development

Set PowerShell env vars:
```powershell
$env:ALERT_EMAIL_TO = "you@example.com"
$env:ALERT_SMTP_HOST = "smtp.gmail.com"
$env:ALERT_SMTP_PORT = "587"
$env:ALERT_SMTP_USER = "you@gmail.com"
$env:ALERT_SMTP_PASSWORD = "app-password"  # myaccount.google.com/apppasswords
$env:ALERT_WEBHOOK_URL = "https://hooks.slack.com/services/YOUR/URL"
```

## AWS Production

Create secret in Secrets Manager:
```bash
aws secretsmanager create-secret \
  --name algo/alerts \
  --secret-string '{"webhook_url":"https://hooks.slack.com/...","email_to":"you@example.com"}'
```

Or set terraform.tfvars (see ALERT_SETUP.md).

## Alert Types

- CRITICAL: Data stale, circuit breaker triggered, DB down, trade failed
- ERROR: Loader failed, API error, signal generation failed
- INFO: Daily report, position snapshot, reconciliation completed

## Email Providers

Gmail: smtp.gmail.com:587 (use app-specific password)
AWS SES: email-smtp.us-east-1.amazonaws.com:587
Custom: Consult admin

## Slack Webhook

1. api.slack.com -> create app -> enable Incoming Webhooks
2. Create webhook -> #alerts channel
3. Copy URL: https://hooks.slack.com/services/<WORKSPACE>/<CHANNEL>/<TOKEN>
4. Store in AWS Secrets Manager

## Testing

```bash
# Email only
python3 -c "
from algo.algo_alerts import AlertManager
AlertManager().critical('Test')
"

# Webhook
curl -X POST https://hooks.slack.com/services/YOUR/URL \
  -H 'Content-Type: application/json' \
  -d '{\"text\":\"Test alert\"}'
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Email fails | Check SMTP credentials, port 587 open, app password (not account password) |
| Slack fails | Verify webhook URL is correct, workspace exists, channel accessible |
| Alerts not sent | Check CloudWatch logs: `aws logs tail /aws/lambda/algo-algo-dev --grep ALERT` |
| Secrets not found | Verify algo/alerts secret exists: `aws secretsmanager get-secret-value --secret-id algo/alerts` |
