# Deployment Instructions

## Step 1: Delete Old VPCs

Account has 5 VPCs (AWS limit). Delete them:

```bash
gh workflow run delete-vpcs.yml
```

Verify:
```bash
aws ec2 describe-vpcs --region us-east-1 --query 'length(Vpcs)' --output text
# Should show < 5
```

## Step 2: Deploy Infrastructure

```bash
gh workflow run deploy-terraform.yml
```

**What happens:**
1. Pre-flight checks (secrets, VPC count)
2. Create backend (S3 + DynamoDB) if needed
3. Initialize Terraform with remote state
4. Import pre-existing resources
5. Plan infrastructure changes
6. Apply changes

**Dependency chain:**
```
Bootstrap (OIDC)
    ↓
Core (VPC, networking, ECR, S3)
    ↓
Data Infrastructure (RDS, ECS)
    ↓
Loaders, Webapp, Algo (can run in parallel)
```

## That's it.

No complexity, no workarounds. Terraform manages everything from the S3 backend.
