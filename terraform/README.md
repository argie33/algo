# Stocks Analytics Platform — Terraform Infrastructure

This is a production-grade, modular Terraform implementation of the Stocks Analytics Platform AWS infrastructure. All resources are defined as code with no manual AWS Console changes.

## Quick Start

### Prerequisites

1. **Terraform 1.5.0+**
   "terraform -version"

2. **AWS CLI v2** with credentials configured
   "aws sts get-caller-identity"

3. **GitHub OIDC Bootstrap** (one-time, required for GitHub Actions)

4. **State Backend** (one-time)

### Deployment

#### Option 1: Local Terraform Commands
- Run "terraform init" to initialize
- Run "terraform plan" to preview changes
- Run "terraform apply" to deploy

#### Option 2: GitHub Actions (Recommended)
- Create a PR with terraform changes
- Review the plan output in PR comments
- Merge PR to trigger terraform apply

## Directory Structure

- terraform/ - Root module
  - main.tf, variables.tf, outputs.tf, locals.tf, versions.tf, backend.tf, terraform.tfvars
  - modules/iam, vpc, storage, database, compute, loaders, services

## Key Features

- **Modular Design**: 7 independent modules for easy maintenance
- **State Backend**: S3 + DynamoDB for state management and locking
- **Security**: Least-privilege IAM roles, VPC endpoints, encrypted secrets
- **Cost Optimization**: VPC endpoints replace NAT Gateway, Spot pricing for ECS
- **Observability**: CloudWatch alarms, logs, and metrics
- **GitOps**: GitHub OIDC for secure deployment, no long-lived credentials

## Common Commands

- View state: 	erraform state list, 	erraform state show <resource>
- Plan changes: 	erraform plan, 	erraform plan -out=tfplan
- Apply changes: 	erraform apply, 	erraform apply tfplan
- Destroy: 	erraform destroy
- Export outputs: 	erraform output -json > outputs.json

## Modules

1. **iam** - IAM roles for GitHub Actions, Bastion, ECS, Lambda, EventBridge
2. **vpc** - VPC, subnets, security groups, 7 VPC endpoints
3. **storage** - S3 buckets with lifecycle policies
4. **database** - RDS PostgreSQL, Secrets Manager, CloudWatch alarms
5. **compute** - ECS cluster, ECR, Bastion host with auto-shutdown
6. **loaders** - 18 ECS task definitions, EventBridge scheduled rules
7. **services** - REST API Lambda, API Gateway, CloudFront, Cognito, Algo orchestrator

## Dependencies

iam → vpc → storage / database → compute → loaders
         ↓
       services

## Cost Estimate

Monthly: $65-90
- RDS: $20-30
- ECS: $10-15
- Lambda: $0-5
- S3: $1-5
- CloudWatch: $5
- Other: $20-40

## Best Practices

✅ Keep modules focused
✅ Use variables for everything
✅ Export outputs for cross-module communication
✅ Tag all resources
✅ Review plans before applying
✅ Use backend locks for concurrent safety

❌ Don't hardcode IDs or ARNs
❌ Don't use --target in production
❌ Don't force destroy without review
❌ Don't modify state directly
❌ Don't commit secrets to git

## Maintenance

**Weekly**: Review CloudWatch alarms, check storage usage
**Monthly**: Review costs, run terraform plan for drift detection
**Quarterly**: Audit IAM roles, test disaster recovery

---

**Last Updated**: 2026-05-07
**Status**: Production-Ready
**Modules**: 7
**Resources**: ~150 AWS resources defined as code
# Fixed bootstrap - retry
