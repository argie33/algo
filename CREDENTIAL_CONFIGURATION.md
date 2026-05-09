# Credential Configuration Guide

## Overview

This document describes how credentials are managed throughout the system. All credentials use environment variables with fallback support for backwards compatibility.

## Environment Variables Reference

### Database Credentials

**Primary Source: Environment Variables**
```bash
DB_HOST=localhost              # PostgreSQL hostname
DB_PORT=5432                   # PostgreSQL port
DB_USER=stocks                 # PostgreSQL username
DB_PASSWORD=<password>         # PostgreSQL password
DB_NAME=stocks                 # PostgreSQL database name
DB_SSL=true|false              # Enable SSL (default: true)
DB_SECRET_ARN=arn:aws:...      # AWS Secrets Manager ARN (production)
```

**Secondary Source: AWS Secrets Manager** (Production only)
- If `DB_SECRET_ARN` is set, credentials are fetched from Secrets Manager
- Expected secret format:
  ```json
  {
    "host": "your-rds.amazonaws.com",
    "port": 5432,
    "username": "stocks",
    "password": "secure-password",
    "dbname": "stocks"
  }
  ```

**Used By:**
- `webapp/lambda/utils/database.js` - All API database connections
- `algo_*.py` - All Python backend scripts
- `docker-compose.yml` - Local development database

**Validation:**
- Required in production: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`
- Validated in: `webapp/lambda/config/environment.js`

---

### Alpaca Trading Credentials

**Primary Names (Alpaca Official):**
```bash
APCA_API_KEY_ID=<key>          # Alpaca API Key ID
APCA_API_SECRET_KEY=<secret>   # Alpaca API Secret Key
ALPACA_PAPER_TRADING=true      # Use paper trading (default: true)
APCA_API_BASE_URL=...          # Alpaca API base URL (optional)
```

**Secondary Names (Legacy Compatibility):**
```bash
ALPACA_API_KEY=<key>           # Falls back to APCA_API_KEY_ID
ALPACA_API_SECRET=<secret>     # Falls back to APCA_API_SECRET_KEY
ALPACA_SECRET_KEY=<secret>     # Falls back to APCA_API_SECRET_KEY
```

**Used By:**
- `webapp/lambda/utils/alpacaTrading.js` - Initialize Alpaca trader
- `webapp/lambda/utils/alpacaSyncScheduler.js` - Portfolio sync scheduler
- `webapp/lambda/utils/alpacaService.js` - Alpaca API operations
- `webapp/lambda/config/environment.js` - Configuration management

**Resolution Order:**
1. Try `APCA_API_KEY_ID` (official Alpaca name)
2. Fall back to `ALPACA_API_KEY` (legacy)
3. Try `APCA_API_SECRET_KEY` (official Alpaca name)
4. Fall back to `ALPACA_API_SECRET` (legacy)
5. Fall back to `ALPACA_SECRET_KEY` (legacy)

**Paper Trading:**
- Default: `ALPACA_PAPER_TRADING=true` (uses paper/sandbox environment)
- Never use live trading in development

---

### Authentication & Authorization

**JWT Signing Secret:**
```bash
JWT_SECRET=<strong-random-secret>  # Min 32 characters in production
```

**Cognito (AWS):**
```bash
COGNITO_USER_POOL_ID=us-east-1_xxx...
COGNITO_CLIENT_ID=xxx...
```

**Validation:**
- Required in production
- Minimum 32 characters for `JWT_SECRET`
- Validated at startup: `webapp/lambda/index.js`

---

### Email & Alerting

**SMTP Credentials:**
```bash
ALERT_SMTP_HOST=smtp.gmail.com
ALERT_SMTP_PORT=587
ALERT_SMTP_USER=your-email@gmail.com
ALERT_SMTP_PASSWORD=<app-password>  # Not your Gmail password!
ALERT_EMAIL_TO=recipient@example.com
```

**AWS SNS (Optional):**
```bash
ALERT_SNS_TOPIC_ARN=arn:aws:sns:us-east-1:xxx...
```

**Used By:**
- `algo_alerts.py` - Alert notifications
- `webapp/lambda/utils/email.js` - Email service

---

### AWS Configuration

**AWS SDK:**
```bash
AWS_REGION=us-east-1           # AWS region for all services
WEBAPP_AWS_REGION=us-east-1    # Override for webapp only (optional)
```

**AWS Credentials** (for local development):
```bash
# For Docker Compose: NOT NEEDED (use Docker's IAM role)
# For local AWS CLI: Configure via `aws configure` instead

# DO NOT PUT IN .env.local:
# AWS_ACCESS_KEY_ID=...
# AWS_SECRET_ACCESS_KEY=...
```

**Used By:**
- Lambda functions for AWS Secrets Manager
- S3 access
- CloudWatch logging

---

### Feature Flags

**Development Mode:**
```bash
NODE_ENV=development            # or "production"
ALLOW_DEV_BYPASS=true          # Allow dev auth bypass (local only)
LOCAL_DEV_MODE=true            # Enable local dev features
```

---

## Configuration Sources (Priority Order)

### For Local Development
1. **`.env.local`** (NOT committed to git)
   - Copy from `.env.local.example`
   - Edit with your local values
   - Only for local testing

2. **Environment variables** (from shell/Docker)
   - Set via `export KEY=value`
   - Passed to Docker via compose or CLI

3. **Defaults** (in code)
   - Used if not provided above
   - Safe defaults like `localhost:5432`

### For Production (AWS Lambda)
1. **AWS Secrets Manager** (via `DB_SECRET_ARN`)
   - Most secure option
   - Automatic rotation support
   - Audit trail

2. **Environment variables** (set in Lambda console or Terraform)
   - Set via Lambda configuration
   - Available at runtime

3. **GitHub Secrets** (used in CI/CD)
   - Stored securely in GitHub
   - Injected into Lambda during deployment

---

## Local Development Setup

### Option 1: Docker Compose (Recommended)
```bash
# Uses dummy credentials in compose file
docker-compose up -d

# No .env.local needed for local development
```

### Option 2: Local Database + Environment Variables
```bash
# Create .env.local from template
cp .env.local.example .env.local

# Edit with your local credentials
nano .env.local

# Source before running
source .env.local
npm start
```

### Option 3: AWS Secrets Manager (Cloud-like)
```bash
# Configure AWS CLI
aws configure

# Create secret in Secrets Manager
aws secretsmanager create-secret \
  --name local/db/postgres \
  --secret-string '{"host":"localhost","port":5432,"username":"stocks","password":"yourpassword","dbname":"stocks"}'

# Set secret ARN in environment
export DB_SECRET_ARN=arn:aws:secretsmanager:us-east-1:xxx:secret:local/db/postgres

# Code will fetch from Secrets Manager automatically
```

---

## Production Deployment

### 1. Create Secrets Manager Secrets

**Database Secret:**
```bash
aws secretsmanager create-secret \
  --name prod/db/postgres \
  --secret-string '{
    "host": "your-rds.amazonaws.com",
    "port": 5432,
    "username": "stocks",
    "password": "secure-password",
    "dbname": "stocks"
  }'
```

**Output: `arn:aws:secretsmanager:us-east-1:xxx:secret:prod/db/postgres`**

### 2. Set GitHub Secrets

In your GitHub repository settings, add:
```
APCA_API_KEY_ID      # Alpaca API Key
APCA_API_SECRET_KEY  # Alpaca API Secret
JWT_SECRET           # Min 32 characters
COGNITO_USER_POOL_ID # AWS Cognito
COGNITO_CLIENT_ID    # AWS Cognito
ALERT_SMTP_PASSWORD  # Email credentials
```

### 3. Deploy via Terraform

```hcl
# terraform/variables.tf
variable "db_secret_arn" {
  description = "AWS Secrets Manager ARN for database"
  type        = string
}

variable "apca_api_key_id" {
  description = "Alpaca API Key ID"
  type        = string
  sensitive   = true
}

# terraform/main.tf
resource "aws_lambda_function" "api" {
  environment {
    variables = {
      DB_SECRET_ARN           = var.db_secret_arn
      APCA_API_KEY_ID         = var.apca_api_key_id
      APCA_API_SECRET_KEY     = var.apca_api_secret_key
      JWT_SECRET              = var.jwt_secret
      ALPACA_PAPER_TRADING    = "false"  # Live trading
      NODE_ENV                = "production"
    }
  }
}
```

---

## Credential Validation

### At Startup

**JavaScript (Node.js):**
```javascript
// webapp/lambda/index.js
validateSecurityConfig(); // Checks JWT_SECRET strength

// webapp/lambda/config/environment.js
validateEnvironment();    // Checks required production vars
```

**Python:**
```python
# Check APCA_API_KEY_ID and APCA_API_SECRET_KEY
# Check DB_HOST, DB_USER, DB_PASSWORD, DB_NAME
```

### Runtime Checks

**Database:**
```
✓ Connection pool initialized
✓ Schema verified (60+ tables)
✓ Test query successful
```

**Alpaca:**
```
✓ API credentials valid
✓ Paper trading enabled
✓ Account accessible
```

---

## Troubleshooting

### Database Connection Failed
```bash
# Check credentials
echo $DB_HOST $DB_USER $DB_PASSWORD $DB_NAME

# Test connection
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT version();"

# If using Secrets Manager
aws secretsmanager get-secret-value --secret-id $DB_SECRET_ARN
```

### Alpaca Connection Failed
```bash
# Check credentials
echo $APCA_API_KEY_ID $APCA_API_SECRET_KEY

# Verify paper trading enabled
echo $ALPACA_PAPER_TRADING

# Test with curl
curl -H "APCA-API-KEY-ID: $APCA_API_KEY_ID" \
     https://paper-api.alpaca.markets/v2/account
```

### JWT Secret Too Weak
```bash
# Generate strong secret
openssl rand -base64 32

# Set in production
export JWT_SECRET=$(openssl rand -base64 32)
```

---

## Security Best Practices

✅ **DO:**
- Use environment variables for all credentials
- Use AWS Secrets Manager in production
- Use `.env.local` for local development (gitignored)
- Rotate credentials every 90 days
- Store secrets in GitHub Secrets (never in code)
- Use paper trading in development
- Set strong JWT secrets (32+ characters)

❌ **DON'T:**
- Commit `.env.local` to git
- Hardcode credentials in code
- Log credentials
- Share credentials via email or chat
- Use live trading credentials in development
- Use weak secrets for JWT signing
- Mix development and production credentials

---

## Credential Rotation

### Development (Local)
- Manual: Edit `.env.local` as needed
- No rotation required

### Production (AWS)
- Automatic via AWS Secrets Manager
- Manual rotation: Update secret and redeploy Lambda
- Consider quarterly rotation schedule

```bash
# Update secret in Secrets Manager
aws secretsmanager update-secret \
  --secret-id prod/db/postgres \
  --secret-string '{...new credentials...}'

# Redeploy Lambda
terraform apply -var="db_secret_arn=..."
```

---

## Configuration Checklist

Before deployment:

- [ ] All database credentials set (DB_HOST, DB_USER, DB_PASSWORD, DB_NAME)
- [ ] Alpaca credentials configured (APCA_API_KEY_ID, APCA_API_SECRET_KEY)
- [ ] JWT_SECRET is 32+ characters
- [ ] ALPACA_PAPER_TRADING=true (development)
- [ ] ALPACA_PAPER_TRADING=false (production, if using live trading)
- [ ] AWS Secrets Manager configured (for production)
- [ ] GitHub Secrets set up (for CI/CD)
- [ ] No credentials in .env files (use example template only)
- [ ] Terraform variables configured
- [ ] Email credentials valid (if using alerts)

---

## Related Files

- `.env.local.example` - Template for local credentials
- `LOCAL_SECRETS_SETUP.md` - Local secrets management strategies
- `webapp/lambda/config/environment.js` - Configuration validation
- `webapp/lambda/utils/database.js` - Database credential handling
- `webapp/lambda/utils/alpaca*.js` - Alpaca credential usage
- `terraform/variables.tf` - Production Terraform variables
