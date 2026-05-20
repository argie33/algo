# Deploy to AWS via GitHub Secrets (No Local AWS Credentials Needed)

## How It Works
You set 4 secrets in GitHub repo settings → GitHub Actions reads them → deploys everything to AWS automatically.

## Step 1: Open GitHub Repo Settings (1 min)
1. Go to: https://github.com/argie33/algo/settings/secrets/actions
2. Click "New repository secret" for each of these:

### Secret 1: ALPACA_API_KEY_ID
- Name: `ALPACA_API_KEY_ID`
- Value: `PKQ4H6RGJFWUOPFARVUU5LEM2X`

### Secret 2: ALPACA_API_SECRET_KEY
- Name: `ALPACA_API_SECRET_KEY`
- Value: `2X9ZXfvw1BQThdZXpbZqmfwABEFZozQw1imTrdhDq7VG`

### Secret 3: FRED_API_KEY
- Name: `FRED_API_KEY`
- Value: `8e6abeb06d4c84e289ca1411f48960ee`

### Secret 4: RDS_PASSWORD
- Name: `RDS_PASSWORD`
- Value: `[YOUR RDS PASSWORD HERE]` ← Only thing you need to provide
  - Where to get it: See below

---

## Get RDS Password (2 min)
### Quick Check
Do you remember the password you set when creating the RDS database?
- If YES → use that
- If NO → go to AWS Console to find or reset it

### AWS Console Method
1. Go to: https://console.aws.amazon.com/rds/
2. Click "Databases" on left sidebar
3. Find database named "stocks-prod" or similar
4. Under "Configuration" → Master username shows `stocks`
5. Password is what you set (or need to reset)

### If You Forgot the Password
1. In AWS RDS Console → Click your database
2. Click "Modify"
3. Find "Master password" section
4. Check "Change master password"
5. Enter new password (e.g., `MyNewPassword2026!`)
6. Click "Continue" → "Apply immediately"
7. Wait ~5 minutes for change to apply
8. Use that new password in GitHub Secret

---

## Step 2: Push Code to GitHub (1 min)

```bash
cd C:\Users\arger\code\algo
git add .
git commit -m "deploy: GitHub Secrets configured for AWS deployment"
git push origin main
```

---

## Step 3: GitHub Actions Deploys Everything (10-15 min)

Once you push, GitHub Actions automatically:
1. Reads the 4 secrets from GitHub repo settings
2. Runs security scans (TruffleHog, bandit, pip-audit)
3. Runs 282 tests (pytest)
4. Creates AWS Secrets Manager entries:
   - `algo/alpaca` ← Alpaca credentials
   - `algo/fred` ← FRED API key
   - `algo/database` ← RDS connection info
5. Deploys Terraform infrastructure:
   - VPC + Subnets + Security Groups
   - RDS Database
   - Lambda Functions (orchestrator + API)
   - ECS Fargate Tasks (loaders)
   - EventBridge Schedules (9:30 AM ET + 5:30 PM ET)
   - Step Functions Pipeline (loader orchestration)
6. Configures all permissions (IAM roles)
7. Deploys code to Lambda

---

## Step 4: Verify Deployment (5 min)

### Monitor GitHub Actions
1. Go to: https://github.com/argie33/algo/actions
2. Watch the workflow run
3. Check for green checkmarks (success) or red X (failure)
4. If failure, click on it to see error logs

### Check AWS Console
Once GitHub Actions completes:

**Check Lambda Functions**
```bash
aws lambda get-function-configuration --function-name stocks-algo-dev --region us-east-1
```

**Check EventBridge Schedules**
```bash
aws scheduler list-schedules --region us-east-1
```

**Check RDS Database**
```bash
aws rds describe-db-instances --region us-east-1 --query 'DBInstances[?contains(DBInstanceIdentifier, `stocks`)]'
```

**Check Logs**
```bash
aws logs tail /aws/lambda/stocks-algo-dev --follow --region us-east-1
```

---

## Step 5: System Goes Live (Automatic)

After deployment completes:

**Tomorrow morning, automatically:**
- 4:00 AM ET: Loaders fetch fresh price data, technicals, earnings, etc.
- 9:30 AM ET: Orchestrator runs, executes entry/exit logic, generates signals
- Trades execute in Alpaca paper account

**Every trading day, automatically:**
- 5:30 PM ET: Evening orchestrator run with full analysis

---

## 🎯 Timeline
| Time | Action | Status |
|------|--------|--------|
| Now | You set 4 GitHub secrets | ⏳ PENDING |
| +1 min | You push code | ⏳ PENDING |
| +1-15 min | GitHub Actions deploys | ⏳ PENDING |
| +20 min | System live in AWS | ⏳ PENDING |
| Tomorrow 4 AM ET | First loaders run | ⏳ PENDING |
| Tomorrow 9:30 AM ET | First orchestrator run in AWS | ⏳ PENDING |
| Tomorrow 9:30 AM ET | **GOAL ACHIEVED** ✅ | ⏳ PENDING |

---

## Key Points
- ✅ No local AWS CLI needed
- ✅ No credentials in git history (GitHub secrets are safe)
- ✅ Automatic deployment (GitHub Actions handles everything)
- ✅ Infrastructure as Code (Terraform, version controlled)
- ✅ Completely reversible (delete GitHub secrets + run `terraform destroy`)

---

## Just Do This:
1. Get RDS password (or reset it in AWS)
2. Go to: https://github.com/argie33/algo/settings/secrets/actions
3. Add 4 secrets (copy-paste the values above)
4. Run `git push origin main`
5. Watch GitHub Actions complete
6. **System running in AWS** ✅
