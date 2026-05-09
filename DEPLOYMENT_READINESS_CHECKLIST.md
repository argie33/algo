# Deployment Readiness Checklist

**Status**: Infrastructure code complete, application layer partially deployed, data layer empty  
**Last updated**: 2026-05-09  
**Next milestone**: End-to-end algo test (7-phase orchestrator → RDS → Alpaca)

---

## ✅ COMPLETED (This sprint)

### Terraform Infrastructure
- ✅ VPC, networking (2 AZs, public/private subnets, VPC endpoints, NatGateway)
- ✅ RDS PostgreSQL (61GB allocated, backups, multi-AZ capable)
- ✅ ECS Fargate cluster + 40 loader task definitions (CPU/memory per loader)
- ✅ Lambda (API + Algo) with proper VPC/security group config
- ✅ API Gateway HTTP API with CORS configured
- ✅ CloudFront CDN for frontend + S3 OAC
- ✅ Cognito user pool + MFA + session timeout
- ✅ EventBridge scheduler (daily 5:30pm ET)
- ✅ IAM roles + OIDC for GitHub Actions
- ✅ S3 buckets with versioning
- ✅ ECR repository for loader images
- ✅ CloudWatch log groups + basic alarms

### Security Hardening
- ✅ Cognito JWT authorizer on API Gateway (all routes auth-required except /health)
- ✅ EventBridge SQS dead-letter queue (loader failures captured, not silent)
- ✅ Lambda SourceArn on permissions (EventBridge trigger scoped)
- ✅ S3 bucket policies for CloudFront access
- ✅ Secrets Manager for RDS credentials + Alpaca API keys

### CI/CD Pipeline
- ✅ `deploy-all-infrastructure.yml` - Terraform-first master: applies infra, then 4 parallel code deploys
- ✅ `build-push-ecr.yml` - Docker build → ECR push (both SHA + latest tags)
- ✅ `deploy-code.yml` - Lambda packaging/update + frontend to S3
- ✅ 7 broken CF workflows archived/stubbed
- ✅ Terraform outputs exposed for CI (Lambda names, S3 bucket, CloudFront ID)

### Data Loader Wiring
- ✅ ECS task definitions for all 40 loaders with correct LOADER_FILE env vars
- ✅ 40 EventBridge rules scheduled (3:30am-5:25pm ET, optimized tiers)
- ✅ Fargate parallelism: loaders within same tier run simultaneously
- ✅ Dead-letter queue for failures

### Algorithm & Frontend
- ✅ 80+ Python modules (80+ lines each, research-backed)
- ✅ 8-phase orchestrator with fail-closed circuit breakers
- ✅ Position monitoring, exit engine, trade executor
- ✅ Data quality patrol (10 checks, remediation)
- ✅ React frontend (20+ pages, Cognito auth, real-time)
- ✅ Node.js API Lambda (29 endpoints, database queries)

---

## ⚠️ CRITICAL BLOCKERS (Must fix before algo can run)

### 1. Database Schema Not Initialized
**Impact**: Loaders have nowhere to write; algo has nothing to read  
**Fix**: 
```bash
# Option A: Run schema init workflow
gh workflow run initialize-database-schema.yml

# Option B: Manual SQL against RDS  
psql -h {rds-endpoint} -U stocks -d stocks < schema.sql
```
**Status**: NOT DONE - RDS is empty

### 2. Docker Image Not Built/Pushed
**Impact**: ECS loader tasks will fail `ErrImagePull`  
**Fix**:
```bash
# Run the ECR build workflow
gh workflow run build-push-ecr.yml
```
**Status**: NOT DONE - No image in ECR yet

### 3. Lambda Code Still Placeholder
**Impact**: API returns placeholder response; algo does nothing  
**Fix**: Run `deploy-all-infrastructure.yml` or `deploy-code.yml` to:
- Package algo orchestrator (lambda/algo_orchestrator/ + algo_*.py)
- Package API Lambda (webapp/lambda/ Node.js)
- Update both via `aws lambda update-function-code`
**Status**: NOT DONE - Placeholder code in place

### 4. Frontend Not Deployed
**Impact**: CloudFront serves nothing; UI unavailable  
**Fix**: Same `deploy-code.yml` handles frontend:
- `npm run build` in webapp/frontend/
- Sync dist/ to S3
- CloudFront invalidation
**Status**: NOT DONE - S3 bucket empty

### 5. No Data in RDS
**Impact**: Loaders succeed but write to empty schema; algo reads nulls  
**Fix**: 
```bash
# After schema init + image push + loader Docker working:
# Option A: Trigger all loaders manually
for loader in stock_symbols stock_prices_daily stock_prices_weekly stock_prices_monthly ...; do
  aws ecs run-task --cluster stocks-ecs-cluster --task-definition stocks-${loader}-loader --network-configuration "awsvpcConfiguration={subnets=[...],securityGroups=[...]}"
done

# Option B: Wait for EventBridge schedule (3:30am ET next weekday)

# Option C: Run locally in Docker
docker build -t stocks-loader:local .
docker run -e LOADER_FILE=loadstocksymbols.py -e DB_HOST=... -e DB_PASSWORD=... stocks-loader:local
```
**Status**: NOT DONE - Tables exist but empty

### 6. Cognito User Doesn't Exist
**Impact**: Can't log in; can't get JWT token; API calls fail 401  
**Fix**:
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
**Status**: NOT DONE - No users in pool

---

## 🔧 HIGH PRIORITY (Needed for safety before live trading)

| Issue | Why Critical | How to Fix | Effort |
|-------|---|---|---|
| API Lambda still placeholder | No actual endpoints | Covered by deploy-code.yml | ✓ Done |
| No CloudWatch alarms for API errors | Silent failures | Add to Terraform services module | 30min |
| Lambda concurrency limits not set | Throttling under load | Add reserved concurrency to main.tf | 30min |
| RDS public accessibility flag | Security hole | Set to false in Terraform | 10min |
| No backup verification | Disaster recovery untested | Run `aws rds describe-db-snapshots` | 5min |
| Alpaca API credentials not tested | Algo can't trade if creds invalid | Test locally: `import alpaca` + auth check | 10min |
| Data completeness thresholds untested | Algo may run on stale data | Unit test algo_data_patrol.py | 30min |

---

## 📋 RECOMMENDED ORDER (Getting to first successful algo run)

### Phase 1: Foundation (2-3 hours)
1. Run `terraform apply` (if not already done)
2. Run `initialize-database-schema.yml` workflow
3. Run `build-push-ecr.yml` workflow

### Phase 2: Code Deployment (1-2 hours)
4. Run `deploy-code.yml` workflow (deploys algo Lambda + API Lambda + frontend)
5. Test API health: `curl https://{api-gateway}/health` → should return 200
6. Test auth (get token from Cognito test user, call API with Bearer token)

### Phase 3: Data Population (10-30 minutes)
7. Trigger one loader manually (e.g., stock_symbols) to verify schema + Docker work
8. Check RDS: `SELECT COUNT(*) FROM stock_symbols;` should be >0
9. Trigger price loaders to populate price_daily table

### Phase 4: End-to-End Test (30 minutes)
10. Manually invoke algo Lambda via AWS console or CLI
11. Watch CloudWatch logs for all 7 phases:
    - Phase 1: Data freshness check
    - Phase 2: Circuit breakers
    - Phase 3: Position monitor + reconciliation
    - Phase 4: Exit execution
    - Phase 5: Signal generation
    - Phase 6: Entry execution
    - Phase 7: Final reconciliation
12. Verify it connects to Alpaca (paper trading mode)
13. Verify audit log populated in algo_audit_log table

### Phase 5: Hardening (1-2 hours)
14. Set up CloudWatch alarms for Lambda errors + loader DLQ depth
15. Add MFA enforcement in Cognito
16. Verify Secrets Manager has all credentials
17. Disable RDS public accessibility
18. Set Lambda reserved concurrency

---

## 🎯 Definition of Done

**Minimum** (algo running):
- [ ] RDS schema initialized
- [ ] ECR has latest loader image
- [ ] API Lambda has real code (not placeholder)
- [ ] Algo Lambda has real code (not placeholder)
- [ ] Frontend deployed to S3/CloudFront
- [ ] Cognito test user exists
- [ ] At least one loader has run and populated data
- [ ] Algo orchestrator completes all 7 phases without error
- [ ] Algo successfully calls Alpaca API (paper trading)

**Production-ready**:
- [ ] All 40 loaders have run at least once (full dataset)
- [ ] Data quality checks passing (completeness > 70% for all tiers)
- [ ] CloudWatch alarms configured and tested
- [ ] RDS backups verified
- [ ] API tested with real JWT tokens (Cognito flow)
- [ ] Algo generates positions and place trades (paper account)
- [ ] Monitoring shows no errors in last 24h
- [ ] Cost tracking under control ($80-100/month)

---

## 🚀 What's Next

**Immediately** (today):
1. Verify terraform apply succeeded (check CloudFormation stacks in AWS console)
2. Trigger database schema initialization
3. Trigger Docker image build
4. Trigger code deployment

**Tomorrow** (once above complete):
1. Test data loading (stock_symbols → stock_prices_daily)
2. Test API endpoints (with JWT auth)
3. Test algo orchestrator Lambda (watch logs)
4. Verify Alpaca paper trading works

**This week**:
1. Run all loaders to populate full dataset
2. Monitor data quality metrics
3. Fine-tune risk parameters (drawdown limits, position size)
4. Set up alerting/monitoring

**Before live trading**:
1. Backtesting validation (verify algo logic against historical data)
2. Paper trading validation (1-2 weeks live on Alpaca paper account)
3. Security audit (API, auth, database)
4. Compliance review (trade logging, audit trails)
5. Manual approval process setup
