# QUICKSTART - Get Everything Working (30 min)

**Prerequisites:** AWS credentials configured locally  
**Outcome:** Fully functional system (Frontend + API + Database)

---

## 🚀 EXECUTE THIS

### 1. Enable Infrastructure in AWS (5 min)
```bash
cd terraform

# Set your AWS region
export AWS_REGION=us-east-1

# Deploy NAT Gateway (for external API access) + Infrastructure
terraform apply -target=aws_nat_gateway.main
terraform apply -target=aws_eip.nat
# Answer: yes

echo "✅ NAT Gateway deployed - yfinance will now work in AWS"
```

### 2. Get API URL (2 min)
```bash
API_URL=$(aws apigatewayv2 get-apis \
  --region us-east-1 \
  --query "Items[?Name=='algo-api-dev'].ApiEndpoint" \
  --output text)

echo "API_URL=$API_URL"
```

### 3. Build & Deploy Frontend (10 min)
```bash
cd ../scripts
chmod +x build-frontend.sh

# Deploy to AWS
./build-frontend.sh "$API_URL" algo-frontend-dev <DIST_ID>

# If you don't have DIST_ID, just build:
./build-frontend.sh "$API_URL"
```

### 4. Test Locally First (5 min)
```bash
cd ..
bash scripts/test-full-stack.sh

# This will:
# - Check database connection
# - Run API contract tests
# - Start frontend dev server on http://localhost:5173
# - Show you where to verify API calls
```

### 5. Access in Browser
```
Frontend: https://<cloudfront-domain>.cloudfront.net
API: $API_URL (from step 2)

Navigate pages → Check Network tab → Verify API calls work
```

---

## ✅ SUCCESS CHECKLIST

- [ ] `curl $API_URL/health` returns 200
- [ ] Frontend loads in browser
- [ ] Network tab shows `/api/scores/stockscores` requests
- [ ] API responses are valid JSON (not 503/504)
- [ ] Frontend shows stock data (or "no data" if loaders haven't run)

---

## 🔧 IF SOMETHING FAILS

**API returns 503:**
```bash
# Lambda cold start, wait 10s and retry
sleep 10
curl $API_URL/health
```

**Frontend can't reach API:**
```bash
# Check CORS headers
curl -i $API_URL/health | grep -i access-control

# If missing, add CORS to Terraform:
# In terraform/modules/services/main.tf, line 118:
# allow_origins = ["https://your-cloudfront-domain.cloudfront.net", "http://localhost:5173"]
terraform apply
```

**Price data not loading:**
```bash
# NAT Gateway just deployed, loaders will work on next run:
python3 run-all-loaders.py
# or via ECS (GitHub Actions will auto-trigger)
```

---

## 📊 WHAT YOU NOW HAVE

```
✅ Local: Orchestrator runs, credentials auto-load
✅ AWS: API Gateway + Lambda deployed
✅ AWS: Frontend deployed to S3 + CloudFront
✅ AWS: NAT Gateway enabled (yfinance works)
✅ Database: PostgreSQL ready, schema initialized
✅ Everything: Connected end-to-end
```

---

## 🎯 NEXT (Optional)

- Load live data: `python3 run-all-loaders.py`
- Set up alerts: Configure ALERT_EMAIL_TO, ALERT_WEBHOOK_URL
- Schedule orchestrator: GitHub Actions already runs daily at 9:30 AM ET
- Monitor: Check CloudWatch dashboards

---

**Total time: 30 minutes → Fully working production system**
