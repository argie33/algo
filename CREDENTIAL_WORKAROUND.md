# AWS Credential Recovery — Manual Workaround

If automated credential rotation fails, use this manual process.

## Problem
AWS Secrets Manager contains invalid `algo/developer-credentials`. Terraform workflows need valid credentials to create new ones (catch-22).

## Solution: Manual IAM Key Creation

### Step 1: Create New IAM Access Key (AWS Console)
1. Login to AWS Console: https://console.aws.amazon.com/iam/
2. Navigate to: Users → algo-developer
3. Click: Security credentials tab
4. Under Access keys: Click "Create access key"
5. Select: "Command Line Interface (CLI)"
6. Copy the access key ID and secret key
   - Save these securely (they won't be shown again)

### Step 2: Update Local Credentials File
```powershell
# Edit C:\Users\arger\.aws\credentials
# Replace with new credentials:

[algo-developer]
aws_access_key_id = AKIA...       # (new ID from step 1)
aws_secret_access_key = ...       # (new secret from step 1)
region = us-east-1
```

### Step 3: Verify Credentials Work
```powershell
aws sts get-caller-identity --profile algo-developer
```
Expected output:
```json
{
    "UserId": "AIDAZDTL...",
    "Account": "626216981288",
    "Arn": "arn:aws:iam::626216981288:user/algo-developer"
}
```

### Step 4: Deploy System Fixes
Once credentials verified:
```powershell
cd C:\Users\arger\code\algo
scripts/deploy-all-fixes.ps1
```

This will:
- Initialize Terraform backend
- Plan all infrastructure changes
- Apply fixes (timezone, failsafe, alerts, etc.)

## Troubleshooting

### "Access Denied" errors
- Verify algo-developer IAM user has proper permissions
- Check: IAM → Users → algo-developer → Permissions
- Should have: AdministratorAccess or custom policy with S3, Lambda, EventBridge, IAM perms

### "No such IAM user" error
- The algo-developer user may have been deleted
- Create it manually:
  ```
  aws iam create-user --user-name algo-developer
  aws iam attach-user-policy --user-name algo-developer --policy-arn arn:aws:iam::aws:policy/AdministratorAccess
  ```

### Terraform backend locked
- If Terraform hangs on "Acquiring state lock":
  ```
  aws dynamodb delete-item \
    --table-name stocks-terraform-locks \
    --key '{"LockID": {"S": "stocks/terraform.tfstate"}}'
  ```

## Prevention
Once system is working:
1. Store credentials in a secure password manager
2. Rotate credentials every 90 days
3. Never commit credentials to git
4. Keep ~/.aws/credentials file secure (chmod 600)

## Alternative: Use AWS CLI Without Local Credentials
If you're comfortable with AWS CLI configuration, you can also:
1. Configure AWS CLI to use AWS SSO or assume role
2. Use `aws configure sso` for temporary credentials
3. Set AWS_PROFILE environment variable

See: https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html
