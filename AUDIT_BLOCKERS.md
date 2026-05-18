# Critical Blockers Audit - 2026-05-18

**Goal:** Identify all issues blocking full deployment with desired architecture visible via API endpoints and UI.

**Status:** ⚠️ **5 CRITICAL BLOCKERS FOUND** | 6 MEDIUM BLOCKERS | Multiple minor issues

---

## 🔴 CRITICAL BLOCKERS (Block Live Deployment)

### BLOCKER #1: Local Development Impossible - Database Credentials Required
**Status:** 🔴 BLOCKS ALL LOCAL WORK  
**Impact:** Cannot run orchestrator, loaders, or tests locally without manual setup  
**Evidence:**
```
orchestrator dry-run fails: Database password not available
```
**Root Cause:**  
- LOCAL_CRED_SETUP.md documents setup but requires manual env var configuration
- System has 3 .env files (webapp/.env.local, lambda/.env.local, ./.env.local) with hardcoded creds
- No automated credential loading for local development

**Fix Priority:** 🔥 HIGHEST  
**Effort:** 2 hours  
**Path Forward:**
1. Delete all .env.local files (violates CLAUDE.md rule #7)
2. Create .env.local.example templates
3. Implement automated credential loading from AWS Secrets Manager or ~/.local_creds
4. Document one-command local setup: `./scripts/setup-local-dev.sh`

**Blocker Until:** Credentials auto-load without manual env vars

---

### BLOCKER #2: .env Files Violate Security Policy
**Status:** 🔴 CRITICAL SECURITY  
**Impact:** Hardcoded plaintext DB credentials (password="stocks") in .env.local files  
**Evidence:**
```
webapp/.env.local: DB_PASSWORD=stocks
lambda/.env.local: exists (checked)
./.env.local: exists (checked)
```
**Files to Delete:**
- webapp/.env.local
- lambda/.env.local
- ./.env.local

**Root Cause:** These were created for convenience but violate CLAUDE.md rule #7: "No .env files, hardcoded secrets, or .env.local"

**Fix Priority:** 🔥 HIGHEST  
**Effort:** 30 minutes  
**Action:**
1. Delete all 3 .env.local files
2. Create .env.example templates
3. Update LOCAL_CRED_SETUP.md with AWS Secrets Manager instructions
4. Add pre-commit hook to reject .env files

**Blocker Until:** All .env files deleted from repo

---

### BLOCKER #3: API Endpoints Not Deployed/Callable in AWS
**Status:** 🔴 NOT IN PRODUCTION  
**Impact:** API_CONTRACT.md defines 10+ endpoints, but unclear if Lambda is deployed or accessible  
**Evidence:**
- API routes defined in lambda/api/routes/ (25+ handler files)
- No deployment configuration found
- No API Gateway endpoint URL documented
- No integration tests verifying API endpoints

**Root Cause:** Lambda function packaged but no Terraform/CloudFormation deployment for API Gateway integration

**Fix Priority:** 🔥 HIGHEST  
**Effort:** 4-6 hours  
**Missing Pieces:**
1. ❌ Terraform/CloudFormation for API Gateway
2. ❌ Lambda permission grants for API Gateway invocation
3. ❌ Environment variable injection (DB_SECRET_ARN, API_KEY, etc.)
4. ❌ CORS configuration in API Gateway
5. ❌ API documentation (OpenAPI/Swagger)

**Action Required:**
```bash
# Test current state
curl https://algo-api.example.com/api/health  # will fail - endpoint not in AWS

# Needed
terraform apply -target=aws_apigateway_rest_api.algo_api
terraform apply -target=aws_lambda_permission.api_gateway_invoke
```

**Blocker Until:** API Gateway deployed + Lambda integrated + /api/health returns 200

---

### BLOCKER #4: Frontend Not Calling Backend API Correctly
**Status:** 🔴 API MISMATCH  
**Impact:** Frontend built & deployed, but API_BASE_URL hardcoded or misconfigured  
**Evidence:**
```javascript
// webapp/frontend/src/config/index.js
API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:3001'
```
**Issues:**
1. ❌ Hardcoded localhost:3001 for production fallback
2. ❌ No environment variable VITE_API_URL in Terraform/GitHub Actions
3. ❌ No Docker/deployment config for frontend
4. ❌ Frontend dist/ exists (compiled) but no deployment pipeline

**Root Cause:** Frontend built locally, API endpoint configuration not externalized for AWS deployment

**Fix Priority:** 🔥 HIGHEST  
**Effort:** 3-4 hours  
**Missing Pieces:**
1. ❌ Build-time VITE_API_URL injection in GitHub Actions
2. ❌ CloudFront/S3 deployment for frontend
3. ❌ API Gateway custom domain (api.example.com)
4. ❌ Frontend environment config in terraform/

**Action Required:**
```bash
# In terraform/main.tf (missing)
resource "aws_cloudfront_distribution" "frontend" {
  # deploy webapp/frontend/dist to S3 + CloudFront
  # set VITE_API_URL = API Gateway URL at build time
}
```

**Blocker Until:** Frontend deploy pipeline created + API_BASE_URL set dynamically

---

### BLOCKER #5: Orchestrator Requires Manual Database Setup Before Any Work
**Status:** 🔴 GATE-KEEPING ALL PHASES  
**Impact:** orchestrator.py --dry-run fails immediately (Phase 7 crash)  
**Evidence:**
```
orchestrator dry-run output:
  [CRITICAL] Database down for 5 consecutive runs -> DEGRADED MODE
  Phase 7: reconciliation ERROR: Database password not available
```
**Root Cause:** Orchestrator assumes DB is already initialized & populated; has no graceful degradation for missing/empty database

**Fix Priority:** 🔥 HIGH (depends on Blocker #1)  
**Effort:** 2-3 hours (after fixing credentials)  
**Action:**
1. Add database health check as optional Phase 0
2. Skip trading if prices table is empty
3. Create init-only mode: `orchestrator --init-only` (runs loaders, skips trading)
4. Add data validation gate that shows what's missing instead of crashing

**Blocker Until:** Orchestrator runs --dry-run without DB_PASSWORD error

---

## 🟠 MEDIUM BLOCKERS (Degrade User Experience)

### BLOCKER #6: Data Loading Pipeline Broken for Tier 1 (Prices)
**Status:** 🟠 DATA MISSING  
**Impact:** API will return 0 records for all price endpoints, all score endpoints fail  
**Evidence:**
- Project memory: "yfinance failing with JSON parse errors in ECS, fetched=0, inserted=0"
- stock_prices_daily loader skips all 10,142 symbols
- Fallback to Alpaca returns 403 Forbidden

**Root Cause:** yfinance API fails in AWS VPC/ECS environment (network proxy, rate limiting, or DNS issue)

**Fix Priority:** 🟡 HIGH (needed for live data)  
**Effort:** 4-6 hours (network debugging)  
**Options:**
1. ✅ VPC endpoint for external APIs (preferred)
2. ✅ NAT gateway routing fix
3. ✅ Switch to AWS Glue for data pipeline
4. ✅ Use alternative data source (not yfinance)

**Action Required:** Run diagnostics in AWS:
```bash
# In ECS task, test external API access
curl -v https://query2.finance.yahoo.com/
# If blocked -> need VPC endpoint or NAT gateway
```

**Blocker Until:** stock_prices_daily loader returns > 0 records in AWS

---

### BLOCKER #7: API Endpoints Not Validated Against API_CONTRACT.md
**Status:** 🟠 POTENTIAL DATA MISMATCH  
**Impact:** Frontend expects specific columns, API might return different structure  
**Evidence:**
- API_CONTRACT.md defines 10 critical endpoints with exact column requirements
- Lambda handlers in routes/*.py not explicitly validated against contract
- No integration tests verifying response schema

**Root Cause:** No schema validation or contract enforcement

**Fix Priority:** 🟡 MEDIUM  
**Effort:** 2 hours  
**Action:**
1. Create test file: tests/test_api_contract_compliance.py
2. For each endpoint in API_CONTRACT.md, add test:
   ```python
   assert 'swing_score' in /api/scores/stockscores response
   assert 'grade' in /api/scores/stockscores response
   ```
3. Run in CI/CD before deployment

**Blocker Until:** All 10 endpoints pass schema validation tests

---

### BLOCKER #8: No Frontend Error Handling for Missing API Data
**Status:** 🟠 USER EXPERIENCE  
**Impact:** If API returns empty results or wrong schema, frontend shows broken UI  
**Evidence:**
- ScoresDashboard.jsx, DeepValueStocks.jsx show charts with no data checks
- No fallback UI for "no data available"
- No loading/error states visible

**Root Cause:** Frontend assumes API always returns valid data

**Fix Priority:** 🟡 MEDIUM  
**Effort:** 3-4 hours  
**Action:**
1. Add error boundary to all dashboard pages
2. Add "Loading..." UI while fetching
3. Add "No data available" placeholder
4. Add API health check on dashboard load

**Blocker Until:** Frontend gracefully handles API errors and empty responses

---

### BLOCKER #9: Deployment Pipeline Not Documented or Automated
**Status:** 🟠 OPERATIONAL  
**Impact:** Cannot deploy API or frontend changes to AWS without manual steps  
**Evidence:**
- GitHub Actions workflows exist (.github/workflows/*.yml)
- But no main deploy workflow for api + frontend
- No deployment documentation

**Root Cause:** Ad-hoc deployment process, no CI/CD pipeline

**Fix Priority:** 🟡 MEDIUM  
**Effort:** 3-4 hours  
**Action:**
1. Create .github/workflows/deploy.yml
2. Trigger on push to main:
   - Lambda: zip + deploy via sam/terraform
   - Frontend: build + deploy to S3/CloudFront
3. Document deployment steps in DEPLOYMENT.md

**Blocker Until:** `git push` → auto-deploys API + frontend

---

### BLOCKER #10: AWS Terraform Configuration Incomplete
**Status:** 🟠 INFRASTRUCTURE  
**Impact:** Lambda, API Gateway, frontend hosting not fully defined in IaC  
**Evidence:**
- terraform/ directory exists but check what's defined
- Missing: API Gateway, S3 bucket for frontend, CloudFront
- Missing: environment variable injection for Lambda

**Root Cause:** Infrastructure defined incrementally, not as complete package

**Fix Priority:** 🟡 MEDIUM  
**Effort:** 4-5 hours  
**Action:**
1. Complete terraform/main.tf with API Gateway + Lambda + S3 + CloudFront
2. Add outputs for API endpoint URL, frontend URL
3. Run `terraform plan` and verify all resources

**Blocker Until:** `terraform apply` creates full working stack

---

## 🟡 MINOR ISSUES (Technical Debt)

- Git has uncommitted changes (deleted tests/test_greeks_calculator.py, modified 4 files)
- test_loader_validation.py and loader_sla_tracker.py deleted (cleanup incomplete)
- No Playwright tests for frontend pages (mentioned in goal)
- Lambda cold start optimization not implemented
- No rate limiting on API endpoints
- Notification system not integrated (alert channels not configured)

---

## 📊 SUMMARY TABLE

| Blocker | Severity | Impact | Fix Time | Dependency |
|---------|----------|--------|----------|------------|
| 1. Local dev creds | 🔴 | Can't work locally | 2h | None |
| 2. .env files security | 🔴 | Security risk | 0.5h | #1 |
| 3. API not deployed | 🔴 | No backend in AWS | 5h | #1, #2 |
| 4. Frontend wrong API URL | 🔴 | Frontend broken in AWS | 3h | #3 |
| 5. Orchestrator DB gate | 🔴 | Can't run at all | 2h | #1 |
| 6. Price data not loading | 🟠 | No data in API | 5h | #3 |
| 7. API contract mismatch | 🟠 | Data format wrong | 2h | #3 |
| 8. Frontend error handling | 🟠 | Poor UX | 3h | #4 |
| 9. No deploy pipeline | 🟠 | Can't deploy | 3h | #1-4 |
| 10. Terraform incomplete | 🟠 | Infrastructure gaps | 4h | #3 |

---

## 🎯 CRITICAL PATH (To Get Working End-to-End)

1. **Fix Blocker #1** (2h): Create automated credential loading
2. **Fix Blocker #2** (0.5h): Delete .env files
3. **Fix Blocker #5** (2h): Fix orchestrator --dry-run
4. **Fix Blocker #3** (5h): Deploy API Gateway + Lambda
5. **Fix Blocker #4** (3h): Fix frontend API URL + deploy
6. **Verify Blocker #6** (ongoing): Check price data loads
7. **Add tests** (2h): Verify endpoints work end-to-end

**Total: 13.5 hours of focused work → working system**

---

## ✅ What IS Working

- ✅ Backend orchestrator code (logic correct, just needs DB + credentials)
- ✅ API route handlers (25+ endpoints implemented in Python)
- ✅ Frontend pages (24+ pages built, just needs correct API URL)
- ✅ Unit tests (180 passing)
- ✅ Database schema (tables defined, just need data)
- ✅ Docker/ECS configuration (loaders containerized)

---

## 🚀 Next Actions (Pick Top 3)

1. **Delete .env files + set up AWS Secrets Manager**
2. **Test orchestrator locally with real credentials**
3. **Deploy API Gateway + verify /api/health endpoint**
4. **Fix frontend API_BASE_URL + deploy to S3**
5. **Run diagnostics on yfinance data loading**

Pick any 3 above → execute in order → system becomes usable.

