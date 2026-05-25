# Pre-Deployment Checklist

**Purpose:** Validate infrastructure readiness before deploying code to AWS.

## Infrastructure Validation

- [ ] AWS account configured with correct region (`us-east-1`)
- [ ] IAM role exists: `algo-svc-github-actions-dev` with OIDC trust
- [ ] RDS instance `algo-db` running with correct security group rules
  - [ ] Inbound 5432 from Lambda security group
  - [ ] Backup retention >= 7 days
- [ ] VPC security groups allow Lambda ↔ RDS communication
- [ ] Secrets Manager secrets created:
  - [ ] `algo-dev-rds-password` (RDS password)
  - [ ] `algo/database` (prod RDS credentials)
  - [ ] `algo/alpaca` (Alpaca API keys)
  - [ ] `algo/fred` (FRED API key)
- [ ] ECS cluster `algo-cluster` active with Fargate capacity
- [ ] S3 bucket for Lambda code deployments exists
- [ ] CloudWatch log groups created:
  - [ ] `/aws/lambda/algo-algo-dev`
  - [ ] `/aws/lambda/algo-api-dev`
  - [ ] `/ecs/algo-cluster`

## Code Prerequisites

- [ ] All tests pass locally: `pytest tests/`
- [ ] No security issues: `bandit -r . --skip B101,B601`
- [ ] Linting passes: `ruff check .`
- [ ] No uncommitted changes except in work-in-progress branches
- [ ] Recent commits pushed to GitHub

## Database Prerequisites

- [ ] RDS database schema initialized via `terraform apply`
  - [ ] All tables in `terraform/modules/database/init.sql` exist
  - [ ] `data_patrol_log` and `data_loader_status` tables present
- [ ] At least one baseline data load (price_daily) to establish schema
- [ ] Database user `stocks` exists with correct password

## Terraform State

- [ ] Terraform state locked (check AWS DynamoDB `terraform-locks`)
- [ ] No pending `terraform plan` changes beyond what's being deployed
- [ ] `.tfvars` file configured for deployment environment

## GitHub Secrets

- [ ] `AWS_ACCOUNT_ID` set correctly
- [ ] `APCA_API_KEY_ID` populated (Alpaca live key)
- [ ] `APCA_API_SECRET_KEY` populated (Alpaca live secret)
- [ ] `ALPACA_API_KEY` populated (fallback key if different)
- [ ] `ALPACA_API_SECRET` populated (fallback secret)
- [ ] `FRED_API_KEY` populated (economic data)
- [ ] `RDS_PASSWORD` matches `algo-dev-rds-password` in Secrets Manager

## Pre-Deployment Smoke Test

- [ ] Manual test data load via AWS CLI: `aws lambda invoke --function-name algo-db-init-dev /tmp/test.json`
- [ ] Check CloudWatch logs for successful execution
- [ ] Verify RDS contains test data
- [ ] Query sample row: `SELECT COUNT(*) FROM stock_symbols;`

## Deployment Execution

1. Run: `git push main`
2. Monitor: GitHub Actions `deploy-code.yml` workflow
3. Verify: All steps complete with ✅
4. Check: CloudWatch logs for Lambda/ECS startup messages
5. Validate: API Gateway returns 200 on health check

## Post-Deployment Validation

- [ ] Orchestrator Lambda `algo-algo-dev` deployed successfully
- [ ] API Lambda `algo-api-dev` deployed and accessible
- [ ] ECS tasks defined for all 24 loaders
- [ ] EventBridge rules active for scheduler
- [ ] Step Functions state machine for pipeline visible in AWS Console

## Rollback Plan

If deployment fails:
1. Check CloudWatch logs for specific error
2. If infrastructure broken: `terraform destroy` and re-apply
3. If code broken: `git revert <commit>` and push
4. Monitor logs until recovery
