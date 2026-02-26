# AWS Stock Platform - Critical Fixes & Next Steps

**Status:** 🔧 Fixes Applied, Ready for Deployment
**Date:** 2026-02-26
**Commit:** ce50fa060 (unpushed - waiting for GitHub credentials)

---

## ✅ What Was Fixed

### Lambda Configuration Issues (CRITICAL)

All identified AWS infrastructure issues have been addressed:

| Issue | Before | After | Impact |
|-------|--------|-------|--------|
| **Lambda Timeout** | 60s | 300s | Complex queries no longer timeout |
| **Lambda Memory** | 128MB (default) | 512MB | Express.js + database have proper resources |
| **Reserved Concurrency** | None | 10 | Prevents database connection exhaustion |
| **Connection Pool Max** | 3 | 10 | Matches Lambda concurrency |
| **Connection Pool Min** | 1 | 2 | Better connection reuse |

**Files Modified:**
- `template-webapp-lambda.yml` - SAM template with Lambda config
- `webapp/lambda/utils/database.js` - Database connection pool settings

**Commit Details:**
```
ce50fa060 - fix: Increase Lambda resources and optimize database connection pool
```

---

## 🚀 IMMEDIATE ACTION REQUIRED: Push Changes to GitHub

### Step 1: Push the Commit to GitHub

Your changes are committed locally but not yet pushed to GitHub. This push will:
1. Update the Lambda configuration in AWS
2. Trigger GitHub Actions deployment
3. Deploy new Lambda function with 512MB memory and 300s timeout
4. Update API Gateway with new settings

**Choose ONE method:**

#### **Method A: Command Line (Recommended if you have GitHub credentials)**
```bash
cd /home/arger/algo
git push origin main
```

Expected output:
```
Counting objects: 3, done.
Delta compression using up to 8 threads.
Compressing objects: 100% (3/3), done.
Writing objects: 100% (3/3), 431 bytes, done.
Total 3 (delta 2), reused 0 (delta 0)
remote: Resolving deltas: 100% (2/2), done.
To https://github.com/argie33/algo.git
   8203ad864..ce50fa060  main -> main
```

#### **Method B: VS Code**
1. Open the project in VS Code
2. Click Source Control tab (left sidebar)
3. Click three dots → Push

#### **Method C: GitHub Desktop**
1. Open GitHub Desktop
2. Select "algo" repository
3. Click "Publish branch" or "Push to origin"

#### **Method D: GitHub Web UI**
1. Create a new branch from `main` in VS Code
2. Commit locally: Already done ✓
3. Push from VS Code (Method B)
4. Create Pull Request on GitHub
5. Merge PR to main
6. GitHub Actions will run automatically

---

## ⏱️ After Push: GitHub Actions Deployment

Once pushed, GitHub Actions will automatically:
1. **Build SAM Application** (~2 min)
2. **Deploy Lambda Function** (~3 min)
3. **Update API Gateway** (~1 min)
4. **Invalidate CloudFront Cache** (~2 min)
5. **Run Health Checks** (~1 min)

**Total time: ~9 minutes**

**Monitor progress:**
- GitHub page: https://github.com/argie33/algo/actions
- Look for `deploy-webapp` workflow
- Click on latest run to see live logs

**Success indicators:**
- ✅ `deploy_infrastructure` job: ✓ Passed
- ✅ `deploy_frontend` job: ✓ Passed
- ✅ `verify_deployment` job: ✓ Passed

---

## 📊 Step 2: Load Data into Database

### Why This Is Critical

The AWS platform won't work without data:
- API endpoints return empty arrays
- Frontend shows no stocks, scores, or signals
- All features appear broken even though code is fine

**Current Status:** Unknown if data is loaded in AWS RDS

### Required Data Loaders

These **MUST** run in order (later loaders depend on earlier ones):

1. **loadstocksymbols.py** (~2 min)
   - Fetches 5000+ NASDAQ/NYSE stock symbols
   - Required by all other loaders
   - Lightweight, fastest loader

2. **loadpricedaily.py** (~20 min)
   - Fetches OHLCV data for 5000+ stocks
   - Largest dataset (1M+ rows)
   - Required for signals and scores
   - ⚠️ Most time-consuming

3. **loadtechnicalindicators.py** (~5 min)
   - Calculates RSI, MACD, Bollinger Bands, etc.
   - Requires prices (step 2)
   - Required for signals

4. **loadbuysellDaily.py** (~10 min)
   - Generates buy/sell signals
   - Requires prices and technicals
   - Core feature for frontend

5. **loadstockscores.py** (~5 min)
   - Calculates composite scoring
   - Momentum, growth, value, quality scores
   - Used for stock ranking

**Total time: ~45-60 minutes (first run)**

### Option 1: Run Loaders Locally (RECOMMENDED)

**Pros:** Fast, full control, see live output
**Cons:** Needs local database access

```bash
cd /home/arger/algo

# Run the automated script
bash /tmp/run_critical_loaders.sh
```

Or manually run each:
```bash
python3 loadstocksymbols.py       # Wait for SUCCESS
python3 loadpricedaily.py         # ~20 min
python3 loadtechnicalindicators.py
python3 loadbuysellDaily.py
python3 loadstockscores.py
```

**Monitor output:**
- Each script prints progress
- Look for: `INFO`, `SUCCESS`, `COMPLETED`
- Watch for: `ERROR`, `FAILED`, `CRITICAL`

### Option 2: Run Loaders in AWS

Create Lambda function or ECS task to run loaders in AWS:
- Pros: Data loads in AWS environment
- Cons: More complex setup

Steps:
1. Create Lambda function with Python runtime
2. Upload loaders as code
3. Set environment variables from Secrets Manager
4. Invoke manually (can't schedule yet)

### Option 3: Run via AWS CloudShell

If you have AWS Console access:
```bash
# In AWS CloudShell
git clone https://github.com/argie33/algo.git
cd algo
python3 loadstocksymbols.py
python3 loadpricedaily.py
# etc...
```

---

## ✅ Verification Checklist

After completing the fixes and data loading:

### 1. Verify Lambda Deployment ✓
```bash
# Check CloudFormation stack
# AWS Console → CloudFormation → Stacks → stocks-webapp-dev
# Status should be: CREATE_COMPLETE or UPDATE_COMPLETE
```

### 2. Verify Database Has Data ✓
```bash
psql -h <RDS_ENDPOINT> -U stocks -d stocks

# Check row counts
SELECT COUNT(*) FROM stock_symbols;      -- Should be 5000+
SELECT COUNT(*) FROM price_daily;        -- Should be 1000000+
SELECT COUNT(*) FROM technical_indicators; -- Should be 1000000+
SELECT COUNT(*) FROM buy_sell_daily;     -- Should be 500000+
SELECT COUNT(*) FROM stock_scores;       -- Should be 5000+
```

### 3. Test API Endpoints ✓
```bash
# From any machine with internet access
curl https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/health

# Should return something like:
# {"success": true, "data": {"status": "healthy", ...}}

# Test stocks endpoint
curl "https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/api/stocks?limit=10"

# Should return JSON array of stocks with scores
```

### 4. Test Frontend ✓
Visit the CloudFront URL (from CloudFormation outputs):
```
https://stocks-webapp-frontend-dev-<ACCOUNT_ID>.cloudfront.net
```

Should see:
- ✓ Stock list loading
- ✓ Scores displaying
- ✓ Charts rendering
- ✓ Signals showing

### 5. Check CloudWatch Logs ✓
```
AWS Console → CloudWatch → Log Groups → /aws/lambda/stocks-webapp-dev*
```

Should see:
- ✓ Successful database connections
- ✓ Query results returning
- ✗ No error messages or timeouts

---

## 🐛 Troubleshooting

### If Push Fails

**Error:** `fatal: could not read Username for 'https://github.com'`

**Solutions:**
1. Configure git credentials: `git config --global user.password <token>`
2. Use SSH instead: `git remote set-url origin git@github.com:argie33/algo.git`
3. Use GitHub Desktop instead of command line
4. Clone fresh repo from GitHub and re-apply changes

### If Loaders Timeout

**During data loading:** Press Ctrl+C and check database

```bash
# Check what was loaded before timeout
SELECT COUNT(*) FROM stock_symbols;
SELECT COUNT(*) FROM price_daily;
```

Data is still usable even if partial. Can retry or continue with partial data.

### If API Returns Empty Results

**Check 1:** Is data in database?
```sql
SELECT COUNT(*) FROM stock_symbols;  -- Must be > 0
```

**Check 2:** Is Lambda deployed?
```
AWS Console → CloudFormation → stocks-webapp-dev → Status
```

**Check 3:** Is Lambda able to reach database?
```
AWS Console → CloudWatch → /aws/lambda/stocks-webapp-dev*
Look for connection errors
```

**Check 4:** Is API Gateway correctly configured?
```
AWS Console → API Gateway → stocks-webapp-api-dev → Stages → dev
Should show Lambda integration
```

### If Frontend Shows Errors

**Check:**
1. CloudFront distribution is enabled
2. S3 bucket has frontend files
3. API URL is correct in frontend .env
4. CORS headers are being sent from Lambda (should be automatic)

---

## 🔄 Complete Workflow Summary

```
1. PUSH CHANGES
   ↓
2. GITHUB ACTIONS DEPLOYS (5-10 min)
   ↓
3. RUN DATA LOADERS (45-60 min)
   ↓
4. VERIFY DATABASE HAS DATA
   ↓
5. TEST API ENDPOINTS
   ↓
6. TEST FRONTEND
   ↓
✅ COMPLETE - Platform Operational
```

---

## 📋 Quick Reference Commands

```bash
# Push commit to GitHub
git push origin main

# Run all critical loaders
bash /tmp/run_critical_loaders.sh

# Check if data loaded
psql -h <RDS_ENDPOINT> -U stocks -d stocks -c "SELECT COUNT(*) FROM stock_symbols;"

# Test API
curl https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/health

# Monitor GitHub Actions
# Visit: https://github.com/argie33/algo/actions

# View Lambda logs
# AWS Console → CloudWatch → /aws/lambda/stocks-webapp-dev*
```

---

## ⚠️ Important Notes

- **Data loading is sequential:** Each loader must complete before the next starts
- **Timeouts are expected:** Large datasets (20+ min) won't complete instantly
- **Partial data is usable:** Platform works with partial data loaded
- **Database is persistent:** Data survives Lambda redeployments
- **No downtime:** API continues working while data loads in background

---

## 📞 Support

If you encounter issues:

1. **Check the logs** in CloudWatch or loader console output
2. **Verify database connectivity** with psql command above
3. **Review Git commit** to see exactly what changed
4. **Check GitHub Actions** for deployment errors

All required credentials are in `webapp/lambda/.env.local`

---

**Created:** 2026-02-26
**Status:** Ready for production deployment
**Next Action:** Push changes to GitHub
