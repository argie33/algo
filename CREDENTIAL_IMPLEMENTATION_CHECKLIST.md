# Credential Implementation Checklist

Complete reference for wiring up credentials across all environments.

---

## Status Overview

**Current Implementation:**
- ✅ Credential Manager (Python) - properly designed with Secrets Manager support
- ✅ Auth Middleware (Node.js) - validates Cognito JWT tokens
- ✅ API Key Service (Node.js) - integrates with Cognito
- ✅ Lambda Environment Variables - properly configured via Terraform
- ✅ CLAUDE.md Rules - No .env files, credentials via environment/Secrets Manager
- ❌ **LOCAL DEVELOPMENT** - DB_HOST and DB_PASSWORD not set in PowerShell

**Audit Results:**
```
Environment: Local Development
  [ERROR] DB_HOST not set (REQUIRED)
  [ERROR] DB_PASSWORD not set (REQUIRED)
  [WARN] Alpaca credentials not configured (optional for trading)
  [OK] Architecture properly supports credentials pipeline
```

---

## Part 1: Local Development Setup (PowerShell - IMMEDIATE ACTION NEEDED)

### Step 1A: Quick Setup (One-time)

```powershell
# Run the setup script (interactive)
.\scripts\setup-powershell-env.ps1

# Enter your PostgreSQL password when prompted
# Database connection will be tested automatically
```

### Step 1B: Manual Setup (If script fails)

```powershell
# Set credentials manually
$env:DB_HOST = "localhost"
$env:DB_PORT = "5432"
$env:DB_USER = "stocks"
$env:DB_NAME = "stocks"
$env:DB_PASSWORD = "your_postgres_password"  # REQUIRED - replace with actual password

# Verify
Write-Host "DB_HOST: $env:DB_HOST"
Write-Host "DB_PASSWORD: $(if ($env:DB_PASSWORD) { '[SET]' } else { '[NOT SET]' })"
```

### Step 1C: Permanent Setup (Optional - for every PowerShell session)

```powershell
# Save to PowerShell profile
.\scripts\setup-powershell-env.ps1 -DBPassword "your_password" -Persistent

# Next time: PowerShell will load these automatically
# Verify by restarting PowerShell and checking:
Write-Host $env:DB_HOST
```

### Step 1D: Verify Setup

```powershell
# Run credential validator
python3 config/credential_validator.py

# Expected output:
# [OK] DB credentials loaded
# [OK] Database connection available
```

---

## Part 2: GitHub Actions Setup (CI/CD Pipeline)

### Step 2A: Create GitHub Secrets

Go to: https://github.com/argie33/algo/settings/secrets/actions

Set these secrets (all REQUIRED for deploy):

| Secret Name | Value | Example |
|---|---|---|
| `AWS_ACCOUNT_ID` | Your AWS account ID | `123456789012` |
| `API_GATEWAY_URL` | URL to your API Gateway | `https://api.example.com` |
| `DB_SECRET_ARN` | ARN of RDS secret in Secrets Manager | `arn:aws:secretsmanager:us-east-1:123456789012:secret:algo/db/postgres-abcde` |
| `COGNITO_USER_POOL_ID` | Cognito user pool ID | `us-east-1_abc123def456` |
| `COGNITO_CLIENT_ID` | Cognito app client ID | `1a2b3c4d5e6f7g8h9i0j1k2l3m` |

### Step 2B: Verify GitHub Secrets Are Set

```bash
# List GitHub secrets (public names only - values not shown)
gh secret list

# Expected output:
# AWS_ACCOUNT_ID               (you set a value)
# API_GATEWAY_URL              (you set a value)
# DB_SECRET_ARN                (you set a value)
# COGNITO_USER_POOL_ID         (you set a value)
# COGNITO_CLIENT_ID            (you set a value)
```

### Step 2C: How GitHub Actions Uses Secrets

The deploy workflow (`.github/workflows/deploy-code.yml`) does:

```yaml
# Step 1: OIDC authentication using GitHub Secrets
- name: Configure AWS credentials
  uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/algo-svc-github-actions-dev

# Step 2: Frontend build uses API_GATEWAY_URL
- name: Install & Build
  env:
    VITE_API_URL: ${{ secrets.API_GATEWAY_URL }}

# Step 3: Lambda deployment uses AWS credentials (from OIDC role)
- name: Deploy API Lambda
  # Uses AWS credentials to update Lambda code
```

---

## Part 3: AWS Setup (Secrets Manager & Cognito)

### Step 3A: Create RDS Secret in Secrets Manager

```bash
# One-time setup - store database credentials
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

# Verify
aws secretsmanager get-secret-value \
  --secret-id algo/db/postgres \
  --region us-east-1 | jq '.SecretString'
```

### Step 3B: Update Lambda Environment with Secret ARN

Get the secret ARN from the create response or:

```bash
aws secretsmanager describe-secret \
  --secret-id algo/db/postgres \
  --region us-east-1 | jq '.ARN'

# Output: arn:aws:secretsmanager:us-east-1:123456789012:secret:algo/db/postgres-abcde
# This ARN goes into GitHub Secret: DB_SECRET_ARN
```

### Step 3C: Cognito User Pool (Auto-created by Terraform)

Terraform creates the Cognito user pool. Get the IDs:

```bash
# Get user pool ID
aws cognito-idp list-user-pools \
  --max-results 10 \
  --region us-east-1 | jq '.UserPools[] | select(.Name | contains("stocks"))'

# Get client ID
POOL_ID="us-east-1_abc123def456"
aws cognito-idp list-user-pool-clients \
  --user-pool-id "$POOL_ID" \
  --max-results 10 \
  --region us-east-1 | jq '.UserPoolClients[0].ClientId'

# These IDs go into GitHub Secrets: COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID
```

### Step 3D: Verify Lambda Has Secrets Manager Access

Lambda execution role must have `secretsmanager:GetSecretValue` permission:

```bash
# Check Lambda role
FUNCTION_NAME="algo-api-dev"
ROLE_ARN=$(aws lambda get-function-configuration \
  --function-name "$FUNCTION_NAME" \
  --region us-east-1 | jq -r '.Role')

ROLE_NAME=$(basename "$ROLE_ARN")

# Check if Secrets Manager permission exists
aws iam get-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-name "algo-lambda-secrets-policy" \
  --region us-east-1 2>/dev/null | jq '.RolePolicyDocument.Statement[] | select(.Action[] | contains("secretsmanager"))'

# If empty, permission is missing - update Terraform iam module
```

---

## Part 4: Lambda Environment Variables (via Terraform)

These are automatically set by Terraform when Lambda functions are created:

### 4A: Verify in AWS Console

```bash
# Check Lambda environment variables
aws lambda get-function-configuration \
  --function-name algo-api-dev \
  --region us-east-1 | jq '.Environment.Variables'

# Expected output:
{
  "DB_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:...:secret:algo/db/postgres-...",
  "DB_ENDPOINT": "your-rds-endpoint.rds.amazonaws.com",
  "DB_NAME": "stocks",
  "COGNITO_USER_POOL_ID": "us-east-1_abc123def456",
  "COGNITO_CLIENT_ID": "1a2b3c4d5e6f7g8h9i0j1k2l3m",
  "NODE_ENV": "production",
  "CLOUDFRONT_DOMAIN": "https://d123456.cloudfront.net",
  ...
}
```

### 4B: How Lambda Retrieves Secrets

When Lambda starts:

```javascript
// Node.js (API Lambda)
const verifier = CognitoJwtVerifier.create({
  userPoolId: process.env.COGNITO_USER_POOL_ID,
  clientId: process.env.COGNITO_CLIENT_ID,
});

// Python (Algo Lambda)
db_creds = credential_manager.get_db_credentials()
# credential_manager fetches from:
# 1. Env var DATABASE_SECRET_ARN
# 2. Calls Secrets Manager get-secret-value
# 3. Parses JSON and returns credentials
```

---

## Part 5: Authentication Flow (Frontend → Cognito → Lambda)

### 5A: Frontend (React/Vite) → Cognito

```javascript
// Frontend initialization
import { Amplify, Auth } from 'aws-amplify';

Amplify.configure({
  Auth: {
    region: 'us-east-1',
    userPoolId: 'us-east-1_abc123def456',  // From COGNITO_USER_POOL_ID
    userPoolWebClientId: '1a2b3c4d5e6f7g8h9i0j1k2l3m',  // From COGNITO_CLIENT_ID
  }
});

// User logs in
const user = await Auth.signIn(email, password);
const token = user.signInUserSession.accessToken.jwtToken;

// Token is stored in browser localStorage
```

### 5B: Frontend → API Gateway → Lambda

```javascript
// Frontend makes authenticated request
const response = await fetch('https://api.example.com/api/signals', {
  headers: {
    'Authorization': `Bearer ${token}`,  // JWT token
    'Content-Type': 'application/json'
  }
});
```

### 5C: API Gateway → Lambda

```
Request flow:
1. API Gateway receives request with Authorization header
2. API Gateway authorizer validates token with Cognito
3. If valid, request passes to Lambda
4. Lambda receives req.user context with decoded token
5. Lambda can check user permissions (role, groups)
```

### 5D: Lambda Auth Middleware

```javascript
// middleware/auth.js - validateJwtToken
const result = await validateJwtToken(token);

// validateJwtToken:
// 1. Uses CognitoJwtVerifier (from COGNITO_USER_POOL_ID)
// 2. Verifies signature and expiration
// 3. Extracts user info (sub, username, groups, role)
// 4. Returns user context to request handler
```

---

## Part 6: Credential Validation at Startup

### 6A: Python Applications

```bash
# Run credential validator before deployment
python3 config/credential_validator.py

# Output:
# [OK] DB credentials loaded
# [OK] Alpaca credentials available (if configured)
# [FAIL] If anything missing, shows clear error
```

### 6B: Lambda Health Check

```bash
# Test Lambda can access Secrets Manager
aws lambda invoke \
  --function-name algo-api-dev \
  --payload '{"health":"check"}' \
  /tmp/response.json \
  --region us-east-1

# Check if successful
cat /tmp/response.json
```

---

## Part 7: Troubleshooting Guide

### Issue: "Database password not available"

```powershell
# Check local PowerShell
Write-Host $env:DB_PASSWORD
# If empty:
$env:DB_PASSWORD = "your_password"

# Check GitHub secret
gh secret list | grep DB_SECRET_ARN

# Check Lambda environment
aws lambda get-function-configuration --function-name algo-api-dev | jq '.Environment.Variables.DB_SECRET_ARN'
```

### Issue: "COGNITO_USER_POOL_ID not configured"

```bash
# Check Lambda environment
aws lambda get-function-configuration --function-name algo-api-dev | jq '.Environment.Variables.COGNITO_USER_POOL_ID'

# If missing, update Terraform variables
cd terraform
terraform apply -var cognito_user_pool_id="us-east-1_abc123def456"
```

### Issue: "Lambda can't read Secrets Manager"

```bash
# Check Lambda role has permission
ROLE_NAME="algo-svc-api-dev"
aws iam get-role-policy --role-name "$ROLE_NAME" --policy-name "algo-lambda-secrets-policy"

# Expected permission:
# "Action": ["secretsmanager:GetSecretValue"]
# "Resource": "arn:aws:secretsmanager:us-east-1:*:secret:algo/*"

# If missing, update terraform/modules/iam/main.tf
```

### Issue: Frontend can't authenticate

```javascript
// Check Cognito credentials in frontend
console.log(window.location.origin);  // Should match CORS allowed origins
console.log(process.env.VITE_API_URL);  // Should be set from GitHub Secret

// Check Lambda CORS headers
// In Lambda logs, look for: "CORS allowed origin" messages

// Check Cognito user pool setup
aws cognito-idp describe-user-pool \
  --user-pool-id "us-east-1_abc123def456" \
  --region us-east-1
```

---

## Part 8: Complete Credential Checklist

### Local Development ✓ / ✗

- [ ] `DB_HOST` set in PowerShell
- [ ] `DB_PASSWORD` set in PowerShell
- [ ] `DB_PORT` set (default: 5432)
- [ ] `DB_USER` set (default: stocks)
- [ ] `DB_NAME` set (default: stocks)
- [ ] Credential validator runs: `python3 config/credential_validator.py`
- [ ] Can connect to database: `python3 init_database.py`

### GitHub Secrets ✓ / ✗

- [ ] `AWS_ACCOUNT_ID` set
- [ ] `API_GATEWAY_URL` set
- [ ] `DB_SECRET_ARN` set
- [ ] `COGNITO_USER_POOL_ID` set
- [ ] `COGNITO_CLIENT_ID` set
- [ ] Verified: `gh secret list`

### AWS Secrets Manager ✓ / ✗

- [ ] RDS secret created: `algo/db/postgres`
- [ ] Secret contains: host, port, username, password, dbname
- [ ] Verified: `aws secretsmanager get-secret-value --secret-id algo/db/postgres`

### AWS IAM ✓ / ✗

- [ ] GitHub OIDC provider configured
- [ ] `algo-svc-github-actions-dev` role exists
- [ ] Lambda execution role has Secrets Manager permissions
- [ ] Lambda role has access to other required services (ECS, S3, etc.)

### AWS Lambda ✓ / ✗

- [ ] API Lambda has `DB_SECRET_ARN` environment variable
- [ ] API Lambda has `COGNITO_USER_POOL_ID` environment variable
- [ ] API Lambda has `COGNITO_CLIENT_ID` environment variable
- [ ] API Lambda can read Secrets Manager (test via Lambda console)
- [ ] Algo Lambda has required environment variables

### AWS Cognito ✓ / ✗

- [ ] User pool created
- [ ] App client created
- [ ] Password policy enforced
- [ ] User pool ID matches GitHub Secret
- [ ] Client ID matches GitHub Secret

### Frontend ✓ / ✗

- [ ] `VITE_API_URL` environment set from GitHub Secret
- [ ] Cognito config matches user pool ID and client ID
- [ ] CORS allowed origins include CloudFront domain

---

## Part 9: Deployment Order

1. **Local Setup First:**
   - Set PowerShell credentials
   - Verify with credential_validator.py
   - Run loaders and test locally

2. **AWS Setup Second:**
   - Create RDS secret in Secrets Manager
   - Create/verify Cognito user pool
   - Ensure Lambda roles have permissions

3. **GitHub Secrets Third:**
   - Set all 5 required secrets
   - Verify with `gh secret list`

4. **Deploy to Production:**
   - Push to main branch
   - GitHub Actions will:
     - Assume OIDC role using AWS_ACCOUNT_ID
     - Use secrets to configure Lambda
     - Deploy code with proper environment

---

## References

- **Local Setup:** `LOCAL_CRED_SETUP.md` (PowerShell instructions)
- **Complete Pipeline:** `CREDENTIALS_SETUP.md` (detailed technical reference)
- **Credential Code:** `config/credential_manager.py`, `config/credential_validator.py`
- **Terraform:** `terraform/modules/iam/`, `terraform/modules/services/`
- **Lambda Auth:** `webapp/lambda/utils/apiKeyService.js`, `webapp/lambda/middleware/auth.js`

