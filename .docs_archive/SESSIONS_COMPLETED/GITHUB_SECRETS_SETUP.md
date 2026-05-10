# GitHub Secrets Setup Guide

This guide documents all secrets and credentials required for the Stock Analytics Platform CI/CD pipeline. All values are stored in GitHub Organization/Repository Secrets and passed to AWS via environment variables during deployment.

**CRITICAL:** Never commit credentials to the repository. All sensitive values must be configured in GitHub Secrets before deployment.

---

## Required GitHub Secrets

### Bootstrap Phase (One-Time Setup)

These secrets are only needed for the initial `terraform apply -target=module.bootstrap` step. They can be deleted after the bootstrap module creates the AWS OIDC provider.

#### 1. AWS_ACCESS_KEY_ID
- **Type:** AWS Access Key
- **Scope:** Bootstrapping only (temporary)
- **Purpose:** Initial AWS authentication for creating S3 backend and DynamoDB lock table
- **Obtaining the Value:**
  1. Log into AWS Console as root or admin user
  2. IAM → Users → (your user) → Security credentials
  3. Access keys → Create access key
  4. Choose "Command Line Interface (CLI)" as use case
  5. Copy the Access Key ID
- **Lifespan:** Delete after bootstrap completes and OIDC is verified working
- **Set In:** GitHub → Settings → Secrets and variables → Actions → New repository secret
- **Value Format:** `AKIA...` (20 characters)

#### 2. AWS_SECRET_ACCESS_KEY
- **Type:** AWS Secret Access Key
- **Scope:** Bootstrapping only (temporary)
- **Purpose:** Complements AWS_ACCESS_KEY_ID for initial authentication
- **Obtaining the Value:** Same as AWS_ACCESS_KEY_ID step above; copy the Secret Access Key
- **Security:** Store securely; this is displayed only once during creation
- **Lifespan:** Delete after bootstrap completes
- **Value Format:** Long alphanumeric string

---

### Production Phase (After Bootstrap)

These secrets are used in all GitHub Actions workflows after the bootstrap module completes. Authentication transitions to AWS OIDC after bootstrap.

#### 3. RDS_PASSWORD
- **Type:** Database password
- **Scope:** Infrastructure and application
- **Purpose:** PostgreSQL database authentication
- **Obtaining the Value:**
  - Option A (Fresh deployment): Generate a strong password (20+ chars, mixed case, numbers, special chars)
  - Option B (Existing database): Retrieve from AWS Secrets Manager or RDS console
  - Option C (From previous deployment): Check encrypted backups or secure password manager
- **Format Example:** `P@ssw0rd!Str0ng#123`
- **Usage Flow:**
  ```
  GitHub Secret RDS_PASSWORD
    → TF_VAR_rds_password env var (GitHub Actions)
    → terraform/variables.tf (type = string, sensitive = true)
    → RDS cluster password at creation time
    → Database connection strings in Lambda environment
  ```
- **Security:** Mark as sensitive in GitHub (automatically done)
- **Rotation:** Every 90 days via AWS Secrets Manager + Lambda update

#### 4. ALPACA_API_KEY_ID
- **Type:** API Key ID
- **Scope:** Algo orchestrator Lambda
- **Purpose:** Authentication with Alpaca (paper trading API)
- **Obtaining the Value:**
  1. Log into Alpaca dashboard (https://app.alpaca.markets)
  2. Account → API Keys
  3. Create new key for "Paper Trading"
  4. Copy the Key ID (starts with `PK...`)
- **Lifecycle:** Can be regenerated in Alpaca dashboard without downtime
- **Usage Flow:**
  ```
  GitHub Secret ALPACA_API_KEY_ID
    → TF_VAR_alpaca_api_key_id env var
    → RDS (persisted as credentials)
    → Algo Lambda queries credentials at runtime
  ```
- **Security:** These are paper-trading-only credentials (not real money)
- **Rotation:** Every 6 months as routine maintenance

#### 5. ALPACA_API_SECRET_KEY
- **Type:** API Secret Key
- **Scope:** Algo orchestrator Lambda
- **Purpose:** Authentication secret for Alpaca API
- **Obtaining the Value:** Same as ALPACA_API_KEY_ID step; copy the Secret Key
- **Security:** Displayed once; store securely; treat as sensitive as password
- **Note:** Unlike key ID, secret key cannot be retrieved again; save it immediately
- **Rotation:** Every 6 months (regenerate new secret + key pair in Alpaca, update both GitHub Secrets)

#### 6. ALERT_EMAIL_ADDRESS
- **Type:** Email address
- **Scope:** SNS notifications
- **Purpose:** Email recipient for algo alerts and trading notifications
- **Format:** Valid email address (e.g., `argeropolos@gmail.com`)
- **Obtaining the Value:** Use the email address that should receive SNS notifications
- **Usage Flow:**
  ```
  GitHub Secret ALERT_EMAIL_ADDRESS
    → TF_VAR_notification_email env var
    → SNS topic subscriptions (email)
    → Lambda publishes alerts to SNS
  ```
- **Security:** Email addresses themselves are not sensitive, but restrict notifications to authorized personnel
- **Verification:** After deployment, confirm SNS subscription email arrives and confirm subscription

#### 7. API_GATEWAY_URL
- **Type:** API endpoint URL
- **Scope:** Frontend application
- **Purpose:** Frontend makes API calls to this URL
- **Format:** `https://api.domain.com/` or API Gateway URL
- **Obtaining the Value:**
  - After Terraform applies, check CloudFormation outputs
  - Or: AWS API Gateway → Stages → your stage → Invoke URL
- **Usage Flow:**
  ```
  GitHub Secret API_GATEWAY_URL
    → VITE_API_URL env var (GitHub Actions build)
    → Frontend build process replaces API endpoint
    → Frontend makes API calls to this URL at runtime
  ```
- **Timing:** Set this AFTER first Terraform deployment (Terraform creates API Gateway)
- **Update Frequency:** Only if API Gateway URL changes (rare)

#### 8. SLACK_WEBHOOK (Optional)
- **Type:** Slack Webhook URL
- **Scope:** Deployment notifications
- **Purpose:** Post deployment status to Slack
- **Obtaining the Value:**
  1. Go to Slack workspace settings
  2. Features → Incoming Webhooks
  3. Add New Webhook to Channel
  4. Copy the Webhook URL
- **Usage Flow:**
  ```
  GitHub Secret SLACK_WEBHOOK
    → GitHub Actions workflow
    → Posts deployment status to Slack channel
  ```
- **Note:** Only used if workflows are updated to include Slack notifications
- **Current Status:** Currently not implemented in deploy-all-infrastructure.yml

---

## Setup Checklist

### Phase 1: Bootstrap (Temporary AWS Credentials)

- [ ] Generate temporary AWS access key for bootstrap user
- [ ] Set GitHub Secret: `AWS_ACCESS_KEY_ID`
- [ ] Set GitHub Secret: `AWS_SECRET_ACCESS_KEY`
- [ ] Run: `gh workflow run bootstrap.yml --repo argie33/algo` (manual trigger)
- [ ] Verify S3 backend bucket created in AWS
- [ ] Verify DynamoDB lock table created in AWS
- [ ] Verify GitHub OIDC provider created in AWS
- [ ] Test OIDC authentication works
- [ ] Delete temporary AWS access keys from AWS Console
- [ ] Delete `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` from GitHub Secrets

### Phase 2: Production Deployment

- [ ] Generate or retrieve RDS password
- [ ] Set GitHub Secret: `RDS_PASSWORD`
- [ ] Obtain Alpaca API credentials (create paper trading account if needed)
- [ ] Set GitHub Secret: `ALPACA_API_KEY_ID`
- [ ] Set GitHub Secret: `ALPACA_API_SECRET_KEY`
- [ ] Set GitHub Secret: `ALERT_EMAIL_ADDRESS` (email for SNS notifications)
- [ ] Run: `gh workflow run deploy-all-infrastructure.yml --repo argie33/algo`
- [ ] After Terraform completes, copy API Gateway URL from outputs
- [ ] Set GitHub Secret: `API_GATEWAY_URL`
- [ ] Run frontend deployment with API_GATEWAY_URL configured
- [ ] Verify SNS email subscription (check inbox, confirm subscription)
- [ ] Test end-to-end: API calls from frontend, algo execution, email notifications

---

## Credential Flow Diagram

```
GitHub Secrets (encrypted at rest)
    ↓
GitHub Actions (decrypted into env vars)
    ↓
Environment Variables (TF_VAR_*, secrets passed to terraform)
    ↓
Terraform → AWS Secrets Manager (for runtime access)
    ↓
Lambda Functions (at runtime, retrieve secrets from Secrets Manager)
    ↓
Application Code (uses secrets for API calls, database connections, etc.)
```

**Key Points:**
- Secrets are encrypted in GitHub and only decrypted into memory during workflow execution
- Terraform passes secrets via environment variables during plan/apply
- Critical secrets (RDS password, API keys) are stored in AWS Secrets Manager for runtime access
- Lambda functions retrieve secrets from Secrets Manager at runtime, not from environment variables
- Logs and error messages never contain plaintext secrets

---

## Security Best Practices

### Storage & Access
- ✅ All secrets stored in GitHub Organization/Repository Secrets (encrypted)
- ✅ Secrets only accessible in GitHub Actions contexts
- ✅ Team members do not need direct access to plaintext secrets
- ✅ Audit logs track who accessed/modified secrets

### In Transit
- ✅ GitHub → AWS uses OIDC (no credentials in workflows)
- ✅ AWS → RDS: encrypted connection strings, no plaintext passwords in logs
- ✅ API keys stored in AWS Secrets Manager, not environment variables

### Rotation Schedule
| Secret | Frequency | Method |
|--------|-----------|--------|
| RDS Password | 90 days | AWS Secrets Manager auto-rotation |
| Alpaca API Keys | 180 days | Manual regeneration in Alpaca dashboard |
| ALERT_EMAIL_ADDRESS | As needed | Update GitHub Secrets when recipient changes |
| AWS Credentials | Never (after bootstrap) | Use OIDC instead |

### Compromised Credentials
If any credential is exposed (e.g., accidentally committed, visible in logs):
1. **Immediately:** Delete the compromised secret from GitHub Secrets
2. **Within 1 hour:** Revoke/rotate the credential in the source system (AWS, Alpaca, etc.)
3. **Document:** Log incident in security tracker
4. **Audit:** Check logs for unauthorized use (GitHub Actions, AWS CloudTrail)
5. **Update:** Set new credential in GitHub Secrets and re-run deployment

---

## Verification & Testing

### After Setting Up GitHub Secrets

```bash
# 1. Verify GitHub Secrets exist (list only names, not values)
gh secret list --repo argie33/algo

# 2. Trigger bootstrap workflow (if not done yet)
gh workflow run deploy-all-infrastructure.yml --repo argie33/algo

# 3. Monitor workflow execution
gh run list --repo argie33/algo --workflow deploy-all-infrastructure.yml

# 4. Check for errors
gh run view <RUN_ID> --repo argie33/algo --log
```

### After Terraform Deployment

```bash
# 1. Verify RDS credentials work
aws secretsmanager get-secret-value --secret-id stocks-rds-credentials --region us-east-1

# 2. Verify Lambda can access secrets
aws lambda invoke --function-name stocks-api-dev /dev/stdout --region us-east-1 | jq '.errorMessage' || echo "Success"

# 3. Verify API Gateway is accessible
curl -X GET "https://<API_GATEWAY_URL>/health"

# 4. Check SNS subscriptions
aws sns list-subscriptions --region us-east-1 | grep -i stocks
```

---

## Post-Bootstrap Cleanup

After the bootstrap workflow completes successfully:

1. **Delete temporary AWS access keys:**
   - AWS Console → IAM → Users → (your bootstrap user)
   - Security credentials → Delete the temporary access key
   - Verify: Try to use old credentials; should fail with "Access Denied"

2. **Remove temporary GitHub Secrets:**
   - GitHub → Settings → Secrets and variables → Actions
   - Delete: `AWS_ACCESS_KEY_ID`
   - Delete: `AWS_SECRET_ACCESS_KEY`

3. **Verify OIDC is working:**
   - Run any workflow that needs AWS access (e.g., terraform plan)
   - Should succeed without AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY
   - Workflow logs should show: "Assuming role via GitHub OIDC..."

4. **Document completion:**
   - Update this file's checklist
   - Update STATUS.md with bootstrap completion timestamp

---

## Troubleshooting

### "AWS credentials not found" during workflow
- **Check:** `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` still set in GitHub Secrets?
- **Check:** Bootstrap workflow completed successfully?
- **Check:** OIDC provider role ARN correct in workflow?
- **Action:** Re-run workflow; OIDC can take a few minutes to propagate

### "RDS password rejected" during Terraform
- **Check:** RDS_PASSWORD value contains special characters? (Some chars need escaping)
- **Check:** Password not accidentally truncated in GitHub Secret?
- **Action:** Regenerate password without special chars like `$` `\` `"` `` ` ``
- **Action:** Re-run Terraform after updating secret

### "Alpaca API authentication failed"
- **Check:** Is the Alpaca account in paper trading mode?
- **Check:** API key not rotated/deleted in Alpaca dashboard?
- **Check:** Key ID and secret key match (not mixed)?
- **Action:** Regenerate new API credentials in Alpaca dashboard
- **Action:** Update both `ALPACA_API_KEY_ID` and `ALPACA_API_SECRET_KEY` in GitHub Secrets

### "SNS email not received"
- **Check:** `ALERT_EMAIL_ADDRESS` correct and accessible?
- **Check:** SNS subscription email confirmation sent? (check spam folder)
- **Check:** Email not bouncing? (AWS SNS bounce list)
- **Action:** Confirm SNS subscription via email link
- **Action:** Check SNS subscription status in AWS Console
- **Action:** Test SNS manually: `aws sns publish --topic-arn <TOPIC_ARN> --message "test"`

---

## Related Documentation
- Deployment workflow: [deployment-reference.md](deployment-reference.md)
- AWS access: [tools-and-access.md](tools-and-access.md)
- Terraform backend: [terraform/backend.tf](terraform/backend.tf)
- Bootstrap module: [terraform/modules/bootstrap/](terraform/modules/bootstrap/)

---

## Status

- ✅ GitHub Secrets documented
- ✅ Bootstrap procedure documented
- ✅ Production secrets listed
- ✅ Verification procedures included
- ⏳ Actual GitHub Secrets configuration: **Ready for user implementation**

**Next step:** Follow the Setup Checklist above to configure all secrets in GitHub.
