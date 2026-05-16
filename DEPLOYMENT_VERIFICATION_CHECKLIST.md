# Deployment Verification Checklist

**Date:** 2026-05-17  
**Status:** Ready to execute once API returns 200

---

## Phase 1: API Authentication Fix Verification (5 minutes)

### 1.1 Health Endpoint
```bash
curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/health
# Expected: {"success":true,"data":{"status":"healthy",...},"timestamp":"..."} 200
```
- [ ] Returns 200 OK
- [ ] Response includes timestamp

### 1.2 Data Endpoints (Core Fix Verification)
```bash
# Test 1: Algo status (should hit _handle_algo)
curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/status
# Expected: {"status":"operational"} 200 (NOT 401)

# Test 2: Stock scores (should hit _get_stock_scores with new fields)
curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/scores/stockscores?limit=5
# Expected: Array with: symbol, current_price, change_percent, market_cap, score

# Test 3: Exposure policy (should hit _get_exposure_policy with fixed SQL)
curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/exposure-policy
# Expected: exposure_pct, exposure_tier, is_entry_allowed, regime
```
- [ ] `/api/algo/status` returns 200 with status field
- [ ] `/api/scores/stockscores` returns 200 with data array
- [ ] Response includes `current_price` field (not `price`)
- [ ] Response includes `change_percent` field
- [ ] Response includes `market_cap` field
- [ ] `/api/algo/exposure-policy` returns 200 with correct fields

---

## Phase 2: Dashboard Functionality (10 minutes)

### 2.1 MetricsDashboard
Open: `https://YOUR-CLOUDFRONT-URL/app/dashboard/metrics`
- [ ] Page loads without errors
- [ ] Stock list displays (not empty)
- [ ] Can sort by different columns
- [ ] Shows stock symbols, prices, change percentages
- [ ] No console errors in DevTools

### 2.2 ScoresDashboard  
Open: `https://YOUR-CLOUDFRONT-URL/app/dashboard/scores`
- [ ] Page loads without errors
- [ ] Score table shows data
- [ ] Prices display correctly (not null)
- [ ] Sorting works (by score, price, etc.)
- [ ] No console errors

### 2.3 VaR Dashboard
Open: `https://YOUR-CLOUDFRONT-URL/app/dashboard/var`
- [ ] Page loads without errors
- [ ] VaR calculations display (or "insufficient data" message if <5 snapshots)
- [ ] No 500 errors in Lambda logs

### 2.4 Market Exposure Dashboard
Open: `https://YOUR-CLOUDFRONT-URL/app/dashboard/market-exposure`
- [ ] Page loads without errors
- [ ] Sector/industry breakdown displays
- [ ] Exposure policy shows (regime, tier, entry allowed)
- [ ] No console errors

---

## Phase 3: Data Integrity Checks (10 minutes)

### 3.1 API Response Format Validation
```bash
# Verify response format matches frontend expectations
python3 << 'EOF'
import json
import requests

api_url = "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com"

# Test stock scores endpoint
resp = requests.get(f"{api_url}/api/scores/stockscores?limit=3")
data = resp.json()

print(f"Status: {resp.status_code}")
print(f"Response keys: {list(data.keys())}")

if 'data' in data:
    scores = data['data']
    if scores and len(scores) > 0:
        print(f"First item keys: {list(scores[0].keys())}")
        print(f"Required fields present: {all(k in scores[0] for k in ['symbol', 'current_price', 'score'])}")
    else:
        print("No data in response")
elif 'items' in data:
    print(f"Response has 'items' key (wrapped format)")
else:
    print(f"Unexpected response format: {data}")
EOF
```
- [ ] Stock scores endpoint returns data in expected format
- [ ] Required fields present: `symbol`, `current_price`, `score`
- [ ] No null values in critical fields
- [ ] Pagination works if data is large

### 3.2 Calculation Verification
```bash
# Verify calculations are correct
python3 << 'EOF'
import requests

api_url = "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com"

# Get stock scores
resp = requests.get(f"{api_url}/api/scores/stockscores?limit=10")
scores = resp.json().get('data', [])

# Validate calculations
for stock in scores[:3]:
    print(f"{stock['symbol']}: price={stock.get('current_price')}, score={stock.get('score')}, change={stock.get('change_percent')}%")
    
    # change_percent should be numeric
    if stock.get('change_percent') is not None:
        try:
            float(stock['change_percent'])
            print("  ✓ change_percent is numeric")
        except:
            print(f"  ✗ change_percent not numeric: {stock['change_percent']}")
EOF
```
- [ ] `change_percent` is numeric (not null)
- [ ] `market_cap` present and numeric
- [ ] Scores within expected range (0-100 or similar)
- [ ] Prices positive and reasonable

---

## Phase 4: Lambda & Database Health (5 minutes)

### 4.1 CloudWatch Logs Check
Go to: AWS CloudWatch → Logs → Log Groups
- [ ] `/aws/lambda/algo-api-dev` - No ERROR or CRITICAL messages in last 5 min
- [ ] `/aws/lambda/algo-algo-dev` - Orchestrator logs show successful phase completions
- [ ] No timeout errors (Lambda timeout = 25s)
- [ ] No database connection failures

### 4.2 RDS Database Health
```bash
# If you have AWS CLI access:
aws rds describe-db-instances --db-instance-identifier algo-db --region us-east-1 \
  --query 'DBInstances[0].{Status:DBInstanceStatus,Engine:Engine,AllocatedStorage:AllocatedStorage}'
```
- [ ] Database status is `available`
- [ ] No pending maintenance
- [ ] Connection pool not exhausted

---

## Phase 5: Frontend Asset Delivery (5 minutes)

### 5.1 Assets Loading
Open `https://YOUR-CLOUDFRONT-URL/` and check:
```javascript
// In browser console:
console.log("Location:", window.location);
console.log("API Config:", window.__CONFIG__?.API_URL);
console.log("React Version:", React.version);
```
- [ ] CloudFront returns 200 for index.html
- [ ] `window.__CONFIG__.API_URL` is set correctly
- [ ] React components load without errors
- [ ] No 404s for CSS/JS assets

### 5.2 Authentication State (if Cognito was disabled)
```javascript
// Check if auth is properly disabled
const auth = window.Auth || window.amplify?.Auth;
console.log("Auth configured:", !!auth);
console.log("User signed in:", auth?.currentAuthenticatedUser ? "yes" : "no (expected if auth disabled)");
```
- [ ] Frontend loads even without authentication
- [ ] Login redirect doesn't appear (if auth was disabled)
- [ ] Dashboard pages accessible without login

---

## Phase 6: Performance Baseline (optional, 5 minutes)

### 6.1 API Response Times
```bash
# Measure response time
for i in {1..5}; do
  curl -w "Time: %{time_total}s\n" -o /dev/null -s \
    https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/scores/stockscores?limit=100
done
# Expected: < 2 seconds per request
```
- [ ] Average API response time < 2 seconds
- [ ] No timeout errors

### 6.2 Database Query Performance
```bash
# Check slow query logs (if available)
# Expected: All queries < 1 second
```
- [ ] No slow queries in logs
- [ ] Query execution times reasonable

---

## Success Criteria ✅

- **Critical:** All Phase 1 endpoints return 200 (not 401)
- **Critical:** Dashboard pages load without errors
- **Critical:** Data displays with correct field names and values
- **Important:** No ERROR logs in CloudWatch
- **Important:** Response times < 2 seconds

---

## If Anything Fails

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| Still getting 401 on data endpoints | Terraform didn't apply changes | Check GitHub Actions workflow, retry deployment |
| Empty tables on dashboards | Data loaders haven't run yet | Wait until 4:05pm ET or trigger manually |
| Wrong field names (e.g., `price` instead of `current_price`) | Code changes not deployed | Check Lambda logs, verify zip deployment |
| Null values in change_percent/market_cap | Schema mismatch | Rerun database initialization, verify column exists |
| 500 errors in Lambda | Query error or calculation issue | Check CloudWatch logs for specific error, review Lambda code |
| Frontend not loading | CloudFront/S3 issue | Check S3 bucket and CloudFront distribution |

---

## Verification Commands Quick Reference

```bash
# Full system health check
echo "Health:" && curl -s https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/health | jq .

echo "Status:" && curl -s https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/status | jq .

echo "Scores (first 3):" && curl -s "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/scores/stockscores?limit=3" | jq '.data | .[:3]'

echo "Exposure:" && curl -s https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/exposure-policy | jq .
```

