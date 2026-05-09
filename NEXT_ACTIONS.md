# Next Actions: Getting the Platform Fully Operational

**Date:** 2026-05-09  
**Status:** Infrastructure complete, application deployment pending, critical blockers ready to fix

---

## What We Fixed (Session Summary)

### Architecture Alignment ✅
- **Confirmed Terraform as IaC source of truth** — eliminated dual CloudFormation/Terraform confusion
- **Rebuilt CI/CD from scratch** — deploy-all-infrastructure.yml is now the single entry point
- **Decoupled infrastructure from application code** — Terraform creates resources, separate workflows deploy code

### Security & Reliability ✅
- **API Gateway JWT authorization** — all routes now require Cognito tokens except /health
- **EventBridge dead-letter queue** — loader failures are captured, not silently dropped
- **Loader script resolution** — all 40 ECS tasks now correctly map to their Python files via LOADER_FILE env var
- **Terraform outputs exposed** — CI/CD workflows can dynamically resolve resource names

### Deployment Automation ✅
- **deploy-all-infrastructure.yml** — Terraform apply → Docker build → 4 parallel code deploys
- **build-push-ecr.yml** — Builds loader Docker image with proper SHA + latest tags
- **deploy-code.yml** — Packages and deploys algo Lambda, API Lambda, and frontend separately
- **Proper dependency chain** — Code deploys wait for Terraform, Docker waits for infrastructure outputs

---

## What Still Needs to Happen (5 Critical Blockers)

### 1. ✅ TERRAFORM INFRASTRUCTURE
**Status:** Already deployed (145 resources)
```
VPC + RDS + Lambda + API Gateway + CloudFront + Cognito + EventBridge + ECS
```

### 2. ❌ DATABASE SCHEMA INITIALIZATION
**Status:** NOT STARTED  
**What it is:** SQL schema (60+ tables, 25+ TimescaleDB hypertables, 50+ indexes)  
**How to fix:**
```bash
# Option A: Via workflow (recommended)
gh workflow run initialize-database-schema.yml \
  --ref main \
  -f rds_endpoint=stocks-data-rds.c7dljvslq.us-east-1.rds.amazonaws.com

# Option B: Manual SQL
psql -h stocks-data-rds.c7dljvslq.us-east-1.rds.amazonaws.com \
  -U stocks -d stocks < init_db.sql
```
**Why critical:** Loaders have nowhere to write; algo has nothing to read  
**Time:** ~5 minutes

### 3. ❌ DOCKER IMAGE BUILD & PUSH
**Status:** NOT STARTED  
**What it is:** 40 loader scripts packaged into single ECR image  
**How to fix:**
```bash
gh workflow run build-push-ecr.yml --ref main
```
**Why critical:** ECS loader tasks will fail `ErrImagePull` without this  
**Time:** ~10 minutes

### 4. ❌ LAMBDA CODE DEPLOYMENT
**Status:** Placeholder code still in place  
**What it is:** Package and upload actual Python algo + Node.js API code  
**How to fix:**
```bash
# This is handled by deploy-all-infrastructure.yml or run separately:
gh workflow run deploy-code.yml --ref main
```
**Includes:**
- Algo Lambda: algo_orchestrator + all algo_*.py modules
- API Lambda: Node.js code in webapp/lambda/
- Frontend: React build from webapp/frontend/

**Why critical:** API returns placeholder; algo does nothing  
**Time:** ~5 minutes

### 5. ❌ COGNITO TEST USER
**Status:** No users in pool  
**What it is:** Create a user account for testing  
**How to fix:**
```bash
aws cognito-idp admin-create-user \
  --user-pool-id us-east-1_qKYUt285Z \
  --username testuser@example.com \
  --temporary-password TempPass123! \
  --message-action SUPPRESS

aws cognito-idp admin-set-user-password \
  --user-pool-id us-east-1_qKYUt285Z \
  --username testuser@example.com \
  --password YourPassword123! \
  --permanent
```
**Why critical:** Can't log in; can't get JWT token; all API calls fail 401  
**Time:** ~2 minutes

---

## Recommended Execution Plan

### Phase 1: Foundation (NOW)
```bash
# 1. Init database schema
gh workflow run initialize-database-schema.yml \
  --ref main \
  -f rds_endpoint=stocks-data-rds.c7dljvslq.us-east-1.rds.amazonaws.com

# 2. Build Docker image
gh workflow run build-push-ecr.yml --ref main

# 3. Create Cognito test user (can do in parallel)
aws cognito-idp admin-create-user \
  --user-pool-id us-east-1_qKYUt285Z \
  --username testuser@example.com \
  --temporary-password TempPass123! \
  --message-action SUPPRESS && \
aws cognito-idp admin-set-user-password \
  --user-pool-id us-east-1_qKYUt285Z \
  --username testuser@example.com \
  --password YourPassword123! \
  --permanent
```
**Timeline:** 15-20 minutes total  
**Success indicators:**
- Schema workflow shows "Schema initialization complete"
- ECR image workflow shows "Pushed: ... dev-latest"
- Cognito user creation succeeds

### Phase 2: Code Deployment (AFTER Phase 1)
```bash
gh workflow run deploy-all-infrastructure.yml \
  --ref main \
  -f skip_terraform=true \
  -f skip_image=false \
  -f skip_code=false
```
**What happens:** Builds Docker again + deploys algo Lambda + API Lambda + frontend  
**Timeline:** ~15 minutes  
**Success indicators:**
- All 4 code jobs succeed (algo, api, frontend)
- CloudWatch shows no Lambda errors

### Phase 3: Verify API Works (AFTER Phase 2)
```bash
# Get API Gateway URL from deployment output or:
API_URL=$(aws cloudformation list-exports \
  --region us-east-1 \
  --query "Exports[?Name=='StocksApp-APIEndpoint'].Value" \
  --output text)

# Test health endpoint (no auth required)
curl $API_URL/health

# Test auth endpoint with JWT token
# (Get token from Cognito, pass as Bearer header)
```

### Phase 4: Verify Data Loaders (AFTER Phase 3)
```bash
# Trigger one loader manually to verify schema + Docker work
aws ecs run-task \
  --cluster stocks-ecs-cluster \
  --task-definition stocks-stock_symbols-loader \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx]}" \
  --launch-type FARGATE

# Check logs
aws logs tail /ecs/stocks/stock_symbols-loader --follow

# Verify data written
aws rds-client query --database stocks \
  --sql "SELECT COUNT(*) FROM stock_symbols;"
```

### Phase 5: Test Algo Orchestrator (AFTER Phase 4)
```bash
# Invoke algo Lambda manually
aws lambda invoke \
  --function-name stocks-algo-dev \
  --payload '{}' \
  /tmp/algo_output.json

# Watch logs
aws logs tail /aws/lambda/stocks-algo-dev --follow

# Check audit log
aws rds-client query --database stocks \
  --sql "SELECT * FROM algo_audit_log ORDER BY created_at DESC LIMIT 5;"
```

---

## Why This Order Matters

**❌ Wrong:** Run deploy-all-infrastructure.yml without schema → Lambda tries to write to non-existent tables  
**✅ Right:** Schema first, then Docker, then code → Everything has dependencies ready

**❌ Wrong:** Trigger loader before testing manually → Silent failures in CloudWatch  
**✅ Right:** Test one loader, verify data written, then trust the full pipeline

**❌ Wrong:** Deploy frontend without testing API → UI makes calls to broken endpoints  
**✅ Right:** API endpoints working, then test UI against real backend

---

## What's Already in Place (Don't Redo)

- ✅ Terraform infrastructure (145 resources deployed)
- ✅ CI/CD workflows (deploy-all-infrastructure.yml is master)
- ✅ Cognito JWT authorizer on API Gateway
- ✅ EventBridge DLQ for loader failures
- ✅ Loader script mapping (LOADER_FILE env var)
- ✅ Database schema file (init_db.sql) ready to deploy
- ✅ Algo orchestrator code (165 modules)
- ✅ API Lambda code (29 endpoints)
- ✅ React frontend (20+ pages)
- ✅ Secrets Manager wiring (RDS password, Alpaca keys)

---

## Key Learnings to Keep

1. **Terraform is source of truth** — all infrastructure flows from terraform/
2. **Infrastructure ≠ Application code** — Terraform creates resources, CI/CD deploys code separately
3. **Fail-closed design** — DLQ, circuit breakers, data quality checks prevent silent failures
4. **JWT + Cognito** — all API access now requires valid token
5. **Parallel execution** — Docker, algo Lambda, API Lambda, frontend can deploy simultaneously after Terraform

---

## Validation Checklist (Do This After Each Phase)

### After Phase 1 (Foundation)
- [ ] `initialize-database-schema.yml` workflow shows "Schema initialization complete"
- [ ] `build-push-ecr.yml` workflow shows "Pushed: ... dev-latest"
- [ ] Cognito user created successfully
- [ ] RDS has 60+ tables: `SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';`
- [ ] ECR has image: `aws ecr describe-repositories | grep stocks`

### After Phase 2 (Code Deployment)
- [ ] Algo Lambda version updated: `aws lambda get-alias --function-name stocks-algo-dev --name live`
- [ ] API Lambda version updated: `aws lambda get-alias --function-name stocks-api-dev --name live`
- [ ] Frontend S3 bucket has files: `aws s3 ls s3://stocks-frontend-dev/`
- [ ] CloudFront serving from S3: `curl -I https://d27wrotae8oi8s.cloudfront.net/`

### After Phase 3 (API Verification)
- [ ] Health check returns 200: `curl https://api-endpoint/health`
- [ ] Auth check returns 401 without token: `curl https://api-endpoint/portfolio`
- [ ] Auth check returns 200 with valid Cognito token

### After Phase 4 (Data Loader)
- [ ] Loader task completed: `aws ecs describe-tasks --cluster stocks-ecs-cluster --tasks [task-arn]`
- [ ] Loader logs show success: `aws logs tail /ecs/stocks/stock_symbols-loader`
- [ ] Data in table: `SELECT COUNT(*) FROM stock_symbols;` (should be > 0)

### After Phase 5 (Algo Test)
- [ ] Algo Lambda invocation succeeds: `aws lambda invoke --function-name stocks-algo-dev /tmp/out.json`
- [ ] Algo logs show all 7 phases completed: `aws logs tail /aws/lambda/stocks-algo-dev`
- [ ] Audit log has entry: `SELECT * FROM algo_audit_log ORDER BY created_at DESC LIMIT 1;`
- [ ] No errors in CloudWatch Logs

---

## Next Decision Point

Once Phase 1 completes:
1. **If all Phase 1 checks pass** → Proceed to Phase 2 immediately
2. **If any Phase 1 fails** → Investigate and fix before proceeding
3. **Once all phases complete** → System is ready for:
   - Full loader orchestration (all 40 loaders)
   - Live algo runs (EventBridge trigger at 5:30pm ET)
   - Performance tuning and hardening

---

## Reference

- **Deploy all:** `gh workflow run deploy-all-infrastructure.yml --ref main`
- **Check status:** `gh workflow view deploy-all-infrastructure.yml --log`
- **RDS endpoint:** `stocks-data-rds.c7dljvslq.us-east-1.rds.amazonaws.com`
- **Cognito pool:** `us-east-1_qKYUt285Z`
- **API Gateway:** Check deployment output or CloudFormation exports
- **Frontend CDN:** `https://d27wrotae8oi8s.cloudfront.net`

