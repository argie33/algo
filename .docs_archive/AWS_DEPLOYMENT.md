# AWS Deployment

## Architecture Overview

```
CloudFront (CDN)
    ↓
S3 (React frontend)
    ↓
API Gateway → Lambda (Express API)
    ↓
RDS PostgreSQL (database)
```

## Infrastructure Components

### 1. RDS Database

- **Engine:** PostgreSQL 14+
- **Instance:** db.t3.micro (development) or larger for production
- **Storage:** 20 GB (adjustable)
- **Backup:** 7-day retention
- **VPC:** Private subnet (no public access)

Deploy via: `deploy-infrastructure.yml`

### 2. Lambda API

- **Runtime:** Node.js 20+
- **Memory:** 512 MB (development), 1024 MB+ (production)
- **Timeout:** 30 seconds
- **Code:** `webapp/lambda/index.js`
- **Framework:** Express.js

Deploy via: `deploy-webapp.yml`

### 3. API Gateway

- **Type:** HTTP API (not REST API)
- **Routes:** All `/api/*` requests → Lambda
- **CORS:** Enabled for frontend
- **Authentication:** OAuth 2.0 (optional)

Deploy via: `deploy-tier1-optimizations.yml`

### 4. CloudFront + S3

- **S3 Bucket:** React build artifacts
- **CloudFront:** CDN + compression
- **Origin:** S3 bucket
- **Cache:** HTML (no cache), JS/CSS (1 year)

Deploy via: `deploy-webapp.yml`

### 5. Data Loaders (ECS)

- **Container:** Docker with Python loaders
- **Runtime:** Fargate (serverless)
- **Schedule:** EventBridge rules (hourly, daily, weekly, etc.)
- **Network:** VPC with RDS access

Deploy via: `deploy-app-stocks.yml`

### 6. Algo Orchestrator (Lambda)

- **Runtime:** Python 3.11
- **Memory:** 512 MB
- **Timeout:** 15 minutes
- **Schedule:** EventBridge (5:30pm ET daily)
- **Execution:** Pre-load patrol → load data → remediation → algo execution

Deploy via: `deploy-algo-orchestrator.yml`

---

## GitHub Actions Workflows

| Workflow | Purpose | Trigger |
|----------|---------|---------|
| `bootstrap-oidc.yml` | GitHub OIDC setup (one-time) | Manual |
| `deploy-core.yml` | Core AWS resources (S3, CloudWatch) | Manual |
| `deploy-infrastructure.yml` | RDS + networking | On template-app-stocks.yml change |
| `deploy-webapp.yml` | Lambda + frontend | On webapp/** change |
| `deploy-tier1-optimizations.yml` | VPC endpoints, HTTP API, SnapStart | Manual |
| `deploy-app-stocks.yml` | Data loaders (ECS) | On load*.py change |
| `deploy-algo-orchestrator.yml` | Algo Lambda + EventBridge | On algo_*.py change |

---

## Deployment Steps

### 1. Initial Setup

```bash
# Set up OIDC provider (one-time)
git push origin main
# GitHub Actions will trigger bootstrap-oidc.yml

# Wait for OIDC to be created, then deploy core resources
# Manually trigger: deploy-core.yml
```

### 2. Deploy Infrastructure

```bash
# Deploy RDS + base CloudFormation
git push origin main
# This triggers: deploy-infrastructure.yml
```

### 3. Deploy Webapp

```bash
# Deploy Lambda API + frontend
git push origin main
# This triggers: deploy-webapp.yml
```

### 4. Deploy Optimizations (optional)

```bash
# Deploy tier 1 optimizations (VPC endpoints, HTTP API, SnapStart)
# In GitHub Actions UI: manually trigger deploy-tier1-optimizations.yml
```

### 5. Deploy Loaders

```bash
# Push a loader change
git push origin main
# This triggers: deploy-app-stocks.yml
```

### 6. Deploy Algo

```bash
# Push an algo_*.py change
git push origin main
# This triggers: deploy-algo-orchestrator.yml
```

---

## Environment Variables

### Lambda (API)

```bash
DB_HOST=your-rds-endpoint.rds.amazonaws.com
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=*** (from AWS Secrets Manager)
DB_NAME=stocks
JWT_SECRET=*** (from AWS Secrets Manager)
```

### ECS (Loaders)

```bash
DB_HOST=your-rds-endpoint.rds.amazonaws.com
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=*** (from AWS Secrets Manager)
DB_NAME=stocks
FRED_API_KEY=*** (from GitHub Secrets)
ALPACA_API_KEY=*** (from AWS Secrets Manager)
ALPACA_API_SECRET=*** (from AWS Secrets Manager)
```

### Lambda (Algo)

```bash
DB_HOST=your-rds-endpoint.rds.amazonaws.com
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=*** (from AWS Secrets Manager)
DB_NAME=stocks
EXECUTION_MODE=paper (or live)
DRY_RUN_MODE=true (or false)
```

---

## Monitoring

### CloudWatch Logs

```bash
# API logs
aws logs tail /aws/lambda/api --follow

# Algo logs
aws logs tail /aws/lambda/algo-orchestrator --follow

# Loader logs
aws logs tail /ecs/loaders --follow
```

### CloudWatch Metrics

- Lambda invocations, duration, errors
- RDS CPU, connections, storage
- API Gateway requests, latency
- ECS task count, CPU, memory

### CloudWatch Alarms

- Lambda errors > 0 → SNS alert
- RDS CPU > 80% → SNS alert
- API latency > 1000ms → SNS alert

---

## Cost Optimization

### RDS
- Use db.t3.micro for development (eligible for free tier)
- Use Graviton (db.t4g) for production (15% cheaper)
- Enable multi-AZ only for production

### Lambda
- API: 512 MB is sufficient (price tier: first 1M free per month)
- Algo: 512 MB, runs once daily (~1 sec) = $0.50/month

### ECS
- Use Fargate Spot for non-critical loaders (70% cheaper)
- Reserved capacity for daily loaders

### S3
- Enable intelligent-tiering (automatic archival of old logs)
- CloudFront caches → reduced S3 requests

---

## Scaling

### Database
- Read replicas for read-heavy workloads
- Aurora for auto-scaling (if using Aurora)
- Connection pooling via RDS Proxy

### API
- Lambda: scales automatically (no configuration needed)
- Provisioned concurrency: if cold-start is an issue

### Loaders
- Parallel ECS tasks: run multiple loaders concurrently
- Fargate Spot: 70% cheaper for batch jobs

---

## Disaster Recovery

### Database
- Automated backups: 7-day retention
- Manual snapshots: create before major changes
- Restore: `aws rds restore-db-instance-from-db-snapshot`

### Code
- GitHub backup: automatic
- CloudFormation templates: stored in repo
- IaC: entire infrastructure is reproducible

---

## Security

- **VPC:** RDS in private subnet, no public access
- **Secrets Manager:** Database creds, API keys
- **IAM:** Least-privilege roles per service
- **HTTPS:** CloudFront enforces HTTPS
- **CORS:** Limited to frontend domain

---

## See Also

- `LOCAL_SETUP.md` — Local development
- `ALGO_DEPLOYMENT.md` — Algo orchestrator specifics
- `DATA_LOADING.md` — Data loader scheduling
- `TROUBLESHOOTING.md` — Common issues
