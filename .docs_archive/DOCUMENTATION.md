# Stock Analytics Platform - Complete Documentation

## AWS Infrastructure & Deployment

### Stack Dependency Order (CRITICAL)

```
[1] stocks-oidc (bootstrap)
    ├─ GitHub OIDC provider, GitHubActionsDeployRole
    ├─ One-time: .github/workflows/bootstrap-oidc.yml
    └─ Exports: StocksOidc-WebIdentityProviderArn, GitHubActionsDeployRoleArn

[2] stocks-core (foundation)
    ├─ VPC, subnets, bastion, ECR, S3, VPC endpoints, algo artifacts bucket
    ├─ Deploy: .github/workflows/deploy-core.yml
    └─ Exports: StocksCore-VpcId, -PublicSubnet1/2Id, -ContainerRepositoryUri, -CfTemplatesBucketName, -AlgoArtifactsBucketName

[3] stocks-data (data layer)
    ├─ RDS PostgreSQL, ECS cluster, Secrets Manager, log groups
    ├─ Deploy: .github/workflows/deploy-data-infrastructure.yml
    └─ Exports: StocksApp-DBEndpoint, -DBPort, -DBName, -SecretArn, -ClusterArn, -EcsTasksSecurityGroupId

[4a] stocks-loaders (data loaders - 62 ECS tasks)
    ├─ ECS task definitions, EventBridge schedules
    ├─ Deploy: .github/workflows/deploy-loaders.yml
    └─ Exports: StocksLoaders-* (task definition ARNs)

[4b] stocks-webapp-dev (frontend & API)
    ├─ Lambda API, API Gateway, CloudFront, Cognito, S3 frontend bucket
    ├─ Deploy: .github/workflows/deploy-webapp.yml
    └─ Exports: ${AWS::StackName}-ApiUrl, -WebsiteURL, -CloudFrontDistributionId

[4c] stocks-algo-dev (algo orchestrator)
    ├─ Algo Lambda, EventBridge scheduler, SNS alerts
    ├─ Deploy: .github/workflows/deploy-algo.yml
    └─ Exports: ${AWS::StackName}-LambdaFunctionArn, -ScheduleArn
```

### Fresh AWS Account Setup

**Prerequisites:**
- AWS account with admin permissions
- GitHub secrets: AWS_ACCOUNT_ID, RDS_USERNAME, RDS_PASSWORD, FRED_API_KEY, APCA_API_KEY_ID, APCA_API_SECRET_KEY

**Deployment (60 minutes total):**
```
Run: .github/workflows/deploy-all-infrastructure.yml
This runs all stacks in correct order automatically
```

**Or manual steps:**
1. `bootstrap-oidc.yml` (2-3 min)
2. `deploy-core.yml` (10-15 min)
3. `deploy-data-infrastructure.yml` (15-20 min)
4. `deploy-webapp.yml` (3-5 min)
5. `deploy-loaders.yml` (5-10 min)
6. `deploy-algo.yml` (2-3 min)

### Architecture Overview

**6 CloudFormation Templates:**
- `template-bootstrap.yml` (42 lines) - OIDC setup
- `template-core.yml` (528 lines) - Foundation: VPC, networking, ECR, S3, bastion
- `template-data-infrastructure.yml` (294 lines) - RDS, ECS cluster, secrets
- `template-loader-tasks.yml` (4092 lines) - 63 ECS task definitions
- `template-webapp.yml` (440 lines) - Lambda API, CloudFront, Cognito
- `template-algo.yml` (268 lines) - Algo orchestrator, EventBridge

**Design Principles:**
- Infrastructure-as-Code (all CloudFormation, version-controlled)
- Explicit dependencies (CloudFormation !ImportValue only, no hardcoded values)
- Secrets in Secrets Manager (never in environment variables)
- Immutable docker images (`:latest` tag, rebuilt on every change)
- Single responsibility (each template does one thing well)

### Troubleshooting

| Issue | Solution |
|-------|----------|
| "Stack does not exist" | Run the dependency stack first |
| "ResourceExistenceCheck failed" | Verify source stack exports exist, stack is COMPLETE |
| Stack stuck in ROLLBACK_COMPLETE | Delete manually in CloudFormation console, retry |
| API endpoint unreachable | Verify CloudFront distribution is DEPLOYED |

### Costs

Monthly breakdown:
- RDS (t3.micro): $15
- ECS (Fargate): $20
- Lambda: $5
- Storage + networking: $5
- **Total: ~$45/month**

Already optimized:
- No NAT gateway (VPC endpoints instead) = saves $32/month
- Bastion DesiredCount: 0 (manual scale-up only)
- Lambda SnapStart (10x faster cold starts)
- ARM Graviton (20% cost reduction)

### Security

**Implemented:**
✅ OIDC scoped to `repo:argeropolos/algo:*`
✅ Secrets in Secrets Manager
✅ All templates version-controlled
✅ No hardcoded credentials

**Before production:**
- Move Lambdas to private subnets with NAT
- Move RDS to private subnets
- Add least-privilege security groups
- Enable RDS encryption at rest
- Enable CloudTrail audit logging

### Operations

**Redeploy a component:**
```bash
.github/workflows/deploy-core.yml              # VPC, ECR, S3, bastion
.github/workflows/deploy-data-infrastructure.yml  # RDS, ECS cluster
.github/workflows/deploy-loaders.yml            # Loader tasks
.github/workflows/deploy-webapp.yml             # Frontend & API
.github/workflows/deploy-algo.yml               # Algo orchestrator
.github/workflows/deploy-all-infrastructure.yml # All in order
```

**Manually run a loader:**
```bash
aws ecs run-task \
  --cluster stocks-app-stack \
  --task-definition stocksymbols-loader:1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}" \
  --region us-east-1
```

**Scale bastion up:**
```bash
aws autoscaling set-desired-capacity \
  --auto-scaling-group-name stocks-bastion-asg \
  --desired-capacity 1
```

**Connect to RDS:**
```bash
# SSH to bastion, then:
psql -h <RDS_ENDPOINT> -U postgres -d stocks
```

### Monitoring

- **CloudWatch Logs:** `/aws/lambda/stocks-*`, `/ecs/*` for task logs
- **CloudWatch Alarms:** Lambda and API Gateway performance
- **EventBridge:** Verify loader schedules and algo runs are active
- **RDS:** Monitor database performance in AWS console
  - Risk management rules
  - Position sizing logic

## AWS Infrastructure

- **`AWS_DEPLOYMENT.md`** (20 min)
  - Architecture overview
  - CloudFormation templates
  - GitHub Actions workflows
  - Environment variables
  - Scaling and optimization
  - Disaster recovery
  - Security

## Design & Planning

- **`MASTER_PLAN.md`** (optional)
  - Overall system roadmap
  - Priority features
  - Technical milestones

- **`FRONTEND_DESIGN_SYSTEM.md`** (optional)
  - UI components
  - Design tokens
  - Page architecture

## Quick Reference

| Document | Purpose | When to Read |
|----------|---------|--------------|
| CLAUDE.md | Getting started | Always (first) |
| LOCAL_SETUP.md | Set up development environment | Before development |
| API_REFERENCE.md | What API endpoints exist | When building frontend |
| AWS_DEPLOYMENT.md | Deploy to AWS | Before deployment |
| DATA_LOADING.md | Data loading pipeline | Understanding data flow |
| ALGO_DEPLOYMENT.md | Deploy algo trading system | Setting up algo |
| ALGO_ARCHITECTURE.md | How the algo works | Understanding the algo |
| TROUBLESHOOTING.md | Fix problems | When something breaks |
| DOCUMENTATION.md | Find what you need | Navigation (this file) |

---

## Common Tasks

### I want to start developing locally
1. Read: `CLAUDE.md` (quick start)
2. Read: `LOCAL_SETUP.md` (detailed setup)
3. Run: Commands from LOCAL_SETUP.md

### I want to add a new API endpoint
1. Read: `API_REFERENCE.md` (see existing patterns)
2. Edit: `webapp/lambda/routes/*.js`
3. Test: `curl http://localhost:3001/api/...`

### I want to load new data
1. Read: `DATA_LOADING.md` (see 39 official loaders)
2. Edit: One of `load*.py` files
3. Test locally: `python3 load*.py --backfill_days 10`

### I want to understand the algo
1. Read: `ALGO_ARCHITECTURE.md` (design and research)
2. Read: `ALGO_DEPLOYMENT.md` (how it runs in AWS)
3. Examine: `algo_*.py` files

### I want to deploy to AWS
1. Read: `AWS_DEPLOYMENT.md` (architecture overview)
2. Read: Related deployment docs (API, loaders, algo)
3. Follow: GitHub Actions workflows

### Something is broken
1. Read: `TROUBLESHOOTING.md` (find your issue)
2. Follow: Debug steps
3. Check: CloudWatch logs (if AWS)

---

## File Organization

```
repo/
├── CLAUDE.md                    (minimal start)
├── DOCUMENTATION.md             (this file)
├── LOCAL_SETUP.md               (dev environment)
├── API_REFERENCE.md             (API spec)
├── AWS_DEPLOYMENT.md            (AWS infrastructure)
├── TROUBLESHOOTING.md           (debugging)
├── DATA_LOADING.md              (loaders)
├── ALGO_DEPLOYMENT.md           (algo in AWS)
├── ALGO_ARCHITECTURE.md         (algo design)
├── MASTER_PLAN.md               (roadmap)
├── FRONTEND_DESIGN_SYSTEM.md    (UI design)
│
├── webapp/                       (frontend + API)
│   ├── lambda/                  (Express API server)
│   │   ├── index.js             (main server)
│   │   └── routes/              (API endpoints)
│   └── frontend/                (React app)
│       └── src/
│
├── lambda/                       (AWS Lambda)
│   └── algo_orchestrator/       (algo execution)
│
├── .github/workflows/            (GitHub Actions)
│   ├── deploy-algo-orchestrator.yml
│   ├── deploy-app-stocks.yml
│   ├── deploy-infrastructure.yml
│   ├── deploy-core.yml
│   ├── deploy-webapp.yml
│   └── ...
│
├── load*.py                      (39 data loaders)
├── algo_*.py                     (algo components)
└── requirements.txt              (Python dependencies)
```

---

## Notes

- All documentation files are in the repo root
- Each file is self-contained (can be read independently)
- Cross-references point to other files (see "See Also" sections)
- Keep documentation separate from CLAUDE.md to avoid cluttering the IDE experience
- Update this index when adding new documentation
