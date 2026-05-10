# GitHub Actions Setup for Terraform Deployment

## Prerequisites Checklist

Before deploying via GitHub Actions, ensure the following are configured:

### 1. AWS Credentials & OIDC

- [ ] **AWS Account ID:** Set in GitHub Secrets as `AWS_ACCOUNT_ID`
  - Value: Your AWS account ID (12 digits)
  - Run: `aws sts get-caller-identity --query Account --output text`

- [ ] **OIDC Role Created:** `github-actions-role` must exist in AWS
  - Run bootstrap: `aws cloudformation deploy --template-file bootstrap/oidc.yml --stack-name stocks-oidc --region us-east-1 --capabilities CAPABILITY_NAMED_IAM`

- [ ] **Legacy AWS Credentials** (if not using OIDC):
  - `AWS_ACCESS_KEY_ID` - GitHub Secret
  - `AWS_SECRET_ACCESS_KEY` - GitHub Secret

### 2. GitHub Secrets Configuration

Set these secrets in your GitHub repository (Settings > Secrets and variables > Actions):

```
Secret Name                 Value                                    Source
-------------------        -----                                    ------
RDS_PASSWORD                [Strong password, 8+ chars]             Generate new
AWS_ACCOUNT_ID              [Your AWS Account ID]                   aws sts get-caller-identity
AWS_ACCESS_KEY_ID           [AWS Access Key]                        AWS IAM (if not using OIDC)
AWS_SECRET_ACCESS_KEY       [AWS Secret Key]                        AWS IAM (if not using OIDC)
SLACK_WEBHOOK               [Optional Slack webhook]                Slack workspace
```

### 3. Infrastructure Bootstrap

The following resources must exist or be auto-created:

- [ ] **S3 State Bucket:** `stocks-terraform-state`
  - Bootstrap script will create if missing
  
- [ ] **DynamoDB Lock Table:** `stocks-terraform-locks`
  - Bootstrap script will create if missing

- [ ] **GitHub OIDC Provider:** (if using OIDC trust)
  - Bootstrap script creates this automatically

### 4. Terraform State

Current configuration in `terraform/backend.tf`:
```hcl
backend "s3" {
  bucket         = "stocks-terraform-state"      # ✓ Correct
  key            = "dev/terraform.tfstate"       # ✓ Correct
  region         = "us-east-1"                   # ✓ Correct
  dynamodb_table = "stocks-terraform-locks"      # ✓ Correct
  encrypt        = true                          # ✓ Secure
}
```

## Deployment Variables (GitHub Actions will provide these)

The following variables are automatically set by GitHub Actions workflows:

```yaml
Environment Variables:
- AWS_REGION = "us-east-1"
- TF_VAR_github_repository = ${{ github.repository }}  # argeropolos/algo
- TF_VAR_github_ref_path = ${{ github.ref }}           # refs/heads/main
- TF_VAR_rds_password = ${{ secrets.RDS_PASSWORD }}    # OVERRIDES tfvars
```

### terraform.tfvars (Base Values)

```hcl
project_name           = "stocks"
environment            = "dev"
aws_region             = "us-east-1"
github_repository      = "argeropolos/algo"
github_ref_path        = "refs/heads/main"
notification_email     = "argeropolos@gmail.com"
```

The RDS password in tfvars will be **overridden** by `TF_VAR_rds_password` environment variable from GitHub secrets.

## Running the Deployment

### Via GitHub UI (Recommended)

1. Go to **Actions** tab
2. Select **Deploy All Infrastructure** workflow
3. Click **Run workflow**
4. Choose: Skip OIDC bootstrap? `false` (first time), `true` (subsequent runs)
5. Click **Run workflow**

### Via GitHub CLI

```bash
# First deployment (includes OIDC bootstrap)
gh workflow run deploy-all-infrastructure.yml --repo argeropolos/algo

# Subsequent deployments (skip bootstrap)
gh workflow run deploy-all-infrastructure.yml --repo argeropolos/algo \
  -f skip_bootstrap=true
```

## Workflow Execution Order

The `deploy-all-infrastructure.yml` orchestrates:

1. **Bootstrap OIDC Provider** (if skip_bootstrap != true)
   - Creates GitHub OIDC trust relationship
   - Enables keyless authentication

2. **Deploy Core Infrastructure** (VPC, ECR, S3, Bastion)
   - VPC with public/private subnets
   - Internet Gateway, NAT Gateway
   - ECR repository for Docker images
   - S3 buckets for code/data/frontend

3. **Deploy Data Infrastructure** (RDS, ECS, Secrets)
   - PostgreSQL RDS instance
   - ECS cluster for loaders
   - Secrets Manager for credentials

4. **Deploy Webapp** (Lambda API, Frontend, CloudFront)
   - API Lambda function
   - API Gateway HTTP API
   - CloudFront distribution
   - Frontend S3 hosting

5. **Deploy Loaders** (62 ECS data loaders)
   - ECS task definitions
   - EventBridge schedules
   - CloudWatch logs

6. **Deploy Algo** (Algo Orchestrator Lambda)
   - Algo Lambda function
   - EventBridge schedule (5:30pm ET)
   - CloudWatch monitoring

## Troubleshooting

### "Role not found" Error
- The OIDC role doesn't exist
- **Fix:** Disable skip_bootstrap or run bootstrap manually
- Run: `aws cloudformation deploy --template-file bootstrap/oidc.yml --stack-name stocks-oidc --region us-east-1 --capabilities CAPABILITY_NAMED_IAM`

### "State bucket does not exist"
- S3 state bucket not created
- **Fix:** Bootstrap script should auto-create, or run:
- `aws s3 mb s3://stocks-terraform-state --region us-east-1`

### "Missing AWS Credentials"
- GitHub secrets not configured
- **Fix:** Set AWS_ACCOUNT_ID, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY in GitHub Secrets

### "Invalid RDS Password"
- RDS_PASSWORD secret not set or invalid
- **Fix:** Set RDS_PASSWORD in GitHub Secrets (8+ characters, alphanumeric)

## Monitoring Deployment

1. **In GitHub Actions:**
   - Watch workflow run on Actions tab
   - Check for step-by-step progress

2. **In AWS Console:**
   - VPC > Check VPC, subnets created
   - RDS > Check PostgreSQL instance status
   - ECS > Check cluster and tasks
   - Lambda > Check API and Algo functions
   - CloudFront > Check distribution status

3. **In CloudWatch:**
   - Check `/aws/lambda/stocks-api-dev` logs
   - Check `/aws/lambda/stocks-algo-dev` logs
   - Verify ECS loaders are running

## Post-Deployment

After successful deployment:

- [ ] Verify database connectivity: `psql -h <RDS_ENDPOINT> -U stocks stocks`
- [ ] Test API endpoint: `curl https://<API_GATEWAY_URL>/`
- [ ] Check data loaders: CloudWatch Logs > `/ecs/loaders`
- [ ] Verify algo schedule: EventBridge > Rules > Look for `stocks-algo-*` rule

