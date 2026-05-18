# Credential Setup Checklist
**Last Updated:** 2026-05-17

---

## PHASE 1: LOCAL DEVELOPMENT SETUP (Do This First)

### Step 1: Set Environment Variables
```bash
# Add to your shell profile (~/.bashrc, ~/.zshrc, or ~/.bash_profile)
export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=stocks
export DB_PASSWORD=your_secure_password
export DB_NAME=stocks

# Optional: For Alpaca trading API (paper trading)
export ALPACA_API_KEY=your_alpaca_key
export ALPACA_API_SECRET=your_alpaca_secret
export APCA_API_BASE_URL=https://paper-api.alpaca.markets
```

### Step 2: Verify PostgreSQL is Running
```bash
# Check if PostgreSQL is running on localhost:5432
psql -h localhost -U stocks -d stocks -c "SELECT version();"

# If not running, start it (macOS with Homebrew)
brew services start postgresql

# Or (Ubuntu/WSL)
sudo service postgresql start
```

### Step 3: Initialize Database Schema
```bash
python3 utils/init_database.py
```

**Expected Output:**
```
INFO: Creating table stock_symbols...
INFO: Creating index idx_symbol...
... (many more tables)
✅ Database schema initialized successfully
```

### Step 4: Test Credential System
```bash
# Test the credential helper
python3 config/credential_helper.py

# Expected output:
# INFO: DB Config: localhost:5432/stocks
```

### Step 5: Test Database Connection
```bash
python3 -c "from utils.db_connection import get_db_connection; conn = get_db_connection(); print('✅ Connected'); conn.close()"
```

### Step 6: Run Credential Validator
```bash
python3 config/credential_validator.py

# Expected:
# ✓ All required credentials validated
```

### Step 7: Run Full Verification Suite
```bash
python3 verify_credentials_local.py

# Should show:
# ✅ OK:       XX checks passed
# ⚠️  Warnings: X checks with warnings (if Alpaca keys not set)
# ❌ Errors:    0 checks failed
```

---

## PHASE 2: GITHUB ACTIONS SECRETS SETUP

### Step 1: Get Your AWS Account ID
```bash
aws sts get-caller-identity --query Account --output text
# Output: 123456789012
```

### Step 2: Create GitHub Secrets

Go to: **GitHub Repository → Settings → Secrets and variables → Actions → New repository secret**

Create these secrets (copy-paste each value):

#### A. AWS Credentials
| Secret Name | Value | Where to Get |
|-------------|-------|--------------|
| `AWS_ACCOUNT_ID` | `123456789012` | `aws sts get-caller-identity` |
| `AWS_ACCESS_KEY_ID` | Your AWS access key | AWS IAM Console (if using legacy) |
| `AWS_SECRET_ACCESS_KEY` | Your AWS secret key | AWS IAM Console (if using legacy) |

#### B. Database Credentials
| Secret Name | Value | Where to Get |
|-------------|-------|--------------|
| `RDS_PASSWORD` | Your RDS master password | Same as local `DB_PASSWORD` |

#### C. Trading API Credentials
| Secret Name | Value | Where to Get |
|-------------|-------|--------------|
| `ALPACA_API_KEY_ID` | `PK...` | Alpaca API Keys page |
| `ALPACA_API_SECRET_KEY` | `...` | Alpaca API Keys page |

#### D. Other Credentials
| Secret Name | Value | Where to Get |
|-------------|-------|--------------|
| `JWT_SECRET` | Random 32+ char string | Generate: `openssl rand -base64 32` |
| `FRED_API_KEY` | Your FRED API key | Federal Reserve Economic Data site |
| `ALERT_EMAIL_ADDRESS` | your-email@example.com | Your email |
| `API_GATEWAY_URL` | Will be set later | After first deployment |

### Step 3: Verify Secrets in GitHub
```bash
# From your local machine, verify secrets are set:
gh secret list --repo argie33/algo

# Output should show:
# AWS_ACCOUNT_ID
# RDS_PASSWORD
# ALPACA_API_KEY_ID
# ... etc
```

---

## PHASE 3: AWS SETUP (After First Terraform Run)

### Step 1: Verify Secrets Manager Secrets Were Created
```bash
aws secretsmanager list-secrets --region us-east-1 | jq '.SecretList[] | select(.Name | contains("stocks"))'

# Output should show:
# - stocks-rds-credentials-dev
# - stocks-algo-secrets-dev
# - stocks-email-config-dev
```

### Step 2: Verify RDS Credentials Secret
```bash
aws secretsmanager get-secret-value \
  --secret-id stocks-rds-credentials-dev \
  --region us-east-1 \
  --query 'SecretString' | jq .

# Output:
# {
#   "username": "postgres",
#   "password": "...",
#   "host": "stocks-db.xxx.rds.amazonaws.com",
#   "port": 5432,
#   "dbname": "stocks",
#   "engine": "postgresql"
# }
```

### Step 3: Verify Algo Secrets
```bash
aws secretsmanager get-secret-value \
  --secret-id stocks-algo-secrets-dev \
  --region us-east-1 \
  --query 'SecretString' | jq .

# Output:
# {
#   "APCA_API_KEY_ID": "...",
#   "APCA_API_SECRET_KEY": "...",
#   ...
# }
```

### Step 4: Check Lambda Environment Variables
```bash
# API Lambda
aws lambda get-function-configuration \
  --function-name stocks-api-dev \
  --region us-east-1 | jq '.Environment.Variables'

# Output should include:
# {
#   "DB_SECRET_ARN": "arn:aws:secretsmanager:...",
#   "DB_ENDPOINT": "stocks-db.xxx.rds.amazonaws.com",
#   ...
# }
```

### Step 5: Verify Lambda Has Secrets Manager Permissions
```bash
# Get Lambda execution role
ROLE=$(aws lambda get-function-configuration \
  --function-name stocks-api-dev \
  --region us-east-1 | jq -r '.Role' | cut -d/ -f2)

# Check role policies
aws iam get-role-policy \
  --role-name $ROLE \
  --policy-name stocks-api-policy \
  --region us-east-1 | jq '.PolicyDocument.Statement[] | select(.Action[] | contains("secretsmanager"))'

# Should show:
# "secretsmanager:GetSecretValue" in actions
```

---

## PHASE 4: LOCAL DEV → GITHUB → AWS INTEGRATION TEST

### Step 1: Trigger a Deployment
```bash
# Push to main to trigger deploy-all-infrastructure workflow
git push origin main

# Watch at: https://github.com/argie33/algo/actions
```

### Step 2: Verify Terraform Used Secrets
```bash
# Check Terraform logs in GitHub Actions (deploy-all-infrastructure workflow)
# Look for:
# ✓ aws_secretsmanager_secret_version.rds_credentials created
# ✓ aws_secretsmanager_secret_version.algo_secrets created
```

### Step 3: Test API Lambda
```bash
# Get API Gateway URL
API_URL=$(aws apigateway get-rest-apis \
  --region us-east-1 \
  --query 'items[0].name' | xargs -I {} aws apigateway get-rest-apis \
  --region us-east-1 \
  --query 'items[?name==`{}`].id' --output text)

curl -i https://$API_URL/api/health

# Should respond:
# HTTP/2 200
# { "status": "healthy" }
```

### Step 4: Test Loaders in ECS
```bash
# Trigger a loader via ECS
aws ecs run-task \
  --cluster stocks-cluster-dev \
  --task-definition stocks-loader-dev \
  --region us-east-1

# Check CloudWatch logs
aws logs tail /ecs/stocks-loader-dev --follow --region us-east-1
```

---

## PHASE 5: ONGOING CREDENTIAL MANAGEMENT

### Rotating Database Password

**Local:**
1. Update `DB_PASSWORD` environment variable
2. Update PostgreSQL password: `ALTER USER stocks WITH PASSWORD 'new_password';`

**GitHub Actions:**
1. Update `RDS_PASSWORD` secret in GitHub

**AWS:**
1. Update Terraform variable: `terraform apply -var="db_master_password=new_password"`
2. This updates both RDS and Secrets Manager

### Rotating API Keys

**If Alpaca Keys Compromise:**
1. Go to Alpaca Dashboard → Settings → API Keys → Revoke old key
2. Create new key
3. Update GitHub secret: `ALPACA_API_KEY_ID` and `ALPACA_API_SECRET_KEY`
4. Run: `terraform apply` (or push to main)

**If JWT Secret Compromise:**
1. Update GitHub secret: `JWT_SECRET`
2. Run: `terraform apply` or push to main
3. Invalidate all existing JWT tokens (application-specific)

### Monitoring Credential Access

```bash
# View CloudTrail logs for Secrets Manager access
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=GetSecretValue \
  --region us-east-1 \
  --max-results 10
```

---

## TROUBLESHOOTING

### "Database password not available"
```bash
# Check environment variable
echo $DB_PASSWORD

# If empty:
export DB_PASSWORD=your_password

# Or check Secrets Manager (if in AWS)
aws secretsmanager get-secret-value --secret-id stocks-rds-credentials-dev
```

### "Alpaca API returned 401 Unauthorized"
```bash
# Verify Alpaca keys in Secrets Manager
aws secretsmanager get-secret-value --secret-id stocks-algo-secrets-dev | jq .SecretString

# Check if keys are correct at Alpaca dashboard
# If compromised, rotate keys (see above)
```

### "Lambda cannot fetch from Secrets Manager"
```bash
# Check Lambda role has permission
ROLE=$(aws lambda get-function-configuration --function-name stocks-api-dev | jq -r '.Role' | cut -d/ -f2)
aws iam get-role-policy --role-name $ROLE --policy-name stocks-api-policy | jq .PolicyDocument

# Should include:
# "secretsmanager:GetSecretValue"
```

### "Terraform variable not passed to Lambda"
```bash
# Check Lambda environment variables
aws lambda get-function-configuration --function-name stocks-api-dev | jq '.Environment.Variables'

# Should show:
# "DB_SECRET_ARN": "arn:aws:secretsmanager:..."
```

---

## Verification Commands (Quick Reference)

```bash
# LOCAL DEV
python3 verify_credentials_local.py                # Full local audit
python3 config/credential_validator.py             # Validate creds
python3 -c "from utils.db_connection import get_db_connection; get_db_connection()" # Test DB

# GITHUB
gh secret list --repo argie33/algo                 # List secrets
gh secret set MY_SECRET --body "value" --repo argie33/algo # Create secret

# AWS
aws secretsmanager list-secrets --region us-east-1 # List secrets
aws secretsmanager get-secret-value --secret-id SECRETNAME # Get secret value
aws lambda get-function-configuration --function-name stocks-api-dev # Check Lambda env
aws cloudtrail lookup-events --lookup-attributes AttributeKey=EventName,AttributeValue=GetSecretValue # Audit access
```

---

## Support

If you encounter issues:

1. **Check LOCAL_CRED_SETUP.md** for detailed local setup
2. **Run `python3 verify_credentials_local.py`** to diagnose
3. **Check GitHub Actions logs** at https://github.com/argie33/algo/actions
4. **Check AWS CloudWatch logs** for Lambda errors
5. **Review CREDENTIAL_AUDIT_2026-05-17.md** for architecture details
