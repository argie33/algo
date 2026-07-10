# System Audit & Fixes - Session 9 (2026-07-09)

## Comprehensive System Assessment

### ✓ Working Components
- ✓ Database connection and schema
- ✓ Config system (AlgoConfig + database defaults)
- ✓ Orchestrator framework (all 9 phases implemented)
- ✓ API Lambda structure 
- ✓ Data loaders (36 consolidated loaders using unified runner)
- ✓ Pre-commit validation
- ✓ Test suite (1091+ tests passing)

### Critical Issues Identified

**PRIORITY 1 - Deployment Pipeline**
1. GitHub Actions workflows are comprehensive but need verification that:
   - Lambda deployment artifacts are built correctly
   - Terraform state management works with DynamoDB locks
   - Cognito setup completes before API Gateway CORS config
   - Database migrations run before orchestrator executes
2. IAM permissions in GitHub Actions role may be incomplete:
   - Needs EC2 describe/run for ECS task execution
   - Needs CloudWatch Logs access
   - Needs parameter store/Secrets Manager access

**PRIORITY 2 - Data Pipeline**
1. Loader orchestration via Step Functions:
   - Morning pipeline (2:15 AM): prices → technical → swing scores
   - EOD pipeline (4:05 PM): prices → market → metrics → stock scores
   - Metrics need ≥70% coverage for scores to compute
2. Data freshness monitoring:
   - Orchestrator Phase 1 should fail-fast if prices stale >1 trading day
   - Portfolio snapshot (Phase 9) used by dashboard for freshness check

**PRIORITY 3 - Trading Execution**
1. Alpaca integration:
   - Paper trading mode enabled (alpaca_paper_trading=true)
   - Execution mode set to "paper" for dev environment
   - Credentials loaded from Secrets Manager in orchestrator Lambda
2. Circuit breakers (Phase 2):
   - 8 halt conditions enforced before Phase 3-5, 7-8 execute
   - Fail-closed logic: if CB state unverifiable, assume halted

**PRIORITY 4 - Dashboard Data**
1. Frontend (Vite + React):
   - CloudFront distribution serving /index.html
   - Cognito auth integration via /api/auth endpoints
   - API calls to /api/portfolio, /api/performance, /api/positions, /api/scores, /api/market, /api/circuit-breaker
2. API Gateway:
   - CORS must include CloudFront domain + localhost:3000/5173
   - Both set by Terraform + updated post-deploy in GitHub Actions

### Fix Checklist

- [ ] Verify GitHub Actions can assume IAM role (OIDC configuration)
- [ ] Verify Terraform backend (S3 state bucket + DynamoDB locks)
- [ ] Verify EventBridge scheduler rules (2x daily at 9:30 AM + 5:30 PM ET)
- [ ] Verify RDS database reachable from Lambda VPC
- [ ] Verify Step Functions pipelines (morning + EOD loaders)
- [ ] Verify CloudFront distribution routes to S3 frontend
- [ ] Verify Cognito user pool created + test user provisioned
- [ ] Test end-to-end orchestrator run via Lambda test
- [ ] Verify dashboard displays portfolio + positions + performance
- [ ] Verify API endpoints return correct data structures

### Configuration Notes
- **Environment**: dev (all resources named -dev, paper trading only)
- **Database**: PostgreSQL RDS algo-db-dev (t4g.small, 100 concurrent max)
- **Execution Schedule**: 9:30 AM + 5:30 PM ET (weekdays only)
- **Loaders**: 36 consolidated loaders (unified runner + OptimalLoader base)
- **Execution Mode**: paper (enforced in ORCHESTRATOR_EXECUTION_MODE env var)

