# Deployment Guide

The system uses **GitHub Actions + Terraform IaC** for fully automated AWS deployments. No manual AWS console work needed.

## How It Works

**Push to `main` → GitHub Actions auto-deploys everything via Terraform**

Watch deployment progress at: https://github.com/argie33/algo/actions

## What Gets Deployed

1. **Lambda Functions** - Data loaders, orchestrator
2. **RDS PostgreSQL** - Database with schemas
3. **ECS Tasks** - Container-based loaders (optional)
4. **API Gateway** - REST endpoints
5. **Secrets Manager** - Credential storage
6. **CloudWatch** - Logs and monitoring

## Workflow

### Local Development

1. Make changes locally
2. Run `python3 run-all-loaders.py` to test
3. Run orchestrator dry-run to verify: `python3 algo/algo_orchestrator.py --mode paper --dry-run`
4. Commit and push to main

### Automatic Deployment

GitHub Actions workflow `deploy-all-infrastructure.yml` triggers:

1. **Validate** - Terraform plan
2. **Build** - Package Lambda functions
3. **Deploy** - Apply Terraform
4. **Test** - Run smoke tests
5. **Report** - Post results to PR/commit

## Configuration

Deployment variables set in GitHub Secrets:

```
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=123456789
POSTGRES_PASSWORD=...
ALPACA_API_KEY=...
ALPACA_API_SECRET=...
```

See GitHub Actions secrets settings to configure.

## Infrastructure Code

All infrastructure defined in `/terraform`:

```
terraform/
├── main.tf           # RDS, Secrets Manager, VPC
├── lambda.tf        # Lambda functions
├── api_gateway.tf   # REST endpoints
├── ecs.tf           # Container tasks
└── variables.tf     # Configuration
```

To modify infrastructure:
1. Edit `.tf` files
2. Push to main
3. GitHub Actions applies changes automatically

## Rollback

If deployment fails or causes issues:

1. GitHub Actions will stop and report error
2. Fix the issue locally
3. Commit and push again
4. New deployment runs

For emergency rollback to previous version:
```bash
git revert <commit-hash>
git push origin main
```

See `troubleshooting-guide.md` for common issues.
