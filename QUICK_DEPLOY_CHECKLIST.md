# Quick Deploy to AWS - 5 Minute Checklist

## ✅ What's Ready
- [x] Code tested and verified (orchestrator runs in live mode locally)
- [x] Terraform infrastructure defined (VPC, RDS, Lambda, EventBridge, Step Functions)
- [x] Alpaca credentials available (in PowerShell profile)
- [x] FRED API key available (in PowerShell profile)
- [x] GitHub Actions configured for auto-deployment

## ⏳ What You Need to Do (Right Now)

### Step 1: Get RDS Master Password (2 min)
You set this password when creating the RDS database in AWS.

**Option A: Check Your Notes/Password Manager**
- Did you save the password somewhere when you created the RDS instance?
- Check password manager, email, or documentation

**Option B: Find it in AWS Console**
1. Go to: https://console.aws.amazon.com/
2. Search for "RDS" in the top search bar
3. Click "Databases" on left sidebar
4. Find your database (name contains "stocks" or "prod")
5. Click on it
6. Scroll down to "Configuration" section
7. Look for "Master username" → it should be `stocks`
8. Password: You set this, so you need to remember it OR reset it

**Option C: Reset Password in AWS Console**
1. Go to RDS → Databases
2. Find your database
3. Click "Modify"
4. Under "Master password", check "Change master password"
5. Set a new password (something like: `StocksTrading2026!`)
6. Click "Continue" → "Apply immediately"
7. Wait ~5 min for it to apply
8. Use that new password

### Step 2: Deploy (3 min)
Once you have the RDS password, open PowerShell and run:

```powershell
cd C:\Users\arger\code\algo

# Set the RDS password (replace with your actual password)
$env:RDS_PASSWORD = "your_actual_rds_password_here"

# Run the deployment
bash ./DEPLOY_TO_AWS.sh
```

This will:
1. Verify all credentials
2. Create AWS Secrets Manager entries
3. Push code to GitHub
4. GitHub Actions auto-deploys everything

---

## ✅ Success Criteria (After Deployment)
- [ ] GitHub Actions completes (check https://github.com/argie33/algo/actions)
- [ ] Lambda functions deployed (check AWS Console → Lambda)
- [ ] EventBridge schedules active (check AWS Console → EventBridge)
- [ ] RDS database accessible (check AWS Console → RDS)
- [ ] Loaders run at 4:00 AM ET → fetch fresh data
- [ ] Orchestrator runs at 9:30 AM ET → generates signals
- [ ] Real trades execute in Alpaca paper account
- [ ] Dashboard shows live positions and P&L

---

## 🎯 Timeline
- **Now**: You get RDS password (2 min)
- **+2 min**: Run deployment script (1 min)
- **+3 min**: GitHub Actions runs (10-15 min, runs in background)
- **+20 min**: System live in AWS ✅

Then every day, **automatically**:
- 4:00 AM ET: Loaders fetch fresh prices, technicals, earnings, etc.
- 9:30 AM ET: Orchestrator runs, executes entry/exit logic
- 5:30 PM ET: Evening run, analysis of day's trading

---

## ❓ Questions?
- **"Where do I find my RDS password?"** → See Step 1 Option B above
- **"Can I reset the password?"** → Yes, see Step 1 Option C
- **"How do I know deployment worked?"** → Check GitHub Actions page + AWS Console
- **"When will the first run happen?"** → After deployment completes (10-15 min), then tomorrow at 4:00 AM ET
- **"How do I monitor it?"** → AWS CloudWatch Logs, Alpaca dashboard, algo dashboard

---

## 🚀 Do This Now:
1. Get RDS password
2. Run deployment script
3. Watch GitHub Actions finish
4. **System goes live in AWS** ✅
