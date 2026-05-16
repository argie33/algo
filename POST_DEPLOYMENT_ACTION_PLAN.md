# Post-Deployment Action Plan

**Status:** Ready to execute once API returns 200 Unauthorized → 200 OK

---

## 🚀 Phase 1: Immediate Verification (10 minutes)

### Step 1: Confirm API Authorization Fix
```bash
# Should return 200 (not 401)
curl -w "Status: %{http_code}\n" https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/status
```

Expected:
```json
{"status":"operational","timestamp":"..."}
Status: 200
```

### Step 2: Run Full System Validation
```bash
python3 run_full_system_validation.py
```

This test verifies:
- ✅ Health endpoint responsive
- ✅ Algo status endpoint working
- ✅ Stock scores endpoint returning data with correct format
- ✅ Exposure policy endpoint working
- ✅ API response times (<2s)
- ✅ Calculations are correct (numeric values, valid ranges)

### Step 3: Run API Format Validator
```bash
python3 validate_api_responses.py
```

This independently verifies:
- Response format matches frontend expectations
- Required fields present
- No null values in critical fields

---

## 🎯 Phase 2: Dashboard Verification (15 minutes)

Open each dashboard in browser and verify real data displays:

### Dashboard 1: Metrics Dashboard
- URL: `https://YOUR-CLOUDFRONT-URL/app/dashboard/metrics`
- Verify:
  - [ ] Stock list displays (not empty)
  - [ ] Shows 5000+ stocks
  - [ ] Can sort by columns
  - [ ] Prices display correctly
  - [ ] No console errors

### Dashboard 2: Scores Dashboard
- URL: `https://YOUR-CLOUDFRONT-URL/app/dashboard/scores`
- Verify:
  - [ ] Score table populated
  - [ ] Prices not null
  - [ ] Can sort by score/price/trend
  - [ ] Minervini phases displaying
  - [ ] No console errors

### Dashboard 3: VaR Dashboard
- URL: `https://YOUR-CLOUDFRONT-URL/app/dashboard/var`
- Verify:
  - [ ] Page loads without errors
  - [ ] Shows "insufficient data" or VaR values
  - [ ] No 500 errors in Lambda logs

### Dashboard 4: Market Exposure
- URL: `https://YOUR-CLOUDFRONT-URL/app/dashboard/market-exposure`
- Verify:
  - [ ] Sector/industry breakdown displays
  - [ ] Exposure policy shows (regime, tier, entry allowed)
  - [ ] No console errors

### Dashboard 5: Portfolio Dashboard
- URL: `https://YOUR-CLOUDFRONT-URL/app/dashboard`
- Verify:
  - [ ] All pages accessible
  - [ ] No 401 errors
  - [ ] Data displays with real numbers
  - [ ] Charts and tables render correctly

---

## 📊 Phase 3: Data Integrity Checks (10 minutes)

### Check 1: Data Flow Verification
```bash
# Verify the complete data pipeline
python3 << 'EOF'
import requests

api_url = "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com"

# 1. Check scores endpoint
scores = requests.get(f"{api_url}/api/scores/stockscores?limit=100").json()
print(f"Scores: {len(scores.get('data', []))} items")

# 2. Check positions endpoint
positions = requests.get(f"{api_url}/api/algo/positions").json()
print(f"Positions: {positions}")

# 3. Check trades endpoint
trades = requests.get(f"{api_url}/api/algo/trades?limit=10").json()
print(f"Trades: {trades}")

# 4. Verify field names match across all endpoints
if scores.get('data'):
    first_score = scores['data'][0]
    print(f"\nStock scores fields: {list(first_score.keys())}")
    print(f"Sample: {first_score.get('symbol')} - price:{first_score.get('current_price')} score:{first_score.get('score')}")
EOF
```

### Check 2: CloudWatch Logs Review
```bash
# Check for errors in Lambda logs
aws logs tail /aws/lambda/algo-api-dev --since 10m --follow
# Look for: ERROR, CRITICAL, Traceback, timeout
```

### Check 3: Database Health
```bash
# If you have AWS CLI access:
aws rds describe-db-instances --db-instance-identifier algo-db \
  --query 'DBInstances[0].[DBInstanceStatus,Engine,AllocatedStorage]'
# Expected: available, postgres, 100+GB
```

---

## ⚡ Phase 4: Performance Validation (10 minutes)

### Load Test
```bash
# Test API under moderate load
for i in {1..10}; do
  curl -s https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/scores/stockscores?limit=50 > /dev/null &
done
wait

# Check response times (should all complete <2s)
# Check CloudWatch for any throttling or errors
```

### Database Performance
```bash
# Sample query performance
python3 << 'EOF'
import requests
import time

url = "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/scores/stockscores"

for i in range(5):
    start = time.time()
    resp = requests.get(url + f"?limit=1000")
    elapsed = time.time() - start
    print(f"Request {i+1}: {elapsed:.3f}s - Status {resp.status_code}")
EOF
```

Expected: All requests <2s, no 500 errors

---

## 🔍 Phase 5: Data Quality Deep-Dive (15 minutes)

### Check 1: Verify Critical Calculations
```bash
python3 << 'EOF'
import requests

api = "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com"

# Get stock scores and verify calculations
scores = requests.get(f"{api}/api/scores/stockscores?limit=50").json()

for stock in scores.get('data', [])[:5]:
    symbol = stock.get('symbol')
    price = stock.get('current_price')
    change = stock.get('change_percent')
    score = stock.get('score')
    cap = stock.get('market_cap')
    
    # Verify all critical fields are present and numeric
    print(f"{symbol}: ${price} ({change}%) - Score:{score} - MarketCap:{cap}")
    
    # Verify calculations make sense
    assert price is not None, f"{symbol} has null price"
    assert price > 0, f"{symbol} has negative price"
    assert 0 <= score <= 100 if score else True, f"{symbol} score out of range"
    
print("\n✅ All calculations valid")
EOF
```

### Check 2: Verify No Data Gaps
```bash
# Check that loaders have populated data
python3 << 'EOF'
import requests

api = "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com"

endpoints = [
    ("/api/scores/stockscores?limit=1", "Stock Scores"),
    ("/api/algo/exposure-policy", "Exposure Policy"),
    ("/api/algo/var", "VaR"),
]

for endpoint, name in endpoints:
    resp = requests.get(api + endpoint)
    if resp.status_code == 200:
        data = resp.json()
        has_data = bool(data.get('data') or data.get('items'))
        status = "✓" if has_data else "⚠"
        print(f"{status} {name}: {resp.status_code}")
    else:
        print(f"✗ {name}: {resp.status_code}")
EOF
```

---

## ✅ Final Sign-Off

Once all phases complete successfully:

- [ ] Phase 1: API returning 200 for all endpoints
- [ ] Phase 2: All dashboards displaying real data
- [ ] Phase 3: No errors in CloudWatch logs
- [ ] Phase 4: API response times <2s consistently
- [ ] Phase 5: All calculations correct, no data gaps

**System Status:** 🟢 **PRODUCTION READY**

---

## 🔧 If Issues Found

| Issue | Root Cause | Quick Fix |
|-------|-----------|-----------|
| Still getting 401 | Terraform didn't apply | Check GitHub Actions logs, retry deployment |
| Empty data in dashboards | Loaders haven't run | Wait until 4:05pm ET or manually trigger |
| Wrong field names | Code not deployed | Check Lambda function version in AWS |
| Null values in critical fields | Schema mismatch | Run init_database.py to sync schema |
| 500 errors in Lambda | Query error | Check CloudWatch logs for SQL error details |
| Slow API response (>2s) | Database query inefficiency | Check if indexes are created, consider caching |
| Frontend not loading | CloudFront/S3 issue | Check S3 bucket and CloudFront distribution |

---

## 📝 Documentation

- `DEPLOYMENT_VERIFICATION_CHECKLIST.md` — Detailed phase breakdown
- `validate_api_responses.py` — Automated API format validation
- `run_full_system_validation.py` — Complete system validation script
- `STATUS.md` — Current system status and logs

---

**Next Step:** Once Terraform deployment completes, execute Phase 1 step by step.

