# GitHub Secrets Setup for Billing Circuit Breaker

The deployment workflow needs these GitHub secrets configured.

## Quick Setup

1. Go to: **Settings → Secrets and variables → Actions**
2. Add each secret below:

---

## Required Secrets

### `AWS_ACCOUNT_ID`
**What it is**: Your AWS account ID  
**Where to get it**:
```bash
aws sts get-caller-identity --query Account --output text
```
**Example**: `626216981288`

---

### `BILLING_PHONE_NUMBER`
**What it is**: Your phone number for SMS alerts  
**Format**: E.164 format (country code + number)  
**Example**: `+13123078620`  
**Current value**: Your phone: `+1-312-307-8620` → use `+13123078620`

---

### `BILLING_EMAIL`
**What it is**: Email address for alerts  
**Example**: `argeropolos@gmail.com`

---

### `BILLING_MONTHLY_LIMIT`
**What it is**: Monthly budget limit in USD  
**Example**: `100`  
**Current value**: `100` (you want to be warned at 50%, 75%, 90% and hard-stopped at 100%+)

---

### `LAMBDA_ROLE_ARN`
**What it is**: ARN of your Lambda execution role  
**Where to get it**:
```bash
aws iam list-roles \
  --query "Roles[?contains(RoleName, 'stocks-algo-api')].Arn" \
  --output text
```
**Example**: `arn:aws:iam::626216981288:role/stocks-algo-api-dev-us-east-1-lambdaRole`

**Note**: The workflow tries to auto-detect this, but having it as a secret is safer.

---

## How to Add Secrets

### Via GitHub CLI (Recommended)
```bash
# Set AWS account ID
gh secret set AWS_ACCOUNT_ID --body "626216981288"

# Set phone number
gh secret set BILLING_PHONE_NUMBER --body "+13123078620"

# Set email
gh secret set BILLING_EMAIL --body "argeropolos@gmail.com"

# Set monthly budget
gh secret set BILLING_MONTHLY_LIMIT --body "100"

# Set Lambda role ARN
gh secret set LAMBDA_ROLE_ARN --body "arn:aws:iam::626216981288:role/stocks-algo-api-dev-us-east-1-lambdaRole"
```

### Via GitHub Web UI
1. Go to repo → **Settings → Secrets and variables → Actions**
2. Click **New repository secret**
3. Add each secret from the list above
4. Click **Add secret**

---

## Verify Setup

```bash
# List all secrets (shows names only, not values - for security)
gh secret list
```

Expected output:
```
AWS_ACCOUNT_ID          Updated 2026-04-28
BILLING_EMAIL           Updated 2026-04-28
BILLING_MONTHLY_LIMIT   Updated 2026-04-28
BILLING_PHONE_NUMBER    Updated 2026-04-28
LAMBDA_ROLE_ARN         Updated 2026-04-28
```

---

## Testing the Workflow

### Trigger Deployment
```bash
# Push the billing circuit breaker template to trigger workflow
git add billing-circuit-breaker.yml .github/workflows/deploy-billing.yml
git commit -m "Deploy billing circuit breaker via GitHub Actions"
git push origin main
```

### Monitor Workflow
1. Go to repo → **Actions** tab
2. Click `deploy-billing-circuit-breaker` workflow
3. Watch the steps complete

### What to Expect
- ✅ **validate**: CloudFormation template syntax check
- ✅ **get-lambda-role**: Auto-discover your Lambda role
- ✅ **deploy**: Create AWS resources (SNS, Budget, Lambda)
- ✅ **test-sns**: Send test message to verify alerts work

---

## After First Deployment

### Check Your Email
AWS sends confirmation emails:
1. "AWS Notification - Subscription Confirmation" → **Click to confirm**
2. Confirmation receipt

### Check Your Phone
SMS confirmation arrives (auto-confirms or reply to confirm)

### Verify Alerts Work
You'll receive a test message:
```
✅ Billing Circuit Breaker Test - Deployed Successfully

Alerts are now active at:
- 50% of budget ($50) → Email + SMS
- 75% of budget ($75) → Email + SMS
- 90% of budget ($90) → Email + SMS
- 100%+ of budget ($100+) → Hard Stop
```

If you **don't receive email or SMS**, check:
1. SNS subscriptions: https://console.aws.amazon.com/sns
2. SNS subscription status (may need confirmation)
3. Phone number format (must be E.164: +1 for US)

---

## Updating Secrets

To change phone number, email, or budget:

```bash
# Update the secret
gh secret set BILLING_PHONE_NUMBER --body "+1-NEW-NUMBER"

# Or via web UI:
# Settings → Secrets → Edit secret → Update → Save
```

Then push to trigger redeployment:
```bash
git commit --allow-empty -m "Update billing settings"
git push origin main
```

---

## Troubleshooting

### Workflow fails: "AWS account ID not found"
- Check `AWS_ACCOUNT_ID` secret is set correctly
- Must be numeric: `626216981288`

### Workflow fails: "Lambda role not found"
- Check `LAMBDA_ROLE_ARN` secret is correct
- Verify the role exists: `aws iam get-role --role-name <role-name>`

### Workflow succeeds but no email/SMS
- Check SNS subscriptions in AWS console
- May need to confirm subscription (check email)
- Phone number may need to be in E.164 format: `+13123078620`

### How to run workflow manually
1. Go to **Actions** tab
2. Click `deploy-billing-circuit-breaker`
3. Click **Run workflow**
4. Select branch (main) → **Run workflow**

---

## Security Notes

✅ **Secrets are encrypted** and only exposed to authorized actions  
✅ **Phone number and email** are protected secrets  
✅ **Cannot be viewed** after creation (only admins can update)  
✅ **Audit trail** exists in GitHub (who changed what)

---

## Next Steps

1. ✅ Add all 5 secrets to GitHub
2. ✅ Push `billing-circuit-breaker.yml` and workflow file
3. ✅ Monitor workflow run in **Actions** tab
4. ✅ Confirm SNS subscriptions in email
5. ✅ Verify test message arrives on phone + email

Your billing circuit breaker is now **fully deployed via GitHub Actions**! 🛡️
