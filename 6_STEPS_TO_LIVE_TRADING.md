# 6 Steps to Get Algo Trading Live in AWS

Follow these 6 steps. System will be running in AWS in under 20 minutes.

---

## STEP 1: Get RDS Password (2 minutes)

### Option A: You Remember It
If you remember the password you set when creating the RDS database → skip to Step 2

### Option B: Find It
1. Open: https://console.aws.amazon.com/rds/
2. Click "Databases"
3. Find "stocks-prod" or similar database
4. Under "Configuration", Master username is `stocks`
5. **You need the password you set**

### Option C: Reset It (if forgotten)
1. AWS RDS Console → Click your database → Click "Modify"
2. Find "Master password" → Check "Change master password"
3. Enter new password: `MyTrading2026!` (or your choice)
4. Click "Continue" → "Apply immediately"
5. Wait 3-5 min
6. That's your password

---

## STEP 2: Copy GitHub Secrets Command

Replace `YOUR_RDS_PASSWORD` with your actual password:

```bash
gh secret set ALPACA_API_KEY_ID --body "PKQ4H6RGJFWUOPFARVUU5LEM2X"
gh secret set ALPACA_API_SECRET_KEY --body "2X9ZXfvw1BQThdZXpbZqmfwABEFZozQw1imTrdhDq7VG"
gh secret set FRED_API_KEY --body "8e6abeb06d4c84e289ca1411f48960ee"
gh secret set RDS_PASSWORD --body "YOUR_RDS_PASSWORD"
```

---

## STEP 3: Open PowerShell in Repo Directory

```powershell
cd C:\Users\arger\code\algo
```

---

## STEP 4: Paste & Run the Secrets Command

Paste the command from STEP 2 (with your RDS password) into PowerShell:

```powershell
gh secret set ALPACA_API_KEY_ID --body "PKQ4H6RGJFWUOPFARVUU5LEM2X"
gh secret set ALPACA_API_SECRET_KEY --body "2X9ZXfvw1BQThdZXpbZqmfwABEFZozQw1imTrdhDq7VG"
gh secret set FRED_API_KEY --body "8e6abeb06d4c84e289ca1411f48960ee"
gh secret set RDS_PASSWORD --body "YOUR_RDS_PASSWORD"
```

Wait for it to complete (should see ✅ success messages)

---

## STEP 5: Commit & Push Code

```powershell
git add .
git commit -m "deploy: secrets configured for AWS live trading"
git push origin main
```

---

## STEP 6: Watch GitHub Actions Deploy

1. Open: https://github.com/argie33/algo/actions
2. You'll see a workflow run
3. Watch the "deploy-code" workflow
4. It will:
   - Run tests
   - Create AWS infrastructure
   - Deploy Lambda functions
   - Configure EventBridge schedules
5. Wait for green checkmark (✅)
6. Done!

---

## ✅ System Now Live in AWS

After deployment completes:

**Tomorrow Morning (4:00 AM ET):**
- Loaders automatically fetch fresh data
- Prices, technicals, earnings, sentiments loaded

**Tomorrow (9:30 AM ET):**
- Orchestrator runs in live mode
- Generates buy/sell signals
- Executes real trades in Alpaca paper account

**Every Trading Day:**
- 4:00 AM ET: Data loads
- 9:30 AM ET: Morning orchestrator (swing entries)
- 5:30 PM ET: Evening orchestrator (analysis)
- Real trades executing automatically

---

## That's It! 🎉

6 steps, 20 minutes, and your algo is trading live in AWS every day before market open.

---

## Troubleshooting

**"gh command not found"**
→ Install GitHub CLI: `winget install github.cli` or `choco install gh`

**"GitHub secrets not setting"**
→ Run: `gh auth login` first

**"GitHub Actions fails"**
→ Go to https://github.com/argie33/algo/actions and click the failed workflow to see error

**"Deployment takes a while"**
→ Normal - Terraform is creating VPC, RDS, Lambda, etc. Wait 10-15 min

**"Can't remember RDS password"**
→ Reset it in AWS Console (see STEP 1 Option C)

---

## You Are Here Now
```
Local System ✅
  ↓
Live AWS System ⏳ ← YOU ARE HERE
  ↓
Trading Every Day ⏳
```

Do steps 1-6, and you move to "Trading Every Day ✅"
