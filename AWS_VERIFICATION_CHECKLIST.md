# AWS Verification Checklist (2026-05-15)

**Status:** System deployed with fixes. Need to verify everything works in AWS.

---

## ✅ STEP 1: Verify GitHub Actions Deployment Succeeded (5 min)

```bash
# Open in browser:
https://github.com/argie33/algo/actions

# Look for "Deploy All Infrastructure" workflow
# Check status: ✅ All jobs passed OR ❌ Any job failed
# If failed: Click job → View logs → Find error → Fix → Commit → Push to trigger redeploy
```

**Expected:**
- Job 1: Terraform Apply ✅
- Job 2: Build Docker Image ✅
- Job 3: Deploy Algo Lambda ✅
- Job 4: Deploy API Lambda ✅
- Job 5: Deploy Frontend ✅
- Job 6: Initialize Database ✅

---

## ✅ STEP 2: Test API Health (2 min)

```bash
# Test API is responding:
curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/health

# Expected response:
# {"status": "healthy", "timestamp": "2026-05-15T..."}
# OR {"success": true, "message": "API Gateway connected"}

# If 503 or timeout: Lambda not deployed, check GitHub Actions
# If 400/403: Auth issue, check API Gateway configuration
```

---

## ✅ STEP 3: Verify Database Schema in AWS (3 min)

```bash
# Connect to RDS database:
# (You'll need RDS endpoint from AWS Console → RDS → Databases → algo-db)

psql -h <RDS-ENDPOINT> -U stocks -d stocks -c "
SELECT COUNT(*) as table_count FROM information_schema.tables 
WHERE table_schema = 'public';"

# Expected: Should return 50+ tables

# Check critical tables exist:
psql -h <RDS-ENDPOINT> -U stocks -d stocks -c "
\dt market_sentiment analyst_sentiment_analysis price_daily buy_sell_daily stock_scores"

# Expected: All tables listed with ✅
```

---

## ✅ STEP 4: Verify Data is Fresh (5 min)

Run the verification script:

```bash
# From algo directory:
python3 verify_data_loaders.py

# Expected output:
# ✅ price_daily: OK (today's data)
# ✅ technical_data_daily: OK (today's data)
# ✅ stock_scores: OK (within 48h)
# ✅ buy_sell_daily: OK (today's data)
# ✅ market_health_daily: OK (today's data)

# If any FAILED:
# → Check data loader logs: aws logs tail /aws/ecs/data-loaders
# → Check orchestrator logs: aws logs tail /aws/lambda/algo-orchestrator
# → Find error → Fix code → Commit → Push → Redeploy
```

---

## ✅ STEP 5: Test Frontend (3 min)

```bash
# Visit in browser:
https://d5j1h4wzrkvw7.cloudfront.net

# Test each page:
□ Home/Dashboard → Loads without 404
□ Markets Health → Shows SPY/QQQ prices (real data, not mock)
□ Trading Signals → Lists actual signals from database
□ Stock Detail (pick AAPL) → All tabs load with real data
  □ Chart tab → Price history visible
  □ Statistics tab → Scores, metrics visible
  □ Signals tab → Buy/sell signals visible
  □ Analyst tab → Sentiment data visible
□ Portfolio → Shows open positions
□ Trades → Shows trade history

# If any page errors:
□ Check browser console (F12) for 404s or JS errors
□ Check API endpoint being called
□ Check if that endpoint is implemented in lambda/api/
□ Fix API endpoint if missing
□ Redeploy
```

---

## ✅ STEP 6: Check CloudWatch Logs for Errors (5 min)

```bash
# Orchestrator logs (should show Phase 1-7 execution):
aws logs tail /aws/lambda/algo-orchestrator --follow --since 6h

# Watch for:
✅ "Phase 1" starting
✅ "Phase 2" starting
... through Phase 7
❌ Any ERROR or CRITICAL messages → Note them

# Data loader logs:
aws logs tail /aws/ecs/data-loaders --follow --since 6h

# Watch for:
✅ Loader names executing
✅ "rows inserted" messages
❌ Any "ERROR" or "FAILED" messages → Note them
```

---

## ✅ STEP 7: Run API Tests

```bash
# Test key endpoints:

# 1. Get stock list
curl "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/stocks?limit=10"

# 2. Get specific stock
curl "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/stocks/AAPL"

# 3. Get prices
curl "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/prices/history/AAPL?days=30"

# 4. Get signals
curl "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/signals/stocks?symbol=AAPL"

# 5. Get sentiment
curl "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/sentiment/analyst/insights/AAPL"

# Expected: All return JSON with data (not 500 errors)
```

---

## 📋 Issues Found & Actions

| Issue | Symptom | Fix | Priority |
|-------|---------|-----|----------|
| | | | |

**Record any issues found and we'll fix them immediately.**

---

## 🔧 When You Find Issues

**Example workflow:**
1. Found error: "market_sentiment table doesn't exist"
2. Check logs: `aws logs tail /aws/lambda/algo-orchestrator`
3. Find which loader is failing
4. Check code: `grep -r "market_sentiment" loadmarket*.py`
5. Fix the code
6. Commit: `git add . && git commit -m "fix: market sentiment table issue"`
7. Push: `git push origin main` (auto-deploys)
8. Wait for GitHub Actions to complete
9. Re-test

---

## 📞 Emergency Debug

If everything breaks, check in this order:

1. **API not responding?**
   ```bash
   aws lambda list-functions --region us-east-1 | grep algo
   # Should show: algo-orchestrator, algo-api-lambda (both exist?)
   ```

2. **Database connection fails?**
   ```bash
   aws rds describe-db-instances --region us-east-1
   # Should show: DBInstanceStatus = "available"
   ```

3. **Loaders not running?**
   ```bash
   aws events list-rules --region us-east-1 | grep -i loader
   # Should show: EventBridge rules for each loader
   ```

4. **Frontend not loading?**
   ```bash
   aws s3 ls s3://algo-frontend-bucket/
   # Should show: index.html and assets
   ```

---

## ✅ Verification Complete When:

- [x] All GitHub Actions jobs passed
- [x] API health endpoint returns 200
- [x] Database has 50+ tables
- [x] Data is fresh (verify_data_loaders.py passes)
- [x] Frontend loads with real data
- [x] No ERROR or CRITICAL in CloudWatch logs
- [x] All 5 sample API endpoints return 200 with data

**Then: System is production-ready for trading.**
