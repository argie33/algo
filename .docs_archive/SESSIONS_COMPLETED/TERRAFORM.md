# Stock Analytics Platform - Terraform Infrastructure

This project uses **Terraform** for Infrastructure as Code (IaC) with AWS, designed for **multi-cloud portability** (future Azure/GCP support).

## Why Terraform over CloudFormation?

✅ **Multi-cloud ready** - AWS/Azure/GCP providers
✅ **Better modularity** - clear module boundaries
✅ **Cleaner syntax** - HCL vs YAML
✅ **State management** - explicit control
✅ **Easier testing** - Terraform test framework
✅ **No CloudFormation quirks** - ResourceExistenceCheck, validation hooks, etc.

## Architecture Overview

```
terraform/
├── main.tf               # Orchestrates all modules
├── variables.tf          # Global variables
├── outputs.tf            # Exported values
├── locals.tf             # Local values, common tags
├── versions.tf           # Terraform version and provider config
├── terraform.tfvars      # Configuration (DO NOT commit sensitive values)
├── terraform.tfvars.example  # Template
└── modules/
    ├── bootstrap/        # OIDC provider for GitHub Actions
    ├── core/             # VPC, networking, ECR, S3
    ├── data_infrastructure/  # RDS, ECS cluster, Secrets
    ├── loaders/          # ECS task definitions, EventBridge
    ├── webapp/           # Lambda API, CloudFront, Cognito
    └── algo/             # Algorithm orchestrator Lambda
```

## Stack Dependency Chain

```
bootstrap (OIDC)
    ↓
core (VPC, ECR, S3)
    ↓
data_infrastructure (RDS, ECS cluster)
    ├─→ loaders (ECS tasks)
    ├─→ webapp (Lambda, CloudFront, Cognito)
    └─→ algo (Lambda scheduler)
```

**Deploy order** (Terraform handles dependencies automatically):
1. `terraform apply -target=module.bootstrap`
2. `terraform apply -target=module.core`
3. `terraform apply -target=module.data_infrastructure`
4. `terraform apply` (remaining modules in parallel)

## Quick Start

### 1. Prerequisites

```bash
# Install Terraform (v1.5+)
terraform --version

# Install AWS CLI
aws --version

# Verify AWS credentials
aws sts get-caller-identity
```

### 2. Create Configuration

```bash
cd terraform

# Copy example to actual config
cp terraform.tfvars.example terraform.tfvars

# Edit with your values
editor terraform.tfvars
```

**Required values in `terraform.tfvars`:**
```hcl
aws_account_id    = "123456789012"
db_password        = "SECURE_PASSWORD_HERE"
notification_email = "your-email@example.com"
```

### 3. Initialize Terraform

```bash
terraform init
```

This:
- Downloads AWS provider
- Creates `.terraform/` directory
- Initializes local state (use remote state for team projects)

### 4. Plan Deployment

```bash
# See what will be created/modified
terraform plan -out=tfplan

# Save plan to file for review
```

### 5. Deploy Infrastructure

```bash
# Apply the plan
terraform apply tfplan

# OR: Direct apply (skips plan step)
terraform apply
```

**First deployment takes ~15-20 minutes** (RDS creation is slow)

### 6. Verify Outputs

```bash
# Display stack outputs
terraform output

# Get specific values
terraform output vpc_id
terraform output ecr_repository_uri
```

## Configuration Options

### Enable/Disable Stacks

```hcl
# terraform.tfvars
deploy_bootstrap             = true  # Set to false if already deployed
deploy_core                  = true
deploy_data_infrastructure   = true
deploy_loaders               = true
deploy_webapp                = true
deploy_algo                  = true
```

### Database Configuration

```hcl
db_instance_class    = "db.t3.micro"      # t3.nano for cheaper
db_allocated_storage = 100                 # GB
db_name              = "stocks"
db_user              = "stocks"
db_password          = "CHANGE_ME"
```

### Network Configuration

```hcl
vpc_cidr             = "10.0.0.0/16"
public_subnet_cidrs  = ["10.0.1.0/24", "10.0.2.0/24"]
private_subnet_cidrs = ["10.0.10.0/24", "10.0.11.0/24"]
```

### ECS Cluster

```hcl
ecs_instance_type = "t3.small"
ecs_min_capacity  = 1
ecs_max_capacity  = 3
```

## Deployment Workflows

### GitHub Actions Integration

Once bootstrap is deployed, GitHub Actions can use Terraform:

```yaml
# .github/workflows/deploy-terraform.yml
jobs:
  terraform:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: actions/checkout@v4
      
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1
      
      - name: Terraform Init
        run: cd terraform && terraform init
      
      - name: Terraform Plan
        run: cd terraform && terraform plan -out=tfplan
      
      - name: Terraform Apply
        run: cd terraform && terraform apply tfplan
```

### Manual Deployment

Deploy from local machine:

```bash
cd terraform
terraform apply
```

### Destroy Infrastructure

```bash
# WARNING: This deletes all resources
terraform destroy

# Destroy specific stack
terraform destroy -target=module.loaders
```

## State Management

### Local State (default)

State stored in `terraform.tfstate` (local machine).

**Use for:** Development only

**Security issue:** State file contains sensitive data (passwords, secrets)

### Remote State (recommended for production)

Store state in S3 + DynamoDB lock:

```hcl
# terraform/backend.tf
terraform {
  backend "s3" {
    bucket         = "terraform-state-123456789012"
    key            = "infrastructure/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-state-lock"
  }
}
```

**Setup:**
```bash
# Create S3 bucket and DynamoDB table for state
aws s3 mb s3://terraform-state-123456789012
aws dynamodb create-table \
  --table-name terraform-state-lock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
```

Then: `terraform init` (migrate from local to remote)

## Troubleshooting

### Common Issues

**"No valid credential sources found"**
```bash
export AWS_PROFILE=myprofile
# OR
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
```

**"Resource already exists"**
```bash
# Import existing resource into state
terraform import aws_vpc.main vpc-12345678
```

**"Timeout waiting for RDS"**
- RDS creation takes 5-10 minutes
- Check AWS Console for creation progress
- Safe to re-run `terraform apply`

**"State lock timeout"**
```bash
# Force unlock (use with caution)
terraform force-unlock <LOCK_ID>
```

## Best Practices

### 1. Code Organization

```bash
# One workspace per environment
terraform workspace new staging
terraform workspace select staging
terraform apply

terraform workspace select default  # Back to dev
```

### 2. Variable Management

```bash
# Keep secrets in CI/CD or .env
export TF_VAR_db_password="secret"
terraform apply

# Use terraform.tfvars for non-sensitive values only
```

### 3. Review Before Apply

```bash
# Always review plan before applying
terraform plan -out=tfplan
# Review tfplan content
terraform apply tfplan
```

### 4. Tag All Resources

```hcl
# Automatically applied to all resources
common_tags = {
  Project     = "stocks"
  Environment = "dev"
  ManagedBy   = "terraform"
  CostCenter  = "engineering"
}
```

### 5. Modular Design

Each module is:
- **Self-contained** - minimal external dependencies
- **Reusable** - can deploy multiple copies
- **Testable** - can test in isolation
- **Documented** - clear inputs/outputs

## Maintenance

### Update Provider Version

```bash
# Check for updates
terraform version
terraform init -upgrade

# Update aws provider
terraform init -upgrade -lock=false
```

### Refresh State

```bash
# Sync state with actual AWS resources
terraform refresh

# Before: terraform plan will show inconsistencies
# After: terraform plan shows accurate state
```

### List Resources

```bash
# Show all resources in state
terraform state list

# Show specific resource details
terraform state show module.core.aws_vpc.main

# Backup state
cp terraform.tfstate terraform.tfstate.backup
```

## Disaster Recovery

### Restore from Backup

```bash
# If state is corrupted
cp terraform.tfstate.backup terraform.tfstate
terraform refresh
```

### Re-import Resources

If state is lost, re-import existing AWS resources:

```bash
# Get VPC ID from AWS
aws ec2 describe-vpcs

# Import into Terraform
terraform import aws_vpc.main vpc-12345678
terraform import aws_subnet.public[0] subnet-12345678
# ... repeat for each resource
```

## Advanced Topics

### Custom Modules

Create new module `terraform/modules/custom/`:

```hcl
# modules/custom/main.tf
resource "aws_s3_bucket" "custom" {
  bucket = var.bucket_name
}

# modules/custom/variables.tf
variable "bucket_name" { type = string }

# modules/custom/outputs.tf
output "bucket_id" { value = aws_s3_bucket.custom.id }
```

Use in root:

```hcl
# main.tf
module "custom" {
  source = "./modules/custom"
  bucket_name = "my-custom-bucket"
}
```

### Testing Terraform

```bash
# Validate syntax
terraform validate

# Format code
terraform fmt -recursive

# Static analysis
tflint

# Unit tests (using test framework)
terraform test
```

## Multi-Cloud (Future)

Current AWS-only. To add Azure/GCP:

```bash
# Add Azure provider
terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

# Create modules/core_azure/
# Use variable to select: var.cloud_provider
```

## Support

- **Terraform Registry:** https://registry.terraform.io/
- **AWS Provider Docs:** https://registry.terraform.io/providers/hashicorp/aws/latest/docs
- **Terraform Forums:** https://discuss.hashicorp.com/c/terraform/27

---

**Last Updated:** 2026-05-06
**Status:** Ready for deployment
**Maintainer:** Claude Code
