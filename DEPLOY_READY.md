# Deployment Implementation Guide - 2026-05-18

**Status:** 🟢 **LOCAL DEVELOPMENT WORKING** | 🟡 **AWS DEPLOYMENT IN PROGRESS**

## ✅ COMPLETED

- [x] Credentials auto-loading for local dev (committed)
- [x] Orchestrator runs locally with --dry-run
- [x] Database schema exists and validates
- [x] API handlers implemented (25+ endpoints)
- [x] Frontend pages built
- [x] Terraform infrastructure defined
- [x] GitHub Actions deploy workflows ready

## 🔴 BLOCKING ITEMS (Must Fix)

### 1. Get API Endpoint URL from AWS
**Current Status:** API Gateway exists in Terraform, Lambda deployed, need invoke URL

**Action:**
```bash
# Run this to get the API endpoint
aws apigatewayv2 get-apis --region us-east-1 --query "Items[?Name=='algo-api-dev'].ApiEndpoint" --output text

# Expected output: https://xxxxxxx.execute-api.us-east-1.amazonaws.com
```

Once you have the URL, save it: **`VITE_API_URL=<URL>`**

### 2. Update Frontend to Use AWS API URL
**File:** `webapp/frontend/src/config/index.js`  
**Current:** Hardcoded to `localhost:3001`  
**Fix Required:** Set `VITE_API_URL` at build time

**Build Command (with API URL):**
```bash
cd webapp/frontend
VITE_API_URL=https://xxxxxxx.execute-api.us-east-1.amazonaws.com npm run build
```

**GitHub Actions:** Add environment variable to build step:
```yaml
- name: Build frontend
  env:
    VITE_API_URL: https://${{ steps.api.outputs.endpoint }}/
  run: npm run build
```

### 3. Deploy Frontend to S3 + CloudFront
**Current:** `webapp/frontend/dist/` built locally, not deployed to AWS  
**Terraform:** S3 + CloudFront defined in `modules/services/main.tf`

**Deploy Steps:**
```bash
# 1. Get S3 bucket name
aws s3 ls | grep algo-frontend

# 2. Upload built files
aws s3 sync webapp/frontend/dist/ s3://<bucket>/ --delete

# 3. Invalidate CloudFront cache
aws cloudfront create-invalidation \
  --distribution-id <DIST_ID> \
  --paths "/*"
```

**Better:** Use GitHub Actions workflow (coming next)

### 4. Verify API Endpoints Are Callable
**Test Health Endpoint:**
```bash
curl -X GET https://xxxxxxx.execute-api.us-east-1.amazonaws.com/health
# Expected: {"status": "healthy"}
```

**Test Data Endpoint:**
```bash
curl https://xxxxxxx.execute-api.us-east-1.amazonaws.com/api/scores/stockscores?limit=5
# Expected: JSON array of stock scores (or empty if data not loaded)
```

### 5. Load Sample Data Into Database
**Current Issue:** Price data not loading from yfinance (network issue in AWS)  
**Temporary Fix:** Load via local loaders and push to AWS RDS

**Steps:**
```bash
# Locally (with PostgreSQL running)
export DB_HOST=localhost
export DB_PASSWORD=stocks
python3 loaders/loadstocksymbols.py  # Start with symbols

# For AWS, we need VPC endpoint or NAT gateway fix (see below)
```

---

## 📋 IMPLEMENTATION CHECKLIST

### Phase 1: Get API URL and Test (30 min)
- [ ] Run AWS CLI command to get API Gateway endpoint
- [ ] Curl /health endpoint to verify API is callable
- [ ] Test /api/scores/stockscores endpoint (expect empty or 200)
- [ ] Document API URL in team notes

### Phase 2: Fix Frontend API Connection (1 hour)
- [ ] Update frontend config with API URL
- [ ] Rebuild frontend: `npm run build`
- [ ] Test locally: `npm run dev` + open http://localhost:5173
- [ ] Check network tab to verify API calls work
- [ ] Deploy to S3 + CloudFront (manual or via GitHub Actions)

### Phase 3: Enable Data Loading (2-4 hours)
**Option A: Fix AWS Network Access (Recommended)**
```bash
# Create VPC endpoint for yfinance API
# OR add NAT gateway to ECS subnet
# OR switch to AWS Glue for data loading
```

**Option B: Load Data Locally, Push to AWS**
```bash
# On your laptop with public internet:
python3 run-all-loaders.py
# This populates local DB with price data
# Then RDS replication or manual transfer to AWS
```

### Phase 4: Deploy via GitHub Actions (1 hour)
Create `.github/workflows/deploy-frontend.yml`:
```yaml
name: Deploy Frontend
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Get API URL
        id: api
        run: |
          API_URL=$(aws apigatewayv2 get-apis --query "Items[?Name=='algo-api-dev'].ApiEndpoint" --output text)
          echo "endpoint=$API_URL" >> $GITHUB_OUTPUT
      
      - name: Build Frontend
        env:
          VITE_API_URL: ${{ steps.api.outputs.endpoint }}
        run: |
          cd webapp/frontend
          npm ci
          npm run build
      
      - name: Deploy to S3
        run: |
          aws s3 sync webapp/frontend/dist/ s3://${{ secrets.FRONTEND_BUCKET }}/ --delete
      
      - name: Invalidate CloudFront
        run: |
          aws cloudfront create-invalidation \
            --distribution-id ${{ secrets.FRONTEND_DISTRIBUTION_ID }} \
            --paths "/*"
```

---

## 🔧 KNOWN ISSUES & WORKAROUNDS

### Issue: Price Data Not Loading in AWS
**Root Cause:** yfinance API calls fail in ECS environment  
**Symptoms:** All price loaders return 0 records, JSON parse errors  
**Workaround Options:**

1. **Add VPC Endpoint for HTTPS** (Preferred, 1 hour)
   ```bash
   terraform apply -target=aws_vpc_endpoint.https
   # In terraform/vpc.tf, add:
   resource "aws_vpc_endpoint" "https" {
     vpc_id              = aws_vpc.main.id
     service_name        = "com.amazonaws.${var.aws_region}.s3"
     vpc_endpoint_type   = "Gateway"
   }
   ```

2. **Add NAT Gateway** (2-3 hours, higher cost)
   ```bash
   # Allows ECS tasks to reach external APIs via NAT
   # Edit terraform/vpc.tf
   ```

3. **Switch to AWS Glue** (4-6 hours, managed alternative)
   - No VPC networking needed
   - Handles retries & throttling
   - More expensive

4. **Load Locally, Push to RDS** (30 min, temporary)
   - Run loaders on your laptop
   - Use AWS DMS or manual copy to push to RDS
   - Only works for backfill, not daily updates

### Issue: Lambda Cold Starts
**Symptom:** First API call takes 5-10 seconds  
**Fix:** Provision concurrency in Terraform:
```hcl
reserved_concurrent_executions = 10
provisioned_concurrent_executions = 2
```

### Issue: CORS Errors on Frontend
**Symptom:** API calls blocked by browser CORS  
**Check:** API Gateway has CORS enabled (line 117 in services/main.tf)  
**Fix:** Update allowed origins:
```hcl
allow_origins = [
  "https://${aws_cloudfront_distribution.frontend[0].domain_name}",
  "http://localhost:5173"  # dev
]
```

---

## 🚀 QUICK START (For Impatient)

```bash
# 1. Get API URL
API_URL=$(aws apigatewayv2 get-apis --region us-east-1 --query "Items[?Name=='algo-api-dev'].ApiEndpoint" --output text)
echo "API: $API_URL"

# 2. Build frontend
cd webapp/frontend
VITE_API_URL=$API_URL npm run build

# 3. Test locally
npm run dev
# Open http://localhost:5173 → check Network tab → verify API calls work

# 4. Deploy
aws s3 sync dist/ s3://algo-frontend-dev/ --delete
aws cloudfront create-invalidation --distribution-id $DIST_ID --paths "/*"

# 5. Check frontend URL
echo "Frontend: https://d123abc.cloudfront.net"
```

---

## 📊 WHAT'S NEXT

After deployment, run integration tests:

```bash
# Test all endpoints match API_CONTRACT.md
python3 -m pytest tests/test_api_contract_compliance.py -v

# Test frontend pages load
npx playwright test tests/e2e/ --headed
```

---

## 🎯 SUCCESS CRITERIA

- [ ] `curl https://api-url/health` returns `{"status": "healthy"}`
- [ ] Frontend loads at `https://frontend-url`
- [ ] ScoresDashboard shows stock scores (or "no data" placeholder)
- [ ] API /api/scores/stockscores returns valid JSON
- [ ] All 10 API endpoints from API_CONTRACT.md respond
- [ ] No 503/504 errors in CloudWatch logs

---

## 💡 REMEMBER

- Frontend + API need same domain (or CORS won't work)
- API Gateway URL = `https://xxx.execute-api.region.amazonaws.com`
- Frontend URL = `https://xxx.cloudfront.net` (with CloudFront)
- Data loading still needs VPC fix (separate from API deployment)

