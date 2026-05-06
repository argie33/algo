# Alert Configuration

Email + SMS alerts for critical data issues. Sends to your inbox and phone when patrol finds problems.

## Quick Setup (5 minutes)

### 1. Gmail (Email Alerts)

Already configured with defaults. Just add to `.env.local`:

```bash
ALERT_EMAIL_FROM=edgebrookecapital@gmail.com
ALERT_EMAIL_TO=argeropolos@gmail.com
ALERT_SMTP_HOST=smtp.gmail.com
ALERT_SMTP_PORT=587
ALERT_SMTP_USER=edgebrookecapital@gmail.com
ALERT_SMTP_PASSWORD=<app_password>
```

**Get Gmail app password:**
1. Go to https://myaccount.google.com/apppasswords
2. Select "Mail" + "Windows Computer" (or your device)
3. Google generates a 16-char password
4. Copy it to `ALERT_SMTP_PASSWORD` (no spaces)

### 2. Twilio (SMS Alerts)

Free tier: 1000 SMS/month. Perfect for alerts.

**Setup:**
1. Sign up: https://www.twilio.com/console
2. Get free trial number (e.g., +1-XXX-XXX-XXXX)
3. Add to `.env.local`:

```bash
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_PHONE_NUMBER=+1-XXX-XXX-XXXX  (your Twilio number)
ALERT_PHONE_NUMBERS=+1-312-307-8620
```

**Find these in Twilio Console:**
- Account SID: top right of dashboard
- Auth Token: next to Account SID
- Twilio number: Phone Numbers → Manage Numbers → Active Numbers

### 3. Optional: Slack Webhook

For alerts in a Slack channel:

```bash
ALERT_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

**Get webhook URL:**
1. In Slack: Settings → Manage apps → Build → Create New App
2. Choose "From scratch", name it "Algo Alerts"
3. Enable Incoming Webhooks
4. Create New Webhook to Channel → choose #trading-alerts
5. Copy URL to `.env.local`

---

## What Gets Alerted

- **CRITICAL** findings → Email + SMS + Slack (always)
- **ERROR** findings (>2) → Email + SMS + Slack
- **WARN** findings → Email + Slack only (no SMS spam)

Examples:
- OHLC corruption (CRITICAL)
- >30% 1-day drop without earnings (WARN)
- Stale orders >1 hour (ERROR)
- Missing price history for filled trades (ERROR)

---

## Testing

Once configured, test with:

```bash
python3 algo_alerts.py
```

Should send a test alert to all channels.

---

## .env.local Example

```bash
# Email
ALERT_EMAIL_FROM=edgebrookecapital@gmail.com
ALERT_EMAIL_TO=argeropolos@gmail.com
ALERT_SMTP_HOST=smtp.gmail.com
ALERT_SMTP_PORT=587
ALERT_SMTP_USER=edgebrookecapital@gmail.com
ALERT_SMTP_PASSWORD=abcd efgh ijkl mnop

# SMS
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_token
TWILIO_PHONE_NUMBER=+1-312-555-0123
ALERT_PHONE_NUMBERS=+1-312-307-8620

# Optional: Slack
ALERT_WEBHOOK_URL=https://hooks.slack.com/services/...
```

Save to `.env.local` (already in .gitignore).
