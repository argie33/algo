# Alert Configuration Guide

Configure alerting for the trading system to receive notifications of critical events, errors, and trading activities.

## Alert Channels

The system supports three alert methods:

1. **Email Alerts** - SMTP-based email notifications
2. **Webhook Alerts** - Slack, Microsoft Teams, Discord, or custom webhooks
3. **SMS Alerts** - Twilio SMS notifications (optional)

## Configuration Methods

### Method 1: AWS Secrets Manager (Recommended - Production)

Configure alerts by creating a secret in AWS Secrets Manager:

```bash
# Create or update the alert configuration secret
aws secretsmanager create-secret \
  --name algo/alerts \
  --secret-string '{
    "webhook_url": "https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
    "email_to": "alerts@example.com",
    "email_from": "trading-alerts@example.com"
  }' \
  --region us-east-1
```

The deploy-code.yml workflow will automatically read this secret and configure the Orchestrator Lambda.

### Method 2: Local Environment Variables (Development)

For local development, set environment variables in your PowerShell profile:

```powershell
# Slack Webhook
$env:ALERT_WEBHOOK_URL = "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

# Email Configuration
$env:ALERT_EMAIL_FROM = "trading-alerts@example.com"
$env:ALERT_EMAIL_TO = "you@example.com"
$env:ALERT_SMTP_HOST = "smtp.gmail.com"
$env:ALERT_SMTP_PORT = "587"
$env:ALERT_SMTP_USER = "your-email@gmail.com"
$env:ALERT_SMTP_PASSWORD = "your-app-password"  # Use app-specific password, not account password

# Twilio SMS (Optional)
$env:TWILIO_ACCOUNT_SID = "your-account-sid"
$env:TWILIO_AUTH_TOKEN = "your-auth-token"
$env:TWILIO_PHONE_NUMBER = "+1234567890"
$env:ALERT_PHONE_NUMBERS = "+1234567890,+0987654321"
```

## Configuration Details

### Slack Webhook Setup

1. Create a Slack workspace if you don't have one
2. Go to https://api.slack.com/apps and create a new app
3. Enable Incoming Webhooks
4. Create a new webhook pointing to your #alerts channel
5. Copy the webhook URL

**Slack Webhook URL format:** `https://hooks.slack.com/services/<WORKSPACE>/<CHANNEL>/<TOKEN>`

Store the webhook URL in AWS Secrets Manager as the `webhook_url` key inside `algo/alerts`.

### Email Configuration

#### Using Gmail:
```
ALERT_SMTP_HOST=smtp.gmail.com
ALERT_SMTP_PORT=587
ALERT_SMTP_USER=your-email@gmail.com
ALERT_SMTP_PASSWORD=<app-specific-password>
```

**Important:** Use an app-specific password, not your account password. Generate one at:
https://myaccount.google.com/apppasswords

#### Using AWS SES:
```
ALERT_SMTP_HOST=email-smtp.us-east-1.amazonaws.com
ALERT_SMTP_PORT=587
ALERT_SMTP_USER=<SMTP username from SES>
ALERT_SMTP_PASSWORD=<SMTP password from SES>
```

#### Using Corporate Email:
Consult your email administrator for SMTP settings.

### Twilio SMS Setup (Optional)

1. Create a Twilio account at https://www.twilio.com
2. Get your Account SID and Auth Token from the Twilio dashboard
3. Purchase a phone number or use an existing one
4. Configure phone numbers to receive alerts

## Alert Types

The system sends alerts for:

### Critical Alerts (CRITICAL severity)
- Data freshness violations (prices > 7 days old)
- Circuit breaker triggered (VIX spike, drawdown limit, daily loss limit)
- Position limit exceeded
- Trade execution failures
- Database connectivity lost

### Error Alerts (ERROR severity)
- Loader execution failures
- API errors
- Signal generation failures
- Position reconciliation errors

### Info Alerts (INFO severity)
- Daily report summary
- Position snapshot
- End-of-day reconciliation completed

## Testing Alerts Locally

Test alert configuration before deployment:

```bash
# Test with dry-run orchestrator
python3 << 'EOF'
import sys
sys.path.insert(0, '.')

from config.env_loader import load_env
from algo.algo_alerts import AlertManager

load_env()
alerts = AlertManager()

# Test email alert
alerts.send_email(
    subject="Test Alert from Algo System",
    body="This is a test alert. If you received this, email alerts are working!"
)

# Test webhook alert
alerts.send_webhook(
    severity="WARNING",
    title="Test Alert",
    message="This is a test webhook alert. If you received this, webhooks are working!"
)

print("Alert tests completed. Check your email/Slack!")
EOF
```

## Troubleshooting

### Alerts Not Received

1. **Check AlertManager initialization:**
   ```bash
   aws logs tail /aws/lambda/algo-algo-dev --grep "ALERT CONFIG" --region us-east-1
   ```

2. **Verify Secrets Manager secret exists:**
   ```bash
   aws secretsmanager get-secret-value --secret-id algo/alerts --region us-east-1
   ```

3. **Check Lambda environment variables:**
   ```bash
   aws lambda get-function-configuration \
     --function-name algo-algo-dev \
     --query 'Environment.Variables.[ALERT_WEBHOOK_URL,ALERT_EMAIL_TO]' \
     --region us-east-1
   ```

4. **Test SMTP connectivity:**
   ```python
   import smtplib
   server = smtplib.SMTP('smtp.gmail.com', 587)
   server.starttls()
   server.login('user@gmail.com', 'password')
   server.sendmail(...)
   ```

### Email Not Sending

- Verify SMTP credentials are correct
- Check Gmail app password (not account password)
- Verify firewall allows outbound port 587 (SMTP)
- Check CloudWatch logs for SSL/TLS errors

### Slack Webhook Not Working

- Verify webhook URL is correct and still active
- Check if Slack workspace still exists
- Verify webhook points to correct channel
- Check CloudWatch logs for HTTP errors

## Production Checklist

Before going live with alerts:

- [ ] Alert configuration created in AWS Secrets Manager
- [ ] Test alert received successfully (email and/or Slack)
- [ ] AlertManager logs show "alert channels configured"
- [ ] No errors in CloudWatch logs from AlertManager
- [ ] Team members notified of alert channel
- [ ] On-call schedule configured to monitor alerts
- [ ] Alert rules match your trading risk tolerance

## Cost Considerations

- **Email (AWS SES):** ~$0.10 per 1,000 emails
- **Slack Webhook:** Free
- **Twilio SMS:** ~$0.0075 per SMS in US

For a trading system, expect 5-10 alerts per trading day in normal conditions.

## Additional Resources

- [Slack Incoming Webhooks](https://api.slack.com/messaging/webhooks)
- [Twilio Python SDK](https://www.twilio.com/docs/libraries/python)
- [SMTP Server Configuration](https://en.wikipedia.org/wiki/Simple_Mail_Transfer_Protocol)
- [AWS Secrets Manager Best Practices](https://docs.aws.amazon.com/secretsmanager/latest/userguide/best-practices.html)
