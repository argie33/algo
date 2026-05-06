# Stock Analytics Platform — Deployment & Operations Guide

## Quick Start

### Prerequisites
1. GitHub secrets configured in repository settings:
   - `AWS_ACCESS_KEY_ID` — AWS IAM access key (must have CloudFormation, EC2, RDS, Lambda, ECS, ECR permissions)
   - `AWS_SECRET_ACCESS_KEY` — AWS IAM secret key
   - `AWS_ACCOUNT_ID` — AWS account ID (12 digits)

2. Ensure you're on the `main` branch:
   ```bash
   git checkout main
   git pull origin main
   ```

### Deploy All Infrastructure
Trigger the master orchestrator workflow:
```bash
gh workflow run deploy-all-infrastructure.yml --repo argie33/algo
```

This deploys in dependency order:
1. Bootstrap OIDC Provider (optional, skip if already done)
2. Core Infrastructure (VPC, subnets, ECR, S3, Bastion)
3. Data Infrastructure (RDS, ECS cluster, Secrets Manager)
4. Webapp (Lambda API, CloudFront, Cognito)
5. Loaders (ECS tasks, EventBridge scheduled rules)
6. Algo Orchestrator (Lambda scheduler, EventBridge)

**Deployment time:** ~20-30 minutes total

### Manual Deployment (if needed)
Deploy individual stacks:
```bash
# 1. Core infrastructure (foundation for all others)
gh workflow run deploy-core.yml

# 2. Data infrastructure (RDS, ECS)
gh workflow run deploy-data-infrastructure.yml

# 3. Dependent stacks (can run in parallel)
gh workflow run deploy-loaders.yml &
gh workflow run deploy-webapp.yml &
gh workflow run deploy-algo.yml &
wait
```

## Architecture Overview

### Stack Dependency Chain
```
stocks-oidc (OIDC provider - one-time setup)
    ↓
stocks-core (VPC, subnets, ECR, S3, Bastion)
    ↓
stocks-data (RDS PostgreSQL, ECS cluster, Secrets Manager)
    ├─→ stocks-loaders (ECS task definitions, EventBridge rules)
    ├─→ stocks-webapp-dev (Lambda API, CloudFront, Cognito)
    └─→ stocks-algo-dev (Algorithm orchestrator Lambda, Scheduler)
```

### CloudFormation Stacks
| Stack | Template | Purpose | Exports |
|-------|----------|---------|---------|
| `stocks-core` | `template-core.yml` | Foundation networking, ECR, S3 | 9 VPC/network exports |
| `stocks-data` | `template-data-infrastructure.yml` | Database, ECS cluster, secrets | 8 database/cluster exports |
| `stocks-loaders` | `template-loader-tasks.yml` | Data ingestion pipelines | 1 state machine ARN |
| `stocks-webapp-dev` | `template-webapp.yml` | REST API, frontend CDN, auth | 3 endpoint exports |
| `stocks-algo-dev` | `template-algo.yml` | Trading algorithm orchestrator | 1 Lambda ARN |

## Security Architecture

### IAM & Access Control
- **GitHub Actions Role:** Limited to CloudFormation, S3, EC2, RDS, Lambda, ECS, ECR actions on `stocks-*` resources
- **Bastion Host:** Accessed via AWS Systems Manager Session Manager (IAM-based, logged in CloudTrail)
- **RDS Database:** In private subnets, restricted to ECS + Bastion security group access only
- **Secrets Manager:** Stores database credentials, API keys, runtime secrets

### Encryption
- **S3 Buckets:** AES256 server-side encryption at rest
- **RDS:** At-rest encryption via AWS managed keys
- **Secrets:** Encrypted in Secrets Manager

### Network Isolation
- **RDS:** Private subnets, no public IP
- **ECS Tasks:** Private subnets, communicate via security groups
- **NAT Gateway:** Not used (cost optimization) — outbound internet access via VPC endpoints
- **Bastion:** Public IP, but SSH disabled (use SSM Session Manager instead)

## Monitoring & Alarms

### CloudWatch Alarms (Auto-created in stocks-data stack)
- **RDS CPU:** Alert if > 80% average over 10 minutes
- **RDS Storage:** Alert if free space < 10GB
- **RDS Connections:** Alert if > 50 active connections

### Accessing Bastion
```bash
# List instances
aws ec2 describe-instances --query 'Reservations[*].Instances[*].[InstanceId,State.Name]' --region us-east-1

# Start a session
aws ssm start-session --target i-0123456789abcdef0 --region us-east-1

# Once in session, access RDS:
psql -h stocks-data-RDS-endpoint.region.rds.amazonaws.com -U stocks -d stocks
```

## Troubleshooting

### Deployment Fails with CloudFormation Error
1. Check the workflow logs: https://github.com/argie33/algo/actions
2. Look for the first error message in "Deploy" or "Diagnose" steps
3. Common issues:
   - **Secrets not set:** Verify `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_ACCOUNT_ID` in GitHub Secrets
   - **Insufficient permissions:** Ensure IAM user has CloudFormation, EC2, RDS, Lambda, ECS, ECR permissions
   - **Stack already exists in bad state:** The workflow auto-cleans up, but check AWS Console if stuck

### RDS Connection Issues
1. Verify RDS is in private subnets: `aws ec2 describe-subnets --region us-east-1`
2. Check security group allows port 5432: `aws ec2 describe-security-groups --region us-east-1`
3. Test from Bastion via Systems Manager Session Manager
4. Verify database credentials in Secrets Manager: `aws secretsmanager get-secret-value --secret-id stocks-db-secrets-*`

### Lambda Functions Not Triggering
1. Check EventBridge rules: `aws events list-rules --name-prefix stocks`
2. Verify Lambda execution role has required permissions
3. Check CloudWatch logs: `/aws/lambda/stocks-*`
4. Verify input/output bindings in EventBridge targets

## Development Workflow

### Making Changes to Templates
1. Edit template in local checkout
2. Validate syntax: `aws cloudformation validate-template --template-body file://template-NAME.yml`
3. Commit changes: `git add template-NAME.yml && git commit -m "Description"`
4. Push to main: `git push origin main`
5. Workflow auto-triggers on template changes

### Making Changes to Workflows
Modify `.github/workflows/deploy-*.yml` files, then:
1. Commit: `git add .github/workflows/ && git commit -m "Description"`
2. Push: `git push origin main`
3. Re-run workflow: `gh workflow run deploy-STACKNAME.yml`

### Adding New Resources
1. Add to appropriate template (core, data-infrastructure, etc.)
2. Follow naming convention: `stocks-{component}-{resource}`
3. Add standard tags:
   ```yaml
   Tags:
     - Key: Project
       Value: stocks-analytics
     - Key: ManagedBy
       Value: cloudformation
     - Key: Stack
       Value: !Ref AWS::StackName
   ```
4. Export important resource identifiers:
   ```yaml
   Outputs:
     ResourceName:
       Value: !Ref Resource
       Export:
         Name: StocksCore-ResourceName
   ```

## Cost Optimization

### Current Monthly Estimate: $65-90
- **VPC:** $0 (no NAT Gateway, using VPC endpoints)
- **RDS:** $20-30 (db.t3.micro, 61GB storage)
- **ECS:** $10-15 (t3 instances, spot pricing)
- **Lambda:** $0-5 (free tier + minimal execution time)
- **S3:** $1-5 (versioning enabled, lifecycle policies)
- **CloudFront:** $0.085/GB (free tier includes significant bandwidth)
- **Data Transfer:** $0-5 (mostly internal)

### Optimization Opportunities
- Consider db.t3.nano for even lower RDS costs
- Implement S3 Intelligent-Tiering on logs
- Review CloudFront caching policies
- Monitor Lambda duration and memory allocation

## Best Practices Summary

✅ **Security First**
- All IAM roles use least-privilege policies
- Databases in private subnets
- Encryption at rest on all storage
- No SSH access (use SSM Session Manager)

✅ **Infrastructure as Code**
- All resources in CloudFormation
- No manual AWS Console changes
- Version-controlled, auditable changes
- Automated rollback on failures

✅ **Reliability**
- Multi-AZ ready (can enable RDS Multi-AZ)
- CloudWatch monitoring and alarms
- Automatic rollback on deploy failures
- Health checks on load balancers

✅ **Cost Optimization**
- No unused services
- Spot pricing where possible
- Lifecycle policies on storage
- Reserved capacity planning

## Maintenance

### Weekly Tasks
- Review CloudWatch alarms for any breaches
- Check CloudFormation stack events for warnings
- Monitor RDS storage usage

### Monthly Tasks
- Review AWS Cost Explorer for unexpected charges
- Analyze CloudWatch logs for errors
- Update dependencies (container images, Lambda layers)

### Quarterly Tasks
- Review security group rules for over-permissive access
- Audit IAM role permissions
- Test disaster recovery (redeploy from scratch)
- Review and update cost optimization settings

---

**Last Updated:** 2026-05-06
**Maintainer:** Claude Code
**Status:** Production-Ready with Security Hardening
