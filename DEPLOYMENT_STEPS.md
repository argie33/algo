# Deployment Steps - Get Everything Working

**Goal:** Frontend + API working end-to-end in AWS (1-2 hours)

---

## STEP 1: Get API URL from AWS (5 min)

**Prerequisite:** AWS credentials configured locally
```bash
aws configure
# Enter: Access Key ID, Secret Access Key, region (us-east-1)
```

**Get API URL:**
```bash
API_URL=$(aws apigatewayv2 get-apis \
  --region us-east-1 \
  --query "Items[?Name=='algo-api-dev'].ApiEndpoint" \
  --output text)

echo "API_URL=$API_URL"
# Expected output: https://xxxxxxx.execute-api.us-east-1.amazonaws.com
```

**Save this URL** — you'll use it in the next step.

---

## STEP 2: Test API Is Callable (2 min)

```bash
# Replace with your API_URL from Step 1
API_URL="https://xxxxxxx.execute-api.us-east-1.amazonaws.com"

# Test health endpoint
curl -X GET "$API_URL/health"
# Expected: {"status": "healthy"}

# Test data endpoint
curl "$API_URL/api/scores/stockscores?limit=1"
# Expected: JSON response (may be empty if no data loaded yet)
```

✅ If both work, **API is deployed and callable.**

---

## STEP 3: Build & Deploy Frontend (20 min)

**Set API URL and build:**
```bash
cd webapp/frontend

# Build with API URL
VITE_API_URL="$API_URL" npm run build

# Result: dist/ folder ready
ls -la dist/
```

**Deploy to S3:**
```bash
# Get S3 bucket name
BUCKET=$(aws s3 ls | grep algo-frontend | awk '{print $3}')
echo "Bucket: $BUCKET"

# Upload
aws s3 sync dist/ "s3://$BUCKET/" --delete --region us-east-1

# Verify
aws s3 ls "s3://$BUCKET/" | head
echo "✅ Frontend deployed to S3"
```

---

## STEP 4: Set Up CloudFront & Domain (10 min)

**Get CloudFront URL:**
```bash
DIST_ID=$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?Origins[0].S3OriginConfig]|[0].Id" \
  --output text)

DOMAIN=$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?Origins[0].S3OriginConfig]|[0].DomainName" \
  --output text)

echo "CloudFront Domain: https://$DOMAIN"
echo "Distribution ID: $DIST_ID"
```

**Invalidate cache (so latest code serves immediately):**
```bash
aws cloudfront create-invalidation \
  --distribution-id "$DIST_ID" \
  --paths "/*" \
  --region us-east-1

echo "✅ Cache invalidated"
```

---

## STEP 5: Verify End-to-End (5 min)

**Open frontend in browser:**
```bash
open "https://$DOMAIN"  # macOS
# or
start "https://$DOMAIN"  # Windows
# or
xdg-open "https://$DOMAIN"  # Linux
```

**Check Network Tab:**
1. Open DevTools (F12)
2. Go to Network tab
3. Refresh page
4. Look for API calls to `$API_URL/api/...`
5. Verify responses are JSON (not errors)

**Check for:**
- ✅ Network tab shows `/api/scores/stockscores` request
- ✅ Response status is 200 (not 404 or 503)
- ✅ Response body is valid JSON
- ✅ No CORS errors in Console

---

## STEP 6: Test Critical Pages (10 min)

Navigate to:
- [ ] Scores Dashboard — should show stock scores (or "loading" placeholder)
- [ ] Deep Value — should show valued stocks (or empty)
- [ ] Trade Tracker — should show trade history
- [ ] Performance Metrics — should show P&L

**If pages show "No data available":**
→ This is expected until loaders populate database (see STEP 7)

**If pages show errors in console:**
→ Check Network tab, verify API responses

---

## STEP 7: Load Sample Data (Optional, 30+ min)

**Current blocker:** yfinance fails in AWS VPC

**Option A: Load Locally (Recommended)**
```bash
# On your laptop (with public internet)
source .env.local  # or set env vars

python3 loaders/loadstocksymbols.py
python3 loaders/loadstocksymbols_daily.py
python3 loaders/load_price_daily.py

# Verify data loaded
python3 -c "
from utils.db_connection import get_db_connection
conn = get_db_connection()
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM price_daily')
print(f\"Prices loaded: {cur.fetchone()[0]}\")
cur.close()
"
```

**Option B: Fix AWS Network (Requires Terraform)**
```bash
# Create VPC endpoint for HTTPS (yfinance API access)
cd terraform
terraform apply -target=aws_vpc_endpoint.https
# This allows ECS tasks to reach external APIs
```

**Option C: Skip Data** 
→ API works with empty tables (UI shows "no data")

---

## TROUBLESHOOTING

### Frontend shows "Cannot reach API"
```bash
# Check API_URL is correct
echo "API_URL=$API_URL"

# Check CORS headers in API response
curl -i "$API_URL/health"
# Look for: Access-Control-Allow-Origin: *

# Check frontend config was built with correct URL
grep "VITE_API_URL" webapp/frontend/dist/assets/*.js || echo "Not found in build"
```

### API returns 503
```bash
# Lambda may be cold-starting, retry after 10 seconds
curl "$API_URL/health"
sleep 10
curl "$API_URL/health"

# Check Lambda logs
aws logs tail "/aws/lambda/algo-api-dev" --follow
```

### S3 bucket not found
```bash
# List all S3 buckets
aws s3 ls

# Find the right bucket
aws s3 ls | grep -i algo
```

### CloudFront showing old version
```bash
# Invalidate cache again
aws cloudfront create-invalidation \
  --distribution-id "$DIST_ID" \
  --paths "/*"

# Wait ~30 seconds for invalidation
# Then refresh browser (Ctrl+Shift+R to skip cache)
```

---

## FINAL CHECKLIST

- [ ] Step 1: API URL retrieved
- [ ] Step 2: `curl /health` returns 200
- [ ] Step 3: Frontend built with VITE_API_URL
- [ ] Step 4: Frontend deployed to S3
- [ ] Step 5: Frontend accessible at CloudFront URL
- [ ] Step 6: Network tab shows API calls
- [ ] Step 7: (Optional) Data loaded

---

## SUCCESS = FULLY DEPLOYED & WORKING

```
Frontend (CloudFront) → API (Lambda) → Database (RDS)
✅ Frontend loads        ✅ API responds        ✅ Data ready
```

**Time to completion:** 1-2 hours  
**Outcome:** Production-ready system visible via browser

