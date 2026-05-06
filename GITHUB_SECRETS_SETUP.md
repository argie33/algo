# GitHub Secrets Setup for Terraform

This guide shows how to configure GitHub repository secrets for Terraform deployments.

## Required Secrets

Configure these in GitHub Settings → Secrets and variables → Actions:

### 1. AWS_ACCOUNT_ID
- **Value:** Your 12-digit AWS account ID (e.g., `123456789012`)
- **Type:** Repository secret
- **Used by:** All Terraform modules

```bash
# Find your account ID
aws sts get-caller-identity --query Account --output text
```

### 2. DB_PASSWORD
- **Value:** Secure PostgreSQL password (12+ characters, mixed case, numbers, symbols)
- **Type:** Repository secret (mark as sensitive)
- **Used by:** data_infrastructure module
- **Rotation:** Store in AWS Secrets Manager after initial deployment

```bash
# Generate secure password
openssl rand -base64 32
```

### 3. NOTIFICATION_EMAIL
- **Value:** Email address for CloudWatch alerts
- **Type:** Repository secret
- **Used by:** data_infrastructure module (SNS subscriptions)

### Optional Secrets

#### SLACK_WEBHOOK
- **Type:** Repository secret
- **Used by:** Workflow notifications on success/failure
- **Get from:** Slack → Settings → Incoming Webhooks

## How to Configure

### Step 1: Go to Repository Settings
```
GitHub → Your Repo → Settings → Secrets and variables → Actions
```

### Step 2: Create Each Secret
Click "New repository secret" for each:

| Secret Name | Value | Example |
|---|---|---|
| `AWS_ACCOUNT_ID` | Your AWS account ID | `123456789012` |
| `DB_PASSWORD` | PostgreSQL password | `Tr0p!cal-P@ssw0rd-2024` |
| `NOTIFICATION_EMAIL` | Email address | `your-email@example.com` |
| `SLACK_WEBHOOK` | (Optional) Slack webhook URL | `https://hooks.slack.com/...` |

### Step 3: Verify in Workflow
Check that workflow has access:
```bash
# Go to Actions tab and check that secrets are available to the workflow
# They will show as *** in logs for security
```

## How Terraform Uses Secrets

The GitHub Actions workflow passes secrets as environment variables using the `TF_VAR_` prefix:

```yaml
env:
  TF_VAR_aws_account_id: ${{ secrets.AWS_ACCOUNT_ID }}
  TF_VAR_db_password: ${{ secrets.DB_PASSWORD }}
  TF_VAR_notification_email: ${{ secrets.NOTIFICATION_EMAIL }}
```

Terraform automatically converts these to variables:
```hcl
variable "aws_account_id" { ... }      # ← TF_VAR_aws_account_id
variable "db_password" { ... }         # ← TF_VAR_db_password
variable "notification_email" { ... }  # ← TF_VAR_notification_email
```

**No `terraform.tfvars` file needed** - Everything comes from secrets!

## Security Best Practices

### ✅ DO:
- Store all sensitive values (passwords, API keys) as encrypted GitHub secrets
- Rotate `DB_PASSWORD` monthly
- Use strong passwords (12+ chars, mixed case, numbers, symbols)
- Enable environment protection rules for production

### ❌ DON'T:
- Commit secrets to git (even in .gitignore'd files)
- Use the same password across environments
- Share access tokens in PRs or comments
- Store plaintext credentials in terraform.tfvars

## Rotating Secrets

### Rotate DB_PASSWORD

1. **Update GitHub Secret:**
   ```
   Settings → Secrets → DB_PASSWORD → Update value
   ```

2. **Run Terraform:**
   ```bash
   # New password will be used on next deployment
   git push origin main
   # Workflow automatically runs and updates RDS
   ```

3. **Verify in AWS:**
   ```bash
   aws secretsmanager get-secret-value \
     --secret-id stocks-db-secret-XXXXXXXX
   ```

## Troubleshooting

### "Missing secret: AWS_ACCOUNT_ID"
- Go to Settings → Secrets → verify all 3 required secrets exist
- Secrets are case-sensitive: `AWS_ACCOUNT_ID` not `aws_account_id`

### "Workflow can't access secrets"
- Ensure workflow file is on `main` branch (not feature branch)
- Check that repository isn't using organization-level secret restrictions
- Verify workflow permissions: `permissions: id-token: write`

### "Invalid credentials"
- Double-check AWS_ACCOUNT_ID is exactly 12 digits
- Verify AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY have the right permissions
- Test credentials locally: `aws sts get-caller-identity`

## Accessing Secrets in Workflow Logs

GitHub automatically masks secrets in workflow logs:
```
[Logs]
Terraform is applying with account: ***
DB password is: ***
[Hidden for security]
```

To debug without exposing secrets:
```yaml
- name: Debug
  run: |
    echo "Account ID length: ${#TF_VAR_aws_account_id}"
    echo "DB password length: ${#TF_VAR_db_password}"
    # ✓ This shows lengths without exposing values
```

## Multi-Environment Setup

For staging/prod environments, use environment-specific secrets:

```
AWS_ACCOUNT_ID_DEV
AWS_ACCOUNT_ID_STAGING
AWS_ACCOUNT_ID_PROD

DB_PASSWORD_DEV
DB_PASSWORD_STAGING
DB_PASSWORD_PROD
```

Then in workflow:
```yaml
env:
  TF_VAR_aws_account_id: ${{ secrets[format('AWS_ACCOUNT_ID_{0}', env.ENVIRONMENT)] }}
```

## CI/CD Security Checklist

- [ ] All 3 required secrets configured
- [ ] Secrets marked as sensitive
- [ ] No credentials in terraform.tfvars
- [ ] Workflow uses `id-token: write` for OIDC
- [ ] Destroy operations require approval
- [ ] Slack notifications enabled (optional)
- [ ] Access logs reviewed
- [ ] Password rotation policy established

---

**Last Updated:** 2026-05-06
**Setup Time:** ~5 minutes
**Next Step:** Configure secrets, then push to trigger deployment workflow
