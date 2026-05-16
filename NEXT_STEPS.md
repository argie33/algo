# 🚀 Next Steps - Quick Reference

**Last Updated:** 2026-05-15  
**All Previous Audit Documents:** See folder root for AUDIT_FINDINGS.md, SESSION_SUMMARY.md, etc.

---

## DO THIS IMMEDIATELY (Today)

### 1️⃣ Verify Data is Loading in AWS
```bash
# Check if EventBridge is executing loaders
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/"
aws logs tail /aws/lambda/algo-data-loader --follow

# Check if database has fresh data (RDS)
psql -h <your-rds-endpoint> -U stocks -d stocks -c "SELECT MAX(date) FROM price_daily;"
psql -h <your-rds-endpoint> -U stocks -d stocks -c "SELECT COUNT(*) FROM stock_scores WHERE date = CURRENT_DATE;"
```

### 2️⃣ Deploy Market Sentiment Loader
```bash
# Add loadmarketsentiment.py to your EventBridge schedule
# Edit .github/workflows/deploy-all-infrastructure.yml
# Add new step to run: python3 loadmarketsentiment.py

git add -A
git commit -m "feat: Add market sentiment data loader and database schema fixes"
git push origin main

# Monitor deployment: https://github.com/argie33/algo/actions
```

### 3️⃣ Check Deployment Status
```bash
# Go to GitHub Actions and watch the deploy-all-infrastructure workflow
# All 6 jobs should succeed:
#   ✅ Terraform Apply
#   ✅ Build Docker Image  
#   ✅ Deploy Algo Lambda
#   ✅ Deploy API Lambda
#   ✅ Build & Deploy Frontend
#   ✅ Initialize Database Schema
```

### 4️⃣ Test One Endpoint
```bash
# Hit the API to verify error handling improvements
curl -X GET "https://YOUR_API_ENDPOINT/api/health"
# Should return: {"status": "healthy", "timestamp": "..."}

curl -X GET "https://YOUR_API_ENDPOINT/api/sentiment/data"
# Should return real data or proper error code (not 200 with empty response)
```

---

## THIS WEEK (5 Priority Items)

### Day 1-2: Data Verification
- [ ] Verify all 50+ database tables have data
- [ ] Check data age across all tables
- [ ] Confirm EventBridge scheduler is running
- [ ] Set up CloudWatch alarms for stale data

### Day 3: Frontend Testing
- [ ] Visit https://d5j1h4wzrkvw7.cloudfront.net
- [ ] Check Sentiment page shows data
- [ ] Check Economic Dashboard shows data
- [ ] Check Commodities Analysis shows data
- [ ] Check Markets Health shows data

### Day 4: Remaining Fixes  
- [ ] Create social sentiment data loader (4 hours)
- [ ] Fix remaining error handling (15+ locations, 3 hours)
- [ ] Verify commodity data loaders (2 hours)

### Day 5: Testing & Monitoring
- [ ] Run test suite in WSL: `pytest -v`
- [ ] Monitor CloudWatch logs for errors
- [ ] Check data freshness every 2 hours
- [ ] Document any failures

---

## CRITICAL PATH (Blocking Issues)

### Issue #1: Data Loaders Not Running  
**Severity:** CRITICAL  
**Status:** 🔴 UNKNOWN - needs verification  
**Fix Time:** 1-2 hours  
**Blocker:** Frontend pages will show empty data

**Action:**  
```bash
# Check if loaders are scheduled
aws events list-rules --name-prefix "stocks-"
aws lambda list-functions --query 'Functions[*].FunctionName' | grep -i load

# Check execution logs
aws logs tail /aws/lambda/loadpricedaily --follow
aws logs tail /aws/lambda/loadstockscores --follow
```

### Issue #2: Social Sentiment Endpoint Stubbed
**Severity:** HIGH  
**Status:** 🟡 NEEDS IMPLEMENTATION  
**Fix Time:** 4 hours  
**Blocker:** /api/sentiment/social/insights/ returns empty

**What To Do:**  
1. Create `loadsocialsentiment.py` (follow loadmarketsentiment.py pattern)
2. Create/populate `sentiment_social` table in schema
3. Add to EventBridge schedule
4. Deploy

### Issue #3: Error Handling Inconsistent
**Severity:** MEDIUM  
**Status:** 🟢 PARTIALLY FIXED (8 endpoints done, 15+ remain)  
**Fix Time:** 3 hours  
**Impact:** Frontend can't distinguish errors

**Remaining Work:**  
- 15 more locations return 200 OK that should be 4xx/5xx
- Pattern: Find all `return json_response(200, [])` and `return json_response(200, {})`
- Replace with `return error_response(STATUS, 'error', message)`

---

## 📋 Commit Checklist

Before you push, make sure:
- [ ] All `.py` files are syntactically valid
- [ ] Database migrations are idempotent (IF NOT EXISTS)
- [ ] Lambda code tested locally with docker-compose
- [ ] No hardcoded credentials or API keys
- [ ] Commit message explains WHY (not just WHAT)
- [ ] All fixes documented in commit message

---

## 🧪 How To Run Tests (When WSL Works)

```bash
# Enter WSL from PowerShell (Admin)
wsl -u argeropolos

# In WSL terminal:
cd /mnt/c/Users/arger/code/algo

# Start database
docker-compose up -d

# Run tests
python3 -m pytest test_algo_locally.py -v
python3 -m pytest test_lambda_handler.py -v
python3 -m pytest test_data_loaders.py -v

# Check database has data
python3 << 'EOF'
import psycopg2
conn = psycopg2.connect(host='localhost', database='stocks', user='stocks')
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM stock_scores")
print("Stock scores:", cur.fetchone()[0])
EOF
```

---

## 📊 Success Indicators

**Data is flowing when:**
- ✅ `SELECT MAX(date) FROM price_daily` shows today's date
- ✅ `SELECT MAX(date) FROM stock_scores` shows today's date
- ✅ Frontend pages display real numbers (not empty)
- ✅ CloudWatch shows loader executions every 24 hours

**API is healthy when:**
- ✅ `/api/health` returns 200 with healthy status
- ✅ `/api/stocks` returns real stock data
- ✅ Error endpoints return 4xx/5xx (not 200 OK)
- ✅ No errors in CloudWatch Logs

**Tests are passing when:**
- ✅ `pytest` shows all green checkmarks
- ✅ No "FAILED" or "ERROR" messages
- ✅ Test coverage > 80%

---

## 🆘 If Something Breaks

### Database Connection Fails
```bash
# Check RDS is accessible
aws rds describe-db-instances --db-instance-identifier stocks-data-rds

# Check security group allows 5432
aws ec2 describe-security-groups | grep -A 20 "rds"

# Test connection
psql -h <rds-endpoint> -U stocks -d stocks -c "SELECT 1;"
```

### Lambda Function Fails
```bash
# Check CloudWatch logs
aws logs tail /aws/lambda/api-handler --follow

# Invoke manually to test
aws lambda invoke \
  --function-name api-handler \
  --payload '{"path":"/api/health","httpMethod":"GET"}' \
  /tmp/response.json

cat /tmp/response.json
```

### Data Not Loading
```bash
# Check EventBridge schedule
aws events describe-rule --name stocks-data-loader
aws events list-targets-by-rule --rule stocks-data-loader

# Check Lambda execution
aws lambda get-function-concurrency --function-name loadpricedaily
```

---

## 💡 Pro Tips

1. **Save time:** Always check CloudWatch logs FIRST before debugging locally
2. **Deploy early:** Push changes to main often, CI/CD catches issues
3. **Monitor always:** Set up CloudWatch alarms for data staleness
4. **Test in parallel:** Run all tests in parallel to save time: `pytest -n auto`
5. **Document changes:** Good commit messages save future debugging time

---

## 📞 Questions?

Check these docs in order:
1. `AUDIT_FINDINGS.md` — Critical issues with code refs
2. `COMPREHENSIVE_FIXES_SUMMARY.md` — Complete issue list
3. `SESSION_SUMMARY.md` — What was done and why
4. `CRITICAL_FIXES_APPLIED.md` — Detailed fix descriptions

---

*Last Updated: 2026-05-15 | All systems ready for verification*
