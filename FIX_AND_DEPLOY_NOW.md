# 🚀 COMPLETE FIX & DEPLOYMENT GUIDE

**Date:** 2026-02-26
**Status:** ❌ Infrastructure not yet deployed → ⬜ Ready to fix
**Time Required:** ~90 minutes total

---

## 🎯 THE PROBLEM IN 10 SECONDS

The deployment has a **3-step dependency chain** that was never started:
```
Step 1: Create core infrastructure     ← NOT DONE
   ↓
Step 2: Create RDS database & exports  ← NOT DONE
   ↓
Step 3: Deploy Lambda & frontend       ← FAILS (missing exports from Step 2)
```

**Result:** No database, no Lambda, no website.

---

## ✅ THE COMPLETE FIX - 5 STEPS

### STEP 1️⃣ Deploy Core Infrastructure (5-10 minutes)

**What it does:** Creates base infrastructure (S3 bucket, VPC, networking, bastion host)

**How to do it:**
1. Go to: **https://github.com/argie33/algo/actions**
2. Search for or find: **"Deploy core infrastructure"**
3. Click the workflow name
4. Click blue **"Run workflow"** button
5. Click **"Run workflow"** (in the dropdown)
6. ✅ Wait for it to complete (status = CREATE_COMPLETE)

**Expected duration:** 5-10 minutes
**Success indicator:** ✅ All jobs show green checkmarks

---

### STEP 2️⃣ Deploy App Infrastructure with RDS (10-15 minutes)

**What it does:** Creates PostgreSQL RDS database, exports credentials, creates ECS cluster

**How to do it:**
1. Go to: **https://github.com/argie33/algo/actions**
2. Find: **"Data Loaders Pipeline"**
3. Click the workflow
4. Click blue **"Run workflow"** button
5. **Leave all input fields empty** (use defaults)
6. Click **"Run workflow"**
7. ✅ Wait for completion

**Expected duration:** 10-15 minutes
**Success indicator:** ✅ All jobs complete (ignore ECS cluster warning if it appears)

**Note:** If ECS cluster job shows warning about "Service Unavailable", that's OK - it's a temporary AWS service issue. The important exports are still created.

---

### STEP 3️⃣ Deploy Lambda & Frontend (5-10 minutes)

**What it does:** Deploys Lambda API, API Gateway, S3, CloudFront for website

**How to do it:**

**Option A: Automatic (Recommended)**
- After Step 2 completes, push a tiny change to trigger deployment:
  ```bash
  git commit --allow-empty -m "Trigger webapp deployment after infrastructure ready"
  git push origin main
  ```
- Deployment starts automatically in GitHub Actions

**Option B: Manual Trigger**
1. Go to: **https://github.com/argie33/algo/actions**
2. Find: **"deploy-webapp"**
3. Click **"Run workflow"**
4. Click **"Run workflow"**

**Expected duration:** 5-10 minutes
**Success indicator:** ✅ Infrastructure job succeeds, frontend builds complete

---

### STEP 4️⃣ Load Data into Database (45-60 minutes)

**What it does:** Populates database with stocks, prices, indicators, signals, scores

**How to do it:**

```bash
# From your Windows terminal OR AWS CloudShell
cd /tmp
git clone https://github.com/argie33/algo.git
cd algo
bash RUN_ALL_LOADERS_WITH_ERRORS.sh
```

**What gets loaded:**
- 5000+ stock symbols
- 1M+ daily prices
- Technical indicators
- Buy/sell signals (Daily, Weekly, Monthly)
- Stock scores
- Company data
- Financial metrics

**Expected duration:** 45-60 minutes
**Success indicator:** ✅ All loaders show green checkmarks

---

### STEP 5️⃣ Verify Everything Works (5 minutes)

**Check API health:**
```bash
curl https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/health
# Should return: {"success": true, "status": "healthy"}
```

**Check frontend:**
- Get CloudFront URL from CloudFormation stack outputs
- Visit it in your browser

**Check database:**
```bash
aws rds describe-db-instances --region us-east-1
# Should show: stocks-db-dev instance AVAILABLE
```

---

## 📊 TIMELINE

```
NOW (2026-02-26):          Ready to start
   ↓ (5-10 min)
~2:50 PM:                  Step 1 complete (core infrastructure)
   ↓ (10-15 min)
~3:05 PM:                  Step 2 complete (RDS database)
   ↓ (5-10 min)
~3:20 PM:                  Step 3 complete (Lambda & frontend)
   ↓ (45-60 min)
~4:15-4:30 PM:             Step 4 complete (data loaded)
   ↓ (5 min)
~4:35 PM:                  Step 5 complete (verified)
   ↓
✅ SYSTEM FULLY OPERATIONAL
```

**Total time:** ~90 minutes

---

## 🔴 CRITICAL NOTES

### ⚠️ DO NOT SKIP STEP 1 OR 2
- Step 3 depends on exports from Step 2
- If you run Step 3 without Step 2, it will fail
- Do them in order

### ⚠️ AWS ERRORS ARE OK
Some "Service Unavailable" errors from AWS are temporary:
- ECS cluster might show service unavailable → Still OK
- These are AWS service hiccups, not your fault
- The workflow will retry and succeed

### ⚠️ DATA LOADING TAKES TIME
- Don't interrupt it once started
- You'll see progress: "Loading stock symbols... Loading prices... etc."
- If a loader fails, you can rerun just that one after

---

## 🆘 IF SOMETHING FAILS

### Deploy-core failed?
```bash
# Delete the failed stack and retry
aws cloudformation delete-stack --stack-name stocks-core-stack --region us-east-1
# Then manually run Step 1 again
```

### Deploy-app failed?
```bash
# Delete the failed stack and retry
aws cloudformation delete-stack --stack-name stocks-app-dev --region us-east-1
# Then manually run Step 2 again
```

### Data loaders failed?
```bash
# Try running just the failed loader
python3 loadstocksymbols.py
python3 loadpricedaily.py
# Then the full load again
bash RUN_ALL_LOADERS_WITH_ERRORS.sh
```

### Lambda not responding?
- Wait 5 minutes after deployment (Lambda is warming up)
- Check CloudWatch logs: https://console.aws.amazon.com/cloudwatch

---

## ✨ WHAT YOU'LL HAVE AFTER THIS

```
✅ Live PostgreSQL database with 50+ tables
✅ 5000+ stock symbols
✅ 1M+ historical price records
✅ Technical indicators for all stocks
✅ Buy/sell signals
✅ Stock scores (quality ratings)
✅ Lambda API backend (serverless)
✅ React frontend website (CloudFront CDN)
✅ Cognito authentication (single sign-on)
✅ Real-time stock data dashboard
```

---

## 📞 QUICK COMMAND REFERENCE

```bash
# Check deployment status
https://github.com/argie33/algo/actions

# Check CloudFormation stacks
aws cloudformation list-stacks --region us-east-1

# Check RDS database
aws rds describe-db-instances --region us-east-1

# Check Lambda
aws lambda list-functions --region us-east-1 | grep stocks

# Load all data
bash RUN_ALL_LOADERS_WITH_ERRORS.sh

# Load specific data
python3 loadstocksymbols.py
python3 loadpricedaily.py
python3 loadstockscores.py

# Test API
curl https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/health
```

---

## ✅ CHECKLIST

- [ ] Step 1: Core infrastructure deployed
- [ ] Step 2: RDS database created
- [ ] Step 3: Lambda & frontend deployed
- [ ] Step 4: Data loaded (45-60 min)
- [ ] Step 5: All systems verified

---

**Ready to start?** → Go to Step 1️⃣ now!

For detailed analysis of issues found, see: `ISSUES_FOUND_AND_FIXES.md`
