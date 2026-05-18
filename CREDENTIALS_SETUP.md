# Credentials Management & Setup Guide

## Overview

This guide documents the complete credentials pipeline for the Stock Analytics Platform:

```
PowerShell Environment
    ↓
GitHub Secrets (via GitHub Actions)
    ↓
AWS (OIDC → IAM Role → Services)
    ↓
Lambda Environment Variables
    ↓
Credential Manager (Python) / apiKeyService (Node.js)
    ↓
AWS Secrets Manager / Environment Variables
    ↓
Database, Cognito, External APIs
```

**Rule:** Credentials NEVER come from `.env` files. All credentials must be:
- Set as environment variables (local dev)
- Stored in AWS Secrets Manager (production)
- Passed via GitHub Secrets → Lambda environment (CI/CD)

---

## 1. Local Development Setup (PowerShell)

### 1.1 Database Credentials

Set these BEFORE running loaders or the orchestrator:

```powershell
# PostgreSQL connection (required)
$env:DB_HOST = "localhost"
$env:DB_PORT = "5432"
$env:DB_USER = "stocks"
$env:DB_NAME = "stocks"
$env:DB_PASSWORD = "your_postgres_password"  # REQUIRED - no default
```

**Verify locally:**
```powershell
python3 -c "from config.credential_manager import get_db_credentials; print(get_db_credentials())"
```

### 1.2 Alpaca API Credentials (Optional - for live trading)

```powershell
# Alpaca paper/live trading
$env:APCA_API_KEY_ID = "your_alpaca_key"
$env:APCA_API_SECRET_KEY = "your_alpaca_secret"
$env:APCA_API_BASE_URL = "https://paper-api.alpaca.markets"  # paper trading
```

### 1.3 AWS Credentials (Optional - for accessing production Secrets Manager)

```powershell
# AWS credentials for local access to Secrets Manager
aws configure
# OR
$env:AWS_ACCESS_KEY_ID = "your_key"
$env:AWS_SECRET_ACCESS_KEY = "your_secret"
$env:AWS_REGION = "us-east-1"
```

**Test local access:**
```powershell
aws secretsmanager get-secret-value --secret-id algo/db/postgres --region us-east-1
```

### 1.4 Email Alerts (Optional)

```powershell
$env:ALERT_ENABLED = "false"
$env:ALERT_SMTP_HOST = "smtp.gmail.com"
$env:ALERT_SMTP_PORT = "587"
$env:ALERT_SMTP_USER = "your_email@gmail.com"
$env:ALERT_SMTP_PASSWORD = "your_app_password"
```

### 1.5 SMS Alerts (Optional)

```powershell
$env:ALERT_SMS_ENABLED = "false"
$env:TWILIO_AUTH_TOKEN = "your_twilio_token"
```

---

## 2. GitHub Secrets Configuration

These secrets are used by GitHub Actions workflows to deploy code and infrastructure.

### 2.1 Required Secrets

**AWS Account & OIDC:**
- `AWS_ACCOUNT_ID`: Your AWS account ID (12 digits)
  - Used by: `aws-actions/configure-aws-credentials` in deploy workflows
  - Role assumed: `algo-svc-github-actions-dev`

**API Gateway & Frontend:**
- `API_GATEWAY_URL`: HTTPS URL to your API Gateway
  - Example: `https://api.example.com`
  - Used by: Frontend build (sets `VITE_API_URL`)

**Database Secret ARN (for Lambda):**
- `DB_SECRET_ARN`: ARN of RDS credentials secret in Secrets Manager
  - Example: `arn:aws:secretsmanager:us-east-1:123456789:secret:algo/db/postgres-abcde`
  - Used by: Lambda functions to fetch DB credentials

**Cognito (for Lambda):**
- `COGNITO_USER_POOL_ID`: Cognito user pool ID
  - Example: `us-east-1_abc123def456`
  - Used by: API Lambda (nodeJS auth validation)

- `COGNITO_CLIENT_ID`: Cognito app client ID
  - Example: `1a2b3c4d5e6f7g8h9i0j1k2l3m`
  - Used by: API Lambda (apiKeyService JWT validation)

### 2.2 How to Set GitHub Secrets

1. Go to: https://github.com/argie33/algo/settings/secrets/actions
2. Click "New repository secret"
3. Add each secret with its value

**Script to set via gh CLI:**
```bash
gh secret set AWS_ACCOUNT_ID --body "123456789012"
gh secret set API_GATEWAY_URL --body "https://api.example.com"
gh secret set DB_SECRET_ARN --body "arn:aws:secretsmanager:us-east-1:123456789:secret:algo/db/postgres-abcde"
gh secret set COGNITO_USER_POOL_ID --body "us-east-1_abc123def456"
gh secret set COGNITO_CLIENT_ID --body "1a2b3c4d5e6f7g8h9i0j1k2l3m"
```

---

## 3. AWS Setup

### 3.1 RDS Database Secret in Secrets Manager

The database password is stored in AWS Secrets Manager so Lambda functions can fetch it at runtime.

**Create the secret (one time):**
```bash
aws secretsmanager create-secret \
  --name algo/db/postgres \
  --secret-string '{
    "host":"your-rds-endpoint.rds.amazonaws.com",
    "port":5432,
    "username":"stocks",
    "password":"your_postgres_password",
    "dbname":"stocks"
  }' \
  --region us-east-1
```

**Update the secret:**
```bash
aws secretsmanager update-secret \
  --secret-id algo/db/postgres \
  --secret-string '{
    "host":"your-rds-endpoint.rds.amazonaws.com",
    "port":5432,
    "username":"stocks",
    "password":"new_postgres_password",
    "dbname":"stocks"
  }' \
  --region us-east-1
```

**Verify the secret:**
```bash
aws secretsmanager get-secret-value --secret-id algo/db/postgres --region us-east-1
```

### 3.2 Cognito User Pool

Cognito is created by Terraform (`terraform/modules/cognito/main.tf`). Get the IDs:

```bash
# Get user pool ID
aws cognito-idp list-user-pools --max-results 10 --region us-east-1 | jq '.UserPools[] | select(.Name | contains("stocks"))'

# Get client ID (app client)
POOL_ID="us-east-1_abc123def456"  # from above
aws cognito-idp list-user-pool-clients \
  --user-pool-id "$POOL_ID" \
  --max-results 10 \
  --region us-east-1 | jq '.UserPoolClients[0].ClientId'
```

### 3.3 Lambda Execution Role Permissions

Lambda roles need permission to:
1. Read from Secrets Manager (for DB credentials)
2. Call other AWS services (RDS proxy, ECS, S3, etc.)

**Verify the role has Secrets Manager permission:**

```bash
ROLE_NAME="algo-svc-api-dev"
aws iam get-role-policy --role-name "$ROLE_NAME" --policy-name "algo-lambda-policy" \
  --query 'RolePolicyDocument.Statement[?Action[?contains(@,"secretsmanager")]]' \
  --region us-east-1
```

Expected policy statement:
```json
{
  "Effect": "Allow",
  "Action": [
    "secretsmanager:GetSecretValue"
  ],
  "Resource": "arn:aws:secretsmanager:us-east-1:*:secret:algo/*"
}
```

If missing, update the role policy in `terraform/modules/iam/main.tf`.

### 3.4 API Gateway Authorizer

Cognito JWT should be verified by API Gateway, not just Lambda.

**Check current authorizer:**
```bash
API_ID="your-api-id"
aws apigateway get-authorizers --rest-api-id "$API_ID" --region us-east-1
```

If no Cognito authorizer exists, add via Terraform or AWS console:
- Type: Cognito User Pool
- User Pool: `stocks-trading-pool-dev`
- Token Source: `Authorization`

---

## 4. Lambda Environment Variables

These are set automatically by Terraform in `terraform/modules/services/main.tf`.

### 4.1 API Lambda Environment Variables

```env
# Database
DB_SECRET_ARN=arn:aws:secretsmanager:us-east-1:123456789:secret:algo/db/postgres-abcde
DB_ENDPOINT=your-rds-endpoint.rds.amazonaws.com
DB_NAME=stocks

# Cognito Authentication
COGNITO_USER_POOL_ID=us-east-1_abc123def456
COGNITO_CLIENT_ID=1a2b3c4d5e6f7g8h9i0j1k2l3m

# Frontend CORS
CLOUDFRONT_DOMAIN=https://d1234567890abc.cloudfront.net
FRONTEND_URL=https://d1234567890abc.cloudfront.net
NODE_ENV=production

# ECS Patrol Task (optional)
ECS_CLUSTER_ARN=arn:aws:ecs:us-east-1:123456789:cluster/algo-cluster
PATROL_TASK_DEFINITION_ARN=arn:aws:ecs:us-east-1:123456789:task-definition/algo-patrol:1
```

**Verify in Lambda console:**
```bash
FUNCTION_NAME="algo-api-dev"
aws lambda get-function-configuration --function-name "$FUNCTION_NAME" --region us-east-1 | jq '.Environment.Variables'
```

### 4.2 Algo Lambda Environment Variables

Similar to API Lambda, with any algo-specific configuration.

---

## 5. Credential Flow Verification

### 5.1 Local Development Flow

```
PowerShell Environment Variables
         ↓
Python: config/credential_manager.py
         ↓
1. Check cache
2. Try Secrets Manager (if AWS_REGION set)
3. Fall back to env vars (ENV_VAR = secret_name.upper().replace('/', '_'))
4. Use default (if provided)
5. Raise error (if required and not found)
         ↓
Database connection / Alpaca API / etc.
```

**Test the flow:**
```powershell
# Verify credential_manager loads from environment
python3 -c "
from config.credential_manager import get_db_credentials, get_alpaca_credentials
print('[DB]', get_db_credentials())
print('[Alpaca]', get_alpaca_credentials())
"
```

### 5.2 Production Flow (Lambda)

```
GitHub Actions
      ↓
OIDC → assume algo-svc-github-actions-dev role
      ↓
Set Lambda environment from Terraform
      ↓
Lambda runtime starts
      ↓
Node.js / Python code reads environment variables
      ↓
Request Secrets Manager for sensitive values
      ↓
Return to application code
```

**Verify Lambda can read Secrets:**
```bash
# Run test in Lambda console or via aws lambda invoke
aws lambda invoke \
  --function-name algo-api-dev \
  --payload '{"test": true}' \
  /tmp/response.json \
  --region us-east-1

cat /tmp/response.json
```

### 5.3 Frontend Flow (Cognito)

```
Frontend (React/Vite)
      ↓
Amplify or SDK initializes with COGNITO_USER_POOL_ID
      ↓
User logs in with email/password
      ↓
Cognito returns access token (JWT)
      ↓
Frontend sends token in Authorization header
      ↓
API Gateway validates with Cognito authorizer
      ↓
Lambda receives authenticated request
      ↓
apiKeyService.js validates token claims
      ↓
Request processed with user context
```

---

## 6. Security Checklist

- [ ] **No hardcoded credentials** in code
- [ ] **No .env files** committed to git
- [ ] **GitHub Secrets** configured and non-empty
- [ ] **AWS Secrets Manager** contains DB password (not in env vars)
- [ ] **Lambda IAM role** has `secretsmanager:GetSecretValue` permission
- [ ] **Database password** has minimum length 12, mixed case + numbers
- [ ] **Cognito** requires strong passwords (enforced by pool policy)
- [ ] **API Gateway** has Cognito authorizer on all /api routes
- [ ] **CORS** explicitly lists allowed origins (no `*`)
- [ ] **Logs** don't contain sensitive data (auth middleware sanitizes)
- [ ] **CSRF protection** enabled on state-changing endpoints

---

## 7. Troubleshooting

### 7.1 "Database password not available"

```powershell
# Check if DB_PASSWORD is set
Write-Host $env:DB_PASSWORD

# If empty, set it
$env:DB_PASSWORD = "your_password"

# Verify
python3 config/credential_manager.py
```

### 7.2 Lambda can't access database

```bash
# Check if DB_SECRET_ARN is set in Lambda
aws lambda get-function-configuration --function-name algo-api-dev | jq '.Environment.Variables.DB_SECRET_ARN'

# Check if Lambda role can read the secret
ROLE_ARN=$(aws lambda get-function-configuration --function-name algo-api-dev | jq -r '.Role')
aws iam get-role-policy --role-name $(basename "$ROLE_ARN") --policy-name algo-lambda-policy
```

### 7.3 "Cognito environment variables not configured"

```bash
# Check if COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID are set
aws lambda get-function-configuration --function-name algo-api-dev | jq '.Environment.Variables | {COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID}'

# If missing, update Terraform variables and re-apply
cd terraform
terraform apply -var cognito_user_pool_id="us-east-1_abc123def456" -var cognito_client_id="1a2b3c..."
```

### 7.4 Frontend can't call API (CORS error)

```bash
# Check if CLOUDFRONT_DOMAIN is set in Lambda
aws lambda get-function-configuration --function-name algo-api-dev | jq '.Environment.Variables.CLOUDFRONT_DOMAIN'

# Check API Gateway CORS settings
aws apigateway get-stage --rest-api-id <API_ID> --stage-name dev | jq '.methodSettings'
```

---

## 8. References

- **Credential Manager:** `config/credential_manager.py`
- **Auth Middleware:** `webapp/lambda/middleware/auth.js`
- **API Key Service:** `webapp/lambda/utils/apiKeyService.js`
- **Credential Validator:** `config/credential_validator.py`
- **Terraform IAM:** `terraform/modules/iam/main.tf`
- **Terraform Services:** `terraform/modules/services/main.tf`
- **LOCAL_CRED_SETUP.md:** Legacy setup guide (see this file for authoritative info)

---

## 9. Next Steps

1. **Verify local setup:**
   ```powershell
   python3 config/credential_validator.py
   ```

2. **Set GitHub Secrets** (if not already done)
3. **Verify AWS Secrets Manager** contains DB password
4. **Deploy via GitHub Actions:**
   ```bash
   git push origin main
   ```
5. **Test Lambda auth:**
   ```bash
   # Frontend should be able to log in and make authenticated requests
   ```

