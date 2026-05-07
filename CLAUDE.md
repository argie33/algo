# Stock Analytics Platform — Deployment & Operations Guide

## Quick Start (Terraform)

### Prerequisites
1. Install Terraform (v1.5.0+):
   ```bash
   terraform -version
   ```

2. GitHub OIDC configured (one-time):
   ```bash
   aws cloudformation deploy \
     --template-file terraform/bootstrap/oidc.yml \
     --stack-name stocks-oidc \
     --region us-east-1 \
     --no-fail-on-empty-changeset \
     --capabilities CAPABILITY_NAMED_IAM
   ```

3. Terraform state backend (one-time):
   ```bash
   # Create S3 state bucket and DynamoDB lock table
   aws s3 mb s3://stocks-terraform-state --region us-east-1
   aws dynamodb create-table \
     --table-name stocks-terraform-locks \
     --attribute-definitions AttributeName=LockID,AttributeType=S \
     --key-schema AttributeName=LockID,KeyType=HASH \
     --billing-mode PAY_PER_REQUEST \
     --region us-east-1
   ```

4. Ensure you're on the `main` branch:
   ```bash
   git checkout main
   git pull origin main
   ```

### Deploy Infrastructure with Terraform

#### Option 1: Automatic via GitHub Actions (Recommended)
```bash
# Plan changes (creates PR comment with diff)
gh pr create -t "Deploy infrastructure" -b "Automatic deployment"

# Apply changes when PR merges
git push origin main
```

#### Option 2: Manual Terraform Commands
```bash
cd terraform

# Initialize Terraform
terraform init

# Plan changes
terraform plan -out=tfplan

# Review plan output

# Apply changes
terraform apply tfplan

# View outputs
terraform output
```

**Deployment time:** ~15-20 minutes total (Terraform is faster than CloudFormation)

## Architecture Overview

### Terraform Module Structure
```
terraform/
├── main.tf                    # Root module orchestration
├── variables.tf               # Input variables (all services)
├── outputs.tf                 # Aggregated outputs
├── locals.tf                  # Common tags and naming
├── versions.tf                # Terraform & provider versions
├── backend.tf                 # S3 state backend
├── terraform.tfvars           # Variable values (dev environment)
└── modules/
    ├── iam/                   # IAM roles & policies (github-actions, bastion, ecs, lambda, eventbridge)
    ├── vpc/                   # VPC, subnets, security groups, 7 VPC endpoints
    ├── storage/               # S3 buckets (code, templates, lambda, data, logs, frontend)
    ├── database/              # RDS PostgreSQL, Secrets Manager, CloudWatch alarms
    ├── compute/               # ECS cluster, ECR, Bastion, auto-shutdown Lambda
    ├── loaders/               # ECS task definitions (18 loaders), EventBridge scheduled rules
    └── services/              # REST API Lambda, API Gateway, CloudFront, Cognito, Algo Lambda, SNS, EventBridge Scheduler
```

### Terraform Module Dependencies
```
iam (no dependencies)
    ↓
vpc (uses IAM roles)
    ↓
storage (no dependencies)
    ↓
database (uses VPC, IAM roles, storage)
    ├─→ compute (uses VPC, IAM roles)
    │   └─→ loaders (uses compute, database, storage)
    │
    └─→ services (uses VPC, database, storage)
```

### CloudFormation Stacks (Legacy)
| Stack | Template | Purpose |
|-------|----------|---------|
| `stocks-core` | `template-core.yml` | Foundation networking, ECR, S3 |
| `stocks-data` | `template-data-infrastructure.yml` | Database, ECS cluster, secrets |
| `stocks-loaders` | `template-loader-tasks.yml` | Data ingestion pipelines |
| `stocks-webapp-dev` | `template-webapp.yml` | REST API, frontend CDN, auth |
| `stocks-algo-dev` | `template-algo.yml` | Trading algorithm orchestrator |

**Note:** CloudFormation templates are superseded by Terraform. Use Terraform for new deployments.

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

### Terraform Plan/Apply Issues

#### State Lock Stuck
```bash
cd terraform
# Force unlock (use only if you're sure no other apply is running)
terraform force-unlock <lock-id>

# Check lock status in DynamoDB
aws dynamodb scan --table-name stocks-terraform-locks --region us-east-1
```

#### Module Not Found
```bash
# Re-initialize Terraform (pulls module sources)
cd terraform
terraform init -upgrade
```

#### Drift Detection
```bash
# Refresh state from AWS and show differences
cd terraform
terraform refresh
terraform plan

# If resources were changed outside Terraform:
terraform import <resource_type.name> <resource_id>
```

#### State Corruption
```bash
# View current state
terraform state list
terraform state show <resource>

# Restore from backup
aws s3 cp s3://stocks-terraform-state/backups/terraform.tfstate.TIMESTAMP.backup \
  s3://stocks-terraform-state/dev/terraform.tfstate --region us-east-1

# Re-apply
terraform apply
```

### Deployment Fails with Terraform Error
1. Check the workflow logs: https://github.com/argie33/algo/actions
2. Look for the validation error or apply error message
3. Common issues:
   - **OIDC role not found:** Run bootstrap OIDC stack first (see Quick Start Prerequisites)
   - **State backend not accessible:** Verify S3 and DynamoDB exist
   - **Variable validation failed:** Check `terraform.tfvars` values match constraints in `variables.tf`

### RDS Connection Issues
1. Verify RDS is in private subnets:
   ```bash
   aws ec2 describe-subnets --region us-east-1 --query 'Subnets[?Tags[?Key==`Name`]].{Name:Tags[?Key==`Name`]|[0].Value,CIDR:CidrBlock}'
   ```
2. Check security group allows port 5432:
   ```bash
   aws ec2 describe-security-groups --region us-east-1 | grep -A5 "rds"
   ```
3. Test from Bastion via Session Manager:
   ```bash
   aws ssm start-session --target i-xxxxx --region us-east-1
   psql -h $(terraform output -raw rds_address) -U stocks -d stocks
   ```

### Lambda Functions Not Triggering
1. Check EventBridge Scheduler rules:
   ```bash
   aws scheduler list-schedules --group-name default --region us-east-1
   ```
2. Verify Lambda execution role permissions:
   ```bash
   aws iam get-role-policy --role-name stocks-algo-dev-role --policy-name stocks-algo-dev-sns
   ```
3. Check CloudWatch logs:
   ```bash
   aws logs tail /aws/lambda/stocks-algo-dev --follow --region us-east-1
   ```

## Development Workflow

### Making Changes to Terraform Code

#### Local Testing
```bash
cd terraform

# Validate syntax
terraform fmt -recursive       # Format code
terraform validate            # Validate HCL

# Plan changes (no AWS access needed with -backend=false)
terraform init -backend=false
terraform plan

# Apply with AWS access
terraform init                # Initialize with S3 backend
terraform plan -out=tfplan
terraform apply tfplan        # Auto-approve for testing
```

#### Creating a Pull Request
```bash
git checkout -b feature/add-new-resource
# Edit terraform files...
git add terraform/
git commit -m "Add: new ECS task definition for data loader"
git push origin feature/add-new-resource

# Create PR (triggers terraform-validate and terraform-plan workflows)
gh pr create --title "Add new data loader task" \
  --body "Adds ECS task definition for market indices loader"
```

#### Merging and Deploying
```bash
# Review the terraform-plan output posted to the PR
# Click "Merge and deploy" (or use CLI)
gh pr merge <number> --merge

# GitHub Actions will auto-run terraform-apply on main branch push
```

### Making Changes to Terraform Workflows
Modify `.github/workflows/terraform-*.yml` files, then:
1. Commit: `git add .github/workflows/terraform-*.yml && git commit -m "Update workflow"`
2. Push: `git push origin main`
3. Workflow changes take effect on next push

### Adding New Resources to Terraform

#### Adding to Existing Module
1. Edit the module's `main.tf` file
2. Add resource block following naming convention: `${var.project_name}-${var.environment}-${resource_type}`
3. Add outputs to module's `outputs.tf`
4. Add any new variables to module's `variables.tf`

Example: Adding an SNS topic to the services module:
```hcl
# terraform/modules/services/main.tf
resource "aws_sns_topic" "notifications" {
  name = "${var.project_name}-notifications-${var.environment}"
  tags = merge(var.common_tags, {
    Name = "${var.project_name}-notifications"
  })
}

# terraform/modules/services/outputs.tf
output "notifications_topic_arn" {
  value = aws_sns_topic.notifications.arn
}

# terraform/modules/services/variables.tf
# (add any input variables needed)
```

5. Export from root module's `outputs.tf` if needed by other components
6. Commit and push to trigger workflow

#### Creating a New Module
1. Create directory: `terraform/modules/new-service/`
2. Add files:
   ```bash
   mkdir -p terraform/modules/new-service
   touch terraform/modules/new-service/{main,variables,outputs}.tf
   ```
3. Reference in root `main.tf`:
   ```hcl
   module "new_service" {
     source = "./modules/new-service"
     
     # Pass required variables
     project_name = var.project_name
     environment = var.environment
     # ... other variables
   }
   ```
4. Add module outputs to root `outputs.tf`

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

## Available Tools & Access

### What Tools Are Available

This project has access to multiple CLI tools for deployment, cleanup, and operations:

| Tool | Location | Purpose | How to Access |
|------|----------|---------|---------------|
| **AWS CLI** | Local system + GitHub Actions | AWS resource management, queries | Installed locally (see "Finding AWS CLI" below) |
| **GitHub CLI (gh)** | Local system + GitHub Actions | GitHub repository operations, workflow control | `gh` command (part of GitHub setup) |
| **Git** | Local system + GitHub Actions | Version control | `git` command |
| **Bash/PowerShell** | Local system (Bash via WSL) + GitHub Actions | Script execution, automation | `bash` in Linux environments; `PowerShell` on Windows |
| **Docker** | Local system (via Docker Desktop) | Container building and testing | `docker` command (for local dev) |

### Finding AWS CLI Locally

AWS CLI may not be in the standard `PATH`. If `which aws` returns nothing, search thoroughly:

```bash
# Search in common locations (not just /usr/bin)
find ~ -name "aws" -o -name "aws.exe" 2>/dev/null | head -20

# Check Python installations (AWS CLI often installed via pip)
find ~/AppData/Local/Programs/Python -name "aws*" 2>/dev/null

# Check Windows Program Files
ls -la "/c/Program Files/Amazon/AWSCLI/bin/" 2>/dev/null

# Check environment PATH more thoroughly
echo $PATH | tr ':' '\n'

# Try different shells
which aws
bash -c "which aws"
pwsh -c "where.exe aws"
```

Once found, test it works:
```bash
aws --version
aws sts get-caller-identity --region us-east-1
```

### Credentials & Authentication

**GitHub Secrets (for workflows):**
- `AWS_ACCESS_KEY_ID` — Set via GitHub repository settings
- `AWS_SECRET_ACCESS_KEY` — Set via GitHub repository settings
- `AWS_ACCOUNT_ID` — Set via GitHub repository settings

These are automatically available in all GitHub Actions workflows via `${{ secrets.SECRET_NAME }}`.

**Local AWS CLI (for manual commands):**
Export credentials before running commands:
```bash
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="us-east-1"

# Then run AWS CLI commands normally
aws ec2 describe-vpcs --region us-east-1
aws cloudformation list-stacks --region us-east-1
```

**In workflows:**
GitHub Actions automatically configures credentials when using `configure-aws-credentials` action:
```yaml
- uses: aws-actions/configure-aws-credentials@v4
  with:
    aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
    aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
    aws-region: us-east-1
```

### AWS CLI Syntax Patterns & Common Mistakes

**Filtering Syntax — The Most Common Error:**

WRONG (multiple filters with --filters):
```bash
# ❌ ERROR: This will fail with "Unknown options: --filters"
aws ec2 describe-nat-gateways --filters Name=vpc-id,Values=$VPC_ID Name=state,Values=available
```

CORRECT (use --filter once per filter, OR chain filters with Name= pairs):
```bash
# ✅ CORRECT — using single --filter with multiple Name= pairs
aws ec2 describe-nat-gateways --region $REGION --filter "Name=vpc-id,Values=$VPC_ID" "Name=state,Values=available,pending"

# ✅ ALSO CORRECT — multiple --filter flags
aws ec2 describe-nat-gateways --region $REGION --filter "Name=vpc-id,Values=$VPC_ID" --filter "Name=state,Values=available,pending"

# ✅ ALSO CORRECT — in subshell for simpler syntax
VPC_ID="vpc-12345"
aws ec2 describe-nat-gateways \
  --region us-east-1 \
  --filter "Name=vpc-id,Values=$VPC_ID" \
  --filter "Name=state,Values=available,pending" \
  --query 'NatGateways[*].NatGatewayId' \
  --output text
```

**JMESPath Queries (the --query parameter):**

Common patterns:
```bash
# Get all VPC IDs
aws ec2 describe-vpcs --query 'Vpcs[*].VpcId' --output text

# Get specific attributes
aws ec2 describe-instances --query 'Reservations[*].Instances[*].[InstanceId,State.Name]' --output table

# Conditional selection
aws rds describe-db-instances --query 'DBInstances[?Engine==`postgres`].DBInstanceIdentifier' --output text

# Get length (count)
aws ec2 describe-vpcs --filters Name=isDefault,Values=false --query 'length(Vpcs)' --output text
```

**Error Handling in Bash Scripts:**

Always suppress errors and check status:
```bash
# ❌ WRONG — script stops on error, masks real issues
set -e
aws ec2 delete-nat-gateway --nat-gateway-id $NGW

# ✅ CORRECT — continue on error, check status
aws ec2 delete-nat-gateway --nat-gateway-id $NGW 2>/dev/null || true

# ✅ ALSO CORRECT — capture error and handle
if ! output=$(aws ec2 delete-vpc --vpc-id $VPC_ID 2>&1); then
  echo "ERROR: $output"
  exit 1
fi
```

### AWS CLI Commands Used in This Project

**VPC Management:**
```bash
# List all VPCs
aws ec2 describe-vpcs --region $REGION --query 'Vpcs[*].VpcId' --output text

# Delete a VPC
aws ec2 delete-vpc --vpc-id $VPC_ID --region $REGION

# Count VPCs
aws ec2 describe-vpcs --region $REGION --filters "Name=isDefault,Values=false" --query 'length(Vpcs)' --output text
```

**EC2 Instances:**
```bash
# List instances in a VPC
aws ec2 describe-instances --region $REGION --filters "Name=vpc-id,Values=$VPC_ID" --output json

# Terminate instance
aws ec2 terminate-instances --instance-ids $INST_ID --region $REGION
```

**RDS Databases:**
```bash
# List databases
aws rds describe-db-instances --region $REGION --query 'DBInstances[*].DBInstanceIdentifier' --output text

# Delete database (skip final snapshot)
aws rds delete-db-instance --db-instance-identifier $DB_ID --skip-final-snapshot --region $REGION
```

**ECS Clusters & Tasks:**
```bash
# List clusters
aws ecs list-clusters --region $REGION --query 'clusterArns' --output text

# List services in cluster
aws ecs list-services --cluster $CLUSTER_ARN --region $REGION --query 'serviceArns' --output text

# Delete service
aws ecs delete-service --cluster $CLUSTER_ARN --service $SERVICE_ARN --force --region $REGION
```

**Security Groups:**
```bash
# Describe security group with rules
aws ec2 describe-security-groups --group-ids $SG_ID --region $REGION --output json

# Revoke all ingress rules (use output from describe command)
aws ec2 revoke-security-group-ingress --group-id $SG_ID --region $REGION --cli-input-json "{\"IpPermissions\":$RULES}"

# Delete security group
aws ec2 delete-security-group --group-id $SG_ID --region $REGION
```

**CloudFormation:**
```bash
# Describe stack
aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION --query 'Stacks[0].StackStatus' --output text

# List stacks
aws cloudformation list-stacks --region $REGION --query 'StackSummaries[?StackStatus!=`DELETE_COMPLETE`].StackName' --output text

# Get stack outputs/exports
aws cloudformation describe-stacks --stack-name $STACK_NAME --query 'Stacks[0].Outputs[?OutputKey==`ExportName`].OutputValue' --output text
```

**Secrets Manager:**
```bash
# Get secret value
aws secretsmanager get-secret-value --secret-id $SECRET_ID --region $REGION --query 'SecretString' --output text

# Parse JSON secret
aws secretsmanager get-secret-value --secret-id $SECRET_ID --region $REGION --query 'SecretString' --output text | jq '.username'
```

**EventBridge:**
```bash
# List rules
aws events list-rules --name-prefix stocks --region $REGION --query 'Rules[*].[Name,State]' --output table

# List targets for rule
aws events list-targets-by-rule --rule $RULE_NAME --region $REGION --query 'Targets[*].[Id,Arn]' --output table

# List EventBridge Scheduler schedules
aws scheduler list-schedules --region $REGION --query 'Schedules[*].[Name,State]' --output table
```

**Terraform State Management:**
```bash
# List all resources in state
terraform state list

# Show specific resource details
terraform state show aws_rds_instance.main

# Import AWS resource into Terraform state
terraform import aws_rds_instance.main stocks-postgres

# Remove resource from state (doesn't delete AWS resource)
terraform state rm aws_rds_instance.main

# Validate state consistency
terraform refresh

# Show state outputs
terraform output
terraform output api_url
```

**Terraform Debugging:**
```bash
# Enable detailed logging
export TF_LOG=DEBUG
terraform plan  # Produces verbose output

# Log to file
export TF_LOG_PATH=/tmp/terraform.log
terraform plan

# Show resource attributes in state
terraform console  # Interactive REPL
# Inside console: aws_rds_instance.main.endpoint
```

---

**Last Updated:** 2026-05-07
**Maintainer:** Claude Code
**Status:** Terraform Migration Complete - Infrastructure as Code v2
