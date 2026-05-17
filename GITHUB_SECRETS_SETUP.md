# GitHub Secrets Setup Guide

**Time Required:** 5 minutes  
**Status:** REQUIRED before deployment

---

## Step 1: Go to GitHub Repository Settings

1. Open: https://github.com/argie33/algo
2. Click: **Settings** (tab at top)
3. Left sidebar: **Secrets and variables** > **Actions**
4. Click: **New repository secret** button

---

## Step 2: Add These 7 Secrets

Add each secret one by one. For each:
1. Click **New repository secret**
2. Enter **Name** and **Secret value**
3. Click **Add secret**

### Required Secrets

| # | Name | Value | Notes |
|---|------|-------|-------|
| 1 | `AWS_ACCOUNT_ID` | YOUR_AWS_ACCOUNT_NUMBER | 12-digit number (e.g., 123456789012) |
| 2 | `RDS_PASSWORD` | `bed0elAn` | Database admin password |
| 3 | `ALPACA_API_KEY_ID` | YOUR_ALPACA_API_KEY | From Alpaca dashboard |
| 4 | `ALPACA_API_SECRET_KEY` | YOUR_ALPACA_SECRET_KEY | From Alpaca dashboard |
| 5 | `ALERT_EMAIL_ADDRESS` | YOUR_EMAIL@example.com | Where alerts should go |
| 6 | `JWT_SECRET` | RANDOM_32_CHAR_STRING | Generate: `openssl rand -hex 16` |
| 7 | `FRED_API_KEY` | YOUR_FRED_API_KEY | From Federal Reserve FRED |

---

## Step 3: Generate JWT_SECRET (if needed)

If you need to generate a random JWT secret:

**Mac/Linux:**
```bash
openssl rand -hex 16
```

**Windows PowerShell:**
```powershell
[Convert]::ToHexString([byte[]](1..16 | ForEach-Object { Get-Random -Maximum 256 }))
```

Or just use any 32-character random string.

---

## Step 4: Verify Secrets are Set

After adding all 7 secrets:
1. Go back to **Settings > Secrets and variables > Actions**
2. You should see all 7 secrets listed
3. Status will show "Last used: ..." or "Not yet used"

---

## Step 5: Trigger Deployment

Once all secrets are added:

```bash
git push origin main
```

This will trigger the `deploy-all-infrastructure.yml` workflow automatically.

Check deployment progress:
- Go to: https://github.com/argie33/algo/actions
- Watch the workflow run

---

## What Each Secret Is Used For

| Secret | Used By | Purpose |
|--------|---------|---------|
| `AWS_ACCOUNT_ID` | Terraform | Determine IAM role for GitHub Actions |
| `RDS_PASSWORD` | Terraform | Create RDS database password |
| `ALPACA_API_KEY_ID` | Lambda + Orchestrator | Connect to Alpaca trading API |
| `ALPACA_API_SECRET_KEY` | Lambda + Orchestrator | Authenticate with Alpaca |
| `ALERT_EMAIL_ADDRESS` | CloudWatch | Send SNS alerts to this email |
| `JWT_SECRET` | API Lambda | Sign/verify JWT tokens |
| `FRED_API_KEY` | Data loaders | Fetch economic data from Federal Reserve |

---

## Deployment Checklist

- [ ] AWS Account ID found (12-digit number)
- [ ] RDS password set to `bed0elAn`
- [ ] Alpaca API key and secret obtained
- [ ] Alert email address configured
- [ ] JWT secret generated (32-char random)
- [ ] FRED API key obtained
- [ ] All 7 secrets added to GitHub
- [ ] Verified secrets appear in GitHub settings
- [ ] Pushed to main branch OR manually triggered workflow

---

## After Secrets Are Added

**Workflow will automatically:**
1. Bootstrap Terraform backend (S3 + DynamoDB)
2. Run Terraform init/validate/plan
3. Deploy all 165 infrastructure modules
4. Build and push Docker image to ECR
5. Build Lambda function ZIPs
6. Deploy Lambda functions
7. Deploy frontend to S3/CloudFront

**Expected time:** 20-30 minutes

---

## How to Monitor Deployment

1. Go to: https://github.com/argie33/algo/actions
2. Click the workflow run you just triggered
3. Watch the logs in real-time
4. Each step will show ✓ or ✗ status

If any step fails, click it to see full error details.

---

## Troubleshooting

**"Resource already exists"** → Infrastructure may already be deployed. Check AWS console.

**"Permission denied"** → Check that GitHub OIDC role is configured in AWS.

**"Rate limited"** → Wait 10 seconds and retry.

**"Terraform state lock"** → Another deployment is running. Wait or force-unlock.

---

## Once Deployment Completes

After workflow succeeds:
1. Check Terraform outputs (shown in GitHub Actions logs)
2. Note: API endpoint, RDS instance, S3 bucket names
3. Run loaders in AWS:
   ```bash
   python3 run-all-loaders.py --cloud aws
   ```
4. Test orchestrator:
   ```bash
   python3 algo/algo_orchestrator.py --mode paper
   ```

---

**Questions?** Check STATUS.md or ISSUES_OUTSTANDING.md for detailed setup info.
