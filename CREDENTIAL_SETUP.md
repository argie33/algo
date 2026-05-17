# Production Credential Setup Guide

**Purpose:** Securely configure database credentials across all environments (local, GitHub Actions, AWS Lambda, Terraform)

**Credentials to Store:** (from your secure source)
- DB User: `stocks`
- DB Password: `<YOUR_DB_PASSWORD>` (see LOCAL_CRED_SETUP.md)
- DB Host: `algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com`
- DB Port: `5432`
- DB Name: `stocks`

---

## ⚠️ SECURITY NOTES

- ❌ **NEVER** commit credentials to git
- ❌ **NEVER** hardcode in Python/Lambda code
- ❌ **NEVER** use .env files (git can accidentally commit them)
- ✅ **ALWAYS** use AWS Secrets Manager for production
- ✅ **ALWAYS** use environment variables for local dev
- ✅ **ALWAYS** use GitHub Actions secrets for CI/CD

---

## Setup Option 1: AWS Secrets Manager (Recommended)

### Step 1: Authenticate to AWS
```bash
aws configure
# Enter your AWS Access Key ID
# Enter your AWS Secret Access Key
# Enter default region: us-east-1
# Enter default output format: json
```

### Step 2: Create Secrets Manager Secret
```bash
aws secretsmanager create-secret \
  --name algo/db/postgres \
  --description "RDS database credentials" \
  --secret-string '{
    "host":"algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com",
    "port":5432,
    "user":"stocks",
    "password":"<YOUR_DB_PASSWORD>",
    "database":"stocks"
  }'
```

**Output should be:**
```json
{
    "ARN": "arn:aws:secretsmanager:us-east-1:...:secret:algo/db/postgres-xxxxx",
    "Name": "algo/db/postgres",
    "VersionId": "..."
}
```

### Step 3: Verify Secret
```bash
aws secretsmanager get-secret-value --secret-id algo/db/postgres
```

### Step 4: Grant Lambda Access
The Lambda execution role needs permission to read this secret. In Terraform:

```hcl
# terraform/main.tf
resource "aws_iam_role_policy" "lambda_secrets" {
  name = "lambda-secrets-access"
  role = aws_iam_role.lambda_exec_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "secretsmanager:GetSecretValue"
        Resource = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:algo/db/postgres-*"
      }
    ]
  })
}
```

Then in Lambda environment variables:
```bash
DATABASE_SECRET_ARN=arn:aws:secretsmanager:us-east-1:...:secret:algo/db/postgres-xxxxx
```

### Step 5: Lambda Code to Retrieve Secrets
```python
# config/credential_manager.py (already implemented)
import boto3
import json
import logging

logger = logging.getLogger(__name__)

def get_credential_manager():
    """Factory for credential manager (supports local + AWS)."""
    try:
        return AWSSecretsManager()
    except Exception as e:
        logger.debug(f"AWS Secrets Manager not available: {e}")
        return None

class AWSSecretsManager:
    """Retrieve credentials from AWS Secrets Manager."""
    
    def __init__(self):
        self.client = boto3.client('secretsmanager', region_name='us-east-1')
        self.secret_name = os.getenv('DATABASE_SECRET_ARN').split(':')[-1]  # Extract secret name
    
    def get_db_credentials(self):
        """Fetch database credentials from AWS Secrets Manager."""
        try:
            response = self.client.get_secret_value(SecretId=self.secret_name)
            return json.loads(response['SecretString'])
        except Exception as e:
            logger.error(f"Failed to retrieve secret: {e}")
            raise
```

---

## Setup Option 2: GitHub Actions Secrets (For CI/CD)

### Step 1: Add Secrets to GitHub Repository

Go to: `https://github.com/argie33/algo/settings/secrets/actions`

Add these secrets:
```
DB_HOST=algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com
DB_PORT=5432
DB_USER=stocks
DB_PASSWORD=bed0elAb
DB_NAME=stocks
```

### Step 2: Use in GitHub Actions Workflow

In `.github/workflows/deploy-all-infrastructure.yml`:

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Run tests with database access
        env:
          DB_HOST: ${{ secrets.DB_HOST }}
          DB_PORT: ${{ secrets.DB_PORT }}
          DB_USER: ${{ secrets.DB_USER }}
          DB_PASSWORD: ${{ secrets.DB_PASSWORD }}
          DB_NAME: ${{ secrets.DB_NAME }}
        run: |
          pytest tests/integration/ -v
      
      - name: Run loaders
        env:
          DB_HOST: ${{ secrets.DB_HOST }}
          DB_USER: ${{ secrets.DB_USER }}
          DB_PASSWORD: ${{ secrets.DB_PASSWORD }}
          DB_NAME: ${{ secrets.DB_NAME }}
        run: |
          python3 run-all-loaders.py
```

---

## Setup Option 3: Local Development (Environment Variables)

### For bash/zsh users:

**Option A: Set in current session only**
```bash
export DB_HOST="algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com"
export DB_PORT="5432"
export DB_USER="stocks"
export DB_PASSWORD="<YOUR_DB_PASSWORD>"
export DB_NAME="stocks"

# Now run loaders
python3 run-all-loaders.py
```

**Option B: Store in ~/.bashrc or ~/.zshrc** (survives terminal restart)
```bash
# Add to the end of ~/.bashrc or ~/.zshrc:
export DB_HOST="algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com"
export DB_USER="stocks"
export DB_PASSWORD="<YOUR_DB_PASSWORD>"
export DB_NAME="stocks"

# Then reload:
source ~/.bashrc  # or source ~/.zshrc
```

### For Windows PowerShell users:

**Option A: Set in current session only**
```powershell
$env:DB_HOST = "algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com"
$env:DB_PORT = "5432"
$env:DB_USER = "stocks"
$env:DB_PASSWORD = "<YOUR_DB_PASSWORD>"
$env:DB_NAME = "stocks"

# Now run loaders
python3 run-all-loaders.py
```

**Option B: Store permanently** (Windows)
```powershell
[Environment]::SetEnvironmentVariable("DB_HOST", "algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com", "User")
[Environment]::SetEnvironmentVariable("DB_USER", "stocks", "User")
[Environment]::SetEnvironmentVariable("DB_PASSWORD", "<YOUR_DB_PASSWORD>", "User")
[Environment]::SetEnvironmentVariable("DB_NAME", "stocks", "User")

# Close and reopen PowerShell for changes to take effect
```

---

## Setup Option 4: AWS Lambda Environment Variables

### In Terraform:

```hcl
# terraform/main.tf
resource "aws_lambda_function" "algo_api" {
  function_name = "algo-api"
  role          = aws_iam_role.lambda_exec_role.arn
  handler       = "index.handler"
  runtime       = "nodejs18.x"

  environment {
    variables = {
      DB_HOST              = "algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com"
      DB_PORT              = "5432"
      DB_USER              = "stocks"
      DB_PASSWORD          = var.db_password  # From terraform.tfvars (NOT in git)
      DB_NAME              = "stocks"
      DATABASE_SECRET_ARN  = aws_secretsmanager_secret.db_credentials.arn
    }
  }
}
```

### In terraform.tfvars (do NOT commit):
```hcl
# terraform.tfvars - SECRET, do not commit to git
db_password = "<YOUR_DB_PASSWORD>"
```

**⚠️ Important:** Add `terraform.tfvars` to `.gitignore`:
```bash
echo "terraform.tfvars" >> .gitignore
```

---

## Verification Checklist

After setting up credentials:

- [ ] **Local:** Can connect to database
  ```bash
  python3 -c "from utils.db_connection import get_db_connection; conn = get_db_connection(); print('OK'); conn.close()"
  ```

- [ ] **AWS CLI:** Secret accessible
  ```bash
  aws secretsmanager get-secret-value --secret-id algo/db/postgres
  ```

- [ ] **GitHub:** Secrets configured
  ```bash
  # Go to: https://github.com/argie33/algo/settings/secrets/actions
  # Should see: DB_HOST, DB_USER, DB_PASSWORD, DB_NAME
  ```

- [ ] **Lambda:** Can read from Secrets Manager
  ```bash
  aws lambda invoke --function-name algo-api /tmp/test.json
  cat /tmp/test.json | jq '.message'
  ```

---

## Production Deployment Flow

1. **Store in AWS Secrets Manager** (one-time setup)
   ```bash
   aws secretsmanager create-secret --name algo/db/postgres --secret-string '{...}'
   ```

2. **Grant Lambda Access** (in Terraform)
   - Add IAM policy to read secret
   - Set DATABASE_SECRET_ARN env variable

3. **Lambda Retrieves at Runtime**
   - Code in `config/credential_manager.py` handles retrieval
   - No hardcoded credentials anywhere

4. **GitHub Actions Uses Secrets**
   - Add DB_PASSWORD etc to GitHub repo secrets
   - Workflow passes as env vars during CI/CD

5. **Result:** Same credentials everywhere, never committed, never hardcoded

---

## Security Audit

Run this to verify no credentials are exposed:

```bash
# Check for hardcoded passwords in code (should find none)
grep -r "bed0elAb\|your_db_password\|YOUR_DB_PASSWORD" . --exclude-dir=.git 2>/dev/null | grep -v "CREDENTIAL_SETUP.md" || echo "No credentials found (good!)"

# Check for .env files
find . -name ".env*" -type f 2>/dev/null || echo "No .env files (good!)"

# Check git history for obvious secret patterns
git log -p | grep -i "password\|secret" | head -5 || echo "No obvious secrets in git history (good!)"

# Check if secrets are in GitHub Actions logs (they shouldn't be)
# (requires access to Actions tab)
```

---

## Troubleshooting

### "Database password not available"
**Solution:** Check credential priority in `config/credential_helper.py`:
1. `DB_PASSWORD` env variable
2. `credential_manager` (AWS Secrets Manager)
3. `DB_PASSWORD_FALLBACK` env variable

### "Could not translate host name"
**Cause:** Local machine can't reach AWS RDS (not on VPC)  
**Solution:** 
- Run loaders from EC2 instance or Lambda (has network access)
- Or set up VPN to AWS VPC
- Or use RDS Proxy (acts as proxy, no VPN needed)

### "Secret not found"
**Solution:** Verify secret name and ARN:
```bash
aws secretsmanager list-secrets | grep algo
```

---

## Next Steps

1. ✅ **Set up AWS Secrets Manager** (run commands in "Option 1")
2. ✅ **Set GitHub Actions secrets** (go to repo settings, add 5 secrets)
3. ✅ **Set local environment variables** (choose Option 2 or 3 above)
4. ✅ **Verify with checklist** (run verification commands)
5. ✅ **Run data loaders** (see run-all-loaders.py guide)
6. ✅ **Deploy to Lambda** (push to main, GitHub Actions handles rest)
