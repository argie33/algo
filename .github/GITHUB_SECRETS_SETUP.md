# GitHub Secrets Setup

All 8 secrets required in GitHub repository settings (Settings → Secrets → Actions):

**AWS (3 secrets):**
- AWS_ACCESS_KEY_ID
- AWS_SECRET_ACCESS_KEY  
- AWS_ACCOUNT_ID (get via: aws sts get-caller-identity --query Account --output text)

**RDS (1 secret):**
- RDS_PASSWORD (your database master password)

**Alpaca API (2 secrets):**
- ALPACA_API_KEY_ID (from app.alpaca.markets/paper/api-keys)
- ALPACA_API_SECRET_KEY (from app.alpaca.markets/paper/api-keys)

**Application (2 secrets):**
- ALERT_EMAIL_ADDRESS (your email for alerts)
- API_GATEWAY_URL (leave empty initially, update after first deployment)

Add all 8 at: https://github.com/argie33/algo/settings/secrets/actions
