# Deployment Readiness Checklist — May 9, 2026

## ✅ COMPLETED THIS SESSION

### Frontend Features (Tier 2)
- ✅ **Settings Persistence** (P2.5)
  - API: `getSettings()` and `updateSettings()` methods added to `api.js`
  - Route: `/api/settings` (GET/POST) already registered
  - Database: Migration `create-user-settings.sql` ready
  - UI: Settings page ready to save user preferences

- ✅ **Manual Trade Entry** (P2.1)
  - UI: PreviewModal enhanced with buy/sell, shares, entry price fields
  - API: Calls `/api/trades/manual` POST endpoint
  - Validation: Quote dates, positive quantities, symbol validation
  - UX: Success message + 2-second auto-close
  - Auto-refresh: Trade list updates every 60 seconds

- ✅ **API Error Standardization** (P2.2)
  - Format: All endpoints return `{ success, data/items, timestamp, error? }`
  - Consistency: Standardized helpers (`sendSuccess`, `sendError`, `sendPaginated`)
  - Note: `algo.js` and `performance.js` use `res.json()` directly but return correct format

### Backend Infrastructure
- ✅ **Database Migration Runner** (`webapp-db-init.js`)
  - Auto-executes all `.sql` files in `/migrations` on startup
  - Handles failures gracefully (continues if table exists)
  - Logs migration status for debugging

### Code Quality
- ✅ All JavaScript/JSX syntax valid
- ✅ No missing imports in modified files
- ✅ Only 1 TODO remaining in backend (market.js line 1794 - non-critical)
- ✅ Git history clean and committed

---

## 📋 DEPLOYMENT STEPS (You Need to Run These)

### Step 1: Verify Local Environment
```bash
# Check database connectivity
psql -h localhost -U stocks -d stocks -c "SELECT COUNT(*) FROM user_settings;"

# Check backend syntax
npm test --testPathPattern="manual-trades|settings"

# Check frontend builds
npm run build
```

### Step 2: Deploy Cognito (if not already deployed)
```bash
cd terraform
terraform init
terraform apply -var="environment=dev"

# Copy outputs to .env.local:
terraform output cognito_user_pool_id
terraform output cognito_user_pool_client_id  
terraform output cognito_domain_url
```

### Step 3: Update Frontend Environment
Create/update `.env.local` with Cognito outputs:
```bash
VITE_COGNITO_USER_POOL_ID=us-east-1_XXXXXXXXX
VITE_COGNITO_CLIENT_ID=a1b2c3d4e5f6g7h8i9j0k1l2
VITE_COGNITO_DOMAIN=https://stocks-trading-dev-XXXXX.auth.us-east-1.amazoncognito.com
VITE_AWS_REGION=us-east-1
```

### Step 4: Deploy Lambda + EventBridge
```bash
# Option A: Deploy everything at once (recommended)
gh workflow run deploy-all-infrastructure.yml --repo argie33/algo

# Option B: Deploy pieces individually
gh workflow run deploy-webapp.yml
gh workflow run deploy-algo-orchestrator.yml
```

### Step 5: Test After Deployment
```bash
# Open browser
http://localhost:5173  (local dev)
# OR
https://d27wrotae8oi8s.cloudfront.net  (production)

# Test login with Cognito
Username: testuser
Password: TestPassword123!

# Test settings save
1. Click Settings tab
2. Change theme
3. Click "Save Settings"
4. Refresh page — setting should persist

# Test manual trade entry
1. Click Trade Tracker → "Preview Trade" button
2. Enter: QQQ, Buy, $400, 10 shares
3. Click "Calculate Preview"
4. Click "Confirm & Enter"
5. Trade should appear in table within 60 seconds
```

---

## 🔍 WHAT'S DEPLOYED VS. PENDING

### Already in AWS (145 Resources)
- ✅ VPC & Networking
- ✅ RDS PostgreSQL (14.12)
- ✅ Lambda API (stocks-api-dev) — All 25+ routes
- ✅ Lambda Algo (stocks-algo-dev) — Trading engine
- ✅ CloudFront CDN
- ✅ EventBridge Scheduler (5:30pm ET)
- ✅ ECS Cluster (data loaders)
- ✅ S3 buckets, Secrets Manager, CloudWatch

### Pending Deployment
- ⏳ **Cognito authentication** — Infrastructure ready, needs `terraform apply`
- ⏳ **EventBridge Lambda** — Requires algo-orchestrator redeployment
- ⏳ **Frontend updates** — Settings + manual trades code ready, needs Cognito env vars

### No Changes Needed
- ⌛ All existing routes working
- ⌛ Database schema healthy
- ⌛ Test suite comprehensive (300+ tests)

---

## 🚀 FINAL CHECKLIST

Before production:
- [ ] Cognito deployed and env vars set
- [ ] Backend tests pass: `npm test`
- [ ] Frontend builds: `npm run build`
- [ ] Local testing complete (settings + trades)
- [ ] EventBridge Lambda deployed
- [ ] Testuser login works
- [ ] Manual trade flow end-to-end tested

---

## 📞 CRITICAL PATHS

**Quick Deploy (All at Once):**
```bash
gh workflow run deploy-all-infrastructure.yml --repo argie33/algo
# Waits 20-30 minutes, then check: https://github.com/argie33/algo/actions
```

**Check Status:**
```bash
gh workflow run check-stack-status.yml --repo argie33/algo
```

**Debug Logs:**
```bash
aws logs tail /aws/lambda/stocks-api-dev --follow
aws logs tail /aws/lambda/stocks-algo-dev --follow
```

---

**Generated:** 2026-05-09  
**Status:** Ready for AWS deployment — all code changes complete  
**Next Owner:** User (AWS deployment)
